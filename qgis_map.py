"""
地图交互 API
============
维护服务端地图会话（Session），提供平移/缩放/点选/框选/测量/书签/坐标转换。

路由前缀: /map
"""
from __future__ import annotations

import io
import math
import os
import time
import uuid
import hashlib
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/map", tags=["Map Interaction"])

# ---------------------------------------------------------------------------
# 内存会话存储（生产环境可替换为 Redis）
# ---------------------------------------------------------------------------
_SESSIONS: dict[str, dict] = {}
SESSION_TTL = 3600  # 1 小时无操作自动过期


def _get_session(session_id: str) -> dict:
    sess = _SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(404, detail={"code": "SESSION_NOT_FOUND",
                                         "msg": f"session_id {session_id!r} 不存在或已过期"})
    sess["last_active"] = time.time()
    return sess


def _bbox_size(bbox: list[float]) -> tuple[float, float]:
    """返回 bbox 的宽度和高度（地图坐标单位）。"""
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------
class SessionCreate(BaseModel):
    project_id: Optional[str] = Field(None, description="图层项目 ID，可选")
    crs: str = Field("EPSG:4326", description="地图坐标系，如 EPSG:4326 或 EPSG:3857")
    bbox: list[float] = Field(..., description="初始视图范围 [xmin, ymin, xmax, ymax]")
    width: int = Field(1280, ge=64, le=8192, description="画布宽度（像素）")
    height: int = Field(720, ge=64, le=8192, description="画布高度（像素）")


class PanRequest(BaseModel):
    dx: float = Field(..., description="X 方向偏移（像素），正值向右")
    dy: float = Field(..., description="Y 方向偏移（像素），正值向下")


class ZoomRequest(BaseModel):
    factor: Optional[float] = Field(None, gt=0, description="缩放倍数：>1 放大，<1 缩小")
    center: Optional[list[float]] = Field(None, description="缩放中心 [x, y]，不填则用视图中心")
    level: Optional[int] = Field(None, ge=0, le=22, description="直接指定瓦片级别（0-22）")


class ZoomToLayerRequest(BaseModel):
    file_id: str = Field(..., description="要缩放到范围的图层 file_id")
    bbox: Optional[list[float]] = Field(None, description="图层范围 [xmin,ymin,xmax,ymax]，不填则从服务端查询")


class IdentifyRequest(BaseModel):
    pixel_x: int = Field(..., description="点击像素 X 坐标（从左上角起）")
    pixel_y: int = Field(..., description="点击像素 Y 坐标（从左上角起）")
    tolerance_px: int = Field(5, ge=0, le=50, description="命中容差（像素）")
    file_ids: Optional[list[str]] = Field(None, description="限定查询的图层 file_id 列表，不填则查询所有图层")


class SelectRequest(BaseModel):
    bbox: list[float] = Field(..., description="框选范围 [xmin, ymin, xmax, ymax]（地图坐标）")
    file_id: str = Field(..., description="要在哪个图层上选择")
    mode: str = Field("new", description="选择模式：new 新建 / add 追加 / remove 移除 / intersect 取交集")


class SelectByExpressionRequest(BaseModel):
    file_id: str = Field(..., description="目标图层 file_id")
    expression: str = Field(..., description='QGIS 表达式，如 "speed" > 80 AND "type" = \'highway\'')


class MeasureDistanceRequest(BaseModel):
    points: list[list[float]] = Field(..., description="折线顶点列表 [[x1,y1],[x2,y2],...]，至少2个点")
    crs: str = Field("EPSG:4326", description="点坐标所在坐标系")
    unit: str = Field("meters", description="返回单位：meters / kilometers / feet / miles")


class MeasureAreaRequest(BaseModel):
    polygon: list[list[float]] = Field(..., description="多边形顶点列表（首尾相同），[[x1,y1],...]")
    crs: str = Field("EPSG:4326", description="点坐标所在坐标系")
    unit: str = Field("sqmeters", description="返回单位：sqmeters / hectares / sqkilometers / sqfeet / sqmiles")


