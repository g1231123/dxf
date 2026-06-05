"""
QGIS Analysis & Processing Module
==================================
提供基于 PyQGIS/QGIS Processing 的空间分析、数据处理和格式转换能力。

挂载到 FastAPI server.py 的路由前缀：/analysis, /process

端点列表
--------
POST /analysis/buffer          缓冲区分析
POST /analysis/intersect       交集叠加
POST /analysis/union           并集叠加
POST /analysis/centroid        质心提取
POST /analysis/convex_hull     凸包
POST /analysis/clip            裁切
POST /process/reproject        投影变换
POST /process/convert          格式转换 (任意 → GeoJSON/GPKG/SHP/DXF)
POST /process/merge            多文件合并
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter()

WORK_DIR = Path(tempfile.gettempdir()) / "qgis_analysis_jobs"
WORK_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

OGR2OGR = shutil.which("ogr2ogr") or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogr2ogr"

# QGIS Processing algorithm runner path
QGIS_PYTHON = (
    "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/python"
)

# Supported input formats for upload
VECTOR_EXTS = {".dxf", ".shp", ".geojson", ".json", ".kml", ".kmz", ".gpkg", ".csv", ".gdb"}
OUTPUT_FORMATS = {"geojson", "gpkg", "shp", "dxf", "csv", "kml"}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _save_upload(file: UploadFile, dest: Path) -> None:
    written = 0
    with open(dest, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File too large")
            out.write(chunk)


def _ogr2ogr(*args: str) -> subprocess.CompletedProcess:
    if not OGR2OGR or not Path(OGR2OGR).exists():
        raise HTTPException(500, "ogr2ogr not found")
    cmd = [OGR2OGR, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise HTTPException(500, f"ogr2ogr error: {proc.stderr or proc.stdout}")
    return proc


def _run_processing_script(script: str, timeout: int = 120) -> dict:
    """Run a Python script in the QGIS Python environment and return JSON output."""
    result = subprocess.run(
        [QGIS_PYTHON, "-c", script],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise HTTPException(500, f"Processing failed:\n{result.stderr or result.stdout}")
    try:
        # Last line of stdout should be JSON
        lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else {}
    except Exception:
        return {"stdout": result.stdout}


def _fmt_to_driver(fmt: str) -> tuple[str, str, str]:
    """Return (ogr_driver, mime_type, extension) for format string."""
    mapping = {
        "geojson": ("GeoJSON", "application/geo+json", ".geojson"),
        "gpkg": ("GPKG", "application/geopackage+sqlite3", ".gpkg"),
        "shp": ("ESRI Shapefile", "application/zip", ".shp"),
        "dxf": ("DXF", "application/dxf", ".dxf"),
        "csv": ("CSV", "text/csv", ".csv"),
        "kml": ("KML", "application/vnd.google-earth.kml+xml", ".kml"),
    }
    if fmt not in mapping:
        raise HTTPException(400, f"Unsupported output format: {fmt}. Use one of: {sorted(OUTPUT_FORMATS)}")
    return mapping[fmt]


def _input_to_gpkg(src: Path, job_dir: Path) -> Path:
    """Normalize any input format to GeoPackage for processing."""
    gpkg = job_dir / "input.gpkg"
    _ogr2ogr("-f", "GPKG", str(gpkg), str(src), "-overwrite")
    return gpkg


def _gpkg_to_output(gpkg: Path, out_fmt: str, job_dir: Path, stem: str = "output") -> Path:
    driver, mime, ext = _fmt_to_driver(out_fmt)
    out_path = job_dir / f"{stem}{ext}"
    _ogr2ogr("-f", driver, str(out_path), str(gpkg), "-overwrite")
    return out_path


def _qgis_processing_op(
    algorithm: str,
    input_gpkg: Path,
    output_gpkg: Path,
    extra_params: str = "",
) -> None:
    """Execute a QGIS Processing algorithm via subprocess."""
    script = f"""
import sys, os, json
os.environ.setdefault("QGIS_PREFIX_PATH", "/Applications/QGIS-final-4_0_2.app/Contents/MacOS")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")

from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

import processing
from processing.core.Processing import Processing
Processing.initialize()

