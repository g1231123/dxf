"""
DXF Render Service
==================
A REST API that accepts DXF files and renders them to images using PyQGIS.

Endpoints
---------
GET  /                 -> simple HTML test page
GET  /health           -> health check
POST /render/dxf       -> upload DXF, get PNG/JPEG/PDF back
GET  /docs             -> auto-generated Swagger UI

Run
---
    python server.py
or
    uvicorn server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import io
import os
import sys
import uuid
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# QGIS bootstrap (must run BEFORE importing qgis.*)
# ---------------------------------------------------------------------------
def _bootstrap_qgis_paths() -> None:
    """Make `import qgis` work for common QGIS install layouts.

    On macOS (QGIS.app), Linux (system pkg) and Windows (OSGeo4W) PyQGIS is
    usually already importable when running with the bundled python. If you
    use a venv, set the env var `QGIS_PREFIX_PATH` and `QGIS_PYTHON_PATH`.
    """
    extra = os.environ.get("QGIS_PYTHON_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)

    # macOS QGIS.app default
    mac_app = "/Applications/QGIS.app/Contents/Resources/python"
    if os.path.isdir(mac_app) and mac_app not in sys.path:
        sys.path.insert(0, mac_app)


# Try to import QGIS, but make it optional (for AutoCAD-only mode on Windows)
QGIS_AVAILABLE = False
try:
    _bootstrap_qgis_paths()
    from qgis.core import (
        QgsApplication,
        QgsVectorLayer,
        QgsMapSettings,
        QgsMapRendererParallelJob,
        QgsRectangle,
        QgsCoordinateReferenceSystem,
        QgsPalLayerSettings,
        QgsTextFormat,
        QgsVectorLayerSimpleLabeling,
        QgsUnitTypes,
    )
    from qgis.PyQt.QtCore import QSize, QEventLoop
    from qgis.PyQt.QtGui import QColor, QFont, QImage
    QGIS_AVAILABLE = True
except ImportError as e:
    sys.stderr.write(
        "\n[WARNING] PyQGIS not available. QGIS features disabled. "
        "AutoCAD COM mode will still work.\n"
        f"Error: {e}\n\n"
    )

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse


# ---------------------------------------------------------------------------
# Qt 5 / Qt 6 compatibility shims
# ---------------------------------------------------------------------------
def _exec_loop(loop: "QEventLoop") -> int:
    """QEventLoop.exec_() in Qt5, QEventLoop.exec() in Qt6."""
    fn = getattr(loop, "exec", None) or getattr(loop, "exec_")
    return fn()


def _enable_flag(settings: "QgsMapSettings", flag_name: str) -> None:
    """Set a QgsMapSettings flag using whichever enum scope is available."""
    flag = getattr(getattr(QgsMapSettings, "Flag", QgsMapSettings), flag_name, None)
    if flag is None:
        flag = getattr(QgsMapSettings, flag_name, None)
    if flag is not None:
        settings.setFlag(flag, True)


def _detect_dxf_encoding(dxf_path: Path, sample_bytes: int = 1_048_576) -> Optional[str]:
    """Heuristically guess the encoding of a DXF file.

    Returns a Python encoding name (e.g. "gbk", "big5") or None if pure ASCII.
    Strategy:
      1. Read up to `sample_bytes` of the file.
      2. If only ASCII bytes, return None (no recoding needed).
      3. Try GB18030, Big5, Shift-JIS, EUC-KR, UTF-8, CP1252 in turn and pick
         the candidate that decodes cleanly with the lowest replacement-char
         count. GB18030 wins ties because it is a common CAD source encoding.
    """
    raw = dxf_path.read_bytes()[:sample_bytes]
    if not any(b >= 0x80 for b in raw):
        return None

    candidates = ["gb18030", "big5", "shift_jis", "euc_kr", "utf-8", "cp1252"]
    best: tuple[int, str] | None = None  # (score, encoding)
    for enc in candidates:
        try:
            decoded = raw.decode(enc, errors="replace")
        except LookupError:
            continue
        # Penalise replacement characters; reward CJK ideographs presence.
        repl = decoded.count("\uFFFD")
        cjk = sum(1 for ch in decoded if "\u4E00" <= ch <= "\u9FFF")
        # Lower score is better.
        score = repl * 10 - cjk
        if best is None or score < best[0]:
            best = (score, enc)

    if best is None:
        return None
    enc = best[1]
    # If the winner is cp1252, that effectively means "no CJK detected" —
    # leave the file alone so OGR decoding stays as-is.
    return None if enc == "cp1252" else enc


def _rewrite_codepage_header(text: str, target: str) -> tuple[str, bool]:
    """Replace the $DWGCODEPAGE value inside a DXF text dump."""
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip() == "$DWGCODEPAGE" and i + 2 < len(lines):
            lines[i + 2] = f"{target}\n"
            return "".join(lines), True
    return text, False


def _normalise_dxf_codepage(dxf_path: Path, *, force_encoding: Optional[str] = None) -> Optional[str]:
    """Patch a DXF file so OGR decodes its strings correctly.

    Two scenarios are handled:

    1. Source bytes are already in a single-byte / DBCS codepage (GBK, Big5,
       Shift-JIS, ...). We just rewrite ``$DWGCODEPAGE`` to match (e.g.
       ``ansi_936``).
    2. Source bytes are **UTF-8**. AutoCAD does not have a UTF-8 codepage value
       so we transcode the entire file from UTF-8 to GBK (broadest CJK
       coverage among AutoCAD codepages) and then set ``$DWGCODEPAGE`` to
       ``ansi_936``.

    Returns the codepage value written into the file (e.g. ``"ansi_936"``) or
    ``None`` if no patching was applied.
    """
    enc = (force_encoding or _detect_dxf_encoding(dxf_path) or "").lower()
    if not enc:
        return None

    # ------------------------------------------------------------------
    # UTF-8 source: transcode bytes -> GBK, then set codepage = ansi_936
    # ------------------------------------------------------------------
    if enc in {"utf-8", "utf8"}:
        try:
            text = dxf_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            LOG.warning("UTF-8 decode failed for %s, skipping transcode", dxf_path.name)
            return None

        target = "ansi_936"
        text, patched = _rewrite_codepage_header(text, target)
        # Encode to GBK; any character GBK can not represent becomes "?".
        new_bytes = text.encode("gbk", errors="replace")
        dxf_path.write_bytes(new_bytes)
        if patched:
            LOG.info("transcoded UTF-8 -> GBK and set $DWGCODEPAGE = %s in %s",
                     target, dxf_path.name)
        else:
            LOG.info("transcoded UTF-8 -> GBK in %s ($DWGCODEPAGE absent)",
                     dxf_path.name)
        return target

    # ------------------------------------------------------------------
    # Single-byte / DBCS source: only patch the $DWGCODEPAGE header.
    # ------------------------------------------------------------------
    target = DXF_CODEPAGE_MAP.get(enc)
    if target is None or target == "utf-8":
        return None

    try:
        text = dxf_path.read_text(encoding="latin-1")
    except UnicodeDecodeError:
        return None

    new_text, patched = _rewrite_codepage_header(text, target)
    if not patched:
        return None
    dxf_path.write_text(new_text, encoding="latin-1")
    LOG.info("patched $DWGCODEPAGE -> %s in %s", target, dxf_path.name)
    return target


def _pick_cjk_font() -> QFont:
    """Return a QFont that covers CJK glyphs if any system font is available.

    Works with both PyQt5 (QFontDatabase needs an instance) and PyQt6 (all
    methods are static and instantiation is rejected).
    """
    from qgis.PyQt.QtGui import QFontDatabase
    families_fn = getattr(QFontDatabase, "families", None)
    try:
        if callable(families_fn):
            families = set(QFontDatabase.families())
        else:
            families = set(QFontDatabase().families())
    except TypeError:
        families = set(QFontDatabase().families())
    for name in CJK_FONT_FALLBACKS:
        if name in families:
            return QFont(name)
    return QFont()


def _apply_dxf_text_labeling(layer: "QgsVectorLayer") -> bool:
    """If the layer carries a `Text` field (DXF TEXT/MTEXT entities), configure
    label-based rendering so the strings show up in the output image.

    Returns True if labeling was enabled.
    """
    field_names = {f.name() for f in layer.fields()}
    if "Text" not in field_names:
        return False

    pal = QgsPalLayerSettings()
    # Only label features whose Text attribute is non-empty so we do not stamp
    # labels on every random point/insert reference.
    pal.fieldName = "CASE WHEN \"Text\" IS NOT NULL AND \"Text\" != '' THEN \"Text\" END"
    pal.isExpression = True
    pal.enabled = True

    # Place the label centred on the point geometry that OGR emits for TEXT.
    placement = getattr(QgsPalLayerSettings, "Placement", QgsPalLayerSettings)
    pal.placement = getattr(placement, "OverPoint", getattr(QgsPalLayerSettings, "OverPoint", 0))

    fmt = QgsTextFormat()
    font = _pick_cjk_font()
    fmt.setFont(font)
    fmt.setSize(10)
    # Try to use point units; fall back gracefully across QGIS versions.
    try:
        unit = getattr(QgsUnitTypes, "RenderPoints", None)
        if unit is None:
            unit = QgsUnitTypes.RenderUnit.Points
        fmt.setSizeUnit(unit)
    except Exception:  # pragma: no cover - extremely defensive
        pass
    fmt.setColor(QColor("#222222"))
    pal.setFormat(fmt)

    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)
    return True


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG = logging.getLogger("dxf_render")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)

WORK_DIR = Path(tempfile.gettempdir()) / "dxf_render_service"
WORK_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
MIN_DIM, MAX_DIM = 64, 8192

DXF_SUBLAYERS = ("entities", "lines", "polygons", "points", "hatch", "insert")

# Map common encoding aliases / codepage names to AutoCAD $DWGCODEPAGE values.
# OGR DXF driver looks at $DWGCODEPAGE to decide how to decode strings.
DXF_CODEPAGE_MAP = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "gbk": "ansi_936",
    "gb2312": "ansi_936",
    "gb18030": "ansi_936",
    "cp936": "ansi_936",
    "ansi_936": "ansi_936",
    "big5": "ansi_950",
    "cp950": "ansi_950",
    "ansi_950": "ansi_950",
    "shift_jis": "ansi_932",
    "sjis": "ansi_932",
    "cp932": "ansi_932",
    "ansi_932": "ansi_932",
    "euc_kr": "ansi_949",
    "cp949": "ansi_949",
    "ansi_949": "ansi_949",
    "latin-1": "ansi_1252",
    "iso-8859-1": "ansi_1252",
    "cp1252": "ansi_1252",
    "ansi_1252": "ansi_1252",
}

# Fonts with broad CJK coverage we try in order (first one that loads wins).
CJK_FONT_FALLBACKS = (
    "PingFang SC",        # macOS default Simplified Chinese
    "Hiragino Sans GB",   # macOS legacy
    "STHeiti",
    "Microsoft YaHei",    # Windows
    "SimHei",
    "Noto Sans CJK SC",   # Linux
    "WenQuanYi Zen Hei",
    "Arial Unicode MS",
    "Helvetica",
)


# ---------------------------------------------------------------------------
# QGIS lifecycle
# ---------------------------------------------------------------------------
_qgs: Optional[QgsApplication] = None


def init_qgis() -> None:
    """Initialise a headless QGIS application (idempotent)."""
    global _qgs
    if not QGIS_AVAILABLE:
        LOG.info("QGIS not available, skipping initialization")
        return
    if _qgs is not None:
        return

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)

    _qgs = QgsApplication([], False)
    _qgs.initQgis()
    LOG.info("QGIS initialised, prefix=%s", QgsApplication.prefixPath())


def shutdown_qgis() -> None:
    global _qgs
    if not QGIS_AVAILABLE:
        return
    if _qgs is not None:
        _qgs.exitQgis()
        _qgs = None
        LOG.info("QGIS shut down")


# ---------------------------------------------------------------------------
# Rendering core
# ---------------------------------------------------------------------------
def _load_dxf_layers(dxf_path: Path) -> list[QgsVectorLayer]:
    """Open every geometry sub-layer that OGR exposes for the DXF."""
    layers: list[QgsVectorLayer] = []
    for sub in DXF_SUBLAYERS:
        uri = f"{dxf_path}|layername={sub}"
        layer = QgsVectorLayer(uri, sub, "ogr")
        if layer.isValid() and layer.featureCount() > 0:
            layers.append(layer)
            LOG.info("loaded sublayer '%s' (%d features)", sub, layer.featureCount())

    # fallback: open the file as a whole
    if not layers:
        layer = QgsVectorLayer(str(dxf_path), "dxf", "ogr")
        if layer.isValid() and layer.featureCount() > 0:
            layers.append(layer)

    # Enable labeling for any layer that exposes the Text attribute
    # (DXF TEXT / MTEXT entities are point geometry + Text field via OGR).
    for lyr in layers:
        if _apply_dxf_text_labeling(lyr):
            LOG.info("labeling enabled on '%s' (Text field)", lyr.name())

    return layers


def _combined_extent(layers: list[QgsVectorLayer]) -> QgsRectangle:
    extent = QgsRectangle()
    extent.setMinimal()
    for lyr in layers:
        extent.combineExtentWith(lyr.extent())
    if extent.isEmpty():
        raise ValueError("Empty extent — DXF contains no geometry")
    extent.scale(1.05)  # 5% padding
    return extent


def _render_to_image(
    layers: list[QgsVectorLayer],
    width: int,
    height: int,
    bg: QColor,
    dest_crs: Optional[QgsCoordinateReferenceSystem] = None,
) -> QImage:
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setBackgroundColor(bg)
    settings.setOutputSize(QSize(width, height))
    settings.setExtent(_combined_extent(layers))
    if dest_crs and dest_crs.isValid():
        settings.setDestinationCrs(dest_crs)
    _enable_flag(settings, "Antialiasing")
    _enable_flag(settings, "UseAdvancedEffects")
    _enable_flag(settings, "DrawLabeling")

    job = QgsMapRendererParallelJob(settings)
    loop = QEventLoop()
    job.finished.connect(loop.quit)
    job.start()
    _exec_loop(loop)
    return job.renderedImage()


def render_dxf(
    dxf_path: Path,
    output_path: Path,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fmt: str = "png",
    background: str = "#ffffff",
    crs: Optional[str] = None,
) -> dict:
    """Render a DXF file to PNG/JPEG/PDF. Returns a small metadata dict."""
    layers = _load_dxf_layers(dxf_path)
    if not layers:
        raise ValueError("No valid geometry layers found in DXF")

    bg = QColor(background)
    if not bg.isValid():
        bg = QColor("#ffffff")

    dest_crs = QgsCoordinateReferenceSystem(crs) if crs else None

    fmt = fmt.lower()
    if fmt in {"png", "jpg", "jpeg"}:
        img = _render_to_image(layers, width, height, bg, dest_crs)
        img.save(str(output_path), "JPEG" if fmt in {"jpg", "jpeg"} else "PNG")
    elif fmt == "pdf":
        # PDF output is rendered to a high-res image first, then embedded.
        # This avoids cross-version QPrinter / QPageSize enum differences and
        # gives a predictable result for vector-light DXF files.
        img = _render_to_image(layers, width, height, bg, dest_crs)
        img.save(str(output_path), "PDF")
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    extent = _combined_extent(layers)
    return {
        "format": fmt,
        "size": [width, height],
        "feature_count": sum(l.featureCount() for l in layers),
        "sublayers": [l.name() for l in layers],
        "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DXF Render Service",
    description="Render DXF files to PNG/JPEG/PDF via PyQGIS.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add specific routes for HTML test pages (after API routes)

# Mount analysis / processing routes
from qgis_analysis import router as analysis_router  # noqa: E402
app.include_router(analysis_router, tags=["Analysis & Processing"])

# Mount parametric 2D renderer routes
from qgis_renderer import router as renderer_router  # noqa: E402
app.include_router(renderer_router, tags=["2D Parametric Renderer"])

# Mount GeoJSON data API for WebGL frontend
from qgis_geojson import router as geojson_router  # noqa: E402
app.include_router(geojson_router, tags=["GeoJSON Data API"])

# Mount WebSocket real-time render server (Netty-style event-driven)
from ws_server import router as ws_router  # noqa: E402
app.include_router(ws_router, tags=["WebSocket Render"])

# Mount map interaction (session, pan, zoom, identify, measure, bookmark)
from qgis_map import router as map_router  # noqa: E402
app.include_router(map_router, tags=["Map Interaction"])

# Mount Processing full algorithm API
from qgis_processing import router as processing_router  # noqa: E402
app.include_router(processing_router, tags=["Processing Algorithms"])

# Mount symbol library and basemap service
from qgis_symbols import router as symbols_router  # noqa: E402
app.include_router(symbols_router, tags=["Symbols & Basemap"])

# Mount DXF template service (upload, parse, store to MinIO & MySQL)
from dxf_template_service import router as template_router  # noqa: E402
app.include_router(template_router, tags=["DXF Template"])

# Mount IP whitelist management service
from ip_whitelist_manager import router as ip_whitelist_router  # noqa: E402
app.include_router(ip_whitelist_router, tags=["IP Whitelist Management"])

# Mount DXF frontend API (simplified, frontend-driven)
from dxf_frontend_api import router as dxf_frontend_router  # noqa: E402
app.include_router(dxf_frontend_router, tags=["DXF Template V2 (Frontend)"])

# Mount DXF simple upload (no parsing, just upload)
from dxf_simple_upload import router as dxf_simple_router  # noqa: E402
app.include_router(dxf_simple_router, tags=["DXF Template Simple Upload"])

# Mount DXF to Excel export API
from dxf_to_excel import router as dxf_to_excel_router  # noqa: E402
app.include_router(dxf_to_excel_router, tags=["DXF to Excel"])

# Mount DXF on-demand API (extract params on-demand, no storage)
from dxf_ondemand_api import router as dxf_ondemand_router  # noqa: E402
app.include_router(dxf_ondemand_router, tags=["DXF On-Demand"])

# Mount DXF image API (click on image to edit)
from dxf_image_api import router as dxf_image_router  # noqa: E402
app.include_router(dxf_image_router, tags=["DXF Image Editor"])

# Mount DXF convert API (DXF <-> TXT)
from dxf_convert_api import router as dxf_convert_router  # noqa: E402
app.include_router(dxf_convert_router, tags=["DXF Convert"])


@app.on_event("startup")
def _on_startup() -> None:
    init_qgis()


@app.on_event("shutdown")
def _on_shutdown() -> None:
    shutdown_qgis()


def _check_autocad_available() -> bool:
    """Check if AutoCAD COM is available (Windows only)."""
    if sys.platform != "win32":
        return False
    try:
        import win32com.client
        acad = win32com.client.Dispatch("AutoCAD.Application")
        return acad is not None
    except Exception:
        return False

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "qgis_available": QGIS_AVAILABLE,
        "qgis_prefix": QgsApplication.prefixPath() if QGIS_AVAILABLE and _qgs else None,
        "autocad_available": _check_autocad_available(),
        "work_dir": str(WORK_DIR),
        "dwg_converter": _detect_dwg_converter(),
    }


# ---------------------------------------------------------------------------
# DWG → DXF conversion
# ---------------------------------------------------------------------------
def _detect_dwg_converter() -> Optional[dict]:
    """Find an installed DWG -> DXF converter. Returns a dict describing it."""
    candidates = [
        # LibreDWG (brew install libredwg).
        ("libredwg", shutil.which("dwg2dxf"), ["{input}", "-o", "{output}"]),
        # Teigha / ODA File Converter CLI — path varies.
        ("oda", shutil.which("ODAFileConverter"), None),
        # Graebert / other
    ]
    for name, binpath, argv in candidates:
        if binpath:
            return {"name": name, "path": binpath, "argv": argv}
    # ODA typically installs as a Mac app bundle
    app_bundle = Path("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")
    if app_bundle.exists():
        return {"name": "oda", "path": str(app_bundle), "argv": None}
    return None


def _run_dwg_to_dxf(dwg_path: Path, dxf_path: Path) -> None:
    """Convert DWG → DXF, raising HTTPException with a helpful message if no
    converter is available. The file layout is flexible:
      - LibreDWG's dwg2dxf accepts a single input and writes next to it.
      - ODAFileConverter takes input/output DIRECTORIES and a filter."""
    conv = _detect_dwg_converter()
    if not conv:
        raise HTTPException(
            501,
            "No DWG converter installed. "
            "Install one of: `brew install libredwg` (simplest), "
            "or ODA File Converter from https://www.opendesign.com/guestfiles/oda_file_converter",
        )

    if conv["name"] == "libredwg":
        # dwg2dxf writes <input>.dxf alongside the DWG by default.
        cmd = [conv["path"], str(dwg_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        produced = dwg_path.with_suffix(".dxf")
        if proc.returncode != 0 or not produced.exists():
            raise HTTPException(500, f"dwg2dxf failed: {proc.stderr or proc.stdout}")
        if produced != dxf_path:
            shutil.move(str(produced), str(dxf_path))
        return

    if conv["name"] == "oda":
        # ODAFileConverter <in_dir> <out_dir> <out_version> <out_fmt:DXF|DWG> <recurse:0|1> <audit:0|1> [filter]
        in_dir = dwg_path.parent
        out_dir = dxf_path.parent / "_oda_out"
        out_dir.mkdir(exist_ok=True)
        cmd = [
            conv["path"],
            str(in_dir),
            str(out_dir),
            "ACAD2018",
            "DXF",
            "0",
            "1",
            dwg_path.name,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        produced = out_dir / (dwg_path.stem + ".dxf")
        if not produced.exists():
            raise HTTPException(
                500,
                f"ODA conversion produced no output. stderr={proc.stderr!r} stdout={proc.stdout!r}",
            )
        shutil.move(str(produced), str(dxf_path))
        shutil.rmtree(out_dir, ignore_errors=True)
        return

    raise HTTPException(500, f"Unknown converter backend: {conv['name']}")


# ---------------------------------------------------------------------------
# Edit endpoint  (apply edit journal to a DXF, optionally re-export to DWG)
# ---------------------------------------------------------------------------
def _apply_edits_with_ezdxf(dxf_in: Path, dxf_out: Path, edits: list[dict]) -> dict:
    """Apply a list of edit ops to a DXF file using ezdxf.

    Supported ops:
      - {"op": "move",   "handle": "...", "dx": float, "dy": float}
      - {"op": "delete", "handle": "..."}
      - {"op": "text",   "handle": "...", "value": str}

    Returns a small summary dict for logging.
    """
    try:
        import ezdxf
    except ImportError as e:
        raise HTTPException(
            500,
            "ezdxf not installed in the QGIS Python — `pip install --user ezdxf` "
            "in the environment that runs server.py.",
        ) from e

    doc = ezdxf.readfile(str(dxf_in))
    msp = doc.modelspace()

    # Build a single index over modelspace + every block definition so we can
    # locate entities by handle no matter where they live.
    by_handle: dict[str, "ezdxf.entities.DXFEntity"] = {}
    for layout in [msp, *(b for b in doc.blocks)]:
        for ent in layout:
            try:
                h = ent.dxf.handle
                if h:
                    by_handle[h] = ent
            except Exception:
                # Entities without handles (tables in older DXF) are not addressable by edit ops
                pass

    summary = {"moved": 0, "deleted": 0, "edited_text": 0, "skipped": 0}
    for op in edits or []:
        handle = op.get("handle")
        kind = op.get("op")
        ent = by_handle.get(handle) if handle else None
        if ent is None:
            summary["skipped"] += 1
            continue
        try:
            if kind == "move":
                dx = float(op.get("dx", 0))
                dy = float(op.get("dy", 0))
                if hasattr(ent, "translate"):
                    ent.translate(dx, dy, 0)
                else:
                    # Fallback for entities without translate(): adjust common
                    # position attributes manually.
                    for attr in ("insert", "center", "start", "end"):
                        if ent.dxf.is_supported(attr):
                            v = getattr(ent.dxf, attr)
                            ent.dxf.set(attr, (v[0] + dx, v[1] + dy, v[2] if len(v) > 2 else 0))
                summary["moved"] += 1
            elif kind == "delete":
                ent.destroy() if hasattr(ent, "destroy") else msp.delete_entity(ent)
                summary["deleted"] += 1
            elif kind == "text":
                if ent.dxftype() in ("TEXT", "MTEXT"):
                    new_value = str(op.get("value", ""))
                    if ent.dxftype() == "MTEXT":
                        ent.text = new_value
                    else:
                        ent.dxf.text = new_value
                    summary["edited_text"] += 1
                else:
                    summary["skipped"] += 1
            else:
                summary["skipped"] += 1
        except Exception as e:
            LOG.warning("edit op %s on %s failed: %s", kind, handle, e)
            summary["skipped"] += 1

    # Audit and fix any missing handles (critical for older DXF R12 files)
    try:
        auditor = doc.audit()
        if auditor.has_errors:
            LOG.info("Audit fixed %d errors in DXF", len(auditor.errors))
    except Exception as e:
        LOG.warning("DXF audit warning: %s", e)

    doc.saveas(str(dxf_out))
    return summary


@app.post("/edit/dxf")
async def edit_dxf_endpoint(
    file: UploadFile = File(..., description=".dxf file"),
    edits: str = Form("[]", description="JSON list of edit ops"),
    format: str = Form("dxf", description="dxf | dwg"),
):
    """Apply edits to an uploaded DXF and return the result (optionally as DWG)."""
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    lower = file.filename.lower()
    if not (lower.endswith(".dxf") or lower.endswith(".dwg")):
        raise HTTPException(400, "File must be .dxf or .dwg")

    import json
    try:
        edit_ops = json.loads(edits) if edits else []
        if not isinstance(edit_ops, list):
            raise ValueError("edits must be a JSON array")
    except Exception as e:
        raise HTTPException(400, f"Invalid edits payload: {e}") from e

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    src_path = job_dir / ("input" + Path(lower).suffix)

    written = 0
    with open(src_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, "File too large")
            out.write(chunk)

    # If we got a DWG, convert to DXF first.
    if lower.endswith(".dwg"):
        dxf_in = job_dir / "input.dxf"
        try:
            _run_dwg_to_dxf(src_path, dxf_in)
        except HTTPException:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
    else:
        dxf_in = src_path

    # Patch encoding so ezdxf reads CJK strings correctly before editing.
    _normalise_dxf_codepage(dxf_in)

    dxf_out = job_dir / "output.dxf"
    try:
        summary = _apply_edits_with_ezdxf(dxf_in, dxf_out, edit_ops)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        LOG.exception("edit failed")
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"Edit failed: {e}") from e

    LOG.info("edit done job=%s edits=%d summary=%s", job_id, len(edit_ops), summary)

    target_ext = format.lower()
    if target_ext == "dwg":
        # DWG export requires a DXF -> DWG converter.  LibreDWG's `dwg2dxf`
        # is one-way; for full DXF -> DWG round-trip, ODA File Converter is
        # the reliable option.
        conv = _detect_dwg_converter()
        if not conv or conv["name"] != "oda":
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(
                501,
                "DWG output requires ODA File Converter. "
                "Install from https://www.opendesign.com/guestfiles/oda_file_converter "
                "or use 'dxf' format instead.",
            )
        dwg_out = job_dir / "output.dwg"
        # Reuse the converter logic in reverse direction
        in_dir = dxf_out.parent
        out_dir = job_dir / "_oda_dwg"
        out_dir.mkdir()
        cmd = [
            conv["path"],
            str(in_dir),
            str(out_dir),
            "ACAD2018",
            "DWG",
            "0",
            "1",
            dxf_out.name,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        produced = out_dir / (dxf_out.stem + ".dwg")
        if not produced.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(500, f"DXF->DWG failed: {proc.stderr or proc.stdout}")
        shutil.move(str(produced), str(dwg_out))
        return FileResponse(
            path=dwg_out,
            media_type="application/acad",
            filename=Path(file.filename).stem + ".edited.dwg",
            headers={"X-Edit-Summary": str(summary)},
        )

    return FileResponse(
        path=dxf_out,
        media_type="application/dxf",
        filename=Path(file.filename).stem + ".edited.dxf",
        headers={"X-Edit-Summary": str(summary)},
    )


@app.post("/convert/dwg")
async def convert_dwg_endpoint(file: UploadFile = File(..., description=".dwg file")):
    """Convert an uploaded DWG to DXF and return the DXF bytes."""
    if not file.filename or not file.filename.lower().endswith(".dwg"):
        raise HTTPException(400, "File must have .dwg extension")

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    dwg_path = job_dir / "input.dwg"
    dxf_path = job_dir / "output.dxf"

    written = 0
    with open(dwg_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, "File too large")
            out.write(chunk)

    try:
        _run_dwg_to_dxf(dwg_path, dxf_path)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        LOG.exception("dwg conversion failed")
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"DWG conversion failed: {e}") from e

    return FileResponse(
        path=dxf_path,
        media_type="application/dxf",
        filename=Path(file.filename).stem + ".dxf",
    )


# ---------------------------------------------------------------------------
# PostGIS import helpers
# ---------------------------------------------------------------------------
OGR2OGR_PATH = shutil.which("ogr2ogr") or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogr2ogr"

SUPPORTED_IMPORT_EXTS = {".dxf", ".shp", ".geojson", ".json", ".kml", ".kmz", ".gpkg", ".csv", ".gdb"}


def _run_ogr2ogr_import(
    src: Path,
    pg_dsn: str,
    table_name: str,
    srs: str = "EPSG:4326",
    overwrite: bool = True,
) -> str:
    """Import a spatial file into PostGIS using ogr2ogr. Returns stdout."""
    if not OGR2OGR_PATH or not Path(OGR2OGR_PATH).exists():
        raise HTTPException(500, "ogr2ogr not found. Add QGIS MacOS dir to PATH.")

    cmd = [
        OGR2OGR_PATH,
        "-f", "PostgreSQL",
        f"PG:{pg_dsn}",
        str(src),
        "-nln", table_name,
        "-a_srs", srs,
        "-progress",
    ]
    if overwrite:
        cmd.append("-overwrite")

    # For DXF: flatten all sub-layers into a single table
    if src.suffix.lower() == ".dxf":
        cmd += ["-nlt", "PROMOTE_TO_MULTI", "-skipfailures"]

    # For CSV: auto-detect lon/lat columns
    if src.suffix.lower() == ".csv":
        cmd += [
            "-oo", "X_POSSIBLE_NAMES=lon,longitude,x,经度,lng",
            "-oo", "Y_POSSIBLE_NAMES=lat,latitude,y,纬度",
        ]

    LOG.info("ogr2ogr import: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise HTTPException(500, f"ogr2ogr failed:\n{proc.stderr or proc.stdout}")
    return proc.stdout or "OK"


@app.post("/import/postgis")
async def import_to_postgis(
    file: UploadFile = File(..., description="空间数据文件 (.dxf/.shp/.geojson/.kml/.gpkg/.csv)"),
    host: str = Form("localhost", description="PostgreSQL 主机"),
    port: int = Form(5432, description="PostgreSQL 端口"),
    dbname: str = Form(..., description="数据库名"),
    user: str = Form("postgres", description="用户名"),
    password: str = Form("", description="密码"),
    table: str = Form("", description="目标表名（留空则用文件名）"),
    srs: str = Form("EPSG:4326", description="坐标系，例如 EPSG:4326 或 EPSG:3857"),
    overwrite: bool = Form(True, description="是否覆盖已有表"),
):
    """
    把上传的空间数据文件导入到 PostgreSQL/PostGIS。
    支持格式：DXF, Shapefile, GeoJSON, KML, GeoPackage, CSV（含坐标列）
    """
    if not file.filename:
        raise HTTPException(400, "Missing filename")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_IMPORT_EXTS:
        raise HTTPException(
            400,
            f"不支持的格式 {suffix}，支持: {', '.join(sorted(SUPPORTED_IMPORT_EXTS))}"
        )

    table_name = (table.strip() or Path(file.filename).stem).replace("-", "_").replace(" ", "_")

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    src_path = job_dir / file.filename

    written = 0
    with open(src_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, "File too large")
            out.write(chunk)

    # Build PG DSN — avoid leaking password in logs
    pg_dsn = f"host={host} port={port} dbname={dbname} user={user}"
    if password:
        pg_dsn += f" password={password}"

    try:
        output = _run_ogr2ogr_import(src_path, pg_dsn, table_name, srs, overwrite)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"Import failed: {e}") from e
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    LOG.info("import done table=%s rows_approx=%s", table_name, output[:200])
    return {
        "status": "ok",
        "table": table_name,
        "database": dbname,
        "host": host,
        "srs": srs,
        "message": f"成功导入到 {dbname}.public.{table_name}",
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = Path(__file__).with_name("index.html")
    if html.exists():
        return html.read_text(encoding="utf-8")
    return "<h1>DXF Render Service</h1><p>POST a .dxf to /render/dxf</p>"


@app.post("/render/dxf")
async def render_dxf_endpoint(
    file: UploadFile = File(..., description=".dxf file"),
    width: int = Form(DEFAULT_WIDTH),
    height: int = Form(DEFAULT_HEIGHT),
    fmt: str = Form("png", description="png | jpeg | pdf"),
    background: str = Form("#ffffff"),
    crs: Optional[str] = Form(None, description="EPSG:xxxx, optional"),
    encoding: str = Form(
        "auto",
        description="auto | gbk | big5 | shift_jis | utf-8 | cp1252 | none",
    ),
):
    if not QGIS_AVAILABLE:
        raise HTTPException(503, "QGIS not available. Install QGIS or use AutoCAD COM mode via ws_server.")
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(400, "File must have .dxf extension")

    width = max(MIN_DIM, min(width, MAX_DIM))
    height = max(MIN_DIM, min(height, MAX_DIM))

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    dxf_path = job_dir / "input.dxf"

    # stream upload to disk with size cap
    written = 0
    with open(dxf_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, f"File too large (>{MAX_UPLOAD_BYTES} bytes)")
            out.write(chunk)

    # Patch $DWGCODEPAGE if requested / detected — this is what fixes the
    # classic "Chinese DXF renders as 乱码" problem.
    enc_input = (encoding or "auto").lower()
    patched_codepage: Optional[str] = None
    if enc_input not in {"none", ""}:
        force = None if enc_input == "auto" else enc_input
        patched_codepage = _normalise_dxf_codepage(dxf_path, force_encoding=force)

    out_ext = "pdf" if fmt.lower() == "pdf" else ("jpg" if fmt.lower() in {"jpg", "jpeg"} else "png")
    out_path = job_dir / f"render.{out_ext}"

    try:
        meta = render_dxf(
            dxf_path,
            out_path,
            width=width,
            height=height,
            fmt=fmt,
            background=background,
            crs=crs,
        )
    except Exception as e:
        LOG.exception("render failed")
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"Render failed: {e}") from e

    if patched_codepage:
        meta["patched_codepage"] = patched_codepage

    media = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "pdf": "application/pdf",
    }[out_ext]

    LOG.info("render done job=%s meta=%s", job_id, meta)

    response = FileResponse(
        path=out_path,
        media_type=media,
        filename=f"{Path(file.filename).stem}.{out_ext}",
        headers={"X-Render-Meta": str(meta)},
    )
    return response


@app.post("/render/dxf/meta")
async def render_dxf_meta(file: UploadFile = File(...)) -> JSONResponse:
    """Quick inspection: count features and report extent without rendering."""
    if not QGIS_AVAILABLE:
        raise HTTPException(503, "QGIS not available.")
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(400, "File must have .dxf extension")

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()
    dxf_path = job_dir / "input.dxf"
    with open(dxf_path, "wb") as out:
        out.write(await file.read())

    try:
        layers = _load_dxf_layers(dxf_path)
        if not layers:
            raise HTTPException(400, "No valid geometry layers in DXF")
        extent = _combined_extent(layers)
        return JSONResponse(
            {
                "feature_count": sum(l.featureCount() for l in layers),
                "sublayers": [
                    {"name": l.name(), "features": l.featureCount(), "type": l.geometryType()}
                    for l in layers
                ],
                "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
            }
        )
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Static HTML files (test pages) - using API routes instead of StaticFiles
# ---------------------------------------------------------------------------
from fastapi.responses import FileResponse, RedirectResponse

STATIC_DIR = Path(__file__).parent.absolute()

@app.get("/ui/{filename:path}")
def serve_static(filename: str):
    """Serve HTML and other static files"""
    file_path = STATIC_DIR / filename
    # Security check: ensure file is within STATIC_DIR
    if not str(file_path.resolve()).startswith(str(STATIC_DIR.resolve())):
        raise HTTPException(403, "Access denied")
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    raise HTTPException(404, f"File not found: {filename}")

@app.get("/")
def root_redirect():
    """Redirect root to test page"""
    return RedirectResponse(url="/ui/test_ai_draw.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,
        ws="websockets",
        log_level="info",
    )