class BookmarkCreate(BaseModel):
    name: str = Field(..., description="书签名称")
    description: str = Field("", description="书签描述（可选）")


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------
@router.post("/session", summary="创建地图会话")
def create_session(req: SessionCreate):
    """
    初始化一个服务端地图会话，保存视图范围和画布尺寸。
    后续所有地图交互操作均需携带返回的 session_id。
    """
    session_id = "sess_" + uuid.uuid4().hex[:12]
    _SESSIONS[session_id] = {
        "session_id":  session_id,
        "project_id":  req.project_id,
        "crs":         req.crs,
        "bbox":        list(req.bbox),
        "width":       req.width,
        "height":      req.height,
        "selection":   {},       # file_id -> [fid, ...]
        "bookmarks":   {},       # bookmark_id -> {name, bbox, ...}
        "created_at":  time.time(),
        "last_active": time.time(),
    }
    return {"session_id": session_id,
            "bbox": req.bbox,
            "crs": req.crs,
            "width": req.width,
            "height": req.height}


@router.delete("/{session_id}", summary="销毁地图会话")
def delete_session(session_id: str):
    """销毁会话，释放服务端内存。"""
    _SESSIONS.pop(session_id, None)
    return {"deleted": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# 平移 / 缩放
# ---------------------------------------------------------------------------
@router.post("/{session_id}/pan", summary="平移地图")
def pan(session_id: str, req: PanRequest):
    """
    按像素偏移平移地图。服务端更新会话的 bbox 并返回新范围。
    dx>0 向右，dy>0 向下（像素坐标系）。
    """
    sess = _get_session(session_id)
    bbox = sess["bbox"]
    w_px, h_px = sess["width"], sess["height"]
    w_map, h_map = _bbox_size(bbox)
    px_per_map_x = w_px / w_map
    px_per_map_y = h_px / h_map
    dx_map =  req.dx / px_per_map_x
    dy_map = -req.dy / px_per_map_y  # 像素 Y 向下，地图 Y 向上
    new_bbox = [
        bbox[0] + dx_map, bbox[1] + dy_map,
        bbox[2] + dx_map, bbox[3] + dy_map,
    ]
    sess["bbox"] = new_bbox
    return {"bbox": new_bbox, "session_id": session_id}


@router.post("/{session_id}/zoom", summary="缩放地图")
def zoom(session_id: str, req: ZoomRequest):
    """
    缩放地图视图。支持按倍数缩放（factor）或指定瓦片级别（level）。
    center 指定缩放中心点（地图坐标），不填则以当前视图中心为准。
    """
    sess = _get_session(session_id)
    bbox = sess["bbox"]
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2

    if req.center:
        cx, cy = req.center[0], req.center[1]

    w_map, h_map = _bbox_size(bbox)

    if req.level is not None:
        # 从瓦片级别反推地图范围（仅适用于 EPSG:4326）
        deg_per_tile = 360.0 / (2 ** req.level)
        new_w = deg_per_tile * (sess["width"] / 256)
        new_h = new_w * (sess["height"] / sess["width"])
    elif req.factor:
        new_w = w_map / req.factor
        new_h = h_map / req.factor
    else:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS",
                                          "msg": "需提供 factor 或 level"})

    new_bbox = [cx - new_w / 2, cy - new_h / 2,
                cx + new_w / 2, cy + new_h / 2]
    sess["bbox"] = new_bbox
    return {"bbox": new_bbox, "session_id": session_id}


@router.post("/{session_id}/zoom_to_layer", summary="缩放到图层范围")
def zoom_to_layer(session_id: str, req: ZoomToLayerRequest):
    """
    将视图缩放到指定图层的完整数据范围。
    bbox 由调用方从 GET /data/{file_id}/info 中的 bbox 字段获取后传入。
    """
    sess = _get_session(session_id)
    if not req.bbox or len(req.bbox) != 4:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS",
                                          "msg": "需提供图层 bbox [xmin,ymin,xmax,ymax]"})
    # 留 5% 边距
    w = req.bbox[2] - req.bbox[0]
    h = req.bbox[3] - req.bbox[1]
    padded = [
        req.bbox[0] - w * 0.05,
        req.bbox[1] - h * 0.05,
        req.bbox[2] + w * 0.05,
        req.bbox[3] + h * 0.05,
    ]
    sess["bbox"] = padded
    return {"bbox": padded, "session_id": session_id, "file_id": req.file_id}


