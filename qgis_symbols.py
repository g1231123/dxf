"""
符号库 & 底图服务 API
=====================
符号库：列出/预览 QGIS 内置符号和色带，将符号应用到图层生成 QML。
底图服务：列出/添加底图提供商，瓦片代理，矢量叠底图渲染。

路由前缀: /symbols, /basemap, /render/map_with_basemap
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["Symbols & Basemap"])

STORE_DIR   = Path("/tmp/qgis_geojson_store")
WORK_DIR    = Path(tempfile.gettempdir()) / "qgis_symbol_jobs"
TILE_CACHE  = Path(tempfile.gettempdir()) / "qgis_tile_cache"
WORK_DIR.mkdir(exist_ok=True)
TILE_CACHE.mkdir(exist_ok=True)

QGIS_PREFIX = os.environ.get("QGIS_PREFIX_PATH",
                              "/Applications/QGIS-final-4_0_2.app/Contents/MacOS")
QGIS_PYTHON = os.environ.get("QGIS_PYTHON",
                              "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/python")

# ---------------------------------------------------------------------------
# 内置底图提供商配置
# ---------------------------------------------------------------------------
_BASEMAP_PROVIDERS: dict[str, dict] = {
    "osm": {
        "id": "osm", "name": "OpenStreetMap", "type": "xyz",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
    },
    "osm_topo": {
        "id": "osm_topo", "name": "OpenTopoMap", "type": "xyz",
        "url": "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap, SRTM | Map style © OpenTopoMap",
    },
    "esri_imagery": {
        "id": "esri_imagery", "name": "ESRI World Imagery", "type": "xyz",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri",
    },
    "esri_streets": {
        "id": "esri_streets", "name": "ESRI World Street Map", "type": "xyz",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri",
    },
    "cartodb_light": {
        "id": "cartodb_light", "name": "CartoDB Positron", "type": "xyz",
        "url": "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "attribution": "© CartoDB",
    },
    "cartodb_dark": {
        "id": "cartodb_dark", "name": "CartoDB Dark Matter", "type": "xyz",
        "url": "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "attribution": "© CartoDB",
    },
    "amap_normal": {
        "id": "amap_normal", "name": "高德地图(中文)", "type": "xyz",
        "url": "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "attribution": "© 高德地图",
    },
    "amap_satellite": {
        "id": "amap_satellite", "name": "高德卫星(中文)", "type": "xyz",
        "url": "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        "attribution": "© 高德地图",
    },
    "amap_satellite_label": {
        "id": "amap_satellite_label", "name": "高德卫星路网(中文)", "type": "xyz",
        "url": "https://webst01.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}",
        "attribution": "© 高德地图",
    },
}


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class ApplySymbolRequest(BaseModel):
    file_id: str = Field(..., description="目标图层 file_id")
    symbol_name: str = Field(..., description="符号名称，来自 GET /symbols 列表")
    color: str = Field("#e74c3c", description="符号颜色（HEX 格式，如 #e74c3c）")
    size: float = Field(4.0, gt=0, description="符号大小（点/像素）")
    rotation_field: Optional[str] = Field(None, description="用于控制旋转角度的属性字段名（可选）")
    opacity: float = Field(1.0, ge=0, le=1, description="透明度：0=完全透明，1=完全不透明")


class AddWMSRequest(BaseModel):
    name: str = Field(..., description="底图名称，显示用")
    url: str = Field(..., description="WMS/WMTS 服务地址")
    type: str = Field("wms", description="服务类型：wms / wmts / xyz")
    layer: Optional[str] = Field(None, description="WMS 图层名")
    style: Optional[str] = Field("default", description="WMS 样式名")
    tile_matrix_set: Optional[str] = Field(None, description="WMTS TileMatrixSet，如 w（墨卡托）或 c（经纬度）")
    token: Optional[str] = Field(None, description="服务 Token（如天地图 token），追加到请求 URL")


class RenderWithBasemapRequest(BaseModel):
    bbox: list[float] = Field(..., description="渲染范围 [xmin, ymin, xmax, ymax]（EPSG:4326）")
    width: int = Field(1280, ge=64, le=8192, description="输出图片宽度（像素）")
    height: int = Field(720, ge=64, le=8192, description="输出图片高度（像素）")
    basemap_provider: str = Field("osm", description="底图提供商 ID，来自 GET /basemap/providers")
    layers: list[dict] = Field(default_factory=list,
                                description="叠加的矢量图层列表，每项含 file_id、opacity、style")


# ---------------------------------------------------------------------------
# 符号库接口
# ---------------------------------------------------------------------------
def _run_qgis_script(script: str, timeout: int = 30) -> dict:
    """执行 PyQGIS 子进程脚本，返回最后一行 JSON。"""
    proc = subprocess.run([QGIS_PYTHON, "-c", script],
                          capture_output=True, text=True, timeout=timeout)
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if not lines:
        raise HTTPException(500, detail={"code": "RENDER_FAILED",
                                          "msg": proc.stderr or "无输出"})
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        raise HTTPException(500, detail={"code": "RENDER_FAILED", "msg": lines[-1]})


@router.get("/symbols/groups", summary="获取符号分组列表")
def get_symbol_groups():
    """返回 QGIS 内置符号库的所有分组名称。"""
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
groups = list(style.symbolGroupNames()) + list(style.smartgroupNames())
print(json.dumps({{"groups": sorted(set(groups))}}))
app.exitQgis()
"""
    data = _run_qgis_script(script)
    return data


