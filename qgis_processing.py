"""
Processing 全算法 API
=====================
通过统一接口调用 QGIS Processing 工具箱中所有算法（native/gdal/grass7/saga 等）。

路由前缀: /processing
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/processing", tags=["Processing Algorithms"])

WORK_DIR   = Path(tempfile.gettempdir()) / "qgis_processing_jobs"
STORE_DIR  = Path("/tmp/qgis_geojson_store")
WORK_DIR.mkdir(exist_ok=True)

QGIS_PYTHON = (
    os.environ.get("QGIS_PYTHON") or
    "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/python"
)
QGIS_PREFIX = os.environ.get(
    "QGIS_PREFIX_PATH",
    "/Applications/QGIS-final-4_0_2.app/Contents/MacOS",
)
OGR2OGR = shutil.which("ogr2ogr") or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogr2ogr"

OUTPUT_FORMATS = {"geojson", "gpkg", "shp", "dxf", "csv", "kml"}

# 内存任务队列 (job_id -> job_info)
_JOBS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class RunAlgorithmRequest(BaseModel):
    parameters: dict[str, Any] = Field(
        ...,
        description=(
            "算法参数字典，键名与算法参数名一致（大写）。"
            "图层参数值用 {\"file_id\": \"xxx\"} 引用已上传文件；"
            "OUTPUT 填 \"memory\" 表示结果直接返回。"
        )
    )
    output_format: str = Field(
        "geojson",
        description="结果文件格式：geojson / gpkg / shp / dxf / csv / kml"
    )
    async_run: bool = Field(
        False,
        description="是否异步执行：true 立即返回 job_id，false 等待结果"
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _resolve_layer_param(value: Any, job_dir: Path) -> str:
    """把 {\"file_id\": \"xxx\"} 解析为实际文件路径。"""
    if isinstance(value, dict) and "file_id" in value:
        fid = value["file_id"]
        store = STORE_DIR / fid
        if not store.exists():
            raise HTTPException(404, detail={"code": "FILE_NOT_FOUND",
                                              "msg": f"file_id {fid!r} 不存在"})
        # 优先用原始文件（DXF 等），其次用 GeoJSON
        for f in store.iterdir():
            if f.suffix.lower() not in (".json", ".geojson") and f.is_file():
                return str(f)
        gj = store / "data.geojson"
        if gj.exists():
            return str(gj)
        raise HTTPException(404, detail={"code": "FILE_NOT_FOUND",
                                          "msg": f"file_id {fid!r} 无可用数据文件"})
    return value


def _build_processing_script(algorithm_id: str, parameters: dict,
                              output_path: str, output_format: str) -> str:
    """生成 PyQGIS standalone 脚本执行 Processing 算法。"""
    # 序列化参数，特殊处理图层路径（已由 _resolve_layer_param 转换）
    params_repr = json.dumps(parameters, ensure_ascii=False)
    return f"""
import sys, os, json, traceback
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
try:
    params = {params_repr}
    # OUTPUT 替换为实际输出路径
    if "OUTPUT" in params and params["OUTPUT"] == "memory":
        params["OUTPUT"] = {json.dumps(output_path)}
    elif "OUTPUT" not in params:
        params["OUTPUT"] = {json.dumps(output_path)}
    result = processing.run({json.dumps(algorithm_id)}, params)
    out_file = result.get("OUTPUT", {json.dumps(output_path)})
    print(json.dumps({{"ok": True, "output": out_file}}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": traceback.format_exc()}}))
app.exitQgis()
"""


def _run_job(job_id: str, algorithm_id: str, parameters: dict,
             output_format: str, job_dir: Path) -> None:
    """同步执行 Processing 算法，更新 job 状态。"""
    _JOBS[job_id]["status"] = "running"
    _JOBS[job_id]["started_at"] = time.time()
    out_ext = {"geojson": ".geojson", "gpkg": ".gpkg", "shp": ".shp",
               "dxf": ".dxf", "csv": ".csv", "kml": ".kml"}.get(output_format, ".geojson")
    out_path = str(job_dir / f"result{out_ext}")

    # 解析图层参数
    resolved = {}
    for k, v in parameters.items():
        try:
            resolved[k] = _resolve_layer_param(v, job_dir)
        except HTTPException as e:
            _JOBS[job_id]["status"] = "failed"
            _JOBS[job_id]["error"] = e.detail
            return

    script = _build_processing_script(algorithm_id, resolved, out_path, output_format)
    t0 = time.monotonic()
    proc = subprocess.run(
        [QGIS_PYTHON, "-c", script],
        capture_output=True, text=True, timeout=600,
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    try:
        last_line = [l for l in proc.stdout.strip().splitlines() if l.strip()][-1]
        result_json = json.loads(last_line)
    except Exception:
        result_json = {"ok": False, "error": proc.stderr or proc.stdout}

    if not result_json.get("ok"):
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["error"] = result_json.get("error", "未知错误")
        return

    # 保存结果到 store
    result_file = Path(result_json.get("output", out_path))
    if result_file.exists():
        file_id = uuid.uuid4().hex
        dest_dir = STORE_DIR / file_id
        dest_dir.mkdir()
        dest_file = dest_dir / result_file.name
        shutil.copy2(result_file, dest_file)
        # 若结果是 GeoJSON，也存 data.geojson
        if result_file.suffix.lower() in (".geojson", ".json"):
            shutil.copy2(result_file, dest_dir / "data.geojson")
        elif OGR2OGR:
            subprocess.run([OGR2OGR, "-f", "GeoJSON",
                            str(dest_dir / "data.geojson"), str(dest_file),
                            "-skipfailures"], capture_output=True)
        # 写 meta
        meta = {"file_id": file_id, "original_name": result_file.name,
                "source_algorithm": algorithm_id, "elapsed_ms": elapsed_ms}
        (dest_dir / "meta.json").write_text(json.dumps(meta))
        _JOBS[job_id].update({
            "status": "done",
            "result_file_id": file_id,
            "elapsed_ms": elapsed_ms,
            "download_url": f"/data/{file_id}/download",
            "finished_at": time.time(),
        })
    else:
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["error"] = f"算法执行完毕但输出文件不存在: {out_path}"


# ---------------------------------------------------------------------------
# 算法列表 / 详情
# ---------------------------------------------------------------------------
@router.get("/algorithms", summary="列出所有可用算法")
def list_algorithms(
    group:     Optional[str] = Query(None, description="按提供商过滤：native / gdal / grass7 / saga"),
    search:    Optional[str] = Query(None, description="关键词搜索算法名或描述"),
    page:      int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数，最大 200"),
):
    """
    列出 QGIS Processing 工具箱中所有可用算法。
    通过 group 过滤提供商，通过 search 搜索名称。
    返回的 parameters 字段描述每个算法的输入参数。
    """
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
algos = []
for a in QgsApplication.processingRegistry().algorithms():
    provider = a.providerId()
    if {json.dumps(group or "")} and provider != {json.dumps(group or "")}:
        continue
    name = a.displayName()
    if {json.dumps(search or "")} and {json.dumps((search or "").lower())} not in name.lower() and {json.dumps((search or "").lower())} not in a.id().lower():
        continue
    params = []
    for p in a.parameterDefinitions():
        params.append({{
            "name": p.name(),
            "description": p.description(),
            "type": type(p).__name__,
            "optional": bool(p.flags() & p.FlagOptional),
        }})
    algos.append({{
        "id": a.id(),
        "name": name,
        "group": a.group(),
        "provider": provider,
        "description": a.shortDescription() or "",
        "parameters": params,
    }})
print(json.dumps({{"algorithms": algos}}))
app.exitQgis()
"""
    try:
        proc = subprocess.run([QGIS_PYTHON, "-c", script],
                              capture_output=True, text=True, timeout=60)
        lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
        data = json.loads(lines[-1]) if lines else {"algorithms": []}
    except Exception as e:
        raise HTTPException(500, detail={"code": "ANALYSIS_FAILED", "msg": str(e)})

    all_algos = data.get("algorithms", [])
    total = len(all_algos)
    start = (page - 1) * page_size
    return {
        "total":      total,           # 满足条件的算法总数
        "page":       page,            # 当前页码
        "page_size":  page_size,       # 每页条数
        "algorithms": all_algos[start: start + page_size],
    }


@router.get("/algorithm/{algorithm_id:path}", summary="获取算法详细参数")
def get_algorithm(algorithm_id: str):
    """
    获取单个 Processing 算法的完整参数说明。
    algorithm_id 格式为 provider:name，如 native:buffer、gdal:rasterize。
    """
    script = f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import QgsApplication
app = QgsApplication([], False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()
import processing
from processing.core.Processing import Processing
Processing.initialize()
a = QgsApplication.processingRegistry().algorithmById({json.dumps(algorithm_id)})
if not a:
    print(json.dumps({{"error": "not_found"}}))
else:
    params = []
    for p in a.parameterDefinitions():
        params.append({{
            "name": p.name(),
            "description": p.description(),
            "type": type(p).__name__,
            "optional": bool(p.flags() & p.FlagOptional),
            "default": str(p.defaultValue()) if p.defaultValue() is not None else None,
        }})
    outputs = []
    for o in a.outputDefinitions():
        outputs.append({{"name": o.name(), "description": o.description(), "type": type(o).__name__}})
    print(json.dumps({{
        "id": a.id(), "name": a.displayName(),
        "group": a.group(), "provider": a.providerId(),
        "description": a.shortHelpString() or a.shortDescription() or "",
        "parameters": params, "outputs": outputs,
    }}))
app.exitQgis()
"""
    try:
        proc = subprocess.run([QGIS_PYTHON, "-c", script],
                              capture_output=True, text=True, timeout=60)
        lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
        data = json.loads(lines[-1]) if lines else {}
    except Exception as e:
        raise HTTPException(500, detail={"code": "ANALYSIS_FAILED", "msg": str(e)})

    if data.get("error") == "not_found":
        raise HTTPException(404, detail={"code": "ALGO_NOT_FOUND",
                                          "msg": f"算法 {algorithm_id!r} 不存在"})
    return data


# ---------------------------------------------------------------------------
# 执行算法（同步 / 异步）
# ---------------------------------------------------------------------------
@router.post("/run/{algorithm_id:path}", summary="执行 Processing 算法")
def run_algorithm(algorithm_id: str, req: RunAlgorithmRequest):
    """
    执行任意 QGIS Processing 算法。

    - 图层参数用 {\"file_id\": \"xxx\"} 引用已上传的文件
    - OUTPUT 填 \"memory\" 或省略，结果自动保存并返回新的 file_id
    - async_run=true 时立即返回 job_id，通过 GET /processing/jobs/{job_id} 轮询进度
    - async_run=false（默认）时阻塞等待结果（适合快速算法）
    """
    if req.output_format not in OUTPUT_FORMATS:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS",
                                          "msg": f"output_format 必须是 {OUTPUT_FORMATS}"})
    job_id  = "job_" + uuid.uuid4().hex[:12]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()

    _JOBS[job_id] = {
        "job_id":       job_id,
        "algorithm_id": algorithm_id,   # 算法 ID，格式 provider:name
        "status":       "queued",       # queued / running / done / failed / cancelled
        "progress":     0,
        "parameters":   req.parameters,
        "output_format": req.output_format,
        "created_at":   time.time(),
        "started_at":   None,
        "finished_at":  None,
        "result_file_id": None,
        "download_url": None,
        "error":        None,
        "elapsed_ms":   None,
    }

    if req.async_run:
        import threading
        t = threading.Thread(target=_run_job, daemon=True,
                             args=(job_id, algorithm_id, req.parameters,
                                   req.output_format, job_dir))
        t.start()
        return {
            "job_id":       job_id,
            "algorithm_id": algorithm_id,
            "status":       "queued",
            "poll_url":     f"/processing/jobs/{job_id}",
        }
    else:
        _run_job(job_id, algorithm_id, req.parameters, req.output_format, job_dir)
        job = _JOBS[job_id]
        if job["status"] == "failed":
            raise HTTPException(500, detail={"code": "ANALYSIS_FAILED",
                                              "msg": job.get("error", "算法执行失败")})
        return {
            "job_id":         job_id,
            "algorithm_id":   algorithm_id,
            "status":         "done",
            "result_file_id": job["result_file_id"],   # 结果文件 ID，用于后续接口
            "elapsed_ms":     job["elapsed_ms"],        # 执行耗时（毫秒）
            "download_url":   job["download_url"],      # 结果下载地址
        }


# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------
@router.get("/jobs", summary="列出所有任务")
def list_jobs(
    status: Optional[str] = Query(None, description="按状态过滤：queued/running/done/failed/cancelled")
):
    """列出所有 Processing 任务及其当前状态。"""
    jobs = list(_JOBS.values())
    if status:
        jobs = [j for j in jobs if j["status"] == status]
    # 清理敏感字段
    return {"jobs": [{k: v for k, v in j.items() if k != "parameters"} for j in jobs],
            "count": len(jobs)}


@router.get("/jobs/{job_id}", summary="查询任务进度")
def get_job(job_id: str):
    """
    查询单个 Processing 任务的执行状态和进度。
    status: queued=排队中 / running=执行中 / done=完成 / failed=失败 / cancelled=已取消
    """
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND",
                                          "msg": f"job_id {job_id!r} 不存在"})
    return {k: v for k, v in job.items() if k != "parameters"}


@router.delete("/jobs/{job_id}", summary="取消任务")
def cancel_job(job_id: str):
    """
    取消指定任务。仅对 queued 状态有效；running 状态的任务标记为 cancelled 但子进程可能仍在运行。
    """
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND",
                                          "msg": f"job_id {job_id!r} 不存在"})
    job["status"] = "cancelled"
    return {"job_id": job_id, "status": "cancelled"}