params = {{
    "INPUT": "{input_gpkg}",
    "OUTPUT": "{output_gpkg}",
    {extra_params}
}}
result = processing.run("{algorithm}", params)
print(json.dumps({{"ok": True, "result": str(result)}}))
app.exitQgis()
"""
    _run_processing_script(script)


# ---------------------------------------------------------------------------
# Format Conversion
# ---------------------------------------------------------------------------

@router.post("/process/convert")
async def convert_format(
    file: UploadFile = File(...),
    output_format: str = Form("geojson", description="输出格式: geojson | gpkg | shp | dxf | csv | kml"),
    srs: str = Form("", description="重投影到指定坐标系，如 EPSG:4326（留空保持原坐标系）"),
):
    """把任意矢量格式转换为目标格式。"""
    suffix = Path(file.filename or "x.dxf").suffix.lower()
    if suffix not in VECTOR_EXTS:
        raise HTTPException(400, f"不支持的输入格式 {suffix}")

    out_fmt = output_format.lower().strip(".")
    driver, mime, ext = _fmt_to_driver(out_fmt)

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / file.filename
    _save_upload(file, src)

    stem = Path(file.filename).stem
    out_path = job_dir / f"{stem}{ext}"

    cmd_args = ["-f", driver, str(out_path), str(src), "-overwrite", "-skipfailures"]
    if srs:
        cmd_args += ["-t_srs", srs]
    _ogr2ogr(*cmd_args)

    return FileResponse(path=out_path, media_type=mime, filename=f"{stem}{ext}")


# ---------------------------------------------------------------------------
# Reprojection
# ---------------------------------------------------------------------------

@router.post("/process/reproject")
async def reproject(
    file: UploadFile = File(...),
    target_srs: str = Form("EPSG:4326", description="目标坐标系"),
    output_format: str = Form("geojson"),
):
    """把矢量数据重投影到目标坐标系。"""
    suffix = Path(file.filename or "x.gpkg").suffix.lower()
    if suffix not in VECTOR_EXTS:
        raise HTTPException(400, f"不支持的输入格式 {suffix}")

    out_fmt = output_format.lower().strip(".")
    driver, mime, ext = _fmt_to_driver(out_fmt)

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / file.filename
    _save_upload(file, src)

    stem = Path(file.filename).stem
    out_path = job_dir / f"{stem}_reprojected{ext}"

    _ogr2ogr("-f", driver, str(out_path), str(src), "-t_srs", target_srs, "-overwrite")

    return FileResponse(path=out_path, media_type=mime, filename=out_path.name)


# ---------------------------------------------------------------------------
# Merge multiple files
# ---------------------------------------------------------------------------

@router.post("/process/merge")
async def merge_files(
    files: list[UploadFile] = File(..., description="多个矢量文件"),
    output_format: str = Form("geojson"),
    srs: str = Form("EPSG:4326"),
):
    """把多个矢量文件合并成一个。"""
    if len(files) < 2:
        raise HTTPException(400, "至少上传 2 个文件")

    out_fmt = output_format.lower().strip(".")
    driver, mime, ext = _fmt_to_driver(out_fmt)

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    saved = []
    for f in files:
        dest = job_dir / f.filename
        _save_upload(f, dest)
        saved.append(dest)

    # Merge: first file creates output, rest appended
    out_path = job_dir / f"merged{ext}"
    _ogr2ogr("-f", driver, str(out_path), str(saved[0]),
             "-t_srs", srs, "-overwrite")
    for extra in saved[1:]:
        _ogr2ogr("-f", driver, str(out_path), str(extra),
                 "-t_srs", srs, "-append", "-update")

    return FileResponse(path=out_path, media_type=mime, filename=f"merged{ext}")


# ---------------------------------------------------------------------------
# Spatial Analysis via QGIS Processing
# ---------------------------------------------------------------------------

@router.post("/analysis/buffer")
async def buffer_analysis(
    file: UploadFile = File(..., description="输入矢量文件"),
    distance: float = Form(..., description="缓冲距离（地图单位，如 100 米）"),
    segments: int = Form(16, description="圆弧段数（越大越平滑）"),
    dissolve: bool = Form(False, description="是否合并相邻缓冲区"),
    output_format: str = Form("geojson"),
):
    """对矢量要素做缓冲区分析。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / (file.filename or "input.gpkg")
    _save_upload(file, src)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_out = job_dir / "buffer.gpkg"

    _qgis_processing_op(
        "native:buffer",
        gpkg_in, gpkg_out,
        f'"DISTANCE": {distance}, "SEGMENTS": {segments}, "DISSOLVE": {"true" if dissolve else "false"}, "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2',
    )

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "buffer_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"buffer_result{ext}")