@router.post("/{session_id}/zoom_to_selection", summary="缩放到选中要素范围")
def zoom_to_selection(session_id: str):
    """缩放视图到当前所有选中要素的合并范围。选集为空时返回 400。"""
    sess = _get_session(session_id)
    sel = sess.get("selection", {})
    if not sel:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS", "msg": "当前无选中要素"})
    # 返回当前 bbox（实际项目中应根据选中要素几何计算范围）
    return {"bbox": sess["bbox"], "session_id": session_id,
            "note": "需结合图层数据计算选中要素实际范围"}


# ---------------------------------------------------------------------------
# 要素识别 / 选择
# ---------------------------------------------------------------------------
@router.post("/{session_id}/identify", summary="点选要素识别")
def identify(session_id: str, req: IdentifyRequest):
    """
    将屏幕像素坐标转换为地图坐标，返回该点附近（容差范围内）的所有要素属性。
    实际几何查询需结合图层数据，此处返回坐标转换结果供调用方进一步查询。
    """
    sess = _get_session(session_id)
    bbox = sess["bbox"]
    w_px, h_px = sess["width"], sess["height"]
    # 像素 → 地图坐标
    map_x = bbox[0] + (req.pixel_x / w_px) * (bbox[2] - bbox[0])
    map_y = bbox[3] - (req.pixel_y / h_px) * (bbox[3] - bbox[1])
    # 容差（像素转地图单位）
    tol_x = req.tolerance_px / w_px * (bbox[2] - bbox[0])
    tol_y = req.tolerance_px / h_px * (bbox[3] - bbox[1])
    query_bbox = [map_x - tol_x, map_y - tol_y,
                  map_x + tol_x, map_y + tol_y]
    return {
        "map_x":       map_x,
        "map_y":       map_y,
        "query_bbox":  query_bbox,
        "crs":         sess["crs"],
        "file_ids":    req.file_ids,
        "hint":        "使用 query_bbox 调用 POST /data/{file_id}/query 获取命中要素",
    }


@router.post("/{session_id}/select", summary="矩形框选要素")
def select_features(session_id: str, req: SelectRequest):
    """
    在指定图层上框选范围内的要素，更新服务端会话的选集。
    mode=new 清空已有选集再选；add 追加；remove 取消；intersect 取交集。
    """
    sess = _get_session(session_id)
    if req.mode not in ("new", "add", "remove", "intersect"):
        raise HTTPException(400, detail={"code": "INVALID_PARAMS",
                                          "msg": "mode 必须是 new/add/remove/intersect"})
    # 实际项目中在此调用空间查询获取 fid 列表
    sel = sess.setdefault("selection", {})
    if req.mode == "new":
        sel.clear()
        sel[req.file_id] = []   # 占位，实际值由调用方通过 /data/{file_id}/query 填充
    return {
        "session_id":  session_id,
        "file_id":     req.file_id,
        "mode":        req.mode,
        "bbox":        req.bbox,
        "hint":        "使用 POST /data/{file_id}/query 配合 bbox 参数获取选中 fid 列表",
    }


@router.post("/{session_id}/select_by_expression", summary="表达式选择要素")
def select_by_expression(session_id: str, req: SelectByExpressionRequest):
    """
    用 QGIS 表达式在指定图层中选择满足条件的要素，更新会话选集。
    表达式语法与 QGIS 属性查询完全一致。
    """
    _get_session(session_id)
    return {
        "session_id": session_id,
        "file_id":    req.file_id,
        "expression": req.expression,
        "hint":       "使用 POST /data/{file_id}/query 配合 filter 参数获取结果",
    }


@router.delete("/{session_id}/selection", summary="清除选集")
def clear_selection(session_id: str):
    """清除当前会话中所有图层的选中要素。"""
    sess = _get_session(session_id)
    sess["selection"] = {}
    return {"session_id": session_id, "cleared": True}


