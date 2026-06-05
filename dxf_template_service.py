"""
DXF/DWG 模板服务
================
上传 DXF/DWG 文件，解析成模板 JSON，存储到 MinIO 和 MySQL
"""
from __future__ import annotations

import io
import json
import uuid
import shutil
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from config import MINIO_CONFIG, MYSQL_CONFIG, get_file_public_url

LOG = logging.getLogger("dxf_template")

router = APIRouter(prefix="/template", tags=["DXF Template"])

WORK_DIR = Path(tempfile.gettempdir()) / "dxf_template_service"
WORK_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def clean_text(text: str) -> str:
    """清理文本中的非法 Unicode 字符"""
    if not text:
        return ""
    # 替换代理字符和其他非法字符
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def get_s3_client():
    """获取 S3 客户端（兼容 MinIO）"""
    import boto3
    from botocore.config import Config
    
    endpoint = MINIO_CONFIG["endpoint"]
    secure = MINIO_CONFIG.get("secure", False)
    protocol = "https" if secure else "http"
    endpoint_url = f"{protocol}://{endpoint}"
    
    client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=MINIO_CONFIG["access_key"],
        aws_secret_access_key=MINIO_CONFIG["secret_key"],
        config=Config(signature_version='s3v4'),
        region_name='us-east-1',
    )
    return client