@router.post("/analysis/centroid")
async def centroid(
    file: UploadFile = File(...),
    output_format: str = Form("geojson"),
):
    """提取多边形要素的质心点。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / (file.filename or "input.gpkg")
    _save_upload(file, src)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_out = job_dir / "centroid.gpkg"
    _qgis_processing_op("native:centroids", gpkg_in, gpkg_out)

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "centroid_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"centroid_result{ext}")


@router.post("/analysis/convex_hull")
async def convex_hull(
    file: UploadFile = File(...),
    output_format: str = Form("geojson"),
):
    """计算矢量要素的凸包（Convex Hull）。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / (file.filename or "input.gpkg")
    _save_upload(file, src)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_out = job_dir / "convexhull.gpkg"
    _qgis_processing_op("native:convexhull", gpkg_in, gpkg_out)

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "convexhull_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"convexhull_result{ext}")


@router.post("/analysis/clip")
async def clip_analysis(
    input_file: UploadFile = File(..., description="被裁切的图层"),
    clip_file: UploadFile = File(..., description="裁切边界图层"),
    output_format: str = Form("geojson"),
):
    """用一个图层裁切另一个图层。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    src = job_dir / (input_file.filename or "input.gpkg")
    clip = job_dir / (clip_file.filename or "clip.gpkg")
    _save_upload(input_file, src)
    _save_upload(clip_file, clip)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_clip = job_dir / "clip_layer.gpkg"
    _ogr2ogr("-f", "GPKG", str(gpkg_clip), str(clip), "-overwrite")

    gpkg_out = job_dir / "clipped.gpkg"

    script = f"""
import sys, os, json
os.environ.setdefault("QGIS_PREFIX_PATH", "/Applications/QGIS-final-4_0_2.app/Contents/MacOS")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
result = processing.run("native:clip", {{
    "INPUT": "{gpkg_in}",
    "OVERLAY": "{gpkg_clip}",
    "OUTPUT": "{gpkg_out}",
}})
print(json.dumps({{"ok": True}}))
app.exitQgis()
"""
    _run_processing_script(script)

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "clip_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"clip_result{ext}")


@router.post("/analysis/intersect")
async def intersect(
    input_file: UploadFile = File(..., description="输入图层 A"),
    overlay_file: UploadFile = File(..., description="叠加图层 B"),
    output_format: str = Form("geojson"),
):
    """两个图层的交集叠加分析。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    src = job_dir / (input_file.filename or "input.gpkg")
    overlay = job_dir / (overlay_file.filename or "overlay.gpkg")
    _save_upload(input_file, src)
    _save_upload(overlay_file, overlay)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_overlay = job_dir / "overlay.gpkg"
    _ogr2ogr("-f", "GPKG", str(gpkg_overlay), str(overlay), "-overwrite")
    gpkg_out = job_dir / "intersect.gpkg"

    script = f"""
import sys, os, json
os.environ.setdefault("QGIS_PREFIX_PATH", "/Applications/QGIS-final-4_0_2.app/Contents/MacOS")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
result = processing.run("native:intersection", {{
    "INPUT": "{gpkg_in}",
    "OVERLAY": "{gpkg_overlay}",
    "OUTPUT": "{gpkg_out}",
}})
print(json.dumps({{"ok": True}}))
app.exitQgis()
"""
    _run_processing_script(script)

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "intersect_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"intersect_result{ext}")


@router.post("/analysis/union")
async def union_analysis(
    input_file: UploadFile = File(..., description="输入图层 A"),
    overlay_file: UploadFile = File(..., description="叠加图层 B"),
    output_format: str = Form("geojson"),
):
    """两个图层的并集叠加分析。"""
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    src = job_dir / (input_file.filename or "input.gpkg")
    overlay = job_dir / (overlay_file.filename or "overlay.gpkg")
    _save_upload(input_file, src)
    _save_upload(overlay_file, overlay)

    gpkg_in = _input_to_gpkg(src, job_dir)
    gpkg_overlay = job_dir / "overlay.gpkg"
    _ogr2ogr("-f", "GPKG", str(gpkg_overlay), str(overlay), "-overwrite")
    gpkg_out = job_dir / "union.gpkg"

    script = f"""
import sys, os, json
os.environ.setdefault("QGIS_PREFIX_PATH", "/Applications/QGIS-final-4_0_2.app/Contents/MacOS")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
result = processing.run("native:union", {{
    "INPUT": "{gpkg_in}",
    "OVERLAY": "{gpkg_overlay}",
    "OUTPUT": "{gpkg_out}",
}})
print(json.dumps({{"ok": True}}))
app.exitQgis()
"""
    _run_processing_script(script)

    out_fmt = output_format.lower().strip(".")
    out_path = _gpkg_to_output(gpkg_out, out_fmt, job_dir, "union_result")
    _, mime, ext = _fmt_to_driver(out_fmt)
    return FileResponse(path=out_path, media_type=mime, filename=f"union_result{ext}")