# ---------------------------------------------------------------------------
# 测量工具
# ---------------------------------------------------------------------------
def _haversine_m(p1: list[float], p2: list[float]) -> float:
    """Haversine 公式计算两经纬度点间距离（米），适用于 EPSG:4326。"""
    R = 6_371_000.0
    lat1, lon1 = math.radians(p1[1]), math.radians(p1[0])
    lat2, lon2 = math.radians(p2[1]), math.radians(p2[0])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


_DIST_FACTOR = {"meters": 1.0, "kilometers": 1e-3, "feet": 3.28084, "miles": 1/1609.344}
_AREA_FACTOR = {"sqmeters": 1.0, "hectares": 1e-4, "sqkilometers": 1e-6,
                "sqfeet": 10.7639, "sqmiles": 3.861e-7}


@router.post("/{session_id}/measure/distance", summary="距离测量")
def measure_distance(session_id: str, req: MeasureDistanceRequest):
    """
    计算折线各段长度和总长度。
    坐标系为 EPSG:4326 时使用 Haversine 球面距离；其他坐标系使用欧氏距离（单位与坐标系一致）。
    """
    _get_session(session_id)
    if len(req.points) < 2:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS", "msg": "至少需要 2 个点"})
    factor = _DIST_FACTOR.get(req.unit, 1.0)
    segments = []
    for i in range(len(req.points) - 1):
        p1, p2 = req.points[i], req.points[i+1]
        if req.crs.upper() in ("EPSG:4326", "CRS:84"):
            d = _haversine_m(p1, p2)
        else:
            d = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        segments.append(round(d * factor, 4))
    total = round(sum(segments), 4)
    return {
        "unit":        req.unit,
        "segments":    segments,   # 各段距离列表
        "total":       total,      # 总距离
        "point_count": len(req.points),
    }


@router.post("/{session_id}/measure/area", summary="面积测量")
def measure_area(session_id: str, req: MeasureAreaRequest):
    """
    计算多边形面积和周长。
    EPSG:4326 使用 Shoelace 公式 + 球面近似；其他坐标系使用平面 Shoelace 公式。
    """
    _get_session(session_id)
    pts = req.polygon
    if len(pts) < 3:
        raise HTTPException(400, detail={"code": "INVALID_PARAMS", "msg": "至少需要 3 个点"})
    area_factor = _AREA_FACTOR.get(req.unit, 1.0)
    dist_factor = _DIST_FACTOR.get("meters", 1.0)

    # Shoelace 公式（平面）
    n = len(pts)
    area = 0.0
    perim = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
        if req.crs.upper() in ("EPSG:4326", "CRS:84"):
            perim += _haversine_m(pts[i], pts[j])
        else:
            perim += math.hypot(pts[j][0]-pts[i][0], pts[j][1]-pts[i][1])

    plane_area = abs(area) / 2.0
    # EPSG:4326: 1度≈111320m，粗略转平方米
    if req.crs.upper() in ("EPSG:4326", "CRS:84"):
        plane_area = plane_area * (111320 ** 2)

    return {
        "area":        round(plane_area * area_factor, 4),
        "area_unit":   req.unit,
        "perimeter_m": round(perim, 4),
        "vertex_count": n,
    }


# ---------------------------------------------------------------------------
# 书签
# ---------------------------------------------------------------------------
@router.post("/{session_id}/bookmark", summary="保存视图书签")
def add_bookmark(session_id: str, req: BookmarkCreate):
    """将当前视图范围保存为命名书签，便于快速跳回。"""
    sess = _get_session(session_id)
    bid = "bk_" + uuid.uuid4().hex[:8]
    sess["bookmarks"][bid] = {
        "bookmark_id": bid,
        "name":        req.name,
        "description": req.description,
        "bbox":        list(sess["bbox"]),
        "crs":         sess["crs"],
        "created_at":  time.time(),
    }
    return sess["bookmarks"][bid]


@router.get("/{session_id}/bookmarks", summary="获取所有书签")
def list_bookmarks(session_id: str):
    """返回当前会话中保存的所有书签列表。"""
    sess = _get_session(session_id)
    return {"bookmarks": list(sess["bookmarks"].values())}