def extract_editable_params_async(template_id: str, dxf_path: Path, template_data: dict):
    """
    后台任务：提取可编辑参数并存储到数据库
    
    智能采样策略：
    1. 只提取关键图层（如"墩身"、"标注"、"尺寸"等）
    2. 只提取可编辑的实体类型（TEXT、MTEXT、关键几何图形）
    3. 批量插入数据库
    """
    try:
        LOG.info(f"开始提取参数: template_id={template_id}")
        
        # 提取可编辑参数
        editable_params = []
        entities = template_data.get("entities", [])
        
        # 关键图层列表（可配置）
        key_layers = {"墩身", "标注", "尺寸", "文字", "0"}  # 0 层通常包含主要内容
        
        # 可编辑实体类型
        editable_types = {"TEXT", "MTEXT", "LINE", "CIRCLE", "ARC", "DIMENSION"}
        
        for entity in entities:
            entity_type = entity.get("type")
            layer = entity.get("layer", "0")
            handle = entity.get("handle")
            
            # 过滤：只处理关键图层和可编辑类型
            if layer not in key_layers and entity_type not in editable_types:
                continue
            
            # 提取参数
            if entity_type == "LINE":
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "start",
                    "param_value": json.dumps(entity.get("start")),
                    "param_type": "point",
                    "description": "起点坐标"
                })
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "end",
                    "param_value": json.dumps(entity.get("end")),
                    "param_type": "point",
                    "description": "终点坐标"
                })
            
            elif entity_type == "CIRCLE":
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "center",
                    "param_value": json.dumps(entity.get("center")),
                    "param_type": "point",
                    "description": "圆心坐标"
                })
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "radius",
                    "param_value": json.dumps(entity.get("radius")),
                    "param_type": "number",
                    "constraints": json.dumps({"min": 0.001}),
                    "description": "半径"
                })
            
            elif entity_type in ["TEXT", "MTEXT"]:
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "text",
                    "param_value": json.dumps(entity.get("text")),
                    "param_type": "string",
                    "description": "文字内容"
                })
                editable_params.append({
                    "template_id": template_id,
                    "entity_handle": handle,
                    "entity_type": entity_type,
                    "layer": layer,
                    "param_name": "insert",
                    "param_value": json.dumps(entity.get("insert")),
                    "param_type": "point",
                    "description": "插入点"
                })
        
        LOG.info(f"提取到 {len(editable_params)} 个可编辑参数")
        
        # 批量插入数据库
        if editable_params:
            conn = get_mysql_connection()
            try:
                with conn.cursor() as cursor:
                    sql = """
                        INSERT INTO dxf_editable_params (
                            template_id, entity_handle, entity_type, layer,
                            param_name, param_value, param_type, constraints, description
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    # 分批插入（每次 1000 条）
                    batch_size = 1000
                    for i in range(0, len(editable_params), batch_size):
                        batch = editable_params[i:i + batch_size]
                        values = [
                            (
                                p["template_id"], p["entity_handle"], p["entity_type"], p["layer"],
                                p["param_name"], p["param_value"], p["param_type"],
                                p.get("constraints"), p.get("description")
                            )
                            for p in batch
                        ]
                        cursor.executemany(sql, values)
                        conn.commit()
                        LOG.info(f"已插入 {i + len(batch)}/{len(editable_params)} 条参数")
                
                # 更新模板状态为 ready
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE dxf_template SET status = %s, params_count = %s WHERE id = %s",
                        ("ready", len(editable_params), template_id)
                    )
                    conn.commit()
                
                LOG.info(f"参数提取完成: template_id={template_id}, count={len(editable_params)}")
            finally:
                conn.close()
        else:
            # 没有可编辑参数，直接标记为 ready
            conn = get_mysql_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE dxf_template SET status = %s WHERE id = %s",
                        ("ready", template_id)
                    )
                    conn.commit()
            finally:
                conn.close()
    
    except Exception as e:
        LOG.exception(f"提取参数失败: template_id={template_id}")
        # 更新状态为 failed
        try:
            conn = get_mysql_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE dxf_template SET status = %s WHERE id = %s",
                    ("failed", template_id)
                )
                conn.commit()
            conn.close()
        except:
            pass


def get_mysql_connection():
    """获取 MySQL 连接"""
    import pymysql
    
    cfg = MYSQL_CONFIG
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset=cfg["charset"],
        cursorclass=pymysql.cursors.DictCursor,
    )


def define_editable_params(entity_type: str, entity) -> dict:
    """
    定义实体的可编辑参数
    返回格式: {
        "param_name": {
            "editable": True/False,
            "type": "number" | "string" | "point" | "angle" | "scale" | "color",
            "min": 最小值 (可选),
            "max": 最大值 (可选),
            "description": "参数说明"
        }
    }
    """
    # 通用不可编辑参数
    readonly_params = {
        "handle": {"editable": False, "type": "string", "description": "实体句柄，系统生成，不可修改"},
        "type": {"editable": False, "type": "string", "description": "实体类型，不可修改"},
    }
    
    # 通用可编辑参数
    common_editable = {
        "layer": {
            "editable": True,
            "type": "string",
            "description": "所属图层，可修改为已存在的图层名"
        },
        "color": {
            "editable": True,
            "type": "color",
            "min": 0,
            "max": 256,
            "description": "颜色索引，0=ByBlock, 256=ByLayer, 1-255=固定颜色"
        },
        "linetype": {
            "editable": True,
            "type": "string",
            "description": "线型名称"
        },
    }
    
    # 各实体类型的特定可编辑参数
    entity_params = {
        "LINE": {
            "start": {
                "editable": True,
                "type": "point",
                "description": "起点坐标 [x, y, z]，可任意修改"
            },
            "end": {
                "editable": True,
                "type": "point",
                "description": "终点坐标 [x, y, z]，可任意修改"
            },
        },
        "CIRCLE": {
            "center": {
                "editable": True,
                "type": "point",
                "description": "圆心坐标 [x, y, z]，可任意修改"
            },
            "radius": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1e10,
                "description": "半径，必须大于0"
            },
        },
        "ARC": {
            "center": {
                "editable": True,
                "type": "point",
                "description": "圆心坐标 [x, y, z]，可任意修改"
            },
            "radius": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1e10,
                "description": "半径，必须大于0"
            },
            "start_angle": {
                "editable": True,
                "type": "angle",
                "min": 0,
                "max": 360,
                "description": "起始角度（度），0-360"
            },
            "end_angle": {
                "editable": True,
                "type": "angle",
                "min": 0,
                "max": 360,
                "description": "终止角度（度），0-360"
            },
        },
        "TEXT": {
            "insert": {
                "editable": True,
                "type": "point",
                "description": "插入点坐标 [x, y, z]，可任意修改"
            },
            "text": {
                "editable": True,
                "type": "string",
                "max_length": 2048,
                "description": "文字内容，可任意修改"
            },
            "height": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1e6,
                "description": "文字高度，必须大于0"
            },
            "rotation": {
                "editable": True,
                "type": "angle",
                "min": 0,
                "max": 360,
                "description": "旋转角度（度），0-360"
            },
        },
        "MTEXT": {
            "insert": {
                "editable": True,
                "type": "point",
                "description": "插入点坐标 [x, y, z]，可任意修改"
            },
            "text": {
                "editable": True,
                "type": "string",
                "max_length": 65535,
                "description": "多行文字内容，可任意修改"
            },
            "char_height": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1e6,
                "description": "字符高度，必须大于0"
            },
            "width": {
                "editable": True,
                "type": "number",
                "min": 0,
                "max": 1e10,
                "description": "文字框宽度，0表示无限制"
            },
        },
        "LWPOLYLINE": {
            "points": {
                "editable": True,
                "type": "point_array",
                "min_points": 2,
                "description": "顶点坐标数组，至少2个点"
            },
            "is_closed": {
                "editable": True,
                "type": "boolean",
                "description": "是否闭合"
            },
            "const_width": {
                "editable": True,
                "type": "number",
                "min": 0,
                "max": 1e6,
                "description": "统一线宽，0表示无宽度"
            },
        },
        "POLYLINE": {
            "points": {
                "editable": True,
                "type": "point_array",
                "min_points": 2,
                "description": "顶点坐标数组，至少2个点"
            },
            "is_closed": {
                "editable": True,
                "type": "boolean",
                "description": "是否闭合"
            },
        },
        "INSERT": {
            "insert": {
                "editable": True,
                "type": "point",
                "description": "插入点坐标 [x, y, z]，可任意修改"
            },
            "block_name": {
                "editable": False,
                "type": "string",
                "description": "块名称，不可修改（需使用已定义的块）"
            },
            "scale": {
                "editable": True,
                "type": "scale",
                "min": 0.001,
                "max": 1e6,
                "description": "缩放比例 [x, y, z]，必须大于0"
            },
            "rotation": {
                "editable": True,
                "type": "angle",
                "min": 0,
                "max": 360,
                "description": "旋转角度（度），0-360"
            },
        },
        "DIMENSION": {
            "dimension_type": {
                "editable": False,
                "type": "number",
                "description": "标注类型，不可修改"
            },
            "text_override": {
                "editable": True,
                "type": "string",
                "description": "标注文字覆盖，空字符串表示使用测量值"
            },
        },
        "HATCH": {
            "pattern_name": {
                "editable": True,
                "type": "string",
                "description": "填充图案名称"
            },
            "pattern_scale": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1e6,
                "description": "图案缩放比例"
            },
            "pattern_angle": {
                "editable": True,
                "type": "angle",
                "min": 0,
                "max": 360,
                "description": "图案旋转角度（度）"
            },
            "solid_fill": {
                "editable": False,
                "type": "boolean",
                "description": "是否实心填充，不可修改"
            },
        },
        "ELLIPSE": {
            "center": {
                "editable": True,
                "type": "point",
                "description": "中心点坐标 [x, y, z]，可任意修改"
            },
            "major_axis": {
                "editable": True,
                "type": "point",
                "description": "长轴端点相对于中心的向量 [x, y, z]"
            },
            "ratio": {
                "editable": True,
                "type": "number",
                "min": 0.001,
                "max": 1.0,
                "description": "短轴与长轴的比值，0-1之间"
            },
        },
        "SPLINE": {
            "control_points": {
                "editable": True,
                "type": "point_array",
                "min_points": 2,
                "description": "控制点坐标数组"
            },
            "degree": {
                "editable": False,
                "type": "number",
                "description": "样条曲线阶数，不可修改"
            },
        },
    }
    
    # 合并参数定义
    result = {**readonly_params, **common_editable}
    if entity_type in entity_params:
        result.update(entity_params[entity_type])
    
    return result


def parse_dxf_to_template(dxf_path: Path) -> dict:
    """
    解析 DXF 文件，提取图层、实体、块等信息，生成模板 JSON
    每个实体包含 editable_params 字段，标明哪些参数可编辑及其约束
    """
    try:
        import ezdxf
    except ImportError as e:
        raise HTTPException(500, "ezdxf 未安装，请执行 pip install ezdxf") from e
    
    # 尝试多种编码读取 DXF 文件
    doc = None
    for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'cp936']:
        try:
            doc = ezdxf.readfile(str(dxf_path), encoding=encoding)
            break
        except (UnicodeDecodeError, ezdxf.DXFError):
            continue
    
    if doc is None:
        # 最后尝试忽略错误
        doc = ezdxf.readfile(str(dxf_path), encoding='utf-8', errors='replace')
    msp = doc.modelspace()
    
    template = {
        "version": "1.0",
        "dxf_version": doc.dxfversion,
        "created_at": datetime.now().isoformat(),
        "units": str(doc.header.get("$INSUNITS", 0)),
        "layers": [],
        "blocks": [],
        "entities": [],
        "text_styles": [],
        "dimension_styles": [],
        "linetypes": [],
        "extent": None,
        "editable_rules": {
            "description": "参数编辑规则说明",
            "param_types": {
                "number": "数值类型，需遵守 min/max 约束",
                "string": "字符串类型，可能有 max_length 约束",
                "point": "坐标点 [x, y, z]，可任意修改",
                "point_array": "坐标点数组，需遵守 min_points 约束",
                "angle": "角度值（度），通常 0-360",
                "scale": "缩放比例 [x, y, z]，需遵守 min/max 约束",
                "color": "颜色索引 0-256",
                "boolean": "布尔值 true/false"
            }
        },
    }
    
    # 解析图层
    for layer in doc.layers:
        layer_info = {
            "name": layer.dxf.name,
            "color": layer.dxf.color,
            "linetype": layer.dxf.linetype,
            "is_on": layer.is_on(),
            "is_locked": layer.is_locked(),
            "is_frozen": layer.is_frozen(),
        }
        template["layers"].append(layer_info)
    
    # 解析块定义
    for block in doc.blocks:
        if block.name.startswith("*"):  # 跳过匿名块
            continue
        block_info = {
            "name": block.name,
            "base_point": list(block.base_point) if block.base_point else [0, 0, 0],
            "entity_count": len(list(block)),
        }
        template["blocks"].append(block_info)
    
    # 解析文字样式
    for style in doc.styles:
        style_info = {
            "name": style.dxf.name,
            "font": style.dxf.font,
            "height": style.dxf.height,
        }
        template["text_styles"].append(style_info)
    
    # 解析标注样式
    for dimstyle in doc.dimstyles:
        dimstyle_info = {
            "name": dimstyle.dxf.name,
        }
        template["dimension_styles"].append(dimstyle_info)
    
    # 解析线型
    for linetype in doc.linetypes:
        linetype_info = {
            "name": linetype.dxf.name,
            "description": linetype.dxf.description,
        }
        template["linetypes"].append(linetype_info)
    
    # 解析实体
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    entity_summary = {}
    
    for entity in msp:
        entity_type = entity.dxftype()
        entity_summary[entity_type] = entity_summary.get(entity_type, 0) + 1
        
        entity_info = {
            "type": entity_type,
            "handle": entity.dxf.handle,
            "layer": entity.dxf.layer,
        }
        
        # 提取实体特定属性
        if entity_type == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            entity_info["start"] = [start.x, start.y, start.z]
            entity_info["end"] = [end.x, end.y, end.z]
            min_x = min(min_x, start.x, end.x)
            min_y = min(min_y, start.y, end.y)
            max_x = max(max_x, start.x, end.x)
            max_y = max(max_y, start.y, end.y)
            
        elif entity_type == "CIRCLE":
            center = entity.dxf.center
            entity_info["center"] = [center.x, center.y, center.z]
            entity_info["radius"] = entity.dxf.radius
            min_x = min(min_x, center.x - entity.dxf.radius)
            min_y = min(min_y, center.y - entity.dxf.radius)
            max_x = max(max_x, center.x + entity.dxf.radius)
            max_y = max(max_y, center.y + entity.dxf.radius)
            
        elif entity_type == "ARC":
            center = entity.dxf.center
            entity_info["center"] = [center.x, center.y, center.z]
            entity_info["radius"] = entity.dxf.radius
            entity_info["start_angle"] = entity.dxf.start_angle
            entity_info["end_angle"] = entity.dxf.end_angle
            min_x = min(min_x, center.x - entity.dxf.radius)
            min_y = min(min_y, center.y - entity.dxf.radius)
            max_x = max(max_x, center.x + entity.dxf.radius)
            max_y = max(max_y, center.y + entity.dxf.radius)
            
        elif entity_type in ("TEXT", "MTEXT"):
            if entity_type == "MTEXT":
                insert = entity.dxf.insert
                entity_info["insert"] = [insert.x, insert.y, insert.z]
                entity_info["text"] = clean_text(entity.text)
            else:
                insert = entity.dxf.insert
                entity_info["insert"] = [insert.x, insert.y, insert.z]
                entity_info["text"] = clean_text(entity.dxf.text)
                entity_info["height"] = entity.dxf.height
            min_x = min(min_x, insert.x)
            min_y = min(min_y, insert.y)
            max_x = max(max_x, insert.x)
            max_y = max(max_y, insert.y)
            
        elif entity_type == "LWPOLYLINE":
            points = list(entity.get_points())
            entity_info["points"] = [[p[0], p[1]] for p in points]
            entity_info["is_closed"] = entity.closed
            for p in points:
                min_x = min(min_x, p[0])
                min_y = min(min_y, p[1])
                max_x = max(max_x, p[0])
                max_y = max(max_y, p[1])
                
        elif entity_type == "POLYLINE":
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            entity_info["points"] = list(points)
            entity_info["is_closed"] = entity.is_closed
            for p in points:
                min_x = min(min_x, p[0])
                min_y = min(min_y, p[1])
                max_x = max(max_x, p[0])
                max_y = max(max_y, p[1])
                
        elif entity_type == "INSERT":
            insert = entity.dxf.insert
            entity_info["insert"] = [insert.x, insert.y, insert.z]
            entity_info["block_name"] = entity.dxf.name
            entity_info["scale"] = [entity.dxf.xscale, entity.dxf.yscale, entity.dxf.zscale]
            entity_info["rotation"] = entity.dxf.rotation
            min_x = min(min_x, insert.x)
            min_y = min(min_y, insert.y)
            max_x = max(max_x, insert.x)
            max_y = max(max_y, insert.y)
            
        elif entity_type == "DIMENSION":
            entity_info["dimension_type"] = entity.dimtype
            
        elif entity_type == "HATCH":
            entity_info["pattern_name"] = entity.dxf.pattern_name
            entity_info["solid_fill"] = entity.dxf.solid_fill
            
        elif entity_type == "ELLIPSE":
            center = entity.dxf.center
            entity_info["center"] = [center.x, center.y, center.z]
            major_axis = entity.dxf.major_axis
            entity_info["major_axis"] = [major_axis.x, major_axis.y, major_axis.z]
            entity_info["ratio"] = entity.dxf.ratio
            
        elif entity_type == "SPLINE":
            control_points = list(entity.control_points)
            entity_info["control_points"] = [[p.x, p.y, p.z] for p in control_points]
            entity_info["degree"] = entity.dxf.degree
        
        # 为每个实体添加可编辑参数定义
        entity_info["editable_params"] = define_editable_params(entity_type, entity)
        
        template["entities"].append(entity_info)
    
    # 设置范围
    if min_x != float('inf'):
        template["extent"] = {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }
    
    # 添加实体统计
    template["entity_summary"] = entity_summary
    template["total_entities"] = len(template["entities"])
    
    return template


def upload_to_minio(file_path: Path, object_name: str, content_type: str = "application/octet-stream") -> str:
    """
    上传文件到 MinIO
    返回文件的公网访问 URL
    """
    client = get_s3_client()
    bucket_name = MINIO_CONFIG["bucket_name"]

    # 存在性检查，避免覆盖
    try:
        client.head_object(Bucket=bucket_name, Key=object_name)
        raise FileExistsError(f"MinIO 对象已存在: {object_name}")
    except Exception as exc:
        # 如果是不存在则继续上传，其他异常抛出
        code = getattr(getattr(exc, "response", {}), "get", lambda *args, **kwargs: None)("Error", {}).get("Code") if hasattr(exc, "response") else None
        if code not in {"404", "NoSuchKey", "NotFound", None}:  # None 表示非 ClientError
            raise

    # 上传文件
    with open(file_path, 'rb') as f:
        client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=f,
            ContentType=content_type,
        )
    
    # 返回公网访问 URL
    return get_file_public_url(object_name)


def upload_bytes_to_minio(data: bytes, object_name: str, content_type: str = "application/json") -> str:
    """
    上传字节数据到 MinIO
    返回文件的公网访问 URL
    """
    client = get_s3_client()
    bucket_name = MINIO_CONFIG["bucket_name"]
    
    # 上传数据
    client.put_object(
        Bucket=bucket_name,
        Key=object_name,
        Body=data,
        ContentType=content_type,
    )
    
    # 返回公网访问 URL
    return get_file_public_url(object_name)


def save_template_to_db(
    template_id: str,
    name: str,
    original_filename: str,
    file_url: str,
    template_url: str,
    template_data: dict,
    is_official: bool = False,
    status: str = "ready",
) -> dict:
    """
    保存模板信息到 MySQL 数据库
    """
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO dxf_template (
                    id, name, original_filename, file_url, template_url,
                    dxf_version, layer_count, block_count, entity_count,
                    extent_min_x, extent_min_y, extent_max_x, extent_max_y,
                    is_official, status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            extent = template_data.get("extent") or {}
            cursor.execute(sql, (
                template_id,
                name,
                original_filename,
                file_url,
                template_url,
                template_data.get("dxf_version", ""),
                len(template_data.get("layers", [])),
                len(template_data.get("blocks", [])),
                template_data.get("total_entities", 0),
                extent.get("min_x"),
                extent.get("min_y"),
                extent.get("max_x"),
                extent.get("max_y"),
                1 if is_official else 0,
                status,
                datetime.now(),
            ))
        conn.commit()
        
        return {
            "id": template_id,
            "name": name,
            "original_filename": original_filename,
            "file_url": file_url,
            "template_url": template_url,
        }
    finally:
        conn.close()


def get_template_from_db(template_id: str) -> Optional[dict]:
    """
    从数据库获取模板信息
    """
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM dxf_template WHERE id = %s"
            cursor.execute(sql, (template_id,))
            result = cursor.fetchone()
            if result:
                # 转换 datetime 为字符串
                if result.get("created_at") and hasattr(result["created_at"], 'isoformat'):
                    result["created_at"] = result["created_at"].isoformat()
                if result.get("updated_at") and hasattr(result["updated_at"], 'isoformat'):
                    result["updated_at"] = result["updated_at"].isoformat()
            return result
    finally:
        conn.close()


def list_templates_from_db(page: int = 1, page_size: int = 20, name: Optional[str] = None, is_official: Optional[bool] = None) -> dict:
    """
    分页获取模板列表，支持按名称模糊搜索和官方/用户筛选
    """
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # 构建查询条件
            where_clauses = []
            params = []
            if name:
                where_clauses.append("name LIKE %s")
                params.append(f"%{name}%")
            if is_official is not None:
                where_clauses.append("is_official = %s")
                params.append(1 if is_official else 0)
            
            where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            # 获取总数
            count_sql = f"SELECT COUNT(*) as total FROM dxf_template {where_clause}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()["total"]
            
            # 分页查询
            offset = (page - 1) * page_size
            sql = f"""
                SELECT id, name, original_filename, file_url, template_url,
                       dxf_version, layer_count, block_count, entity_count,
                       is_official, created_at
                FROM dxf_template
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, params + [page_size, offset])
            records = cursor.fetchall()
            
            # 转换 datetime
            for r in records:
                if r.get("created_at"):
                    r["created_at"] = r["created_at"].isoformat()
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "records": records,
            }
    finally:
        conn.close()