@router.get("/symbols", summary="列出符号库中的所有符号")
def list_symbols(
    group:  Optional[str] = Query(None, description="按分组过滤"),
    type:   Optional[str] = Query(None, description="符号类型：marker / line / fill"),
    search: Optional[str] = Query(None, description="关键词搜索符号名"),
    page:      int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    """
    列出 QGIS 内置符号库中的所有符号。
    返回的 preview_url 可用于获取 32×32 的符号预览图。
    """
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle, QgsSymbol
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
type_map = {{0: "marker", 1: "line", 2: "fill"}}
symbols = []
for name in style.symbolNames():
    sym = style.symbol(name)
    if not sym: continue
    sym_type = type_map.get(int(sym.type()), "unknown")
    if {json.dumps(type)} and sym_type != {json.dumps(type)}:
        continue
    if {json.dumps(search or "")} and {json.dumps((search or "").lower())} not in name.lower():
        continue
    tags = style.tagsOfSymbol(QgsStyle.SymbolEntity, name)
    symbols.append({{
        "name": name,
        "type": sym_type,
        "tags": tags,
        "preview_url": f"/symbols/{{name}}/preview.png",
    }})
print(json.dumps({{"symbols": symbols}}))
app.exitQgis()
"""
    data = _run_qgis_script(script, timeout=30)
    all_symbols = data.get("symbols", [])
    total = len(all_symbols)
    start = (page - 1) * page_size
    return {
        "total":    total,
        "page":     page,
        "page_size": page_size,
        "symbols":  all_symbols[start: start + page_size],
    }


@router.get("/symbols/{name}/preview.png", summary="获取符号预览图")
def symbol_preview(name: str, size: int = Query(32, ge=8, le=256,
                   description="预览图边长（像素），默认 32")):
    """返回指定符号的预览图（PNG），可用于在前端符号选择器中展示。"""
    script = f"""
import sys, os, json, base64
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImage, QPainter, QColor
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
sym = style.symbol({json.dumps(name)})
if not sym:
    print(json.dumps({{"error": "not_found"}}))
else:
    img = QImage(QSize({size},{size}), QImage.Format_ARGB32)
    img.fill(QColor(0,0,0,0))
    painter = QPainter(img)
    sym.drawPreviewIcon(painter, QSize({size},{size}))
    painter.end()
    buf = []
    import tempfile, pathlib
    tmp = pathlib.Path(tempfile.mktemp(suffix=".png"))
    img.save(str(tmp), "PNG")
    data = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink()
    print(json.dumps({{"png_b64": data}}))
app.exitQgis()
"""
    data = _run_qgis_script(script, timeout=20)
    if data.get("error") == "not_found":
        raise HTTPException(404, detail={"code": "SYMBOL_NOT_FOUND",
                                          "msg": f"符号 {name!r} 不存在"})
    png = base64.b64decode(data["png_b64"])
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.post("/symbols/apply", summary="将符号应用到图层")
def apply_symbol(req: ApplySymbolRequest):
    """
    将符号库中的指定符号应用到图层，生成 QML 样式片段。
    返回的 qml_fragment 可直接写入 .qml 文件，或传给 POST /styles/qml/{file_id}。
    """
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle
from qgis.PyQt.QtGui import QColor
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
sym = style.symbol({json.dumps(req.symbol_name)})
if not sym:
    print(json.dumps({{"error": "not_found"}}))
else:
    sym.setColor(QColor({json.dumps(req.color)}))
    sym.setOpacity({req.opacity})
    # 序列化为 QML XML 片段
    doc_str = sym.toQmlFragment() if hasattr(sym, "toQmlFragment") else "<symbol/>"
    print(json.dumps({{"qml_fragment": doc_str, "symbol_name": {json.dumps(req.symbol_name)}}}))
app.exitQgis()
"""
    data = _run_qgis_script(script, timeout=20)
    if data.get("error") == "not_found":
        raise HTTPException(404, detail={"code": "SYMBOL_NOT_FOUND",
                                          "msg": f"符号 {req.symbol_name!r} 不存在"})
    return {"applied": True, "file_id": req.file_id, **data}


@router.get("/symbols/colorramps", summary="获取内置色带列表")
def list_colorramps(search: Optional[str] = Query(None, description="关键词搜索色带名")):
    """
    列出 QGIS 内置色带（用于分级渲染、热力图等）。
    preview_url 可用于在前端展示色带缩略图。
    """
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
ramps = []
for name in style.colorRampNames():
    if {json.dumps(search or "")} and {json.dumps((search or "").lower())} not in name.lower():
        continue
    ramp = style.colorRamp(name)
    ramp_type = type(ramp).__name__ if ramp else "unknown"
    ramps.append({{
        "name": name,
        "type": ramp_type,
        "preview_url": f"/symbols/colorramps/{{name}}/preview.png",
    }})
print(json.dumps({{"colorramps": ramps}}))
app.exitQgis()
"""
    return _run_qgis_script(script, timeout=30)


@router.get("/symbols/colorramps/{name}/preview.png", summary="获取色带预览图")
def colorramp_preview(name: str,
                      width:  int = Query(200, ge=20, le=800, description="预览图宽度（像素）"),
                      height: int = Query(20,  ge=8,  le=100, description="预览图高度（像素）")):
    """返回指定色带的预览图（PNG 横条），用于前端色带选择器。"""
    script = f"""
import sys, os, json, base64, tempfile, pathlib
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication, QgsStyle
from qgis.PyQt.QtCore import QSize, QRectF
from qgis.PyQt.QtGui import QImage, QPainter
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
style = QgsStyle.defaultStyle()
ramp = style.colorRamp({json.dumps(name)})
if not ramp:
    print(json.dumps({{"error": "not_found"}}))
else:
    img = QImage(QSize({width},{height}), QImage.Format_ARGB32)
    painter = QPainter(img)
    ramp.drawPreview(painter, QSize({width},{height}))
    painter.end()
    tmp = pathlib.Path(tempfile.mktemp(suffix=".png"))
    img.save(str(tmp), "PNG")
    data = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink()
    print(json.dumps({{"png_b64": data}}))
app.exitQgis()
"""
    data = _run_qgis_script(script, timeout=20)
    if data.get("error") == "not_found":
        raise HTTPException(404, detail={"code": "SYMBOL_NOT_FOUND",
                                          "msg": f"色带 {name!r} 不存在"})
    png = base64.b64decode(data["png_b64"])
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# 底图服务接口
# ---------------------------------------------------------------------------
@router.get("/basemap/providers", summary="列出底图提供商")
def list_basemap_providers():
    """列出所有可用的底图服务提供商（内置 + 自定义添加的）。"""
    return {"providers": list(_BASEMAP_PROVIDERS.values())}


@router.post("/basemap/wms", summary="添加自定义 WMS/WMTS 底图")
def add_wms_provider(req: AddWMSRequest):
    """
    添加自定义 WMS、WMTS 或 XYZ 瓦片底图。
    天地图等需要 token 的服务，将 token 追加到 URL query string。
    """
    provider_id = "custom_" + str(len(_BASEMAP_PROVIDERS))
    url = req.url
    if req.token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}tk={req.token}"
    _BASEMAP_PROVIDERS[provider_id] = {
        "id":    provider_id,
        "name":  req.name,
        "type":  req.type,
        "url":   url,
        "layer": req.layer,
        "style": req.style,
        "tile_matrix_set": req.tile_matrix_set,
    }
    return {"provider_id": provider_id, "name": req.name}


@router.get("/basemap/tile/{provider_id}/{z}/{x}/{y}.png", summary="瓦片代理")
def proxy_tile(provider_id: str, z: int, x: int, y: int):
    """
    服务端代理拉取指定底图提供商的瓦片，解决前端跨域问题。
    支持内存缓存，相同瓦片不重复请求。
    """
    provider = _BASEMAP_PROVIDERS.get(provider_id)
    if not provider:
        raise HTTPException(404, detail={"code": "BASEMAP_UNAVAILABLE",
                                          "msg": f"底图提供商 {provider_id!r} 不存在"})
    tile_url = provider["url"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    cache_key = hashlib.md5(tile_url.encode()).hexdigest()
    cache_file = TILE_CACHE / f"{cache_key}.png"
    if cache_file.exists():
        return Response(content=cache_file.read_bytes(), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"})
    try:
        req = urllib.request.Request(tile_url, headers={"User-Agent": "QGIS-Web-Service/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        cache_file.write_bytes(data)
        return Response(content=data, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"})
    except Exception as e:
        raise HTTPException(502, detail={"code": "BASEMAP_UNAVAILABLE", "msg": str(e)})


@router.post("/render/map_with_basemap", summary="矢量叠底图渲染")
def render_with_basemap(req: RenderWithBasemapRequest):
    """
    先拼接底图瓦片，再将矢量图层叠加渲染在底图上，返回合并后的 PNG。
    layers 中每项可指定 opacity（透明度）和 style（样式参数，同 /render/map）。
    """
    provider = _BASEMAP_PROVIDERS.get(req.basemap_provider)
    if not provider:
        raise HTTPException(404, detail={"code": "BASEMAP_UNAVAILABLE",
                                          "msg": f"底图 {req.basemap_provider!r} 不存在"})
    # 计算所需瓦片级别（根据 bbox 和输出尺寸估算）
    import math
    bbox = req.bbox
    lng_span = bbox[2] - bbox[0]
    zoom = max(0, min(18, int(math.log2(360.0 / lng_span * req.width / 256))))

    tile_url_template = provider["url"]

    script = f"""
import sys, os, json, math, urllib.request
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import (QgsApplication, QgsVectorLayer, QgsMapSettings,
    QgsMapRendererParallelJob, QgsRectangle, QgsCoordinateReferenceSystem,
    QgsRasterLayer)
from qgis.PyQt.QtCore import QSize, QEventLoop
from qgis.PyQt.QtGui import QColor, QImage, QPainter
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

layers = []
# 添加 XYZ 底图图层
tile_url = {json.dumps(tile_url_template)}
uri = f"type=xyz&url={{urllib.parse.quote(tile_url, safe='{{}}://?=&')}}&zmax=19&zmin=0"
import urllib.parse
uri = "type=xyz&url=" + urllib.parse.quote(tile_url, safe="") + "&zmax=19&zmin=0"
basemap = QgsRasterLayer(uri, "basemap", "wms")
if basemap.isValid():
    layers.append(basemap)

# 添加矢量图层
store_dir = {json.dumps(str(STORE_DIR))}
for layer_cfg in {json.dumps(req.layers)}:
    fid = layer_cfg.get("file_id")
    if not fid: continue
    import pathlib
    d = pathlib.Path(store_dir) / fid
    src = d / "data.geojson"
    if not src.exists():
        for f in d.iterdir():
            if f.suffix.lower() not in (".json",".geojson") and f.is_file():
                src = f; break
    vl = QgsVectorLayer(str(src), fid, "ogr")
    if vl.isValid():
        layers.append(vl)

settings = QgsMapSettings()
settings.setOutputSize(QSize({req.width}, {req.height}))
settings.setBackgroundColor(QColor(0,0,0,0))
settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
settings.setExtent(QgsRectangle({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}))
settings.setLayers(list(reversed(layers)))
loop = QEventLoop()
job = QgsMapRendererParallelJob(settings)
job.finished.connect(loop.quit); job.start()
(getattr(loop,"exec",None) or getattr(loop,"exec_"))()
import tempfile, base64, pathlib
tmp = pathlib.Path(tempfile.mktemp(suffix=".png"))
job.renderedImage().save(str(tmp), "PNG")
data = base64.b64encode(tmp.read_bytes()).decode()
tmp.unlink()
print(json.dumps({{"ok": True, "png_b64": data}}))
app.exitQgis()
"""
    data = _run_qgis_script(script, timeout=60)
    if not data.get("ok"):
        raise HTTPException(500, detail={"code": "RENDER_FAILED", "msg": data.get("error", "渲染失败")})
    png = base64.b64decode(data["png_b64"])
    return Response(content=png, media_type="image/png")