@router.post("/{session_id}/goto_bookmark/{bookmark_id}", summary="跳转到书签")
def goto_bookmark(session_id: str, bookmark_id: str):
    """将当前视图范围切换到指定书签保存的范围。"""
    sess = _get_session(session_id)
    bk = sess["bookmarks"].get(bookmark_id)
    if not bk:
        raise HTTPException(404, detail={"code": "BOOKMARK_NOT_FOUND",
                                          "msg": f"书签 {bookmark_id!r} 不存在"})
    sess["bbox"] = list(bk["bbox"])
    return {"bbox": sess["bbox"], "bookmark": bk}


# ---------------------------------------------------------------------------
# 坐标转换
# ---------------------------------------------------------------------------
@router.get("/{session_id}/coordinate", summary="像素坐标转地图坐标")
def pixel_to_map(session_id: str, px: float, py: float):
    """
    将画布像素坐标 (px, py) 转换为地图坐标，同时返回 EPSG:4326 和 EPSG:3857 投影值及度分秒格式。
    px: 像素 X（0=左边），py: 像素 Y（0=顶部）。
    """
    sess = _get_session(session_id)
    bbox = sess["bbox"]
    w_px, h_px = sess["width"], sess["height"]
    map_x = bbox[0] + (px / w_px) * (bbox[2] - bbox[0])
    map_y = bbox[3] - (py / h_px) * (bbox[3] - bbox[1])

    # EPSG:4326 直接返回（若会话 CRS 本身是 4326）
    lon, lat = map_x, map_y

    def _to_dms(deg: float, is_lat: bool) -> str:
        direction = ("N" if deg >= 0 else "S") if is_lat else ("E" if deg >= 0 else "W")
        deg = abs(deg)
        d = int(deg)
        m = int((deg - d) * 60)
        s = round(((deg - d) * 60 - m) * 60, 1)
        return f"{d}°{m}'{s}\"{direction}"

    # EPSG:3857 近似（仅适用于 EPSG:4326 输入）
    x3857 = lon * 20037508.34 / 180
    y3857 = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y3857 = y3857 * 20037508.34 / 180

    return {
        "map_x":    round(map_x, 8),    # 当前会话坐标系下的 X
        "map_y":    round(map_y, 8),    # 当前会话坐标系下的 Y
        "crs":      sess["crs"],
        "epsg4326": [round(lon, 8), round(lat, 8)],      # 经纬度 [经度, 纬度]
        "epsg3857": [round(x3857, 2), round(y3857, 2)],  # Web 墨卡托坐标
        "dms":      f"{_to_dms(lon, False)}, {_to_dms(lat, True)}",  # 度分秒格式
    }


@router.get("/sessions", summary="列出所有活跃会话")
def list_sessions():
    """列出当前服务器上所有活跃的地图会话（含创建时间和最后活跃时间）。"""
    now = time.time()
    result = []
    for sid, sess in list(_SESSIONS.items()):
        idle = now - sess["last_active"]
        if idle > SESSION_TTL:
            _SESSIONS.pop(sid, None)
            continue
        result.append({
            "session_id":    sid,
            "crs":           sess["crs"],
            "bbox":          sess["bbox"],
            "idle_seconds":  int(idle),
            "bookmark_count": len(sess["bookmarks"]),
        })
    return {"sessions": result, "count": len(result)}


# ---------------------------------------------------------------------------
# QGIS 服务端渲染瓦片
# ---------------------------------------------------------------------------
_TILE_CACHE_DIR = Path(tempfile.gettempdir()) / "qgis_render_tile_cache"
_TILE_CACHE_DIR.mkdir(exist_ok=True)

# 内置中文底图 XYZ 源配置
_QGIS_TILE_SOURCES: dict[str, dict] = {
    "amap": {
        "name": "高德地图(中文)",
        "url": "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "zmax": 18,
    },
    "amap_satellite": {
        "name": "高德卫星(中文路网)",
        "url": "https://webst01.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}",
        "zmax": 18,
    },
    "tianditu": {
        "name": "天地图矢量(中文)",
        "url": "https://t0.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={token}",
        "zmax": 18,
    },
    "osm": {
        "name": "OpenStreetMap",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "zmax": 19,
    },
    "esri_satellite": {
        "name": "ESRI卫星影像",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "zmax": 19,
    },
}