@router.post("/upload")
async def upload_dxf_template(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="DXF 或 DWG 文件"),
    name: Optional[str] = Form(None, description="模板名称，不传则使用文件名"),
    x_api_key: Optional[str] = Header(None, description="官方 API Key"),
):
    """
    上传 DXF/DWG 文件，解析成模板 JSON，存储到 MinIO 和 MySQL
    
    参数:
    - file: DXF 或 DWG 文件
    - name: 模板名称（可选，不传则使用文件名）
    
    请求头（官方上传，满足任一即可）:
    - X-API-Key: 官方 API Key
    - X-Timestamp + X-Signature: 时间戳签名（防重放）
    - 或通过 IP 白名单自动识别
    
    返回:
    - id: 模板 ID
    - name: 模板名称
    - original_filename: 原始文件名
    - file_url: 原始文件的 MinIO URL
    - template_url: 模板 JSON 的 MinIO URL
    - is_official: 是否官方模板
    - template: 解析后的模板数据
    """
    if not file.filename:
        raise HTTPException(400, "缺少文件名")
    
    lower_name = file.filename.lower()
    if not (lower_name.endswith(".dxf") or lower_name.endswith(".dwg") or lower_name.endswith(".md")):
        raise HTTPException(400, "文件必须是 .dxf 或 .dwg 或 .md 格式")
    
    template_id = uuid.uuid4().hex
    job_dir = WORK_DIR / template_id
    job_dir.mkdir()
    
    try:
        # 保存上传的文件
        src_path = job_dir / file.filename
        written = 0
        with open(src_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "文件太大")
                out.write(chunk)
        
        # 如果是 DWG，先转换为 DXF
        if lower_name.endswith(".dwg"):
            from server import _run_dwg_to_dxf
            dxf_path = job_dir / (Path(file.filename).stem + ".dxf")
            _run_dwg_to_dxf(src_path, dxf_path)
        else:
            dxf_path = src_path
        
        # 判断是否官方上传（综合认证：IP白名单 / API Key / 签名）
        from auth_middleware import check_official_auth
        is_official = check_official_auth(request, x_api_key)
        
        # 模板名称：用户传入的 name，否则使用文件名（去掉后缀）
        template_name = name.strip() if name and name.strip() else Path(file.filename).stem
        
        # 解析 DXF 生成模板
        template_data = parse_dxf_to_template(dxf_path)
        template_data["id"] = template_id
        template_data["name"] = template_name
        template_data["original_filename"] = file.filename
        template_data["is_official"] = is_official
        
        # 上传原始文件到 MinIO
        file_object_name = f"dxf_templates/{template_id}/{file.filename}"
        file_url = upload_to_minio(
            src_path,
            file_object_name,
            content_type="application/dxf" if lower_name.endswith(".dxf") else "application/dwg",
        )
        
        # 不生成完整 JSON，直接使用原始 DXF
        template_url = file_url
        entity_count = template_data.get("total_entities", 0)
        
        # 保存到数据库（状态为 processing）
        db_result = save_template_to_db(
            template_id,
            template_name,
            file.filename,
            file_url,
            template_url,
            template_data,
            is_official,
            status="processing"  # 标记为处理中
        )
        
        LOG.info("模板上传成功: id=%s, name=%s, filename=%s, entities=%s", template_id, template_name, file.filename, entity_count)
        
        # 添加后台任务：提取可编辑参数
        background_tasks.add_task(
            extract_editable_params_async,
            template_id,
            dxf_path,
            template_data
        )
        
        # 返回简化的响应数据（不包含完整 template，避免响应过大）
        # 客户端可以通过 template_url 获取完整模板数据
        return JSONResponse({
            "code": 0,
            "message": "上传成功，正在后台提取可编辑参数",
            "data": {
                "id": template_id,
                "name": template_name,
                "original_filename": file.filename,
                "file_url": file_url,
                "template_url": template_url,
                "is_official": is_official,
                "status": "processing",  # 处理中
                "dxf_version": template_data.get("dxf_version"),
                "layer_count": len(template_data.get("layers", [])),
                "block_count": len(template_data.get("blocks", [])),
                "entity_count": template_data.get("total_entities", 0),
                "extent": template_data.get("extent"),
                "created_at": template_data.get("created_at")
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("模板上传失败")
        raise HTTPException(500, f"上传失败: {e}") from e
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@router.get("/list")
async def list_templates(
    page: int = 1,
    page_size: int = 20,
    name: Optional[str] = None,
    is_official: Optional[bool] = None,
):
    """
    分页获取模板列表
    
    参数:
    - page: 页码，默认 1
    - page_size: 每页数量，默认 20
    - name: 模板名称（模糊搜索，可选）
    - is_official: 是否官方模板（可选，true=官方，false=用户，不传=全部）
    """
    try:
        result = list_templates_from_db(page, page_size, name, is_official)
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": result,
        })
    except Exception as e:
        LOG.exception("查询模板列表失败")
        raise HTTPException(500, f"查询失败: {e}") from e


@router.get("/detail")
async def get_template_detail(
    id: str,
):
    """
    获取模板详情
    """
    if not id:
        raise HTTPException(400, "缺少模板 ID")
    
    try:
        result = get_template_from_db(id)
        if not result:
            raise HTTPException(404, "模板不存在")
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": result,
        })
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("查询模板详情失败")
        raise HTTPException(500, f"查询失败: {e}") from e


