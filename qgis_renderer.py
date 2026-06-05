"""
QGIS 2D Parametric Renderer Module
====================================
外部通过 JSON 参数控制渲染样式，PyQGIS 实时出图。

端点
----
POST /render/map          通用参数化渲染（上传文件 + JSON 样式）
POST /render/layers       多图层叠加渲染
POST /render/styled       使用 QML 样式文件渲染
GET  /render/styles       列出内置预设样式
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

WORK_DIR = Path(tempfile.gettempdir()) / "qgis_render_jobs"
WORK_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

QGIS_PREFIX = os.environ.get(
    "QGIS_PREFIX_PATH",
    "/Applications/QGIS-final-4_0_2.app/Contents/MacOS",
)

# ---------------------------------------------------------------------------
# Built-in style presets
# ---------------------------------------------------------------------------
STYLE_PRESETS: dict[str, dict] = {
    "default": {
        "fill_color": "#4a90d9",
        "fill_opacity": 0.6,
        "stroke_color": "#1a5276",
        "stroke_width": 0.5,
        "label_field": "",
        "label_size": 8,
        "label_color": "#000000",
    },
    "satellite": {
        "fill_color": "#2ecc71",
        "fill_opacity": 0.4,
        "stroke_color": "#27ae60",
        "stroke_width": 1.0,
        "label_field": "",
        "label_size": 9,
        "label_color": "#ffffff",
    },
    "grayscale": {
        "fill_color": "#aaaaaa",
        "fill_opacity": 0.5,
        "stroke_color": "#444444",
        "stroke_width": 0.5,
        "label_field": "",
        "label_size": 8,
        "label_color": "#222222",
    },
    "heatmap": {
        "fill_color": "#e74c3c",
        "fill_opacity": 0.7,
        "stroke_color": "#c0392b",
        "stroke_width": 0.3,
        "label_field": "",
        "label_size": 7,
        "label_color": "#ffffff",
    },
    "blueprint": {
        "background": "#0a1628",
        "fill_color": "#1a6fb5",
        "fill_opacity": 0.5,
        "stroke_color": "#4fc3f7",
        "stroke_width": 0.8,
        "label_field": "",
        "label_size": 8,
        "label_color": "#4fc3f7",
    },
    "autocad": {
        "background": "#fafafa",
        "fill_color": "#e8f4fd",
        "fill_opacity": 0.4,
        "stroke_color": "#1a3050",
        "stroke_width": 0.5,
        "label_field": "",
        "label_size": 9,
        "label_color": "#1a3050",
    },
}


def _save_upload(file: UploadFile, dest: Path) -> None:
    written = 0
    with open(dest, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File too large")
            out.write(chunk)


def _hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Convert #RRGGBB to (R, G, B, A) with opacity 0-1."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    a = int(max(0.0, min(1.0, opacity)) * 255)
    return r, g, b, a


# ---------------------------------------------------------------------------
# Core rendering function (runs inside QGIS Python env)
# ---------------------------------------------------------------------------

def _build_render_script(
    src_path: str,
    out_path: str,
    params: dict,
    width: int,
    height: int,
) -> str:
    """
    Build a self-contained Python script that runs PyQGIS rendering.
    The script is executed in the QGIS Python environment via subprocess.
    """
    bg = params.get("background", "#ffffff")
    fill_color = params.get("fill_color", "#4a90d9")
    fill_opacity = float(params.get("fill_opacity", 0.6))
    stroke_color = params.get("stroke_color", "#1a5276")
    stroke_width = float(params.get("stroke_width", 0.5))
    label_field = params.get("label_field", "")
    label_size = float(params.get("label_size", 8))
    label_color = params.get("label_color", "#000000")
    label_font = params.get("label_font", "PingFang SC,Microsoft YaHei,Arial")
    show_labels = bool(label_field)

    # Per-layer overrides list for multi-layer rendering
    layers_cfg = json.dumps(params.get("layers", []))

    r, g, b, a = _hex_to_rgba(fill_color, fill_opacity)
    sr, sg, sb, _ = _hex_to_rgba(stroke_color)
    lr, lg, lb, _ = _hex_to_rgba(label_color)
    bgr, bgg, bgb, _ = _hex_to_rgba(bg)

    script = f"""
