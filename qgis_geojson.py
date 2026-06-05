"""
GeoJSON Data API
=================
把任意矢量文件转成 GeoJSON 供前端 WebGL 渲染器消费。

POST /data/upload     上传文件，返回 file_id + 属性字段列表
GET  /data/{file_id}  获取 GeoJSON（支持投影变换到 EPSG:4326）
GET  /data/{file_id}/info  获取图层元信息（范围、字段、要素数）
DELETE /data/{file_id}     删除缓存
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/data")

# Use system temp directory (works on Windows, macOS, Linux)
STORE_DIR = Path(tempfile.gettempdir()) / "qgis_geojson_store"
STORE_DIR.mkdir(exist_ok=True)

OGR2OGR  = shutil.which("ogr2ogr")  or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogr2ogr"
OGRINFO  = shutil.which("ogrinfo")  or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogrinfo"
ODA_CONVERTER = (
    shutil.which("ODAFileConverter")
    or "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"
)

# .dwg 需要先经 ODAFileConverter 转成 DXF，再走 ogr2ogr
VECTOR_EXTS = {
    ".dxf", ".dwg",
    ".shp", ".geojson", ".json",
    ".kml", ".kmz", ".gpkg",
    ".csv", ".gdb", ".sqlite",
}
# DXF/DWG 使用工程坐标系，不强制转 EPSG:4326，避免 ogr2ogr 报坐标系错误
CAD_EXTS = {".dxf", ".dwg"}
MAX_BYTES = 200 * 1024 * 1024


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise HTTPException(500, f"Command failed: {proc.stderr or proc.stdout}")
    return proc


def _dwg_to_dxf(dwg_path: Path, out_dir: Path) -> Path:
    """
    用 ODAFileConverter 把 DWG 转成 DXF。
    返回转出的 .dxf 文件路径。
    """
    if not ODA_CONVERTER or not Path(ODA_CONVERTER).exists():
        raise HTTPException(500, "ODAFileConverter 未安装，无法处理 .dwg 文件")
    # ODAFileConverter <inputDir> <outputDir> <outputType> <version> <recurse> <audit>
    dxf_dir = out_dir / "dxf_out"
    dxf_dir.mkdir(exist_ok=True)
    proc = subprocess.run(
        [ODA_CONVERTER, str(dwg_path.parent), str(dxf_dir),
         "ACAD2018", "DXF", "0", "1"],
        capture_output=True, text=True, timeout=120,
    )
    candidates = list(dxf_dir.glob("*.dxf"))
    if not candidates:
        raise HTTPException(500, f"DWG 转 DXF 失败: {proc.stderr or proc.stdout}")
    return candidates[0]


def _ogrinfo_meta(src: Path) -> dict:
    """
    当 ogr2ogr 转换后 GeoJSON 为空时（常见于工程坐标 DXF），
    改用 ogrinfo 直接读取 bbox、字段、要素数，保存到 meta。
    """
    try:
        proc = subprocess.run(
            [OGRINFO, "-al", "-so", str(src)],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout
        import re
        # Extent: (xmin, ymin) - (xmax, ymax)
        m = re.search(r"Extent:\s*\(([\d.eE+\-]+),\s*([\d.eE+\-]+)\)\s*-\s*\(([\d.eE+\-]+),\s*([\d.eE+\-]+)\)", out)
        bbox = [float(m.group(i)) for i in range(1, 5)] if m else [0, 0, 0, 0]
        # Feature Count
        fm = re.search(r"Feature Count:\s*(\d+)", out)
        count = int(fm.group(1)) if fm else 0
        # Fields
        fields = re.findall(r"^(\w+): \w+", out, re.MULTILINE)
        # Geometry type
        gm = re.search(r"Geometry:\s*(.+)", out)
        geom_types = [gm.group(1).strip()] if gm else []
        return {"bbox": bbox, "feature_count": count,
                "fields": fields, "geometry_types": geom_types}
    except Exception:
        return {"bbox": [0, 0, 0, 0], "feature_count": 0,
                "fields": [], "geometry_types": []}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    srs: str = Form("EPSG:4326", description="输出坐标系，前端 WebGL 一般用 EPSG:4326"),
):
    """
    上传任意矢量文件，服务端转为 GeoJSON 缓存。
    返回 file_id，后续用 GET /data/{file_id} 取数据。
    """
    suffix = Path(file.filename or "x").suffix.lower()
    if suffix not in VECTOR_EXTS:
        raise HTTPException(400, f"不支持 {suffix}，支持: {sorted(VECTOR_EXTS)}")

    file_id = uuid.uuid4().hex
    store = STORE_DIR / file_id
    store.mkdir()

    src = store / file.filename
    written = 0
    with open(src, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_BYTES:
                shutil.rmtree(store, ignore_errors=True)
                raise HTTPException(413, "File too large (>200MB)")
            out.write(chunk)

    # DWG → DXF（ODAFileConverter），再按 DXF 流程处理
    render_src = src
    if suffix == ".dwg":
        render_src = _dwg_to_dxf(src, store)

    # DXF/DWG 保留工程坐标，不强制重投影（避免坐标系未知导致 ogr2ogr 报错）
    is_cad = suffix in CAD_EXTS
    geojson_path = store / "data.geojson"
    ogr_cmd = [
        OGR2OGR, "-f", "GeoJSON",
        str(geojson_path), str(render_src),
        "-overwrite", "-skipfailures", "-dim", "XY",
    ]
    if not is_cad:
        ogr_cmd += ["-t_srs", srs]
    try:
        _run(ogr_cmd)
    except HTTPException:
        # ogr2ogr 失败时继续，后续用 ogrinfo 兜底
        pass

    # 读取 GeoJSON 元信息；若为空（DXF 工程坐标常见），改用 ogrinfo 兜底
    try:
        with open(geojson_path, encoding="utf-8") as f:
            gj = json.load(f)
        features = gj.get("features", [])
        if features:
            fields = list(features[0]["properties"].keys())
            count  = len(features)
            xs = [c[0] for feat in features for c in _extract_coords(feat["geometry"])]
            ys = [c[1] for feat in features for c in _extract_coords(feat["geometry"])]
            bbox       = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]
            geom_types = list({feat["geometry"]["type"] for feat in features if feat.get("geometry")})
        else:
            raise ValueError("empty geojson")
    except Exception:
        # GeoJSON 为空或解析失败 → ogrinfo 兜底（直接读原始文件）
        fb = _ogrinfo_meta(render_src)
        fields, count, bbox, geom_types = (
            fb["fields"], fb["feature_count"], fb["bbox"], fb["geometry_types"]
        )

    actual_srs = "native" if is_cad else srs
    meta = {
        "file_id":        file_id,
        "original_name":  file.filename,
        "srs":            actual_srs,
        "fields":         fields,
        "feature_count":  count,
        "bbox":           bbox,
        "geometry_types": geom_types,
        "size_bytes":     src.stat().st_size,
        "note":           "DXF/DWG 使用工程坐标，bbox 单位与文件坐标系一致" if is_cad else "",
    }
    with open(store / "meta.json", "w") as f:
        json.dump(meta, f)

    return meta


def _extract_coords(geom: dict) -> list[list[float]]:
    if geom is None:
        return []
    t = geom.get("type", "")
    c = geom.get("coordinates", [])
    if t == "Point":
        return [c] if c else []
    if t in ("LineString", "MultiPoint"):
        return c
    if t in ("Polygon", "MultiLineString"):
        return [pt for ring in c for pt in ring]
    if t == "MultiPolygon":
        return [pt for poly in c for ring in poly for pt in ring]
    return []


@router.get("/{file_id}")
def get_geojson(file_id: str):
    """返回 GeoJSON 数据，供前端 WebGL 渲染器加载。"""
    path = STORE_DIR / file_id / "data.geojson"
    if not path.exists():
        raise HTTPException(404, f"file_id {file_id!r} not found")
    return FileResponse(
        path=path,
        media_type="application/geo+json",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{file_id}/info")
def get_info(file_id: str):
    """返回图层元信息（不含几何数据）。"""
    meta_path = STORE_DIR / file_id / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, f"file_id {file_id!r} not found")
    with open(meta_path) as f:
        return json.load(f)


@router.delete("/{file_id}")
def delete_file(file_id: str):
    """删除缓存的 GeoJSON 文件。"""
    store = STORE_DIR / file_id
    if not store.exists():
        raise HTTPException(404, f"file_id {file_id!r} not found")
    shutil.rmtree(store)
    return {"status": "deleted", "file_id": file_id}


@router.get("/")
def list_files():
    """列出所有已缓存的文件。"""
    files = []
    for d in STORE_DIR.iterdir():
        meta_path = d / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                files.append(json.load(f))
    return {"files": files}