@router.get("/template-json")
async def get_template_json(id: str):
    """
    获取模板的完整 JSON 数据（从 MinIO）
    
    用于获取大文件的完整模板数据，避免上传接口响应过大
    """
    if not id:
        raise HTTPException(400, "缺少模板 ID")
    
    try:
        # 从数据库获取 template_url
        result = get_template_from_db(id)
        if not result:
            raise HTTPException(404, "模板不存在")
        
        template_url = result.get("template_url")
        if not template_url:
            raise HTTPException(404, "模板 JSON 不存在")
        
        # 从 MinIO 读取 JSON 文件
        import requests
        response = requests.get(template_url, timeout=30)
        if response.status_code != 200:
            raise HTTPException(500, f"无法获取模板数据: HTTP {response.status_code}")
        
        template_data = response.json()
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": template_data
        })
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("获取模板 JSON 失败")
        raise HTTPException(500, f"获取失败: {e}") from e


@router.post("/generate-dxf")
async def generate_dxf_from_template(
    template_id: str = Form(..., description="模板 ID"),
    modifications: Optional[str] = Form(None, description="修改内容（JSON 字符串）"),
):
    """
    根据模板生成新的 DXF 文件（直接基于原始 DXF 修改）
    
    工作原理：
    1. 从 MinIO 下载原始 DXF 文件
    2. 使用 ezdxf 打开并修改
    3. 保存为新的 DXF 文件
    4. 上传到 MinIO
    
    优点：
    - 不需要传输或解析巨大的 JSON
    - 直接操作 DXF 文件，保留所有原始信息
    - 内存占用小
    
    修改内容格式：
    {
      "entities": [
        {"handle": "1A0", "start": [100, 200, 0], "end": [300, 400, 0]},
        {"handle": "1B5", "text": "新文字"}
      ]
    }
    """
    try:
        import ezdxf
        import json
        import requests
        from io import BytesIO
        
        # 从数据库获取模板信息
        db_template = get_template_from_db(template_id)
        if not db_template:
            raise HTTPException(404, "模板不存在")
        
        file_url = db_template.get("file_url")
        if not file_url:
            raise HTTPException(404, "原始 DXF 文件不存在")
        
        # 解析修改内容
        mods = {}
        if modifications:
            try:
                mods = json.loads(modifications)
            except json.JSONDecodeError:
                raise HTTPException(400, "修改内容格式错误")
        
        # 生成唯一 ID
        job_id = uuid.uuid4().hex
        job_dir = WORK_DIR / job_id
        job_dir.mkdir()
        
        try:
            # 从 MinIO 下载原始 DXF 文件
            LOG.info(f"下载原始 DXF: {file_url}")
            response = requests.get(file_url, timeout=120)
            if response.status_code != 200:
                raise HTTPException(500, f"无法下载 DXF 文件: HTTP {response.status_code}")
            
            # 保存到临时文件
            temp_dxf = job_dir / "template.dxf"
            temp_dxf.write_bytes(response.content)
            
            # 使用 ezdxf 打开 DXF 文件
            doc = ezdxf.readfile(str(temp_dxf))
            msp = doc.modelspace()
            
            # 应用修改
            modified_count = 0
            if mods and "entities" in mods:
                for mod_entity in mods["entities"]:
                    handle = mod_entity.get("handle")
                    if not handle:
                        continue
                    
                    try:
                        # 通过 handle 查找实体
                        entity = doc.entitydb.get(handle)
                        if not entity:
                            LOG.warning(f"未找到实体: {handle}")
                            continue
                        
                        # 根据实体类型应用修改
                        entity_type = entity.dxftype()
                        
                        if entity_type == "LINE":
                            if "start" in mod_entity:
                                entity.dxf.start = tuple(mod_entity["start"])
                            if "end" in mod_entity:
                                entity.dxf.end = tuple(mod_entity["end"])
                        
                        elif entity_type == "CIRCLE":
                            if "center" in mod_entity:
                                entity.dxf.center = tuple(mod_entity["center"])
                            if "radius" in mod_entity:
                                entity.dxf.radius = mod_entity["radius"]
                        
                        elif entity_type == "ARC":
                            if "center" in mod_entity:
                                entity.dxf.center = tuple(mod_entity["center"])
                            if "radius" in mod_entity:
                                entity.dxf.radius = mod_entity["radius"]
                            if "start_angle" in mod_entity:
                                entity.dxf.start_angle = mod_entity["start_angle"]
                            if "end_angle" in mod_entity:
                                entity.dxf.end_angle = mod_entity["end_angle"]
                        
                        elif entity_type in ["TEXT", "MTEXT"]:
                            if "text" in mod_entity:
                                entity.dxf.text = mod_entity["text"]
                            if "insert" in mod_entity:
                                entity.dxf.insert = tuple(mod_entity["insert"])
                            if "height" in mod_entity:
                                entity.dxf.height = mod_entity["height"]
                            if "char_height" in mod_entity:
                                entity.dxf.char_height = mod_entity["char_height"]
                        
                        elif entity_type == "LWPOLYLINE":
                            if "points" in mod_entity:
                                entity.set_points(mod_entity["points"])
                        
                        # 可以继续添加其他实体类型...
                        
                        modified_count += 1
                        LOG.info(f"修改实体: {handle} ({entity_type})")
                        
                    except Exception as e:
                        LOG.warning(f"修改实体失败: {handle}, 错误: {e}")
                        continue
            
            # 保存 DXF 文件
            output_filename = db_template.get("name", "generated") + "_modified.dxf"
            output_path = job_dir / output_filename
            doc.saveas(str(output_path))
            
            # 上传到 MinIO
            object_name = f"dxf_generated/{job_id}/{output_filename}"
            file_url = upload_to_minio(
                output_path,
                object_name,
                content_type="application/dxf"
            )
            
            LOG.info(f"生成 DXF 成功: {output_filename}, URL: {file_url}")
            
            return JSONResponse({
                "code": 0,
                "message": "生成成功",
                "data": {
                    "filename": output_filename,
                    "file_url": file_url,
                    "entity_count": len(template_data.get("entities", []))
                }
            })
        
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("生成 DXF 失败")
        raise HTTPException(500, f"生成失败: {e}") from e


@router.delete("/delete")
async def delete_template(
    id: str,
):
    """
    删除模板
    """
    if not id:
        raise HTTPException(400, "缺少模板 ID")
    
    conn = get_mysql_connection()
    try:
        # 先查询模板信息
        template = get_template_from_db(id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 删除 MinIO 中的文件
        client = get_s3_client()
        bucket_name = MINIO_CONFIG["bucket_name"]
        prefix = f"dxf_templates/{id}/"
        
        # 列出并删除所有对象
        response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        if 'Contents' in response:
            for obj in response['Contents']:
                client.delete_object(Bucket=bucket_name, Key=obj['Key'])
        
        # 删除数据库记录
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM dxf_template WHERE id = %s", (id,))
        conn.commit()
        
        LOG.info("模板删除成功: id=%s", id)
        
        return JSONResponse({
            "code": 0,
            "message": "删除成功",
        })
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("删除模板失败")
        raise HTTPException(500, f"删除失败: {e}") from e
    finally:
        conn.close()