import sys, os, json
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH", "{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA", "{QGIS_PREFIX}/../Resources/qgis/proj")

from qgis.core import (
    QgsApplication, QgsVectorLayer, QgsMapSettings, QgsMapRendererParallelJob,
    QgsRectangle, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsProject, QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtCore import QSize, QEventLoop
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont

app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

src_path = {json.dumps(src_path)}
out_path = {json.dumps(out_path)}
width = {width}
height = {height}
layers_cfg = {layers_cfg!r}

# ---------------------------------------------------------------------------
# Load layer(s)
# ---------------------------------------------------------------------------
all_qgs_layers = []

if layers_cfg:
    for lcfg in layers_cfg:
        p = lcfg.get("path", src_path)
        lname = lcfg.get("name", "layer")
        qlay = QgsVectorLayer(p, lname, "ogr")
        if qlay.isValid():
            all_qgs_layers.append((qlay, lcfg))
else:
    qlay = QgsVectorLayer(src_path, "layer", "ogr")
    if qlay.isValid():
        all_qgs_layers.append((qlay, {{}}))

if not all_qgs_layers:
    print(json.dumps({{"error": "No valid layers loaded"}}))
    app.exitQgis()
    sys.exit(1)

# ---------------------------------------------------------------------------
# Apply symbols
# ---------------------------------------------------------------------------
from qgis.core import (
    QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer, QgsSimpleMarkerSymbolLayer,
    QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling,
)

def apply_style(layer, cfg):
    fc = cfg.get("fill_color", {json.dumps(fill_color)!r})
    fo = float(cfg.get("fill_opacity", {fill_opacity}))
    sc = cfg.get("stroke_color", {json.dumps(stroke_color)!r})
    sw = float(cfg.get("stroke_width", {stroke_width}))
    geom_type = layer.geometryType()  # 0=Point 1=Line 2=Polygon

    if geom_type == 2:  # Polygon
        sym_layer = QgsSimpleFillSymbolLayer()
        r2,g2,b2,a2 = {r},{g},{b},{a}
        _hex = fc.lstrip("#")
        if len(_hex)==6:
            r2,g2,b2 = int(_hex[0:2],16),int(_hex[2:4],16),int(_hex[4:6],16)
            a2 = int(fo*255)
        sym_layer.setFillColor(QColor(r2,g2,b2,a2))
        _sh = sc.lstrip("#")
        if len(_sh)==6:
            sr2,sg2,sb2 = int(_sh[0:2],16),int(_sh[2:4],16),int(_sh[4:6],16)
            sym_layer.setStrokeColor(QColor(sr2,sg2,sb2))
        sym_layer.setStrokeWidth(sw)
        sym = QgsFillSymbol([sym_layer])
        layer.setRenderer(QgsSingleSymbolRenderer(sym))

    elif geom_type == 1:  # Line
        sym_layer = QgsSimpleLineSymbolLayer()
        _sh = sc.lstrip("#")
        if len(_sh)==6:
            sr2,sg2,sb2 = int(_sh[0:2],16),int(_sh[2:4],16),int(_sh[4:6],16)
            sym_layer.setColor(QColor(sr2,sg2,sb2))
        sym_layer.setWidth(sw)
        # Line style
        line_style = cfg.get("line_style", "solid")
        styles = {{"solid":0,"dash":1,"dot":2,"dash_dot":3}}
        sym_layer.setPenStyle(list(styles.values())[list(styles.keys()).index(line_style)] if line_style in styles else 0)
        sym = QgsLineSymbol([sym_layer])
        layer.setRenderer(QgsSingleSymbolRenderer(sym))

    else:  # Point
        sym_layer = QgsSimpleMarkerSymbolLayer()
        _hex = fc.lstrip("#")
        if len(_hex)==6:
            r2,g2,b2 = int(_hex[0:2],16),int(_hex[2:4],16),int(_hex[4:6],16)
            a2 = int(fo*255)
            sym_layer.setColor(QColor(r2,g2,b2,a2))
        _sh = sc.lstrip("#")
        if len(_sh)==6:
            sr2,sg2,sb2 = int(_sh[0:2],16),int(_sh[2:4],16),int(_sh[4:6],16)
            sym_layer.setStrokeColor(QColor(sr2,sg2,sb2))
        marker_shape = cfg.get("marker_shape", "circle")
        sym_layer.setShape(QgsSimpleMarkerSymbolLayer.Shape.Circle if marker_shape=="circle" else QgsSimpleMarkerSymbolLayer.Shape.Square)
        sym_layer.setSize(float(cfg.get("marker_size", 3.0)))
        sym = QgsMarkerSymbol([sym_layer])
        layer.setRenderer(QgsSingleSymbolRenderer(sym))

    # Labels
    lf = cfg.get("label_field", {json.dumps(label_field)!r})
    if lf:
        pal = QgsPalLayerSettings()
        pal.fieldName = lf
        pal.enabled = True
        fmt = QgsTextFormat()
        lc = cfg.get("label_color", {json.dumps(label_color)!r})
        _lh = lc.lstrip("#")
        if len(_lh)==6:
            lr2,lg2,lb2 = int(_lh[0:2],16),int(_lh[2:4],16),int(_lh[4:6],16)
            fmt.setColor(QColor(lr2,lg2,lb2))
        font = QFont({json.dumps(label_font)!r}.split(",")[0].strip())
        font.setPointSizeF(float(cfg.get("label_size", {label_size})))
        fmt.setFont(font)
        pal.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)

for qlay, lcfg in all_qgs_layers:
    apply_style(qlay, lcfg)

# ---------------------------------------------------------------------------
# Map settings
# ---------------------------------------------------------------------------
settings = QgsMapSettings()
settings.setOutputSize(QSize(width, height))
settings.setBackgroundColor(QColor({bgr},{bgg},{bgb},255))

# Compute combined extent
from qgis.core import QgsRectangle
ext = None
for qlay, _ in all_qgs_layers:
    e = qlay.extent()
    ext = e if ext is None else ext.combineExtentWith(e)

if ext is None or ext.isEmpty():
    print(json.dumps({{"error":"Empty extent"}}))
    app.exitQgis()
    sys.exit(1)

# Add 5% padding
ext.grow(ext.width() * 0.05)
# Adjust to output aspect ratio
ratio_out = width / height
ratio_ext = ext.width() / (ext.height() or 1)
if ratio_out > ratio_ext:
    extra = ext.height() * ratio_out - ext.width()
    ext.setXMinimum(ext.xMinimum() - extra/2)
    ext.setXMaximum(ext.xMaximum() + extra/2)
else:
    extra = ext.width() / ratio_out - ext.height()
    ext.setYMinimum(ext.yMinimum() - extra/2)
    ext.setYMaximum(ext.yMaximum() + extra/2)

settings.setExtent(ext)
settings.setLayers([qlay for qlay, _ in all_qgs_layers])

flag_fn = getattr(QgsMapSettings, "Flag", QgsMapSettings)
for fname in ("Antialiasing", "DrawLabeling", "UseAdvancedEffects", "ForceVectorOutput"):
    flag = getattr(flag_fn, fname, None) or getattr(QgsMapSettings, fname, None)
    if flag:
        settings.setFlag(flag, True)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
job = QgsMapRendererParallelJob(settings)
loop = QEventLoop()
job.finished.connect(loop.quit)
job.start()
exec_fn = getattr(loop, "exec", None) or getattr(loop, "exec_")
exec_fn()

img = job.renderedImage()
img.save(out_path, "PNG")
print(json.dumps({{"ok": True, "width": width, "height": height}}))
app.exitQgis()
"""
    return script


def _do_render(src_path: str, out_path: str, params: dict, width: int, height: int) -> None:
    import subprocess
    script = _build_render_script(src_path, out_path, params, width, height)
    qgis_python = os.path.join(QGIS_PREFIX, "python")
    proc = subprocess.run(
        [qgis_python, "-c", script],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0 or not Path(out_path).exists():
        raise HTTPException(
            500,
            f"Render failed:\n{proc.stderr or proc.stdout}",
        )
    # Check for error JSON in last line
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if lines:
        try:
            result = json.loads(lines[-1])
            if "error" in result:
                raise HTTPException(500, f"Render error: {result['error']}")
        except (json.JSONDecodeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/render/styles")
def list_styles() -> dict:
    """列出所有内置渲染样式预设。"""
    return {
        "presets": list(STYLE_PRESETS.keys()),
        "details": STYLE_PRESETS,
    }


@router.post("/render/map")
async def render_map(
    file: UploadFile = File(..., description="矢量文件 (.dxf/.shp/.geojson/.gpkg/.kml 等)"),
    width: int = Form(1920, description="输出宽度 px"),
    height: int = Form(1080, description="输出高度 px"),
    preset: str = Form("", description="预设样式名（default/satellite/grayscale/heatmap/blueprint/autocad）"),
    style: str = Form("{}", description="""
JSON 样式参数，可覆盖预设：
{
  "background":    "#ffffff",      背景色
  "fill_color":    "#4a90d9",      填充色（面）
  "fill_opacity":  0.6,            填充透明度 0-1
  "stroke_color":  "#1a5276",      边线/线条颜色
  "stroke_width":  0.5,            线宽（地图单位）
  "line_style":    "solid",        线型: solid|dash|dot|dash_dot
  "marker_shape":  "circle",       点符号: circle|square
  "marker_size":   3.0,            点大小
  "label_field":   "name",         标注字段名（空=不标注）
  "label_size":    8,              标注字号
  "label_color":   "#000000",      标注颜色
  "label_font":    "PingFang SC"   字体（支持 CJK）
}
    """),
    fmt: str = Form("png", description="输出格式: png | jpeg"),
):
    """
    **参数化实时 2D 渲染**

    上传任意矢量文件，传入 JSON 样式参数，返回渲染图片。
    支持预设样式（preset）和自定义参数（style）叠加使用。
    """
    suffix = Path(file.filename or "x.gpkg").suffix.lower()

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    src = job_dir / (file.filename or "input" + suffix)
    _save_upload(file, src)

    # Merge preset + custom style
    params: dict[str, Any] = {}
    if preset and preset in STYLE_PRESETS:
        params.update(STYLE_PRESETS[preset])
    try:
        custom = json.loads(style) if style else {}
        params.update(custom)
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, f"style 参数 JSON 解析失败: {e}")

    out_ext = ".jpg" if fmt == "jpeg" else ".png"
    out_path = job_dir / f"render{out_ext}"
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"

    try:
        _do_render(str(src), str(out_path), params, width, height)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, str(e))

    stem = Path(file.filename or "render").stem
    return FileResponse(path=out_path, media_type=mime, filename=f"{stem}_render{out_ext}")


@router.post("/render/layers")
async def render_layers(
    files: list[UploadFile] = File(..., description="多个矢量文件（按顺序叠加渲染，最后一个在最上层）"),
    width: int = Form(1920),
    height: int = Form(1080),
    layers_config: str = Form("[]", description="""
每个图层的样式配置 JSON 数组，顺序与文件对应：
[
  {
    "fill_color": "#4a90d9", "fill_opacity": 0.5,
    "stroke_color": "#1a5276", "stroke_width": 0.5,
    "label_field": "name", "label_size": 9
  },
  {
    "fill_color": "#e74c3c", "stroke_color": "#c0392b",
    "marker_shape": "circle", "marker_size": 5
  }
]
    """),
    background: str = Form("#ffffff"),
    fmt: str = Form("png"),
):
    """
    **多图层叠加渲染**

    多个矢量文件叠加，每层独立样式配置。
    """
    if not files:
        raise HTTPException(400, "至少上传一个文件")

    try:
        layer_styles = json.loads(layers_config)
    except Exception as e:
        raise HTTPException(400, f"layers_config JSON 解析失败: {e}")

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    saved_paths = []
    for i, f in enumerate(files):
        dest = job_dir / (f.filename or f"layer_{i}.gpkg")
        _save_upload(f, dest)
        saved_paths.append(str(dest))

    # Build layers config with paths
    layers_with_paths = []
    for i, path in enumerate(saved_paths):
        cfg = layer_styles[i] if i < len(layer_styles) else {}
        cfg["path"] = path
        cfg["name"] = files[i].filename or f"layer_{i}"
        layers_with_paths.append(cfg)

    params = {
        "background": background,
        "layers": layers_with_paths,
    }

    out_ext = ".jpg" if fmt == "jpeg" else ".png"
    out_path = job_dir / f"render{out_ext}"
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"

    try:
        _do_render(saved_paths[0], str(out_path), params, width, height)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, str(e))

    return FileResponse(path=out_path, media_type=mime, filename=f"multilayer_render{out_ext}")


@router.post("/render/styled")
async def render_with_qml(
    file: UploadFile = File(..., description="矢量数据文件"),
    qml: UploadFile = File(..., description=".qml 样式文件（QGIS 样式）"),
    width: int = Form(1920),
    height: int = Form(1080),
    background: str = Form("#ffffff"),
    fmt: str = Form("png"),
):
    """
    **使用 QML 样式文件渲染**

    直接从 QGIS 导出 .qml 样式文件，上传后原样应用渲染。
    适合精确复现 QGIS 桌面端的出图效果。
    """
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    src = job_dir / (file.filename or "input.gpkg")
    qml_path = job_dir / (qml.filename or "style.qml")
    _save_upload(file, src)
    _save_upload(qml, qml_path)

    out_ext = ".jpg" if fmt == "jpeg" else ".png"
    out_path = job_dir / f"render{out_ext}"
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"

    bgr, bgg, bgb, _ = _hex_to_rgba(background)

    script = f"""
import sys, os, json
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0, "/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH", "{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA", "{QGIS_PREFIX}/../Resources/qgis/proj")