def _tile_to_bbox_mercator(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """将 XYZ 瓦片坐标转换为 Web 墨卡托 (EPSG:3857) bbox。"""
    n = 2 ** z
    # 墨卡托范围 ±20037508.3427892
    EXTENT = 20037508.3427892
    tile_size = 2 * EXTENT / n
    xmin = -EXTENT + x * tile_size
    xmax = xmin + tile_size
    ymax =  EXTENT - y * tile_size
    ymin = ymax - tile_size
    return xmin, ymin, xmax, ymax


@router.get("/tile/sources", summary="列出 QGIS 渲染底图源")
def list_tile_sources():
    """返回所有可用的 QGIS 服务端渲染底图源列表。"""
    return {
        "sources": [
            {"id": k, "name": v["name"], "zmax": v["zmax"]}
            for k, v in _QGIS_TILE_SOURCES.items()
        ]
    }


@router.get(
    "/tile/{source}/{z}/{x}/{y}.png",
    summary="QGIS 底图源瓦片（服务端下载+缓存）",
    response_class=Response,
)
def render_tile(
    source: str,
    z: int,
    x: int,
    y: int,
    token: Optional[str] = Query(None, description="天地图等需要 token 的服务"),
):
    """
    从指定底图源下载 XYZ 瓦片并缓存返回。
    支持中文高德、天地图、OSM、ESRI 卫星等。
    QGIS 可在此基础上叠加矢量图层渲染。
    """
    import urllib.request
    src = _QGIS_TILE_SOURCES.get(source)
    if not src:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND",
                                         "msg": f"底图源 {source!r} 不存在，可用: {list(_QGIS_TILE_SOURCES)}"})
    if z > src["zmax"]:
        raise HTTPException(400, detail={"code": "ZOOM_TOO_HIGH",
                                         "msg": f"该底图源最大缩放级别为 {src['zmax']}"})

    cache_key = hashlib.md5(f"{source}/{z}/{x}/{y}".encode()).hexdigest()
    cache_file = _TILE_CACHE_DIR / f"{cache_key}.png"
    if cache_file.exists():
        return Response(content=cache_file.read_bytes(), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"})

    url = src["url"]
    if token:
        url = url.replace("{token}", token)
    elif "{token}" in url:
        raise HTTPException(400, detail={"code": "TOKEN_REQUIRED",
                                         "msg": "该底图源需要提供 token 参数"})

    tile_url = (url
                .replace("{z}", str(z))
                .replace("{x}", str(x))
                .replace("{y}", str(y)))

    try:
        req = urllib.request.Request(tile_url, headers={
            "User-Agent": "Mozilla/5.0 QGIS/3",
            "Referer": "https://webrd01.is.autonavi.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            png_bytes = resp.read()
    except Exception as e:
        raise HTTPException(502, detail={"code": "UPSTREAM_ERROR", "msg": str(e)})

    cache_file.write_bytes(png_bytes)
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"})


# ---------------------------------------------------------------------------
# QGIS 渲染：DXF 矢量叠加底图
# ---------------------------------------------------------------------------
_RENDER_WORK_DIR = Path(tempfile.gettempdir()) / "qgis_overlay_renders"
_RENDER_WORK_DIR.mkdir(exist_ok=True)

_GEOJSON_STORE = Path(tempfile.gettempdir()) / "qgis_geojson_store"


class OverlayRenderRequest(BaseModel):
    file_id: str = Field(..., description="已上传文件的 file_id（来自 POST /data/upload）")
    bbox: list[float] = Field(..., description="渲染范围 [xmin,ymin,xmax,ymax]（工程坐标或 EPSG:4326）")
    width: int = Field(1280, ge=64, le=4096, description="输出图片宽度（像素）")
    height: int = Field(720, ge=64, le=4096, description="输出图片高度（像素）")
    basemap: Optional[str] = Field("amap", description="底图源 ID，来自 GET /map/tile/sources，None 则不加底图")
    dxf_color: str = Field("#00ff88", description="DXF 矢量颜色（HEX）")
    dxf_line_width: float = Field(1.0, ge=0.1, le=10.0, description="DXF 线宽（像素）")
    dxf_opacity: float = Field(1.0, ge=0.0, le=1.0, description="DXF 图层透明度")
    background_color: str = Field("#1a1a2e", description="背景色（HEX），无底图时有效")


def _hex_to_qcolor(hex_str: str):
    from qgis.PyQt.QtGui import QColor
    return QColor(hex_str)


def _fetch_basemap_tile_img(source: str, z: int, x: int, y: int) -> Optional[bytes]:
    """下载单张瓦片，失败返回 None。"""
    import urllib.request
    src = _QGIS_TILE_SOURCES.get(source)
    if not src:
        return None
    url = src["url"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 QGIS/3",
            "Referer": "https://webrd01.is.autonavi.com/",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()
    except Exception:
        return None


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    import math
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _mercator_to_lonlat(mx: float, my: float) -> tuple[float, float]:
    import math
    EARTH_R = 6378137.0
    lon = math.degrees(mx / EARTH_R)
    lat = math.degrees(2 * math.atan(math.exp(my / EARTH_R)) - math.pi / 2)
    return lon, lat


@router.post("/render/overlay", summary="QGIS 渲染 DXF 矢量叠加底图")
def render_overlay(req: OverlayRenderRequest):
    """
    用 PyQGIS 将已上传的 DXF/GeoJSON 矢量叠加在底图上渲染，返回 PNG 图片。
    bbox 为工程坐标时直接渲染（无底图）；为地理坐标时可叠加网络底图。
    """
    try:
        from qgis.core import (
            QgsVectorLayer, QgsMapSettings, QgsRectangle,
            QgsCoordinateReferenceSystem, QgsMapRendererParallelJob,
            QgsSingleSymbolRenderer, QgsLineSymbol, QgsFillSymbol,
            QgsMarkerSymbol, QgsSimpleLineSymbolLayer,
        )
        from qgis.PyQt.QtCore import QSize, QEventLoop, QBuffer, QIODevice
        from qgis.PyQt.QtGui import QColor, QImage
    except ImportError:
        raise HTTPException(503, detail={"code": "QGIS_UNAVAILABLE", "msg": "PyQGIS 未启用"})

    # 找 GeoJSON 文件
    store = _GEOJSON_STORE / req.file_id
    geojson_path = store / "data.geojson"
    # 若没有 GeoJSON，找原始 DXF
    dxf_files = list(store.glob("*.dxf")) if store.exists() else []
    if geojson_path.exists():
        src_path = str(geojson_path)
        provider = "ogr"
    elif dxf_files:
        src_path = str(dxf_files[0])
        provider = "ogr"
    else:
        raise HTTPException(404, detail={"code": "FILE_NOT_FOUND",
                                         "msg": f"file_id {req.file_id!r} 不存在，请先 POST /data/upload"})

    # 加载矢量图层
    layer = QgsVectorLayer(src_path, "dxf", provider)
    if not layer.isValid():
        raise HTTPException(500, detail={"code": "LAYER_INVALID",
                                         "msg": f"无法加载矢量文件: {src_path}"})

    # 设置样式
    color = QColor(req.dxf_color)
    color.setAlphaF(req.dxf_opacity)
    geom_type = layer.geometryType()  # 0=Point 1=Line 2=Polygon
    if geom_type == 1:  # Line
        sym = QgsLineSymbol.createSimple({"color": req.dxf_color,
                                          "width": str(req.dxf_line_width)})
    elif geom_type == 2:  # Polygon
        sym = QgsFillSymbol.createSimple({"color": "transparent",
                                          "outline_color": req.dxf_color,
                                          "outline_width": str(req.dxf_line_width)})
    else:  # Point/Mixed
        sym = QgsMarkerSymbol.createSimple({"color": req.dxf_color,
                                             "size": str(req.dxf_line_width * 2)})
    sym.setOpacity(req.dxf_opacity)
    layer.setRenderer(QgsSingleSymbolRenderer(sym))

    # 准备底图图片（拼接瓦片）
    basemap_img: Optional[QImage] = None
    if req.basemap and req.basemap in _QGIS_TILE_SOURCES:
        try:
            from PIL import Image
            import math, io as _io

            # 估算合适 zoom level
            xmin, ymin, xmax, ymax = req.bbox
            # 假设 bbox 是地理坐标 (lon/lat)
            dx = abs(xmax - xmin)
            zoom = max(2, min(16, int(math.log2(360.0 / dx * req.width / 256))))

            tx0, ty0 = _lonlat_to_tile(xmin, ymax, zoom)
            tx1, ty1 = _lonlat_to_tile(xmax, ymin, zoom)
            tx0, tx1 = min(tx0, tx1), max(tx0, tx1)
            ty0, ty1 = min(ty0, ty1), max(ty0, ty1)

            tw = (tx1 - tx0 + 1) * 256
            th = (ty1 - ty0 + 1) * 256
            canvas = Image.new("RGB", (tw, th), (30, 30, 50))

            for tx in range(tx0, tx1 + 1):
                for ty in range(ty0, ty1 + 1):
                    data = _fetch_basemap_tile_img(req.basemap, zoom, tx, ty)
                    if data:
                        tile = Image.open(_io.BytesIO(data)).convert("RGB")
                        canvas.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))

            # 裁剪到精确 bbox
            EXTENT = 20037508.3427892
            n = 2 ** zoom
            tile_deg = 360.0 / n

            def lon_to_px(lon):
                return int((lon - tx0 * tile_deg - (-180)) / tile_deg * 256) % tw

            import math as _math
            def lat_to_px(lat):
                lat_r = _math.radians(lat)
                merc_y = _math.log(_math.tan(_math.pi/4 + lat_r/2))
                tile_y_f = (1 - merc_y / _math.pi) / 2 * n
                return int((tile_y_f - ty0) * 256)

            px0 = max(0, int((xmin + 180) / tile_deg * 256) - tx0 * 256)
            px1 = max(0, int((xmax + 180) / tile_deg * 256) - tx0 * 256)
            py0 = lat_to_px(ymax)
            py1 = lat_to_px(ymin)
            px1 = min(tw, px1)
            py1 = min(th, py1)

            if px1 > px0 and py1 > py0:
                canvas = canvas.crop((px0, py0, px1, py1))
            canvas = canvas.resize((req.width, req.height), Image.LANCZOS)

            buf = _io.BytesIO()
            canvas.save(buf, "PNG")
            from qgis.PyQt.QtGui import QImage as _QImage
            basemap_img = _QImage()
            basemap_img.loadFromData(buf.getvalue())
        except Exception:
            basemap_img = None

    # QGIS 渲染 DXF 矢量
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setOutputSize(QSize(req.width, req.height))
    settings.setDestinationCrs(layer.crs() if layer.crs().isValid()
                                else QgsCoordinateReferenceSystem("EPSG:4326"))
    xmin, ymin, xmax, ymax = req.bbox
    settings.setExtent(QgsRectangle(xmin, ymin, xmax, ymax))
    settings.setBackgroundColor(QColor(0, 0, 0, 0))  # 透明背景

    job = QgsMapRendererParallelJob(settings)
    loop = QEventLoop()
    job.finished.connect(loop.quit)
    job.start()
    loop.exec()
    vector_img = job.renderedImage()

    # 合成：底图 + 矢量
    from qgis.PyQt.QtGui import QPainter
    from qgis.PyQt.QtCore import Qt

    final = QImage(QSize(req.width, req.height), QImage.Format.Format_ARGB32_Premultiplied)
    final.fill(QColor(req.background_color))

    painter = QPainter(final)
    if basemap_img and not basemap_img.isNull():
        painter.drawImage(0, 0, basemap_img.scaled(
            req.width, req.height, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
    painter.drawImage(0, 0, vector_img)
    painter.end()

    qbuf = QBuffer()
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    final.save(qbuf, "PNG")
    png_bytes = bytes(qbuf.data())
    qbuf.close()

    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "no-cache"})
