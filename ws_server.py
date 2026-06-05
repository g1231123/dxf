# -*- coding: utf-8 -*-
"""
WebSocket DXF/DWG 导出服务
============================
基于 asyncio 的事件驱动架构。
客户端上传数据，服务端处理后实时推送 DXF 或 DWG 文件。

完整协议文档见同目录 ws_protocol.md

连接地址
--------
  ws://your-server:8080/ws/render

客户端 → 服务端 消息类型
------------------------
  export   发起导出（上传数据 + 操作参数 → 推送 DXF/DWG）
  ping     心跳检测
  cancel   取消当前任务

服务端 → 客户端 消息类型
------------------------
  connected   连接握手成功
  started     任务开始
  progress    进度 { pct: 0-100, msg: str }
  result      导出完成 { format: "dxf_base64" | "dwg_base64", filename, data, size_bytes, elapsed_ms }
  error       错误 { code: str, msg: str }
  cancelled   任务已取消
  pong        心跳回复

并发控制
--------
  最多同时运行 4 个导出任务（EXPORT_SEMAPHORE）。
  每个客户端连接同时只处理一个任务，新请求自动取消旧任务。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# ezdxf for AI drawing operations (circle, line, rectangle, etc.)
try:
    import ezdxf
    from ezdxf import colors
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    logging.warning("ezdxf not installed, AI drawing features will be disabled")

# pyautocad for AutoCAD COM interface (Windows only)
try:
    from pyautocad import Autocad, APoint
    import win32com.client
    import pythoncom
    AUTOCAD_AVAILABLE = True
except ImportError:
    AUTOCAD_AVAILABLE = False
    logging.info("pyautocad not installed, AutoCAD COM features will be disabled (Windows only)")

LOG = logging.getLogger("ws_render")

router = APIRouter()

# ---------------------------------------------------------------------------
# 配置常量（可通过环境变量覆盖）
# ---------------------------------------------------------------------------

# QGIS Python 可执行文件路径
# 部署到其他机器时修改此路径，或设置环境变量 QGIS_PREFIX_PATH
QGIS_PREFIX = os.environ.get(
    "QGIS_PREFIX_PATH",
    "/Applications/QGIS-final-4_0_2.app/Contents/MacOS",
)
QGIS_PYTHON = os.path.join(QGIS_PREFIX, "python")

# 已上传文件的 GeoJSON 缓存目录（由 POST /data/upload 写入）
GEOJSON_STORE = Path("/tmp/qgis_geojson_store")

# 渲染任务临时工作目录（渲染完成后自动清理）
WORK_DIR = Path(tempfile.gettempdir()) / "ws_render_jobs"
WORK_DIR.mkdir(exist_ok=True)

# 最大并发导出任务数。超出的请求会排队等待，不会被拒绝。
EXPORT_SEMAPHORE = asyncio.Semaphore(4)

# 导出超时（秒）。超时后任务自动取消并返回 error。
EXPORT_TIMEOUT_SECONDS = 120

# 心跳超时（秒）。连接空闲超过此时间服务端主动发送 ping_from_server。
HEARTBEAT_TIMEOUT_SECONDS = 60

# 单次通过 WebSocket 上传的文件大小上限（字节）
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB

# ODA File Converter 路径（DWG 导出时使用，没有则只支持 DXF 导出）
ODA_CONVERTER = shutil.which("ODAFileConverter") or "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

# ogr2ogr 路径（格式转换）
OGR2OGR = shutil.which("ogr2ogr") or "/Applications/QGIS-final-4_0_2.app/Contents/MacOS/ogr2ogr"


# ---------------------------------------------------------------------------
# 错误码常量
# ---------------------------------------------------------------------------

class ErrCode:
    """服务端推送 error 消息时使用的标准错误码。"""
    FILE_NOT_FOUND  = "FILE_NOT_FOUND"   # file_id 不存在，需先通过消息上传文件数据
    EXPORT_FAILED   = "EXPORT_FAILED"    # DXF/DWG 导出处理失败
    INVALID_PARAMS  = "INVALID_PARAMS"   # 请求参数格式或取值不合法
    EXPORT_TIMEOUT  = "EXPORT_TIMEOUT"   # 导出超过 EXPORT_TIMEOUT_SECONDS 秒
    CANCELLED       = "CANCELLED"        # 任务被客户端主动取消
    UNSUPPORTED_FMT = "UNSUPPORTED_FMT"  # 请求了不支持的输出格式（如没有 ODA 时请求 DWG）
    INTERNAL        = "INTERNAL"         # 其他未预期错误


# ---------------------------------------------------------------------------
# 连接管理器 — 跟踪所有活跃 WebSocket 客户端
# 每个连接分配一个唯一 client_id，用于日志追踪和服务端广播
# ---------------------------------------------------------------------------
class ConnectionManager:
    """线程安全的 WebSocket 连接注册表。"""

    def __init__(self):
        self._clients: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket) -> str:
        """接受 WebSocket 握手，注册连接，返回 client_id。"""
        await ws.accept()
        cid = uuid.uuid4().hex[:8]
        self._clients[cid] = ws
        LOG.info("WS client connected: %s  total=%d", cid, len(self._clients))
        return cid

    def disconnect(self, cid: str):
        """注销连接（客户端断开或异常时调用）。"""
        self._clients.pop(cid, None)
        LOG.info("WS client disconnected: %s  total=%d", cid, len(self._clients))

    async def send(self, cid: str, data: dict):
        """向指定客户端发送 JSON 消息，发送失败时记录警告但不抛出。"""
        ws = self._clients.get(cid)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                LOG.warning("send to %s failed: %s", cid, e)

    async def broadcast(self, data: dict):
        """向所有已连接的前端客户端广播 JSON 消息（用于控制通道推送）。"""
        for cid, ws in list(self._clients.items()):
            try:
                await ws.send_json(data)
            except Exception as e:
                LOG.warning("broadcast to %s failed: %s", cid, e)

    @property
    def count(self) -> int:
        """当前活跃连接数。"""
        return len(self._clients)

    def list_clients(self) -> list[str]:
        """返回所有客户端ID列表。"""
        return list(self._clients.keys())


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# DXF/DWG 导出核心逻辑
# ---------------------------------------------------------------------------

def _apply_edits_and_export(
    src_dxf: Path,
    out_dxf: Path,
    edits: list[dict],
) -> None:
    """
    用 ezdxf 对 DXF 文件应用编辑操作，保存到 out_dxf。

    编辑操作格式（edits 列表中每条）
    --------------------------------
    { "op": "move",   "handle": "1A2B", "dx": 10.0, "dy": 5.0 }
        移动指定实体。handle 是 DXF 实体句柄（十六进制字符串）。
        dx/dy 是 X/Y 方向偏移量（DXF 文件单位）。

    { "op": "delete", "handle": "1A2B" }
        删除指定实体。

    { "op": "set_text", "handle": "1A2B", "text": "新文本内容" }
        修改 TEXT 或 MTEXT 实体的文字内容。

    { "op": "set_layer", "handle": "1A2B", "layer": "图层名" }
        把实体移到指定图层（图层不存在会自动创建）。

    { "op": "set_color", "handle": "1A2B", "color": 1 }
        设置实体颜色（ACI 颜色索引 1-255，或 0=ByBlock, 256=ByLayer）。
    """
    import ezdxf  # type: ignore

    doc = ezdxf.readfile(str(src_dxf))
    msp = doc.modelspace()

    # 建立 handle → 实体 映射表（跳过没有 handle 的旧格式实体）
    by_handle: dict[str, object] = {}
    for layout in [msp, *(b for b in doc.blocks)]:
        for ent in layout:
            try:
                h = ent.dxf.handle
                if h:
                    by_handle[h.upper()] = ent
            except Exception:
                pass

    deleted_handles: set[str] = set()

    for op in edits:
        handle = str(op.get("handle", "")).upper()
        if not handle:
            continue
        ent = by_handle.get(handle)
        if ent is None or handle in deleted_handles:
            continue

        kind = op.get("op", "")

        if kind == "move":
            # 移动实体：修改插入点 / 起点
            dx = float(op.get("dx", 0))
            dy = float(op.get("dy", 0))
            for attr in ("insert", "start", "center"):
                try:
                    pt = getattr(ent.dxf, attr)
                    setattr(ent.dxf, attr, (pt[0] + dx, pt[1] + dy, pt[2] if len(pt) > 2 else 0))
                    break
                except Exception:
                    pass

        elif kind == "delete":
            # 删除实体
            try:
                ent.destroy()
                deleted_handles.add(handle)
            except Exception:
                pass

        elif kind == "set_text":
            # 修改文字内容（TEXT / MTEXT）
            new_text = str(op.get("text", ""))
            for attr in ("text", "plain_mtext"):
                try:
                    setattr(ent.dxf, attr, new_text)
                    break
                except Exception:
                    pass

        elif kind == "set_layer":
            # 修改图层
            layer_name = str(op.get("layer", "0"))
            try:
                ent.dxf.layer = layer_name
            except Exception:
                pass

        elif kind == "set_color":
            # 修改颜色（ACI 索引）
            try:
                ent.dxf.color = int(op.get("color", 256))
            except Exception:
                pass

    # 修复旧格式 DXF 缺失的 handle（R12 文件常见）
    try:
        auditor = doc.audit()
        if auditor.has_errors:
            LOG.info("DXF audit fixed %d issues", len(auditor.errors))
    except Exception as e:
        LOG.warning("DXF audit warning: %s", e)

    doc.saveas(str(out_dxf))


def _convert_dxf_to_dwg(dxf_path: Path, dwg_path: Path) -> None:
    """
    用 ODA File Converter 把 DXF 转换为 DWG。
    需要提前安装 ODAFileConverter。
    下载地址: https://www.opendesign.com/guestfiles/oda_file_converter
    """
    if not Path(ODA_CONVERTER).exists():
        raise RuntimeError(
            "未找到 ODA File Converter，无法导出 DWG 格式。"
            f"请安装后确认路径: {ODA_CONVERTER}"
        )
    out_dir = dwg_path.parent / "_oda_out"
    out_dir.mkdir(exist_ok=True)
    cmd = [
        ODA_CONVERTER,
        str(dxf_path.parent),  # 输入目录
        str(out_dir),          # 输出目录
        "ACAD2018",            # 目标 DWG 版本
        "DWG",                 # 输出格式
        "0",                   # 是否递归子目录
        "1",                   # 是否审计
        dxf_path.name,         # 输入文件名
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    produced = out_dir / (dxf_path.stem + ".dwg")
    if not produced.exists():
        raise RuntimeError(f"DXF→DWG 转换失败: {proc.stderr or proc.stdout}")
    shutil.move(str(produced), str(dwg_path))


# ---------------------------------------------------------------------------
# AI Drawing Operations (ezdxf)
# ---------------------------------------------------------------------------

def _apply_ai_draw_operations(doc: ezdxf.document.Drawing, shapes: list[dict]) -> list[dict]:
    """
    应用AI绘图操作，在DXF文档中绘制几何图形。

    支持的 shape 类型:
    - circle: 圆 (cx, cy, r)
    - line: 直线/折线 (points, closed)
    - rectangle: 矩形 (x, y, width, height, rotation)
    - polygon: 多边形 (rings - 支持外环+内孔)
    - text: 文字 (x, y, text, height, rotation)
    - arc: 圆弧 (cx, cy, r, start_angle, end_angle)
    - ellipse: 椭圆 (cx, cy, rx, ry, rotation)

    返回: 操作结果列表 [{"shape_id": ..., "handle": ..., "status": ...}]
    """
    if not EZDXF_AVAILABLE:
        raise RuntimeError("ezdxf not installed, AI drawing features are disabled")

    msp = doc.modelspace()
    results = []

    for shape in shapes:
        shape_id = shape.get("id", str(uuid.uuid4())[:8])

        # 如果没有 type，默认画圆
        shape_type = shape.get("type", "").lower()
        if not shape_type:
            shape_type = "circle"

        layer = shape.get("layer", "0")
        style = shape.get("style", {})

        # 样式提取 - 支持平铺参数 (pyautocad 风格)
        stroke_color = shape.get("color", style.get("stroke_color", "#FFFFFF"))
        stroke_width = shape.get("stroke_width", style.get("stroke_width", 0.25))
        fill_color = shape.get("fill_color", style.get("fill_color"))
        fill_opacity = shape.get("fill_opacity", style.get("fill_opacity", 1.0))

        # 颜色转换 (HEX -> ACI)
        def hex_to_aci(hex_color: str) -> int:
            """简单HEX转AutoCAD颜色索引，白色返回7"""
            if not hex_color:
                return 7
            try:
                # 尝试从颜色名映射
                color_map = {
                    "#FF0000": 1, "#FFFF00": 2, "#00FF00": 3, "#00FFFF": 4,
                    "#0000FF": 5, "#FF00FF": 6, "#FFFFFF": 7, "#808080": 8,
                    "#C0C0C0": 9, "#FF0000": 1, "#FF7F7F": 1, "#7F0000": 10,
                }
                return color_map.get(hex_color.upper(), 7)
            except:
                return 7

        try:
            if shape_type in ("circle", "addcircle"):
                # 圆: 平铺参数 {center, radius} 或 geometry {center, radius} 或旧格式 {cx, cy, r}
                # 优先平铺参数 (pyautocad 风格)
                center = shape.get("center")
                radius = shape.get("radius")
                if center and radius:
                    cx, cy = float(center[0]), float(center[1])
                    r = float(radius)
                else:
                    # 兼容 geometry 嵌套格式
                    geom = shape.get("geometry", {})
                    center = geom.get("center")
                    radius = geom.get("radius")
                    if center and radius:
                        cx, cy = float(center[0]), float(center[1])
                        r = float(radius)
                    else:
                        # 旧格式 {cx, cy, r}
                        cx = float(geom.get("cx", 100.0))   # 默认圆心 X=100
                        cy = float(geom.get("cy", 100.0))   # 默认圆心 Y=100
                        r = float(geom.get("r", 50.0))      # 默认半径=50

                # 如果未指定颜色，默认红色
                circle_color = stroke_color if stroke_color != "#FFFFFF" else "#FF0000"

                # 创建圆
                circle = msp.add_circle(
                    center=(cx, cy, 0),
                    radius=r,
                    dxfattribs={
                        "layer": layer,
                        "color": hex_to_aci(circle_color),
                    }
                )
                results.append({
                    "shape_id": shape_id,
                    "type": "circle",
                    "handle": str(circle.dxf.handle),
                    "status": "created",
                    "center": [cx, cy],
                    "radius": r
                })

            elif shape_type in ("arc", "addarc"):
                # 圆弧: 平铺参数 {center, radius, start_angle, end_angle} 或 geometry 嵌套
                geom = shape.get("geometry", {})
                center = shape.get("center") or geom.get("center")
                radius = shape.get("radius") if shape.get("radius") is not None else geom.get("radius")
                if center and radius is not None:
                    cx, cy = float(center[0]), float(center[1])
                    r = float(radius)
                else:
                    cx = float(shape.get("cx", geom.get("cx", 0)))
                    cy = float(shape.get("cy", geom.get("cy", 0)))
                    r = float(shape.get("r", geom.get("r", 1)))
                start_angle = float(shape.get("start_angle", geom.get("start_angle", 0)))
                end_angle = float(shape.get("end_angle", geom.get("end_angle", 90)))

                arc = msp.add_arc(
                    center=(cx, cy, 0),
                    radius=r,
                    start_angle=start_angle,
                    end_angle=end_angle,
                    dxfattribs={
                        "layer": layer,
                        "color": hex_to_aci(stroke_color),
                    }
                )
                results.append({
                    "shape_id": shape_id,
                    "type": "arc",
                    "handle": str(arc.dxf.handle),
                    "status": "created"
                })

            elif shape_type in ("line", "addline", "addpolyline"):
                # 直线/多段线: 平铺参数 {start_point, end_point} 或 {points: [], closed}
                # 优先平铺参数 (pyautocad 风格)
                start_point = shape.get("start_point")
                end_point = shape.get("end_point")
                if start_point and end_point:
                    points = [start_point, end_point]
                else:
                    points = shape.get("points", [])
                # 支持 closed 参数
                closed = shape.get("closed", False)

                if len(points) < 2:
                    results.append({
                        "shape_id": shape_id,
                        "type": "line",
                        "status": "error",
                        "msg": "至少需要2个点"
                    })
                    continue

                # 转换为3D点
                vertices = [(float(p[0]), float(p[1]), 0) for p in points]

                if closed and len(vertices) >= 3:
                    # 闭合多段线
                    lwpolyline = msp.add_lwpolyline(
                        points=vertices,
                        close=True,
                        dxfattribs={
                            "layer": layer,
                            "color": hex_to_aci(stroke_color),
                        }
                    )
                    handle = str(lwpolyline.dxf.handle)
                else:
                    # 开放多段线或直线
                    lwpolyline = msp.add_lwpolyline(
                        points=vertices,
                        close=False,
                        dxfattribs={
                            "layer": layer,
                            "color": hex_to_aci(stroke_color),
                        }
                    )
                    handle = str(lwpolyline.dxf.handle)

                results.append({
                    "shape_id": shape_id,
                    "type": "line",
                    "handle": handle,
                    "status": "created",
                    "point_count": len(vertices)
                })

            elif shape_type in ("rectangle", "addrectangle"):
                # 矩形: {x, y, width, height, rotation} 或 {insert_point, width, height}
                # 优先平铺参数，兼容 geometry 嵌套
                x = float(shape.get("x", shape.get("geometry", {}).get("x", 0)))
                y = float(shape.get("y", shape.get("geometry", {}).get("y", 0)))
                if shape.get("insert_point"):
                    x = float(shape.get("insert_point")[0])
                    y = float(shape.get("insert_point")[1])
                width = float(shape.get("width", shape.get("geometry", {}).get("width", 100)))
                height = float(shape.get("height", shape.get("geometry", {}).get("height", 100)))
                rotation = float(shape.get("rotation", shape.get("geometry", {}).get("rotation", 0)))

                # 计算4个角点 (未旋转)
                corners = [(x, y, 0), (x + width, y, 0), (x + width, y + height, 0), (x, y + height, 0)]

                # 如果需要旋转，计算旋转后的坐标
                if rotation != 0:
                    import math
                    ar = math.radians(rotation)
                    cos_a, sin_a = math.cos(ar), math.sin(ar)
                    cx, cy = x + width / 2, y + height / 2
                    rotated_corners = []
                    for px, py, pz in corners:
                        dx, dy = px - cx, py - cy
                        rotated_corners.append((dx * cos_a - dy * sin_a + cx, dx * sin_a + dy * cos_a + cy, pz))
                    corners = rotated_corners

                rect = msp.add_lwpolyline(
                    points=corners, close=True,
                    dxfattribs={"layer": layer, "color": hex_to_aci(stroke_color)}
                )
                results.append({
                    "shape_id": shape_id, "type": "rectangle",
                    "handle": str(rect.dxf.handle), "status": "created",
                    "width": width, "height": height
                })

            elif shape_type == "polygon":
                # 多边形: {rings: [[[x,y], [x,y], ...], ...]} 支持多环
                geom = shape.get("geometry", {})
                rings = geom.get("rings", [])

                if not rings or len(rings[0]) < 3:
                    results.append({
                        "shape_id": shape_id,
                        "type": "polygon",
                        "status": "error",
                        "msg": "多边形至少需要3个顶点"
                    })
                    continue

                # ezdxf Hatch 用于多边形填充
                exterior = [(float(p[0]), float(p[1])) for p in rings[0]]
                holes = []
                for hole_ring in rings[1:]:
                    if len(hole_ring) >= 3:
                        holes.append([(float(p[0]), float(p[1])) for p in hole_ring])

                hatch = msp.add_hatch(
                    color=hex_to_aci(fill_color) if fill_color else 7,
                    dxfattribs={"layer": layer}
                )
                hatch.paths.add_polyline_path(exterior, is_closed=True)
                for hole in holes:
                    hatch.paths.add_polyline_path(hole, is_closed=True)

                results.append({
                    "shape_id": shape_id,
                    "type": "polygon",
                    "handle": str(hatch.dxf.handle) if 'hatch' in locals() else None,
                    "status": "created"
                })

            elif shape_type in ("text", "addtext", "mtext", "addmtext"):
                # 文字处理：支持 insert_point 或 x/y 平铺坐标
                text_content = shape.get("text", "")
                if not text_content:
                    results.append({
                        "shape_id": shape_id,
                        "type": shape_type,
                        "status": "skipped",
                        "msg": "空文字内容"
                    })
                    continue

                # 坐标：优先 insert_point，兼容平铺 x/y
                ip = shape.get("insert_point")
                if ip:
                    tx, ty = float(ip[0]), float(ip[1])
                else:
                    geom = shape.get("geometry", {})
                    tx = float(shape.get("x", geom.get("x", 0)))
                    ty = float(shape.get("y", geom.get("y", 0)))

                th = float(shape.get("height", 2.5))
                tr = float(shape.get("rotation", 0))
                t_color = hex_to_aci(shape.get("color", stroke_color))

                if shape_type in ("mtext", "addmtext"):
                    # 多行文字
                    mtext_ent = msp.add_mtext(
                        text=text_content,
                        dxfattribs={
                            "layer": layer,
                            "color": t_color,
                            "insert": (tx, ty, 0),
                            "char_height": th,
                            "rotation": tr,
                        }
                    )
                    results.append({
                        "shape_id": shape_id,
                        "type": "mtext",
                        "handle": str(mtext_ent.dxf.handle),
                        "status": "created",
                        "content": text_content[:50]
                    })
                else:
                    # 单行文字
                    text_ent = msp.add_text(
                        text=text_content,
                        height=th,
                        dxfattribs={
                            "layer": layer,
                            "color": t_color,
                            "insert": (tx, ty, 0),
                            "rotation": tr,
                        }
                    )
                    results.append({
                        "shape_id": shape_id,
                        "type": "text",
                        "handle": str(text_ent.dxf.handle),
                        "status": "created",
                        "content": text_content[:50]
                    })

            elif shape_type in ("ellipse", "addellipse"):
                # 椭圆：支持新格式 {center, major_axis, radius_ratio}
                # 兼容旧格式 geometry {cx, cy, rx, ry, rotation}
                import math
                center_v = shape.get("center")
                major_axis_v = shape.get("major_axis")
                radius_ratio_v = shape.get("radius_ratio")

                if center_v and major_axis_v and radius_ratio_v is not None:
                    # 新格式（与 parse 返回格式完全一致）
                    ecx, ecy = float(center_v[0]), float(center_v[1])
                    major_axis = (float(major_axis_v[0]) - ecx,
                                  float(major_axis_v[1]) - ecy, 0)
                    if major_axis == (0, 0, 0):
                        major_axis = (float(major_axis_v[0]), float(major_axis_v[1]), 0)
                    ratio = float(radius_ratio_v)
                else:
                    # 旧格式
                    geom = shape.get("geometry", {})
                    ecx = float(geom.get("cx", 0))
                    ecy = float(geom.get("cy", 0))
                    rx = float(geom.get("rx", 1))
                    ry = float(geom.get("ry", 0.5))
                    er = float(geom.get("rotation", 0))
                    ar = math.radians(er)
                    major_axis = (rx * math.cos(ar), rx * math.sin(ar), 0)
                    ratio = ry / rx if rx > 0 else 1.0
                    ecx, ecy = ecx, ecy

                ellipse = msp.add_ellipse(
                    center=(ecx, ecy, 0),
                    major_axis=major_axis,
                    ratio=ratio,
                    dxfattribs={
                        "layer": layer,
                        "color": hex_to_aci(stroke_color),
                    }
                )
                results.append({
                    "shape_id": shape_id,
                    "type": "ellipse",
                    "handle": str(ellipse.dxf.handle),
                    "status": "created"
                })

            elif shape_type in ("insert", "addinsert"):
                # 块参照: {block_name, insert_point, scale, rotation}
                block_name = shape.get("block_name", shape.get("name", ""))
                if not block_name:
                    results.append({"shape_id": shape_id, "type": "insert",
                                    "status": "error", "msg": "缺少 block_name"})
                    continue
                ip = shape.get("insert_point", [0, 0, 0])
                sc = shape.get("scale", [1, 1, 1])
                ir = float(shape.get("rotation", 0))
                try:
                    ins_ent = msp.add_blockref(
                        name=block_name,
                        insert=(float(ip[0]), float(ip[1]), 0),
                        dxfattribs={
                            "layer": layer,
                            "color": hex_to_aci(stroke_color),
                            "xscale": float(sc[0]) if len(sc) > 0 else 1,
                            "yscale": float(sc[1]) if len(sc) > 1 else 1,
                            "rotation": ir,
                        }
                    )
                    results.append({
                        "shape_id": shape_id,
                        "type": "insert",
                        "handle": str(ins_ent.dxf.handle),
                        "status": "created",
                        "block_name": block_name
                    })
                except Exception as ie:
                    results.append({"shape_id": shape_id, "type": "insert",
                                    "status": "error", "msg": str(ie)})

            else:
                results.append({
                    "shape_id": shape_id,
                    "type": shape_type,
                    "status": "error",
                    "msg": f"不支持的图形类型: {shape_type}"
                })

        except Exception as e:
            LOG.exception("Failed to create shape %s", shape_id)
            results.append({
                "shape_id": shape_id,
                "type": shape_type,
                "status": "error",
                "msg": str(e)
            })

    return results


def _render_dxf_to_png(doc, width: int = 800, height: int = 600) -> bytes:
    """
    使用 ezdxf 和 matplotlib 将 DXF 渲染为 PNG 图片。
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        from matplotlib.patches import Circle, Rectangle, Polygon, FancyBboxPatch
        from matplotlib.lines import Line2D
        import numpy as np
        import io

        # 设置支持中文的字体，避免乱码
        _zh_fonts = [f.name for f in fm.fontManager.ttflist if any(
            kw in f.name for kw in ('PingFang', 'Heiti', 'STHeiti', 'SimHei', 'SimSun',
                                     'WenQuanYi', 'Noto', 'CJK', 'Source Han', 'Arial Unicode')
        )]
        if _zh_fonts:
            plt.rcParams['font.family'] = _zh_fonts[0]
        else:
            plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        
        fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
        ax.set_aspect('equal')
        ax.axis('off')
        
        msp = doc.modelspace()
        
        # 获取边界框 - 手动计算所有实体的边界
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        
        for entity in msp:
            try:
                if entity.dxftype() == 'CIRCLE':
                    cx, cy = entity.dxf.center[0], entity.dxf.center[1]
                    r = entity.dxf.radius
                    min_x = min(min_x, cx - r)
                    max_x = max(max_x, cx + r)
                    min_y = min(min_y, cy - r)
                    max_y = max(max_y, cy + r)
                elif entity.dxftype() == 'LINE':
                    x1, y1 = entity.dxf.start[0], entity.dxf.start[1]
                    x2, y2 = entity.dxf.end[0], entity.dxf.end[1]
                    min_x = min(min_x, x1, x2)
                    max_x = max(max_x, x1, x2)
                    min_y = min(min_y, y1, y2)
                    max_y = max(max_y, y1, y2)
            except:
                pass
        
        # 如果计算出了有效边界
        if min_x != float('inf'):
            margin = max(max_x - min_x, max_y - min_y) * 0.1
            ax.set_xlim(min_x - margin, max_x + margin)
            ax.set_ylim(min_y - margin, max_y + margin)
        else:
            ax.set_xlim(-100, 100)
            ax.set_ylim(-100, 100)
        
        # 绘制所有实体
        for entity in msp:
            try:
                if entity.dxftype() == 'CIRCLE':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    color = entity.dxf.color if entity.dxf.color > 0 else 1
                    circle = Circle((center[0], center[1]), radius, fill=False, color=plt.cm.tab10(color % 10))
                    ax.add_patch(circle)
                    
                elif entity.dxftype() == 'LINE':
                    start = entity.dxf.start
                    end = entity.dxf.end
                    color = entity.dxf.color if entity.dxf.color > 0 else 1
                    ax.plot([start[0], end[0]], [start[1], end[1]], color=plt.cm.tab10(color % 10), linewidth=1)
                    
                elif entity.dxftype() == 'LWPOLYLINE' or entity.dxftype() == 'POLYLINE':
                    points = list(entity.vertices_in_wcs())
                    if points:
                        x = [p[0] for p in points]
                        y = [p[1] for p in points]
                        color = entity.dxf.color if entity.dxf.color > 0 else 1
                        is_closed = entity.is_closed if hasattr(entity, 'is_closed') else False
                        if is_closed and x:
                            x.append(x[0])
                            y.append(y[0])
                        ax.plot(x, y, color=plt.cm.tab10(color % 10), linewidth=1)
                       
                elif entity.dxftype() == 'ARC':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    color = entity.dxf.color if entity.dxf.color > 0 else 1
                    arc = plt.matplotlib.patches.Arc((center[0], center[1]), radius*2, radius*2,
                                                    angle=0, theta1=start_angle, theta2=end_angle,
                                                    color=plt.cm.tab10(color % 10), linewidth=1)
                    ax.add_patch(arc)
                    
                elif entity.dxftype() == 'TEXT' or entity.dxftype() == 'MTEXT':
                    insert = entity.dxf.insert
                    text = entity.dxf.text if hasattr(entity.dxf, 'text') else str(entity)
                    color = entity.dxf.color if entity.dxf.color > 0 else 1
                    ax.text(insert[0], insert[1], text, color=plt.cm.tab10(color % 10), fontsize=8)
                    
                elif entity.dxftype() == 'ELLIPSE':
                    center = entity.dxf.center
                    major_axis = entity.dxf.major_axis
                    ratio = entity.dxf.ratio
                    color = entity.dxf.color if entity.dxf.color > 0 else 1
                    width = (major_axis[0]**2 + major_axis[1]**2)**0.5 * 2
                    height = width * ratio
                    ellipse = plt.matplotlib.patches.Ellipse((center[0], center[1]), width, height,
                                                               angle=np.degrees(np.arctan2(major_axis[1], major_axis[0])),
                                                               fill=False, color=plt.cm.tab10(color % 10), linewidth=1)
                    ax.add_patch(ellipse)
                    
            except Exception as e:
                LOG.debug("Failed to render entity %s: %s", entity.dxftype(), e)
                continue
        
        plt.tight_layout(pad=0)
        
        # 保存为 PNG
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
        buf.seek(0)
        png_bytes = buf.read()
        plt.close(fig)
        
        return png_bytes
        
    except ImportError as e:
        LOG.warning(f"matplotlib not available for rendering: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        LOG.error(f"Failed to render DXF to PNG: {e}")
        import traceback
        traceback.print_exc()
        return None


def _apply_ai_draw_operations_autocad(acad, shapes: list[dict]) -> list[dict]:
    """
    使用 AutoCAD COM 接口绘制几何图形（Windows + AutoCAD 环境）。

    支持的 shape 类型: circle, arc, line, rectangle, polygon, text, ellipse

    返回: 操作结果列表 [{"shape_id": ..., "handle": ..., "status": ...}]
    """
    if not AUTOCAD_AVAILABLE:
        raise RuntimeError("pyautocad not installed, AutoCAD COM features are disabled")
    
    # Initialize COM for this thread (required in multi-threaded contexts)
    try:
        pythoncom.CoInitialize()
    except:
        pass  # May already be initialized

    try:
        model = acad.model
    except Exception as e:
        raise RuntimeError(f"无法访问 AutoCAD ModelSpace: {e}")

    results = []

    for shape in shapes:
        shape_id = shape.get("id", str(uuid.uuid4())[:8])

        # 如果没有 type，默认画圆
        shape_type = shape.get("type", "").lower()
        if not shape_type:
            shape_type = "circle"

        layer = shape.get("layer", "0")
        style = shape.get("style", {})

        # 样式提取
        stroke_color = style.get("stroke_color", "#FF0000")  # 默认红色
        stroke_width = style.get("stroke_width", 0.25)
        fill_color = style.get("fill_color")

        # HEX 颜色转 AutoCAD ACI 颜色号
        def hex_to_aci_autocad(hex_color: str) -> int:
            """简单HEX转AutoCAD颜色索引"""
            if not hex_color:
                return 1  # 红色
            color_map = {
                "#FF0000": 1, "#FFFF00": 2, "#00FF00": 3, "#00FFFF": 4,
                "#0000FF": 5, "#FF00FF": 6, "#FFFFFF": 7, "#808080": 8,
                "#C0C0C0": 9, "#7F0000": 10,
            }
            return color_map.get(hex_color.upper(), 1)

        try:
            if shape_type in ("circle", "AddCircle"):
                # 圆: {cx, cy, r} 或 {center: [x,y,z], radius}
                geom = shape.get("geometry", {})
                # 支持 CadLike 格式
                center = geom.get("center")
                radius = geom.get("radius")
                if center and radius:
                    cx, cy = float(center[0]), float(center[1])
                    r = float(radius)
                else:
                    cx = float(geom.get("cx", 100.0))
                    cy = float(geom.get("cy", 100.0))
                    r = float(geom.get("r", 50.0))

                # 使用 pyautocad 的 APoint
                center = APoint(cx, cy, 0)
                circle = model.AddCircle(center, r)
                circle.Layer = layer
                circle.Color = hex_to_aci_autocad(stroke_color)

                results.append({
                    "shape_id": shape_id,
                    "type": "circle",
                    "handle": str(circle.Handle),
                    "status": "created",
                    "center": [cx, cy],
                    "radius": r
                })

            elif shape_type in ("arc", "AddArc"):
                # 圆弧: {cx, cy, r, start_angle, end_angle} 或 {center, radius, ...}
                geom = shape.get("geometry", {})
                # 支持 CadLike 格式
                center = geom.get("center")
                radius = geom.get("radius")
                if center and radius:
                    cx, cy = float(center[0]), float(center[1])
                    r = float(radius)
                else:
                    cx = float(geom.get("cx", 100.0))
                    cy = float(geom.get("cy", 100.0))
                    r = float(geom.get("r", 50.0))
                start_angle = float(geom.get("start_angle", 0))
                end_angle = float(geom.get("end_angle", 90))

                center = APoint(cx, cy, 0)
                arc = model.AddArc(center, r, start_angle, end_angle)
                arc.Layer = layer
                arc.Color = hex_to_aci_autocad(stroke_color)

                results.append({
                    "shape_id": shape_id,
                    "type": "arc",
                    "handle": str(arc.Handle),
                    "status": "created"
                })

            elif shape_type in ("line", "addline", "addpolyline"):
                # 直线/多段线: 平铺参数 {start_point, end_point} 或 {points: [], closed}
                # 优先平铺参数 (pyautocad 风格)
                start_point = shape.get("start_point")
                end_point = shape.get("end_point")
                if start_point and end_point:
                    points = [start_point, end_point]
                else:
                    points = shape.get("points", [])
                # 支持 closed 参数
                closed = shape.get("closed", False)

                if len(points) < 2:
                    results.append({
                        "shape_id": shape_id,
                        "type": "line",
                        "status": "error",
                        "msg": "至少需要2个点"
                    })
                    continue

                # AutoCAD 创建多段线
                # 转换为变体数组
                point_array = []
                for p in points:
                    point_array.extend([float(p[0]), float(p[1]), 0.0])

                # 使用 win32com 创建 safearray
                # pyautocad 会处理转换
                points_vb = win32com.client.VARIANT(
                    win32com.client.pythoncom.VT_ARRAY | win32com.client.pythoncom.VT_R8,
                    point_array
                )

                pline = model.AddPolyline(points_vb)
                pline.Layer = layer
                pline.Color = hex_to_aci_autocad(stroke_color)

                results.append({
                    "shape_id": shape_id,
                    "type": "line",
                    "handle": str(pline.Handle),
                    "status": "created",
                    "point_count": len(points)
                })

            elif shape_type == "rectangle":
                # 矩形: {x, y, width, height, rotation}
                geom = shape.get("geometry", {})
                x = float(geom.get("x", 0))
                y = float(geom.get("y", 0))
                width = float(geom.get("width", 100))
                height = float(geom.get("height", 50))
                rotation = float(geom.get("rotation", 0))

                # 计算4个角点
                corners = [
                    APoint(x, y, 0),
                    APoint(x + width, y, 0),
                    APoint(x + width, y + height, 0),
                    APoint(x, y + height, 0),
                    APoint(x, y, 0),  # 闭合
                ]

                # 创建闭合多段线
                point_array = []
                for p in corners:
                    point_array.extend([p.x, p.y, p.z])

                points_vb = win32com.client.VARIANT(
                    win32com.client.pythoncom.VT_ARRAY | win32com.client.pythoncom.VT_R8,
                    point_array
                )

                pline = model.AddPolyline(points_vb)
                pline.Layer = layer
                pline.Color = hex_to_aci_autocad(stroke_color)
                pline.Closed = closed if 'closed' in locals() else True

                # 如果需要旋转
                if rotation != 0:
                    import math
                    angle_rad = math.radians(rotation)
                    cx = x + width / 2
                    cy = y + height / 2
                    base_point = APoint(cx, cy, 0)
                    pline.Rotate(base_point, angle_rad)

                results.append({
                    "shape_id": shape_id,
                    "type": "rectangle",
                    "handle": str(pline.Handle),
                    "status": "created",
                    "width": width,
                    "height": height
                })

            elif shape_type in ("text", "addtext"):
                # 文字: 平铺参数 {text, insert_point, height} 或旧格式
                # 优先平铺参数 (pyautocad 风格)
                text_content = shape.get("text", "")
                height = float(shape.get("height", 12))
                insert_point = shape.get("insert_point")
                if insert_point:
                    x, y = float(insert_point[0]), float(insert_point[1])
                else:
                    # 兼容旧格式 {geometry: {x, y}}
                    geom = shape.get("geometry", {})
                    x = float(geom.get("x", 100.0))
                    y = float(geom.get("y", 100.0))
                    text_content = text_content or shape.get("style", {}).get("text", "")
                    height = float(shape.get("style", {}).get("font_size", height))

                if not text_content:
                    results.append({
                        "shape_id": shape_id,
                        "type": "text",
                        "status": "skipped",
                        "msg": "空文字内容"
                    })
                    continue

                insert_point = APoint(x, y, 0)
                text = model.AddText(text_content, insert_point, height)
                text.Layer = layer
                text.Color = hex_to_aci_autocad(style.get("color", stroke_color))

                results.append({
                    "shape_id": shape_id,
                    "type": "text",
                    "handle": str(text.Handle),
                    "status": "created",
                    "content": text_content[:50]
                })

            elif shape_type in ("ellipse", "addellipse"):
                # 椭圆: 平铺参数 {center, major_axis, radius_ratio} 或 {cx, cy, rx, ry}
                # 优先平铺参数 (pyautocad 风格)
                center = shape.get("center")
                major_axis = shape.get("major_axis")
                radius_ratio = shape.get("radius_ratio")
                if center and major_axis and radius_ratio:
                    cx = float(center[0])
                    cy = float(center[1])
                    mx, my = float(major_axis[0]), float(major_axis[1])
                    rx = ((mx - cx)**2 + (my - cy)**2)**0.5
                    ry = rx * float(radius_ratio)
                else:
                    # 兼容旧格式
                    geom = shape.get("geometry", {})
                    center = geom.get("center")
                    major_axis = geom.get("major_axis")
                    radius_ratio = geom.get("radius_ratio")
                    if center and major_axis and radius_ratio:
                        cx = float(center[0])
                        cy = float(center[1])
                        mx, my = float(major_axis[0]), float(major_axis[1])
                        rx = ((mx - cx)**2 + (my - cy)**2)**0.5
                        ry = rx * float(radius_ratio)
                    else:
                        cx = float(geom.get("cx", 100.0))
                        cy = float(geom.get("cy", 100.0))
                        rx = float(geom.get("rx", 50.0))
                        ry = float(geom.get("ry", 30.0))
                rotation = float(shape.get("rotation", shape.get("geometry", {}).get("rotation", 0)))

                center_pt = APoint(cx, cy, 0)
                major_axis_pt = APoint(cx + rx, cy, 0)  # 主轴端点

                # 创建椭圆
                ellipse = model.AddEllipse(center_pt, major_axis_pt, ry / rx if rx > 0 else 1.0)
                ellipse.Layer = layer
                ellipse.Color = hex_to_aci_autocad(stroke_color)

                # 旋转
                if rotation != 0:
                    import math
                    base_point = APoint(cx, cy, 0)
                    ellipse.Rotate(base_point, math.radians(rotation))

                results.append({
                    "shape_id": shape_id,
                    "type": "ellipse",
                    "handle": str(ellipse.Handle),
                    "status": "created"
                })

            else:
                results.append({
                    "shape_id": shape_id,
                    "type": shape_type,
                    "status": "error",
                    "msg": f"AutoCAD COM 不支持的图形类型: {shape_type}"
                })

        except Exception as e:
            LOG.exception("AutoCAD COM failed to create shape %s", shape_id)
            results.append({
                "shape_id": shape_id,
                "type": shape_type,
                "status": "error",
                "msg": str(e)
            })

    return results


def _ai_edit_and_export(
    dxf_bytes: bytes | None,
    filename: str,
    shapes: list[dict],
    output_format: str,
    force_engine: str = None,  # "autocad", "ezdxf", None=auto
) -> tuple[bytes, str, list[dict], str]:
    """
    AI编辑：在DXF/DWG文件中绘制几何图形，然后导出。

    参数:
        dxf_bytes: 原文件内容，None 表示创建新文件
        filename: 原始文件名（用于推断格式和生成输出名）
        shapes: 绘图指令列表
        output_format: 输出格式 dxf/dwg
        force_engine: 强制指定引擎 "autocad" | "ezdxf" | None=自动选择

    返回: (file_bytes, output_filename, operation_results, engine_used)
    """
    # ── 引擎选择策略 ─────────────────────────────────────────────────
    # 优先级: 1. 用户强制指定  2. AutoCAD COM (Windows+AutoCAD运行中)  3. ezdxf (跨平台)

    use_autocad = False
    engine_used = "ezdxf"

    if force_engine == "autocad":
        if AUTOCAD_AVAILABLE:
            use_autocad = True
            engine_used = "autocad"
        elif EZDXF_AVAILABLE:
            LOG.info("AutoCAD engine requested but unavailable; using ezdxf backend")
            use_autocad = False
            engine_used = "ezdxf"
        else:
            raise RuntimeError("当前环境没有 AutoCAD COM，且 ezdxf 未安装。运行: pip install ezdxf")
    elif force_engine == "ezdxf":
        use_autocad = False
        engine_used = "ezdxf"
    elif AUTOCAD_AVAILABLE:
        # 自动模式：尝试连接 AutoCAD
        try:
            acad = Autocad(create_if_not_exists=True)
            # 测试连接是否有效
            _ = acad.doc.Name
            use_autocad = True
            engine_used = "autocad"
            LOG.info("Using AutoCAD COM engine for AI drawing")
        except Exception as e:
            LOG.warning("AutoCAD COM connection failed, falling back to ezdxf: %s", e)
            use_autocad = False
            engine_used = "ezdxf"

    if use_autocad:
        # ── 使用 AutoCAD COM 引擎 ─────────────────────────────────────
        return _ai_edit_and_export_autocad(dxf_bytes, filename, shapes, output_format)
    else:
        # ── 使用 ezdxf 引擎 ───────────────────────────────────────────
        return _ai_edit_and_export_ezdxf(dxf_bytes, filename, shapes, output_format)


def _ai_edit_and_export_autocad(
    dxf_bytes: bytes | None,
    filename: str,
    shapes: list[dict],
    output_format: str,
) -> tuple[bytes, str, list[dict], str]:
    """
    使用 AutoCAD COM 接口进行 AI 绘图。
    直接在运行的 AutoCAD 实例中绘图，然后保存文件。

    注意: 此方法仅在 Windows + AutoCAD 运行环境中有效。
    """
    if not AUTOCAD_AVAILABLE:
        raise RuntimeError("pyautocad not installed. Install with: pip install pyautocad pywin32")

    # Initialize COM for this thread (required for pyautocad in async context)
    try:
        pythoncom.CoInitialize()
    except:
        pass  # May already be initialized

    try:
        # 连接 AutoCAD（如果不存在则创建新文档）
        acad = Autocad(create_if_not_exists=True)
        doc = acad.doc
        model = acad.model

        LOG.info("Connected to AutoCAD: %s", doc.Name)

        # 如果有输入文件，先打开它
        if dxf_bytes is not None:
            job_dir = WORK_DIR / uuid.uuid4().hex
            job_dir.mkdir()

            try:
                src_suffix = Path(filename).suffix.lower()
                src_path = job_dir / f"input{src_suffix}"
                src_path.write_bytes(dxf_bytes)

                # 如果是 DWG，先用 ODA 转换为 DXF，然后 AutoCAD 打开
                if src_suffix == ".dwg":
                    if Path(ODA_CONVERTER).exists():
                        dxf_path = job_dir / "input.dxf"
                        _convert_dwg_to_dxf(src_path, dxf_path)
                        src_path = dxf_path
                    else:
                        LOG.warning("ODAFileConverter not found, attempting to open DWG directly")

                # 打开文件
                doc.Close(False)  # 关闭当前空文档
                doc = acad.app.Documents.Open(str(src_path))
                model = doc.ModelSpace
                LOG.info("Opened file in AutoCAD: %s", src_path)

            finally:
                shutil.rmtree(job_dir, ignore_errors=True)

        # 确保图层存在
        for shape in shapes:
            layer_name = shape.get("layer", "0")
            try:
                doc.Layers.Add(layer_name)
            except Exception:
                pass  # 图层已存在

        # 应用绘图操作
        draw_results = _apply_ai_draw_operations_autocad(acad, shapes)

        # 保存文件到临时目录
        job_dir = WORK_DIR / uuid.uuid4().hex
        job_dir.mkdir()

        try:
            base_name = "ai_drawing" if dxf_bytes is None else Path(filename).stem + "_ai_edited"

            if output_format == "dwg":
                output_path = job_dir / f"{base_name}.dwg"
                doc.SaveAs(str(output_path), 24)  # 24 = ACAD2018 format
            else:
                output_path = job_dir / f"{base_name}.dxf"
                doc.SaveAs(str(output_path), 25)  # 25 = DXF format

            result_bytes = output_path.read_bytes()
            result_name = output_path.name

            LOG.info("AutoCAD saved file: %s (%d bytes)", result_name, len(result_bytes))

            return result_bytes, result_name, draw_results, "autocad"

        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    except Exception as e:
        LOG.exception("AutoCAD COM operation failed")
        raise RuntimeError(f"AutoCAD COM operation failed: {e}")
    finally:
        # Clean up COM initialization
        try:
            pythoncom.CoUninitialize()
        except:
            pass


def _ai_edit_and_export_ezdxf(
    dxf_bytes: bytes | None,
    filename: str,
    shapes: list[dict],
    output_format: str,
) -> tuple[bytes, str, list[dict], str]:
    """
    使用 ezdxf 库进行 AI 绘图（跨平台，无需 AutoCAD）。
    """
    if not EZDXF_AVAILABLE:
        raise RuntimeError("ezdxf not installed. Install with: pip install ezdxf")

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    try:
        # ── 创建或打开 DXF 文件 ────────────────────────────────────────
        if dxf_bytes is None:
            # 创建新的空白 DXF 文件
            doc = ezdxf.new("R2018")
        else:
            src_suffix = Path(filename).suffix.lower()
            src_path = job_dir / f"input{src_suffix}"
            src_path.write_bytes(dxf_bytes)

            # ── 如果输入是 DWG，先转换为 DXF ──────────────────────────────
            if src_suffix == ".dwg":
                if not Path(ODA_CONVERTER).exists():
                    raise RuntimeError("ODAFileConverter not found, cannot process DWG input")
                dxf_path = job_dir / "input.dxf"
                _convert_dwg_to_dxf(src_path, dxf_path)
            else:
                dxf_path = src_path

            # ── 用 ezdxf 打开 ──────────────────────────────────────────────
            doc = ezdxf.readfile(str(dxf_path))

        # 确保图层存在
        for shape in shapes:
            layer_name = shape.get("layer", "0")
            if layer_name not in doc.layers:
                doc.layers.add(layer_name)

        # 应用绘图操作
        draw_results = _apply_ai_draw_operations(doc, shapes)

        # 修复可能的DXF问题
        try:
            auditor = doc.audit()
            if auditor.has_errors:
                LOG.info("DXF audit fixed %d issues", len(auditor.errors))
        except Exception as e:
            LOG.warning("DXF audit warning: %s", e)

        # 保存修改后的DXF
        edited_dxf = job_dir / "edited.dxf"
        doc.saveas(str(edited_dxf))

        # ── 如果目标格式是 DWG，再转换回去 ──────────────────────────────
        # 确定输出文件名：新建文件用 ai_drawing，编辑文件用原名_ai_edited
        base_name = "ai_drawing" if dxf_bytes is None else Path(filename).stem + "_ai_edited"

        if output_format == "dwg":
            dwg_out = job_dir / "output.dwg"
            _convert_dxf_to_dwg(edited_dxf, dwg_out)
            result_bytes = dwg_out.read_bytes()
            result_name = f"{base_name}.dwg"
        else:
            result_bytes = edited_dxf.read_bytes()
            result_name = f"{base_name}.dxf"

        return result_bytes, result_name, draw_results, "ezdxf"

    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _convert_dwg_to_dxf(dwg_path: Path, dxf_path: Path) -> None:
    """用 ODA File Converter 把 DWG 转换为 DXF（输入处理时使用）。"""
    if not Path(ODA_CONVERTER).exists():
        raise RuntimeError(
            "未找到 ODA File Converter，无法处理 DWG 输入文件。"
            f"请安装后确认路径: {ODA_CONVERTER}"
        )
    out_dir = dxf_path.parent / "_oda_out"
    out_dir.mkdir(exist_ok=True)
    cmd = [
        ODA_CONVERTER,
        str(dwg_path.parent),  # 输入目录
        str(out_dir),          # 输出目录
        "ACAD2018",            # 目标 DXF 版本
        "DXF",                 # 输出格式
        "0",                   # 是否递归子目录
        "1",                   # 是否审计
        dwg_path.name,         # 输入文件名
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    produced = out_dir / (dwg_path.stem + ".dxf")
    if not produced.exists():
        raise RuntimeError(f"DWG→DXF 转换失败: {proc.stderr or proc.stdout}")
    shutil.move(str(produced), str(dxf_path))




async def _export_async(
    dxf_bytes: bytes,
    filename: str,
    edits: list[dict],
    output_format: str,
    progress_cb,
) -> tuple[bytes, str]:
    """
    异步执行 DXF/DWG 导出任务。

    流程：
      1. 把客户端上传的 DXF/DWG 字节写入临时文件
      2. 若为 DWG 则先转为 DXF（需要 ODA File Converter）
      3. 用 ezdxf 应用编辑操作（移动/删除/改文字/改图层/改颜色）
      4. 若目标格式是 DWG 则再次转换
      5. 读取结果文件字节并返回

    参数
    ----
    dxf_bytes     : 客户端上传的原始文件字节（DXF 或 DWG）
    filename      : 原始文件名，用于推断格式和生成输出文件名
    edits         : 编辑操作列表（见 _apply_edits_and_export 注释）
    output_format : 输出格式，"dxf" 或 "dwg"
    progress_cb   : async callable(pct: int, msg: str)

    返回
    ----
    (file_bytes, output_filename) : 处理后文件的原始字节 + 推荐保存的文件名

    异常
    ----
    RuntimeError           : 处理失败
    asyncio.CancelledError : 任务被取消
    """
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    src_suffix = Path(filename).suffix.lower()
    src_path = job_dir / f"input{src_suffix}"
    src_path.write_bytes(dxf_bytes)

    try:
        await progress_cb(10, "接收文件，准备处理...")

        # ── 如果输入是 DWG，先转换为 DXF ──────────────────────────────
        if src_suffix == ".dwg":
            await progress_cb(20, "DWG → DXF 转换中...")
            dxf_input = job_dir / "input_converted.dxf"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: _convert_dxf_to_dwg(src_path, dxf_input),  # 复用 ODA，反向调用
            )
            # 实际上需要 DWG→DXF，这里调用 ogr2ogr 做转换
            proc = subprocess.run(
                [OGR2OGR, "-f", "DXF", str(dxf_input), str(src_path), "-overwrite"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"DWG→DXF 转换失败: {proc.stderr}")
        else:
            dxf_input = src_path

        await progress_cb(30, "应用编辑操作...")

        # ── 应用编辑，输出中间 DXF ──────────────────────────────────
        dxf_out = job_dir / "output.dxf"
        async with EXPORT_SEMAPHORE:
            loop = asyncio.get_event_loop()
            t0 = time.monotonic()
            await loop.run_in_executor(
                None,
                lambda: _apply_edits_and_export(dxf_input, dxf_out, edits),
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

        await progress_cb(75, f"编辑完成 ({elapsed_ms}ms)，准备输出...")

        stem = Path(filename).stem

        # ── 输出 DXF ─────────────────────────────────────────────────
        if output_format == "dxf":
            await progress_cb(95, "打包 DXF 文件...")
            result_bytes = dxf_out.read_bytes()
            result_name  = f"{stem}.edited.dxf"

        # ── 输出 DWG ─────────────────────────────────────────────────
        elif output_format == "dwg":
            await progress_cb(80, "DXF → DWG 转换中（ODA）...")
            dwg_out = job_dir / f"{stem}.edited.dwg"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: _convert_dxf_to_dwg(dxf_out, dwg_out),
            )
            await progress_cb(95, "打包 DWG 文件...")
            result_bytes = dwg_out.read_bytes()
            result_name  = dwg_out.name

        else:
            raise ValueError(f"不支持的输出格式: {output_format!r}，支持: dxf | dwg")

        _export_async._last_elapsed_ms = elapsed_ms
        return result_bytes, result_name

    finally:
        # 无论成功失败都清理临时目录
        shutil.rmtree(job_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# PNG 渲染（PyQGIS 子进程）
# ---------------------------------------------------------------------------

def _build_png_script(src: str, out: str, p: dict, w: int, h: int, view: dict | None = None) -> str:
    """
    生成独立 PyQGIS 渲染脚本，输出 PNG 到 out 路径。

    view 参数（可选，不传则自动适配数据范围）
    -----------------------------------------
    方式一：指定 bbox（推荐，精确控制画面范围）
      { "bbox": [xmin, ymin, xmax, ymax] }   坐标单位与数据一致（度/米等）

    方式二：指定中心点 + 比例尺
      { "center": [x, y], "scale": 50000 }   scale 为地图比例尺分母

    方式三：指定中心点 + 半径
      { "center": [x, y], "radius": 1000 }   radius 单位与数据坐标单位一致
    """
    import json as _json

    def _hex(h6, op=1.0):
        h6 = h6.lstrip("#")
        r, g, b = int(h6[0:2],16), int(h6[2:4],16), int(h6[4:6],16)
        return r, g, b, int(op*255)

    bg   = str(p.get("background",   "#ffffff") or "#ffffff")
    fill = str(p.get("fill_color",   "#4a90d9") or "#4a90d9")
    fop  = float(p.get("fill_opacity", 0.5) or 0.5)
    strk = str(p.get("stroke_color", "#1a5276") or "#1a5276")
    sw   = float(p.get("stroke_width", 0.8) or 0.8)
    lf   = str(p.get("label_field",  "") or "")
    ls   = float(p.get("label_size", 9) or 9)
    lc   = str(p.get("label_color",  "#000000") or "#000000")

    br,bg_,bb,_  = _hex(bg)
    fr,fg,fb,fa  = _hex(fill, fop)
    sr,sg,sb,_   = _hex(strk)
    lr,lg,lb,_   = _hex(lc)

    # ---- 视图范围代码段：根据 view 参数生成不同的范围设置逻辑 ----
    view = view or {}
    if "bbox" in view:
        bx = view["bbox"]  # [xmin, ymin, xmax, ymax]
        view_code = f"""
from qgis.core import QgsRectangle
ext = QgsRectangle({bx[0]}, {bx[1]}, {bx[2]}, {bx[3]})
# 调整宽高比以防止变形
ro={w}/{h}; re=ext.width()/(ext.height() or 1e-9)
if ro>re:
    ex=ext.height()*ro-ext.width(); ext.setXMinimum(ext.xMinimum()-ex/2); ext.setXMaximum(ext.xMaximum()+ex/2)
else:
    ex=ext.width()/ro-ext.height(); ext.setYMinimum(ext.yMinimum()-ex/2); ext.setYMaximum(ext.yMaximum()+ex/2)
"""
    elif "center" in view and "scale" in view:
        cx, cy = view["center"]
        sc = float(view["scale"])
        view_code = f"""
from qgis.core import QgsRectangle
# scale 为比例尺分母，按屏幕 DPI=96 计算半宽
half_w = {w} / 96 * 0.0254 * {sc} / 2
half_h = {h} / 96 * 0.0254 * {sc} / 2
ext = QgsRectangle({cx}-half_w, {cy}-half_h, {cx}+half_w, {cy}+half_h)
"""
    elif "center" in view and "radius" in view:
        cx, cy = view["center"]
        r = float(view["radius"])
        view_code = f"""
from qgis.core import QgsRectangle
ext = QgsRectangle({cx}-{r}, {cy}-{r}, {cx}+{r}, {cy}+{r})
ro={w}/{h}
if ro>1:
    ext.setXMinimum(ext.xMinimum()-(ext.height()*ro-ext.width())/2)
    ext.setXMaximum(ext.xMaximum()+(ext.height()*ro-ext.width())/2)
else:
    ext.setYMinimum(ext.yMinimum()-(ext.width()/ro-ext.height())/2)
    ext.setYMaximum(ext.yMaximum()+(ext.width()/ro-ext.height())/2)
"""
    else:
        # 默认：自动适配数据范围
        view_code = f"""
ext=layer.extent(); ext.grow(ext.width()*0.05)
ro={w}/{h}; re=ext.width()/(ext.height() or 1e-9)
if ro>re:
    ex=ext.height()*ro-ext.width(); ext.setXMinimum(ext.xMinimum()-ex/2); ext.setXMaximum(ext.xMaximum()+ex/2)
else:
    ex=ext.width()/ro-ext.height(); ext.setYMinimum(ext.yMinimum()-ex/2); ext.setYMaximum(ext.yMaximum()+ex/2)
"""

    return f"""
import sys, os, json
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python")
sys.path.insert(0,"/Applications/QGIS-final-4_0_2.app/Contents/Resources/python/plugins")
os.environ.setdefault("QGIS_PREFIX_PATH","{QGIS_PREFIX}")
os.environ.setdefault("PROJ_DATA","{QGIS_PREFIX}/../Resources/qgis/proj")
from qgis.core import (QgsApplication,QgsVectorLayer,QgsMapSettings,
    QgsMapRendererParallelJob,QgsSingleSymbolRenderer,
    QgsSimpleFillSymbolLayer,QgsSimpleLineSymbolLayer,QgsSimpleMarkerSymbolLayer,
    QgsFillSymbol,QgsLineSymbol,QgsMarkerSymbol,
    QgsPalLayerSettings,QgsTextFormat,QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QSize,QEventLoop
from qgis.PyQt.QtGui import QColor,QFont
app=QgsApplication([],False)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"],True)
app.initQgis()
layer=QgsVectorLayer({_json.dumps(src)},"layer","ogr")
if not layer.isValid():
    print(json.dumps({{"error":"Invalid layer"}})); app.exitQgis(); sys.exit(1)
gt=layer.geometryType()
if gt==2:
    sl=QgsSimpleFillSymbolLayer()
    sl.setFillColor(QColor({fr},{fg},{fb},{fa}))
    sl.setStrokeColor(QColor({sr},{sg},{sb})); sl.setStrokeWidth({sw})
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol([sl])))
elif gt==1:
    sl=QgsSimpleLineSymbolLayer()
    sl.setColor(QColor({sr},{sg},{sb})); sl.setWidth({sw})
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol([sl])))
else:
    sl=QgsSimpleMarkerSymbolLayer()
    sl.setColor(QColor({fr},{fg},{fb},{fa})); sl.setSize(4)
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol([sl])))
if {bool(lf)}:
    pal=QgsPalLayerSettings(); pal.fieldName={_json.dumps(str(lf))}; pal.enabled=True
    fmt=QgsTextFormat(); fmt.setColor(QColor({lr},{lg},{lb}))
    f=QFont("PingFang SC"); f.setPointSizeF({ls}); fmt.setFont(f); pal.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal)); layer.setLabelsEnabled(True)
settings=QgsMapSettings()
settings.setOutputSize(QSize({w},{h}))
settings.setBackgroundColor(QColor({br},{bg_},{bb},255))
{view_code}
settings.setExtent(ext); settings.setLayers([layer])
for fn in("Antialiasing","DrawLabeling","UseAdvancedEffects"):
    flag=getattr(getattr(QgsMapSettings,"Flag",QgsMapSettings),fn,None) or getattr(QgsMapSettings,fn,None)
    if flag: settings.setFlag(flag,True)
job=QgsMapRendererParallelJob(settings)
loop=QEventLoop(); job.finished.connect(loop.quit); job.start()
(getattr(loop,"exec",None) or getattr(loop,"exec_"))()
job.renderedImage().save({_json.dumps(out)},"PNG")
print(json.dumps({{"ok":True}}))
app.exitQgis()
"""

def _resolve_src(file_id: str) -> Path:
    """返回用于渲染的数据源路径（优先原始文件，GeoJSON 为空则回退）。"""
    store_dir    = GEOJSON_STORE / file_id
    geojson_path = store_dir / "data.geojson"
    if not store_dir.exists():
        raise FileNotFoundError(f"file_id {file_id!r} 不存在")
    if geojson_path.exists() and geojson_path.stat().st_size >= 200:
        return geojson_path
    for f in store_dir.iterdir():
        if f.suffix.lower() not in (".json", ".geojson") and f.is_file():
            LOG.info("GeoJSON empty, using original file: %s", f.name)
            return f
    return geojson_path


def _run_render_script(src: Path, out: Path, params: dict,
                       w: int, h: int, view: dict | None) -> subprocess.CompletedProcess:
    """同步执行 PyQGIS 渲染脚本（在 executor 中调用）。"""
    script = _build_png_script(str(src), str(out), params, w, h, view)
    return subprocess.run(
        [QGIS_PYTHON, "-c", script],
        capture_output=True, text=True,
        timeout=EXPORT_TIMEOUT_SECONDS,
    )


async def _render_png_async(
    file_id: str,
    params: dict,
    width: int,
    height: int,
    progress_cb,
    view: dict | None = None,
    *,
    result_cb=None,
) -> bytes:
    """
    流式两阶段 PyQGIS 渲染。

    阶段一（~0.5s）：先渲染低分辨率预览图，通过 result_cb 立即推给客户端。
    阶段二（~1-3s）：再渲染全分辨率图，作为最终结果返回并推送。

    参数
    ----
    file_id    : POST /data/upload 返回的文件 ID
    params     : 样式参数字典
    width/height: 最终输出分辨率
    progress_cb : async(pct, msg) 进度回调
    view        : 视图范围，None 则自动适配
    result_cb   : async(png_bytes, is_preview) 每阶段结果回调，is_preview=True 为预览帧
    """
    src_path = _resolve_src(file_id)
    loop     = asyncio.get_event_loop()
    job_dir  = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    try:
        await progress_cb(5, "准备渲染...")

        async with EXPORT_SEMAPHORE:
            t0 = time.monotonic()

            # ── 阶段一：低分辨率预览（1/4 尺寸，快速出图）────────────────
            pre_w = max(160, width  // 4)
            pre_h = max(90,  height // 4)
            pre_out = job_dir / "preview.png"

            await progress_cb(10, "渲染预览帧...")
            proc1 = await loop.run_in_executor(
                None,
                lambda: _run_render_script(src_path, pre_out, params, pre_w, pre_h, view),
            )
            if pre_out.exists():
                preview_bytes = pre_out.read_bytes()
                await progress_cb(30, f"预览就绪 ({pre_w}×{pre_h})，渲染高清图...")
                if result_cb:
                    await result_cb(preview_bytes, True)   # 立即推预览

            # ── 阶段二：全分辨率最终图 ────────────────────────────────────
            full_out = job_dir / "full.png"
            proc2 = await loop.run_in_executor(
                None,
                lambda: _run_render_script(src_path, full_out, params, width, height, view),
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

        await progress_cb(95, f"高清图就绪 ({elapsed_ms}ms)...")

        if not full_out.exists():
            err = proc2.stderr or proc2.stdout or proc1.stderr or proc1.stdout
            raise RuntimeError(f"PyQGIS 渲染失败:\n{err}")

        png_bytes = full_out.read_bytes()
        await progress_cb(100, "完成")
        _render_png_async._last_elapsed_ms = elapsed_ms
        return png_bytes

    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/render")
async def ws_render_endpoint(ws: WebSocket):
    """
    WebSocket DXF/DWG 导出端点。

    完整协议见 ws_protocol.md。
    简要流程：
      1. 客户端连接后收到 { type: "connected", client_id, total_clients }
      2. 客户端发送 { type: "export", file_data, filename, edits, output_format }
      3. 服务端推送多条 { type: "progress", pct, msg }
      4. 服务端推送 { type: "result", format: "dxf_base64"|"dwg_base64", filename, data, size_bytes, elapsed_ms }

    export 消息参数
    --------------
    file_data     string  必填  原始 DXF 或 DWG 文件的 Base64 编码内容
                               （JavaScript: btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)))）
    filename      string  必填  原始文件名，如 "drawing.dxf" 或 "plan.dwg"，用于格式推断
    output_format string  可选  输出格式: "dxf"（默认）或 "dwg"（需要 ODA File Converter）
    edits         array   可选  编辑操作列表，为空时原样导出，格式如下：
      [
        { "op": "move",     "handle": "1A2B", "dx": 10.0, "dy": 5.0 },
        { "op": "delete",   "handle": "3C4D" },
        { "op": "set_text", "handle": "5E6F", "text": "新标注" },
        { "op": "set_layer","handle": "7A8B", "layer": "图层名" },
        { "op": "set_color","handle": "9C0D", "color": 1 }
      ]
    """
    cid = await manager.connect(ws)

    # 当前客户端正在执行的渲染任务（同一客户端同时只有一个）
    current_task = None

    async def send(data: dict):
        """向本客户端发送 JSON 消息。"""
        await manager.send(cid, data)

    async def broadcast(data: dict):
        """向所有客户端广播 JSON 消息（用于监控）。"""
        for other_cid in manager.list_clients():
            await manager.send(other_cid, data)

    async def progress(pct: int, msg: str):
        """推送渲染进度（pct: 0-100）。"""
        await send({"type": "progress", "pct": pct, "msg": msg})

    try:
        # ── 握手：发送连接成功消息 ──────────────────────────────────────────
        await send({
            "type": "connected",
            "client_id": cid,          # 本连接的唯一标识，用于日志追踪
            "total_clients": manager.count,
            "msg": "WebSocket 渲染服务就绪",
        })

        # ── 主消息循环 ────────────────────────────────────────────────────
        while True:
            try:
                # HEARTBEAT_TIMEOUT_SECONDS 秒内无消息则发送服务端 ping
                raw = await asyncio.wait_for(
                    ws.receive_text(),
                    timeout=float(HEARTBEAT_TIMEOUT_SECONDS),
                )
            except asyncio.TimeoutError:
                # 连接空闲超时，发送服务端心跳探测
                await send({"type": "ping_from_server"})
                continue

            # 解析 JSON 消息
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send({
                    "type": "error",
                    "code": ErrCode.INVALID_PARAMS,
                    "msg": "消息必须是合法的 JSON 字符串",
                })
                continue

            msg_type = msg.get("type", "")

            # ── 处理 ping ────────────────────────────────────────────────
            if msg_type == "ping":
                # 客户端心跳，回复 pong + 时间戳
                await send({"type": "pong", "ts": time.time()})
                continue

            # ── 处理 cancel ──────────────────────────────────────────────
            if msg_type == "cancel":
                if current_task and not current_task.done():
                    current_task.cancel()
                    await send({"type": "cancelled"})
                continue

            # ── 处理 export ──────────────────────────────────────────────
            if msg_type == "export":

                # --- 必填：文件数据（Base64 编码的 DXF 或 DWG 原始内容） ---
                file_data_b64 = msg.get("file_data", "")
                if not file_data_b64:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  "缺少必填参数 file_data（DXF/DWG 文件的 Base64 内容）",
                    })
                    continue

                try:
                    file_bytes = base64.b64decode(file_data_b64)
                except Exception:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  "file_data 不是合法的 Base64 字符串",
                    })
                    continue

                if len(file_bytes) > MAX_FILE_BYTES:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  f"文件过大（{len(file_bytes)//1024//1024}MB），上限 {MAX_FILE_BYTES//1024//1024}MB",
                    })
                    continue

                # --- 必填：原始文件名（用于格式推断和输出命名） ---
                filename = msg.get("filename", "output.dxf").strip()
                if not filename:
                    filename = "output.dxf"

                # --- 可选：输出格式，默认 dxf ---
                # "dxf" — 直接用 ezdxf 输出，无需额外工具
                # "dwg" — 需要安装 ODA File Converter
                output_format = msg.get("output_format", "dxf").lower().strip()
                if output_format not in ("dxf", "dwg"):
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  f"output_format 必须是 'dxf' 或 'dwg'，收到: {output_format!r}",
                    })
                    continue

                # 检查 DWG 导出依赖；没有 ODA 时自动降级为 DXF
                if output_format == "dwg" and not Path(ODA_CONVERTER).exists():
                    LOG.info("DWG output requested but ODA File Converter is unavailable; using DXF output")
                    output_format = "dxf"

                # --- 可选：编辑操作列表 ---
                # 为空时原样导出（格式转换），有内容时应用后再导出
                # 格式说明见 ws_render_endpoint docstring
                edits = msg.get("edits", [])
                if not isinstance(edits, list):
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  "edits 必须是数组（可以为空数组 []）",
                    })
                    continue

                # --- 取消旧任务 ---
                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                # --- 创建导出协程任务（闭包捕获参数，避免循环变量污染） ---
                async def do_export(
                    _bytes=file_bytes,
                    _fname=filename,
                    _edits=edits,
                    _fmt=output_format,
                ):
                    try:
                        await send({"type": "started", "filename": _fname, "output_format": _fmt})

                        result_bytes, result_name = await _export_async(
                            _bytes, _fname, _edits, _fmt, progress
                        )

                        elapsed_ms = getattr(_export_async, "_last_elapsed_ms", 0)
                        b64 = base64.b64encode(result_bytes).decode()

                        await send({
                            "type":       "result",
                            # format 固定为 "dxf_base64" 或 "dwg_base64"
                            # 客户端用 atob() 解码后另存为对应格式文件
                            "format":     f"{_fmt}_base64",
                            "filename":   result_name,   # 推荐保存的文件名
                            "data":       b64,           # Base64 编码的完整文件内容
                            "size_bytes": len(result_bytes),  # 文件字节大小
                            "elapsed_ms": elapsed_ms,    # 总处理耗时毫秒
                            "edit_count": len(_edits),   # 应用的编辑操作数
                        })

                    except asyncio.CancelledError:
                        LOG.info("export cancelled for client=%s", cid)

                    except subprocess.TimeoutExpired:
                        LOG.error("export timeout for client=%s", cid)
                        await send({
                            "type": "error",
                            "code": ErrCode.EXPORT_TIMEOUT,
                            "msg":  f"导出超时（>{EXPORT_TIMEOUT_SECONDS}s）",
                        })

                    except Exception as e:
                        LOG.exception("export error for client=%s", cid)
                        await send({
                            "type": "error",
                            "code": ErrCode.EXPORT_FAILED,
                            "msg":  str(e),
                        })

                # create_task 让导出在后台运行，不阻塞消息循环
                current_task = asyncio.create_task(do_export())
                continue

            # ── 处理 ai_edit（AI实时绘图编辑）───────────────────────────────────
            if msg_type == "ai_edit":
                # --- 可选：文件数据（不传则创建新文件） ---
                file_data_b64 = msg.get("file_data", "")
                file_bytes = None  # None 表示创建新文件

                if file_data_b64:
                    try:
                        file_bytes = base64.b64decode(file_data_b64)
                    except Exception:
                        await send({
                            "type": "error",
                            "code": ErrCode.INVALID_PARAMS,
                            "msg": "file_data 不是合法的 Base64 字符串",
                        })
                        continue

                    if len(file_bytes) > MAX_FILE_BYTES:
                        await send({
                            "type": "error",
                            "code": ErrCode.INVALID_PARAMS,
                            "msg": f"文件过大（{len(file_bytes)//1024//1024}MB），上限 {MAX_FILE_BYTES//1024//1024}MB",
                        })
                        continue

                # --- 可选：原始文件名（不传则自动生成 ai_drawing.dxf） ---
                filename = msg.get("filename", "").strip()
                if not filename:
                    filename = "ai_drawing.dxf"

                # --- 可选：shapes（绘图指令列表），不传则默认画圆 ---
                shapes = msg.get("shapes", [])
                if not isinstance(shapes, list):
                    shapes = []

                # 如果 shapes 为空，默认画一个圆
                if len(shapes) == 0:
                    shapes = [
                        {
                            "id": "default_circle",
                            "type": "circle",
                            "geometry": {"cx": 100.0, "cy": 100.0, "r": 50.0},
                            "style": {"stroke_color": "#FF0000"}
                        }
                    ]

                # --- 可选：输出格式，默认 dxf ---
                output_format = msg.get("output_format", "dxf").lower().strip()
                if output_format not in ("dxf", "dwg"):
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg": f"output_format 必须是 'dxf' 或 'dwg'，收到: {output_format!r}",
                    })
                    continue

                # --- 可选：指定绘图引擎 ---
                engine = msg.get("engine", None)  # None=auto, "autocad", "ezdxf"

                # 检查引擎可用性
                if engine == "ezdxf" and not EZDXF_AVAILABLE:
                    await send({
                        "type": "error",
                        "code": "EZDXF_NOT_INSTALLED",
                        "msg": "AI绘图功能需要安装 ezdxf。运行: pip install ezdxf",
                    })
                    continue

                if engine == "autocad" and not AUTOCAD_AVAILABLE:
                    if EZDXF_AVAILABLE:
                        LOG.info("AutoCAD COM requested but unavailable; falling back to ezdxf")
                        engine = "ezdxf"
                    else:
                        await send({
                            "type": "error",
                            "code": "EZDXF_NOT_INSTALLED",
                            "msg": "当前环境没有 AutoCAD COM，已尝试切换 ezdxf，但 ezdxf 未安装。运行: pip install ezdxf",
                        })
                        continue

                # 检查 DWG 导出依赖；没有 ODA 时自动降级为 DXF
                if output_format == "dwg" and not Path(ODA_CONVERTER).exists():
                    LOG.info("DWG output requested but ODA File Converter is unavailable; using DXF output")
                    output_format = "dxf"

                # --- 取消旧任务 ---
                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                # --- 创建 AI 编辑协程任务 ---
                async def do_ai_edit(
                    _bytes=file_bytes,
                    _fname=filename,
                    _shapes=shapes,
                    _fmt=output_format,
                    _engine=engine,
                ):
                    try:
                        # 广播给所有客户端（包括监控页面）
                        await broadcast({
                            "type": "started",
                            "filename": _fname,
                            "output_format": _fmt,
                            "shape_count": len(_shapes),
                            "engine_requested": _engine,
                        })

                        result_bytes, result_name, draw_results, engine_used = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: _ai_edit_and_export(_bytes, _fname, _shapes, _fmt, _engine)
                        )

                        # 统计结果
                        success_count = sum(1 for r in draw_results if r.get("status") == "created")
                        error_count = len(draw_results) - success_count

                        b64 = base64.b64encode(result_bytes).decode()

                        # 广播给所有客户端（包括监控页面）
                        await broadcast({
                            "type": "result",
                            "status": 200,  # 完成状态码
                            "format": f"{_fmt}_base64",
                            "filename": result_name,
                            "data": b64,
                            "size_bytes": len(result_bytes),
                            "shape_count": len(_shapes),
                            "success_count": success_count,
                            "error_count": error_count,
                            "engine_used": engine_used,  # 实际使用的引擎
                            "details": draw_results,  # 每个shape的详细结果
                        })

                    except asyncio.CancelledError:
                        LOG.info("ai_edit cancelled for client=%s", cid)

                    except RuntimeError as e:
                        await send({
                            "type": "error",
                            "code": "AI_EDIT_FAILED",
                            "msg": str(e),
                        })

                    except Exception as e:
                        LOG.exception("ai_edit error for client=%s", cid)
                        await send({
                            "type": "error",
                            "code": "AI_EDIT_FAILED",
                            "msg": str(e),
                        })

                current_task = asyncio.create_task(do_ai_edit())
                continue

            # ── 处理 preview（DXF 渲染为 PNG 预览）───────────────────────────────
            if msg_type == "preview":
                # 上传 DXF 文件后渲染为 PNG 图片预览
                file_data_b64 = msg.get("file_data", "")
                width = msg.get("width", 800)
                height = msg.get("height", 600)
                
                if not file_data_b64:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg": "缺少 file_data 参数",
                    })
                    continue
                
                try:
                    import tempfile
                    import io
                    
                    # 解码 base64 (base64 already imported at module level)
                    if isinstance(file_data_b64, str):
                        file_bytes = base64.b64decode(file_data_b64)
                    else:
                        file_bytes = base64.b64decode(file_data_b64.encode('utf-8'))
                    
                    LOG.info(f"DEBUG: file_bytes type={type(file_bytes)}, len={len(file_bytes)}")
                    
                    # 方法1: 尝试直接用 ezdxf.read 读取 BytesIO
                    try:
                        doc = ezdxf.read(io.BytesIO(file_bytes))
                        LOG.info("DEBUG: Method 1 (BytesIO) succeeded")
                    except Exception as e1:
                        LOG.info(f"DEBUG: Method 1 failed: {e1}")
                        # 方法2: 写入临时文件，用 readfile 读取
                        temp_path = None
                        try:
                            # DXF 是文本文件，解码为字符串
                            dxf_text = file_bytes.decode('utf-8', errors='ignore')
                            LOG.info(f"DEBUG: Decoded to text, len={len(dxf_text)}")
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False, encoding='utf-8') as f:
                                f.write(dxf_text)
                                temp_path = f.name
                            LOG.info(f"DEBUG: Written to temp file: {temp_path}")
                            doc = ezdxf.readfile(temp_path)
                            LOG.info("DEBUG: Method 2 (readfile) succeeded")
                        except Exception as e2:
                            LOG.info(f"DEBUG: Method 2 also failed: {e2}")
                            raise
                        finally:
                            if temp_path and os.path.exists(temp_path):
                                os.unlink(temp_path)
                    
                    # 渲染为 PNG
                    png_bytes = _render_dxf_to_png(doc, width, height)
                    
                    if png_bytes:
                        b64_png = base64.b64encode(png_bytes).decode('utf-8')
                        await send({
                            "type": "preview",
                            "format": "png_base64",
                            "data": b64_png,
                            "width": width,
                            "height": height,
                        })
                        LOG.info("Rendered DXF preview for client %s", cid)
                    else:
                        await send({
                            "type": "error",
                            "code": "RENDER_FAILED",
                            "msg": "DXF 渲染失败，请检查 matplotlib 是否安装",
                        })
                        
                except Exception as e:
                    LOG.exception("Preview render failed for client %s", cid)
                    await send({
                        "type": "error",
                        "code": "PREVIEW_FAILED",
                        "msg": str(e),
                    })
                continue

            # ── 处理 parse（解析 DXF/DWG 返回结构化实体数据）────────────────────
            if msg_type == "parse":
                file_data_b64 = msg.get("file_data", "")
                filename = msg.get("filename", "upload.dxf").strip()

                if not file_data_b64:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg": "缺少 file_data 参数",
                    })
                    continue

                try:
                    import io as _io

                    file_bytes = base64.b64decode(file_data_b64)
                    suffix = Path(filename).suffix.lower()

                    # DWG 先转 DXF
                    if suffix == ".dwg":
                        if not Path(ODA_CONVERTER).exists():
                            await send({
                                "type": "error",
                                "code": "DWG_NOT_SUPPORTED",
                                "msg": "DWG 解析需要安装 ODA File Converter",
                            })
                            continue
                        job_dir = WORK_DIR / uuid.uuid4().hex
                        job_dir.mkdir()
                        try:
                            dwg_path = job_dir / filename
                            dwg_path.write_bytes(file_bytes)
                            dxf_path = job_dir / (Path(filename).stem + ".dxf")
                            _convert_dwg_to_dxf(dwg_path, dxf_path)
                            doc = ezdxf.readfile(str(dxf_path))
                        finally:
                            shutil.rmtree(job_dir, ignore_errors=True)
                    else:
                        import tempfile as _tmp

                        # ── 步骤1：嗅探文件头，确定原始编码 ───────────────
                        def _sniff_dxf_encoding(raw: bytes) -> str:
                            """
                            检测 DXF 文件实际编码：
                            1. 优先尝试 UTF-8 严格解码（成功则必定是 UTF-8）
                            2. 再查 $DWGCODEPAGE 变量
                            3. 兜底 GBK
                            """
                            codepage_map = {
                                "ANSI_936": "gbk",
                                "ANSI_950": "big5",
                                "ANSI_932": "shift_jis",
                                "ANSI_949": "euc_kr",
                                "ANSI_1252": "cp1252",
                                "UTF-8": "utf-8",
                                "UTF8": "utf-8",
                            }
                            # 步骤1：UTF-8 严格验证（UTF-8 字节序列有严格规则，GBK 通常无法通过）
                            try:
                                raw.decode("utf-8")
                                return "utf-8"
                            except UnicodeDecodeError:
                                pass
                            # 步骤2：扫描 $DWGCODEPAGE
                            import re as _re2
                            head_str = raw[:4096].decode("gbk", errors="ignore")
                            m = _re2.search(r'\$DWGCODEPAGE[^\n]*\n\s*\d+\n\s*(\S+)', head_str)
                            if m:
                                cp = m.group(1).strip().upper()
                                return codepage_map.get(cp, "gbk")
                            # 步骤3：兜底 GBK
                            return "gbk"

                        file_enc = _sniff_dxf_encoding(file_bytes)
                        LOG.info("Parse: detected DXF encoding=%s", file_enc)

                        # ── 步骤2：写二进制临时文件，让 ezdxf 用原始编码读取 ──
                        # 不做任何预解码，ezdxf 会按 $DWGCODEPAGE 自动处理
                        with _tmp.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
                            f.write(file_bytes)
                            _tp = f.name
                        try:
                            # 强制指定检测到的编码，覆盖 ezdxf 的自动检测
                            doc = ezdxf.readfile(_tp, encoding=file_enc)
                            LOG.info("Parse: ezdxf opened with encoding=%s, doc.encoding=%s",
                                     file_enc, getattr(doc, 'encoding', '?'))
                        except Exception:
                            doc = ezdxf.readfile(_tp)
                        finally:
                            try: os.unlink(_tp)
                            except Exception: pass

                    # ACI 颜色索引 → HEX（常用色）
                    _ACI_HEX = {
                        1:"#FF0000", 2:"#FFFF00", 3:"#00FF00", 4:"#00FFFF",
                        5:"#0000FF", 6:"#FF00FF", 7:"#FFFFFF", 8:"#808080",
                        9:"#C0C0C0", 30:"#FF7F00", 50:"#FFFF00", 70:"#7FFF00",
                        130:"#00FFFF", 150:"#007FFF", 170:"#0000FF",
                    }
                    def aci_to_hex(c):
                        return _ACI_HEX.get(int(c), "#FFFFFF")

                    import re as _re
                    def clean_dxf_text(s: str) -> str:
                        """清理 DXF 文字控制码，还原可读文字"""
                        if not s:
                            return s
                        # 如果含 surrogate 字符（ezdxf 编码失败残留），尝试重新 GBK 解码
                        if any('\uD800' <= c <= '\uDFFF' for c in s):
                            try:
                                s = s.encode('utf-16', 'surrogatepass').decode('utf-16')
                            except Exception:
                                pass
                            try:
                                s = s.encode('raw_unicode_escape').decode('gbk', errors='replace')
                            except Exception:
                                pass
                        # MTEXT 格式控制码（大括号分组、字体切换等）
                        s = _re.sub(r'\\[fFpPlLqQsS][^;]*;', '', s)   # \F字体; \P换段等
                        s = _re.sub(r'\{[\\][^}]*\}', '', s)            # {\...}
                        s = _re.sub(r'\\[AaWwTtOo][^;]*;', '', s)       # 对齐/宽度等
                        s = _re.sub(r'\{|\}', '', s)                    # 剩余大括号
                        # 常见特殊字符控制码
                        s = s.replace('%%d', '°').replace('%%D', '°')
                        s = s.replace('%%c', 'Ø').replace('%%C', 'Ø')
                        s = s.replace('%%p', '±').replace('%%P', '±')
                        s = s.replace('%%u', '').replace('%%U', '')     # 下划线开关
                        s = s.replace('%%o', '').replace('%%O', '')     # 上划线开关
                        s = _re.sub(r'%%\d{3}', '', s)                  # 其他 %%nnn 编码
                        return s.strip()

                    msp = doc.modelspace()
                    shapes = []      # 与 ai_edit shapes 格式完全对齐
                    layers_set = set()
                    idx_counter = [0]

                    def next_id(prefix):
                        idx_counter[0] += 1
                        return f"{prefix}_{idx_counter[0]}"

                    for ent in msp:
                        try:
                            t = ent.dxftype()

                            # ── 公共属性 ──────────────────────────────
                            aci = 7
                            try:
                                v = ent.dxf.color
                                if v and v > 0:
                                    aci = v
                            except Exception:
                                pass
                            color_hex = aci_to_hex(aci)

                            layer = "0"
                            try:
                                layer = ent.dxf.layer or "0"
                            except Exception:
                                pass

                            handle = ""
                            try:
                                handle = str(ent.dxf.handle or "")
                            except Exception:
                                pass

                            # name: 优先取 xdata / 属性块名，否则用 handle
                            name = handle or f"{t}_{idx_counter[0]+1}"

                            layers_set.add(layer)

                            # ── 按类型构建 shape（与 ai_edit shapes 格式一致）──
                            if t == "LINE":
                                s, e_ = ent.dxf.start, ent.dxf.end
                                shapes.append({
                                    "id":          next_id("line"),
                                    "name":        name,
                                    "type":        "AddLine",
                                    "start_point": [s.x, s.y, 0],
                                    "end_point":   [e_.x, e_.y, 0],
                                    "color":       color_hex,
                                    "layer":       layer,
                                    "handle":      handle,
                                })

                            elif t == "CIRCLE":
                                c_ = ent.dxf.center
                                shapes.append({
                                    "id":     next_id("circle"),
                                    "name":   name,
                                    "type":   "AddCircle",
                                    "center": [c_.x, c_.y, 0],
                                    "radius": ent.dxf.radius,
                                    "color":  color_hex,
                                    "layer":  layer,
                                    "handle": handle,
                                })

                            elif t == "ARC":
                                c_ = ent.dxf.center
                                shapes.append({
                                    "id":          next_id("arc"),
                                    "name":        name,
                                    "type":        "AddArc",
                                    "center":      [c_.x, c_.y, 0],
                                    "radius":      ent.dxf.radius,
                                    "start_angle": ent.dxf.start_angle,
                                    "end_angle":   ent.dxf.end_angle,
                                    "color":       color_hex,
                                    "layer":       layer,
                                    "handle":      handle,
                                })

                            elif t in ("LWPOLYLINE", "POLYLINE"):
                                try:
                                    pts = [[p[0], p[1], 0] for p in ent.get_points()]
                                except Exception:
                                    pts = [[v.dxf.location.x, v.dxf.location.y, 0] for v in ent.vertices]
                                closed = False
                                try:
                                    closed = bool(ent.closed)
                                except Exception:
                                    pass
                                shapes.append({
                                    "id":     next_id("poly"),
                                    "name":   name,
                                    "type":   "AddPolyline",
                                    "points": pts,
                                    "closed": closed,
                                    "color":  color_hex,
                                    "layer":  layer,
                                    "handle": handle,
                                })

                            elif t == "ELLIPSE":
                                c_ = ent.dxf.center
                                ma = ent.dxf.major_axis
                                shapes.append({
                                    "id":           next_id("ellipse"),
                                    "name":         name,
                                    "type":         "AddEllipse",
                                    "center":       [c_.x, c_.y, 0],
                                    "major_axis":   [ma.x, ma.y, 0],
                                    "radius_ratio": ent.dxf.ratio,
                                    "color":        color_hex,
                                    "layer":        layer,
                                    "handle":       handle,
                                })

                            elif t == "TEXT":
                                ins = ent.dxf.insert
                                shapes.append({
                                    "id":           next_id("text"),
                                    "name":         name,
                                    "type":         "AddText",
                                    "text":         clean_dxf_text(ent.dxf.text or ""),
                                    "insert_point": [ins.x, ins.y, 0],
                                    "height":       ent.dxf.height if ent.dxf.hasattr("height") else 2.5,
                                    "rotation":     ent.dxf.rotation if ent.dxf.hasattr("rotation") else 0,
                                    "color":        color_hex,
                                    "layer":        layer,
                                    "handle":       handle,
                                })

                            elif t == "MTEXT":
                                ins = ent.dxf.insert
                                _raw = ent.plain_mtext() if hasattr(ent, "plain_mtext") else (ent.dxf.text or "")
                                shapes.append({
                                    "id":           next_id("mtext"),
                                    "name":         name,
                                    "type":         "AddMText",
                                    "text":         clean_dxf_text(_raw),
                                    "insert_point": [ins.x, ins.y, 0],
                                    "height":       ent.dxf.char_height if ent.dxf.hasattr("char_height") else 2.5,
                                    "rotation":     ent.dxf.rotation if ent.dxf.hasattr("rotation") else 0,
                                    "color":        color_hex,
                                    "layer":        layer,
                                    "handle":       handle,
                                })

                            elif t == "SPLINE":
                                try:
                                    pts = [[p[0], p[1], 0] for p in ent.flattening(0.1)]
                                    shapes.append({
                                        "id":     next_id("spline"),
                                        "name":   name,
                                        "type":   "AddSpline",
                                        "points": pts,
                                        "closed": False,
                                        "color":  color_hex,
                                        "layer":  layer,
                                        "handle": handle,
                                    })
                                except Exception:
                                    pass

                            elif t == "INSERT":
                                ins = ent.dxf.insert
                                block_name = ent.dxf.name or ""
                                shapes.append({
                                    "id":         next_id("insert"),
                                    "name":       block_name or name,
                                    "type":       "AddInsert",
                                    "block_name": block_name,
                                    "insert_point": [ins.x, ins.y, 0],
                                    "scale":      [
                                        ent.dxf.xscale if ent.dxf.hasattr("xscale") else 1,
                                        ent.dxf.yscale if ent.dxf.hasattr("yscale") else 1,
                                        1,
                                    ],
                                    "rotation":   ent.dxf.rotation if ent.dxf.hasattr("rotation") else 0,
                                    "color":      color_hex,
                                    "layer":      layer,
                                    "handle":     handle,
                                })

                            elif t == "DIMENSION":
                                # 标注实体：提取标注文字和位置
                                try:
                                    dim_text = clean_dxf_text(ent.dxf.text or "<>")
                                    if dim_text in ("<>", ""):
                                        # 自动测量值
                                        try:
                                            dim_text = str(round(ent.get_measurement(), 4))
                                        except Exception:
                                            dim_text = "DIM"
                                    mid = ent.dxf.text_midpoint if ent.dxf.hasattr("text_midpoint") else ent.dxf.defpoint
                                    shapes.append({
                                        "id":           next_id("dim"),
                                        "name":         name,
                                        "type":         "AddText",
                                        "text":         dim_text,
                                        "insert_point": [mid.x, mid.y, 0],
                                        "height":       ent.dxf.text_height if ent.dxf.hasattr("text_height") else 2.5,
                                        "rotation":     0,
                                        "color":        color_hex,
                                        "layer":        layer,
                                        "handle":       handle,
                                        "_source":      "DIMENSION",
                                    })
                                except Exception:
                                    pass

                            elif t == "HATCH":
                                # 填充：提取外轮廓作为多段线
                                try:
                                    for path in ent.paths:
                                        if hasattr(path, 'vertices') and len(path.vertices) >= 2:
                                            pts = [[v[0], v[1], 0] for v in path.vertices]
                                            shapes.append({
                                                "id":     next_id("hatch"),
                                                "name":   name,
                                                "type":   "AddPolyline",
                                                "points": pts,
                                                "closed": True,
                                                "color":  color_hex,
                                                "layer":  layer,
                                                "handle": handle,
                                                "_source": "HATCH",
                                            })
                                except Exception:
                                    pass

                            elif t == "SOLID" or t == "TRACE":
                                # 实心四边形
                                try:
                                    pts = [
                                        [ent.dxf.vtx0.x, ent.dxf.vtx0.y, 0],
                                        [ent.dxf.vtx1.x, ent.dxf.vtx1.y, 0],
                                        [ent.dxf.vtx3.x, ent.dxf.vtx3.y, 0],
                                        [ent.dxf.vtx2.x, ent.dxf.vtx2.y, 0],
                                    ]
                                    shapes.append({
                                        "id":     next_id("solid"),
                                        "name":   name,
                                        "type":   "AddPolyline",
                                        "points": pts,
                                        "closed": True,
                                        "color":  color_hex,
                                        "layer":  layer,
                                        "handle": handle,
                                        "_source": t,
                                    })
                                except Exception:
                                    pass

                        except Exception as _e:
                            LOG.debug("Skip entity %s: %s", ent.dxftype(), _e)
                            continue

                    await broadcast({
                        "type":         "parsed",
                        "filename":     filename,
                        "entity_count": len(shapes),
                        "layers":       sorted(layers_set),
                        "shapes":       shapes,       # 与 ai_edit shapes 格式完全一致
                    })
                    LOG.info("Parsed DXF %s → %d shapes, broadcasted to all clients", filename, len(shapes))

                except Exception as e:
                    LOG.exception("Parse failed for client %s", cid)
                    await send({
                        "type": "error",
                        "code": "PARSE_FAILED",
                        "msg": str(e),
                    })
                continue

            # ── 处理 render（PNG 预览）────────────────────────────────────────
            if msg_type == "render":
                # --- 必填： file_id（先调 POST /data/upload 上传矢量文件） ---
                file_id = msg.get("file_id", "").strip()
                if not file_id:
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  "缺少必填参数 file_id。请先调用 POST /data/upload 上传文件。",
                    })
                    continue

                # 分辨率（限制在合法范围内）
                width  = max(64, min(int(msg.get("width",  1280)), 8192))
                height = max(64, min(int(msg.get("height", 720)),  8192))

                # 样式参数（全部可选）
                style_params = msg.get("style", {})
                if not isinstance(style_params, dict):
                    await send({
                        "type": "error",
                        "code": ErrCode.INVALID_PARAMS,
                        "msg":  "style 字段必须是 JSON 对象",
                    })
                    continue

                # 视图范围（可选）—— 3 种方式任选其一，不传则自动适配数据范围
                # 方式一：bbox  { "bbox": [xmin, ymin, xmax, ymax] }
                # 方式二：     { "center": [x, y], "scale": 50000 }  scale 为比例尺分母
                # 方式三：     { "center": [x, y], "radius": 1000 }  radius 单位与数据坐标一致
                view_param = msg.get("view")  # None 或上述字典

                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                async def do_render(
                    _file_id=file_id,
                    _style=style_params,
                    _w=width,
                    _h=height,
                    _view=view_param,
                ):
                    async def _push_frame(frame_bytes: bytes, is_preview: bool):
                        """result_cb：预览帧和最终帧都走这里推送给客户端。"""
                        await send({
                            "type":       "result",
                            "format":     "png_base64",
                            "is_preview": is_preview,   # True=预览帧(模糊)，False=最终高清帧
                            "data":       base64.b64encode(frame_bytes).decode(),
                            "size_bytes": len(frame_bytes),
                            "width":      _w if not is_preview else max(160, _w // 4),
                            "height":     _h if not is_preview else max(90,  _h // 4),
                            "elapsed_ms": 0,
                        })

                    try:
                        await send({"type": "started", "file_id": _file_id})
                        png_bytes = await _render_png_async(
                            _file_id, _style, _w, _h, progress, _view,
                            result_cb=_push_frame,
                        )
                        elapsed_ms = getattr(_render_png_async, "_last_elapsed_ms", 0)
                        await send({
                            "type":       "result",
                            "format":     "png_base64",
                            "is_preview": False,
                            "data":       base64.b64encode(png_bytes).decode(),
                            "size_bytes": len(png_bytes),
                            "width":      _w,
                            "height":     _h,
                            "elapsed_ms": elapsed_ms,
                        })
                    except asyncio.CancelledError:
                        LOG.info("render cancelled for client=%s", cid)
                    except FileNotFoundError as e:
                        await send({"type": "error", "code": ErrCode.FILE_NOT_FOUND, "msg": str(e)})
                    except subprocess.TimeoutExpired:
                        await send({"type": "error", "code": "RENDER_TIMEOUT", "msg": f"渲染超时 (>{EXPORT_TIMEOUT_SECONDS}s)"})
                    except Exception as e:
                        LOG.exception("render error for client=%s", cid)
                        await send({"type": "error", "code": "RENDER_FAILED", "msg": str(e)})

                current_task = asyncio.create_task(do_render())
                continue

            # ── 未知消息类型 ──────────────────────────────────────────────
            await send({
                "type": "error",
                "code": ErrCode.INVALID_PARAMS,
                "msg":  f"未知消息类型: {msg_type!r}，支持: ai_edit | render | export | ping | cancel",
            })

    except WebSocketDisconnect:
        # 客户端正常断开，不需要记录错误
        pass
    except Exception as e:
        LOG.exception("WS unexpected error for client=%s: %s", cid, e)
    finally:
        # 无论何种原因断开，确保清理正在运行的渲染任务
        if current_task and not current_task.done():
            current_task.cancel()
        manager.disconnect(cid)


# ---------------------------------------------------------------------------
# 控制通道 /ws/control
# 外部工具连接此端点，发送渲染参数，后端渲染后广播给所有前端 /ws/render 连接
# ---------------------------------------------------------------------------

@router.websocket("/ws/control")
async def ws_control_endpoint(ws: WebSocket):
    """
    外部调试控制通道。

    连接地址
    --------
      ws://localhost:8080/ws/control

    发送渲染参数（与 /ws/render 的 render 消息完全相同）：
    {
      "type":    "render",
      "file_id": "e9c841cef6c949c8a86589ea0e4d11af",
      "width":   1280,
      "height":  720,
      "view": {
        "center": [116.4, 39.9],
        "radius": 0.5
      },
      "style": {
        "background":    "#ffffff",
        "fill_color":    "#4a90d9",
        "fill_opacity":  0.5,
        "stroke_color":  "#1a5276",
        "stroke_width":  0.8,
        "label_field":   "",
        "label_size":    9,
        "label_color":   "#000000"
      }
    }

    渲染完成后：
    1. 结果广播给所有已连接的 /ws/render 前端（前端画布自动更新）
    2. 同时也回送给控制通道本身（可用于确认）
    """
    await ws.accept()
    LOG.info("Control client connected")

    async def ack(data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    control_task = None

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=float(HEARTBEAT_TIMEOUT_SECONDS))
            except asyncio.TimeoutError:
                await ack({"type": "ping_from_server"})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ack({"type": "error", "code": ErrCode.INVALID_PARAMS, "msg": "JSON 格式错误"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await ack({"type": "pong", "ts": time.time()})
                continue

            if msg_type == "cancel":
                if control_task and not control_task.done():
                    control_task.cancel()
                    await ack({"type": "cancelled"})
                continue

            if msg_type == "render":
                file_id = msg.get("file_id", "").strip()
                if not file_id:
                    await ack({"type": "error", "code": ErrCode.INVALID_PARAMS,
                               "msg": "缺少 file_id，请先 POST /data/upload 上传文件"})
                    continue

                width  = max(64, min(int(msg.get("width",  1280)), 8192))
                height = max(64, min(int(msg.get("height", 720)),  8192))
                style_params = msg.get("style", {}) or {}
                view_param   = msg.get("view")

                if control_task and not control_task.done():
                    control_task.cancel()
                    try:
                        await control_task
                    except asyncio.CancelledError:
                        pass

                async def do_control_render(
                    _fid=file_id, _s=style_params, _w=width, _h=height, _v=view_param
                ):
                    async def ctrl_progress(pct: int, m: str):
                        payload = {"type": "progress", "pct": pct, "msg": m}
                        await ack(payload)
                        await manager.broadcast(payload)

                    async def ctrl_result_cb(frame_bytes: bytes, is_preview: bool):
                        """流式帧回调：预览帧和最终帧广播给所有前端。"""
                        frame_w = max(160, _w // 4) if is_preview else _w
                        frame_h = max(90,  _h // 4) if is_preview else _h
                        result = {
                            "type":       "result",
                            "format":     "png_base64",
                            "is_preview": is_preview,
                            "data":       base64.b64encode(frame_bytes).decode(),
                            "size_bytes": len(frame_bytes),
                            "width":      frame_w,
                            "height":     frame_h,
                            "elapsed_ms": 0,
                        }
                        await manager.broadcast(result)
                        await ack({**result, "data": f"<{len(frame_bytes)//1024}KB>",
                                   "msg": f"{'预览' if is_preview else '高清'}帧已广播给 {manager.count} 个前端"})

                    try:
                        await ack({"type": "started", "file_id": _fid,
                                   "msg": f"渲染中... 将推送给 {manager.count} 个前端"})
                        await manager.broadcast({"type": "started", "file_id": _fid})

                        png_bytes  = await _render_png_async(
                            _fid, _s, _w, _h, ctrl_progress, _v,
                            result_cb=ctrl_result_cb,
                        )
                        elapsed_ms = getattr(_render_png_async, "_last_elapsed_ms", 0)
                        result = {
                            "type":       "result",
                            "format":     "png_base64",
                            "is_preview": False,
                            "data":       base64.b64encode(png_bytes).decode(),
                            "size_bytes": len(png_bytes),
                            "width":      _w,
                            "height":     _h,
                            "elapsed_ms": elapsed_ms,
                        }
                        await manager.broadcast(result)
                        await ack({**result, "data": f"<{len(png_bytes)//1024}KB base64>",
                                   "msg": f"高清帧已广播给 {manager.count} 个前端"})

                    except asyncio.CancelledError:
                        pass
                    except FileNotFoundError as e:
                        err = {"type": "error", "code": ErrCode.FILE_NOT_FOUND, "msg": str(e)}
                        await ack(err); await manager.broadcast(err)
                    except Exception as e:
                        LOG.exception("control render error")
                        err = {"type": "error", "code": "RENDER_FAILED", "msg": str(e)}
                        await ack(err); await manager.broadcast(err)

                control_task = asyncio.create_task(do_control_render())
                continue

            await ack({"type": "error", "code": ErrCode.INVALID_PARAMS,
                       "msg": f"未知消息类型: {msg_type!r}，支持: render | ping | cancel"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOG.exception("Control WS error: %s", e)
    finally:
        if control_task and not control_task.done():
            control_task.cancel()
        LOG.info("Control client disconnected")


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@router.get("/ws/status")
def ws_status():
    """
    查询 WebSocket 服务当前状态。

    响应字段
    --------
    active_connections    : 当前活跃的 WebSocket 连接数
    max_concurrent_renders: 最大并发渲染数（由 RENDER_SEMAPHORE 控制）
    """
    return {
        "active_connections":     manager.count,
        "max_concurrent_renders": EXPORT_SEMAPHORE._value,
    }