from qgis.core import (
    QgsApplication, QgsVectorLayer, QgsMapSettings,
    QgsMapRendererParallelJob, QgsRectangle,
)
from qgis.PyQt.QtCore import QSize, QEventLoop
from qgis.PyQt.QtGui import QColor

app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

layer = QgsVectorLayer({json.dumps(str(src))!r}, "layer", "ogr")
if not layer.isValid():
    print(json.dumps({{"error": "Invalid layer"}}))
    app.exitQgis(); sys.exit(1)

layer.loadNamedStyle({json.dumps(str(qml_path))!r})

settings = QgsMapSettings()
settings.setOutputSize(QSize({width}, {height}))
settings.setBackgroundColor(QColor({bgr},{bgg},{bgb},255))
ext = layer.extent()
ext.grow(ext.width() * 0.05)
settings.setExtent(ext)
settings.setLayers([layer])

flag_fn = getattr(QgsMapSettings, "Flag", QgsMapSettings)
for fname in ("Antialiasing","DrawLabeling","UseAdvancedEffects"):
    flag = getattr(flag_fn, fname, None) or getattr(QgsMapSettings, fname, None)
    if flag:
        settings.setFlag(flag, True)

job = QgsMapRendererParallelJob(settings)
loop = QEventLoop()
job.finished.connect(loop.quit)
job.start()
exec_fn = getattr(loop, "exec", None) or getattr(loop, "exec_")
exec_fn()

img = job.renderedImage()
img.save({json.dumps(str(out_path))!r}, "PNG")
print(json.dumps({{"ok": True}}))
app.exitQgis()
"""
    import subprocess
    qgis_python = os.path.join(QGIS_PREFIX, "python")
    proc = subprocess.run([qgis_python, "-c", script], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not out_path.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"QML render failed:\n{proc.stderr or proc.stdout}")

    stem = Path(file.filename or "render").stem
    return FileResponse(path=out_path, media_type=mime, filename=f"{stem}_styled{out_ext}")
