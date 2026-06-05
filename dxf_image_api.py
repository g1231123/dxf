"""
DXF 图片点击编辑 API
1. 生成 DXF 预览图
2. 根据点击坐标查找实体
3. 返回实体参数
"""
from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import Response, JSONResponse
import logging
import requests
import tempfile
from pathlib import Path
import io

LOG = logging.getLogger("dxf_image")

router = APIRouter(prefix="/template/image", tags=["DXF Image Editor"])


def get_template_from_db(template_id: str):
    """获取模板信息"""
    from dxf_template_service import get_template_from_db as get_template
    return get_template(template_id)


@router.get("/preview")
async def generate_preview_image(template_id: str, width: int = 1200):
    """
    生成 DXF 预览图（使用 QGIS）
    
    参数:
    - template_id: 模板 ID
    - width: 图片宽度（默认 1200px）
    
    返回: PNG 图片
    """
    try:
        from qgis.core import QgsVectorLayer, QgsProject, QgsMapSettings, QgsMapRendererCustomPainterJob
        from qgis.PyQt.QtCore import QSize
        from qgis.PyQt.QtGui import QImage, QPainter, QColor
        
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 下载 DXF 文件
        LOG.info(f"下载 DXF: {template['file_url']}")
        response = requests.get(template["file_url"], timeout=120)
        if response.status_code != 200:
            raise HTTPException(500, "无法下载 DXF 文件")
        
        # 保存到临时文件
        temp_file = Path(tempfile.gettempdir()) / f"{template_id}.dxf"
        temp_file.write_bytes(response.content)
        
        # 使用 QGIS 加载 DXF
        layer = QgsVectorLayer(str(temp_file), "dxf", "ogr")
        if not layer.isValid():
            raise Exception("无法加载 DXF 文件")
        
        # 添加到项目
        QgsProject.instance().addMapLayer(layer)
        
        # 设置渲染参数
        settings = QgsMapSettings()
        settings.setLayers([layer])
        settings.setBackgroundColor(QColor(255, 255, 255))
        settings.setOutputSize(QSize(width, width))
        settings.setExtent(layer.extent())
        
        # 创建图像
        from qgis.PyQt.QtGui import QImage
        image = QImage(QSize(width, width), QImage.Format.Format_ARGB32)
        image.fill(QColor(255, 255, 255))
        
        # 渲染
        painter = QPainter(image)
        job = QgsMapRendererCustomPainterJob(settings, painter)
        job.start()
        job.waitForFinished()
        painter.end()
        
        # 保存为 PNG（先保存到临时文件）
        temp_png = Path(tempfile.gettempdir()) / f"{template_id}.png"
        image.save(str(temp_png), "PNG")
        
        # 读取文件内容
        png_content = temp_png.read_bytes()
        
        # 清理
        QgsProject.instance().removeMapLayer(layer)
        temp_file.unlink(missing_ok=True)
        temp_png.unlink(missing_ok=True)
        
        LOG.info(f"预览图生成成功: {template_id}")
        
        return Response(content=png_content, media_type="image/png")
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("生成预览图失败")
        raise HTTPException(500, f"生成预览图失败: {e}") from e


@router.get("/extent")
async def get_dxf_extent(template_id: str):
    """
    获取 DXF 文件的范围（用于坐标转换）
    """
    try:
        import ezdxf
        
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 下载 DXF 文件
        response = requests.get(template["file_url"], timeout=120)
        if response.status_code != 200:
            raise HTTPException(500, "无法下载 DXF 文件")
        
        # 保存到临时文件
        temp_file = Path(tempfile.gettempdir()) / f"{template_id}.dxf"
        temp_file.write_bytes(response.content)
        
        # 读取 DXF（自动检测编码）
        # 先尝试默认编码（通常是 UTF-8），再尝试 GBK
        try:
            doc = ezdxf.readfile(str(temp_file))
        except:
            try:
                doc = ezdxf.readfile(str(temp_file), encoding='gbk')
            except:
                try:
                    doc = ezdxf.readfile(str(temp_file), encoding='gb18030')
                except:
                    # 使用 replace 而不是 ignore，避免产生替代字符
                    doc = ezdxf.readfile(str(temp_file), errors='replace')
        msp = doc.modelspace()
        
        # 计算范围
        extmin = [float('inf'), float('inf')]
        extmax = [float('-inf'), float('-inf')]
        
        for entity in msp:
            try:
                if hasattr(entity.dxf, 'start'):
                    pt = entity.dxf.start
                    extmin[0] = min(extmin[0], pt.x)
                    extmin[1] = min(extmin[1], pt.y)
                    extmax[0] = max(extmax[0], pt.x)
                    extmax[1] = max(extmax[1], pt.y)
                if hasattr(entity.dxf, 'end'):
                    pt = entity.dxf.end
                    extmin[0] = min(extmin[0], pt.x)
                    extmin[1] = min(extmin[1], pt.y)
                    extmax[0] = max(extmax[0], pt.x)
                    extmax[1] = max(extmax[1], pt.y)
                if hasattr(entity.dxf, 'center'):
                    pt = entity.dxf.center
                    extmin[0] = min(extmin[0], pt.x)
                    extmin[1] = min(extmin[1], pt.y)
                    extmax[0] = max(extmax[0], pt.x)
                    extmax[1] = max(extmax[1], pt.y)
                if hasattr(entity.dxf, 'insert'):
                    pt = entity.dxf.insert
                    extmin[0] = min(extmin[0], pt.x)
                    extmin[1] = min(extmin[1], pt.y)
                    extmax[0] = max(extmax[0], pt.x)
                    extmax[1] = max(extmax[1], pt.y)
            except:
                pass
        
        temp_file.unlink(missing_ok=True)
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": {
                "min": extmin,
                "max": extmax,
                "width": extmax[0] - extmin[0],
                "height": extmax[1] - extmin[1]
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("获取范围失败")
        raise HTTPException(500, f"获取范围失败: {e}") from e


@router.get("/entity-at")
async def get_entity_at_position(
    template_id: str,
    x: float,
    y: float,
    tolerance: float = 500.0
):
    """
    根据点击坐标查找实体
    
    参数:
    - template_id: 模板 ID
    - x, y: 点击坐标（DXF 图纸坐标系）
    - tolerance: 容差（默认 500 单位）
    
    返回: 找到的实体列表
    """
    try:
        import ezdxf
        from ezdxf.math import Vec2
        
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 下载 DXF 文件
        response = requests.get(template["file_url"], timeout=120)
        if response.status_code != 200:
            raise HTTPException(500, "无法下载 DXF 文件")
        
        # 保存到临时文件
        temp_file = Path(tempfile.gettempdir()) / f"{template_id}.dxf"
        temp_file.write_bytes(response.content)
        
        # 读取 DXF（自动检测编码）
        # 先尝试默认编码（通常是 UTF-8），再尝试 GBK
        try:
            doc = ezdxf.readfile(str(temp_file))
        except:
            try:
                doc = ezdxf.readfile(str(temp_file), encoding='gbk')
            except:
                try:
                    doc = ezdxf.readfile(str(temp_file), encoding='gb18030')
                except:
                    # 使用 replace 而不是 ignore，避免产生替代字符
                    doc = ezdxf.readfile(str(temp_file), errors='replace')
        msp = doc.modelspace()
        
        click_point = Vec2(x, y)
        found_entities = []
        
        total_entities = 0
        # 遍历所有实体，找到距离点击位置最近的
        for entity in msp:
            total_entities += 1
            entity_type = entity.dxftype()
            distance = float('inf')
            
            try:
                if entity_type == "LINE":
                    # 计算点到线段的距离
                    start_pt = entity.dxf.start
                    end_pt = entity.dxf.end
                    start = Vec2(start_pt.x, start_pt.y)
                    end = Vec2(end_pt.x, end_pt.y)
                    # 计算点到线段的距离
                    line_vec = end - start
                    point_vec = click_point - start
                    line_len = line_vec.magnitude
                    if line_len == 0:
                        distance = click_point.distance(start)
                    else:
                        t = max(0, min(1, point_vec.dot(line_vec) / (line_len * line_len)))
                        projection = start + line_vec * t
                        distance = click_point.distance(projection)
                
                elif entity_type == "CIRCLE":
                    # 计算点到圆的距离
                    center_pt = entity.dxf.center
                    center = Vec2(center_pt.x, center_pt.y)
                    radius = entity.dxf.radius
                    dist_to_center = click_point.distance(center)
                    distance = abs(dist_to_center - radius)
                
                elif entity_type == "ARC":
                    # 简化：计算点到圆弧圆心的距离
                    center_pt = entity.dxf.center
                    center = Vec2(center_pt.x, center_pt.y)
                    distance = click_point.distance(center)
                
                elif entity_type in ["TEXT", "MTEXT"]:
                    # 计算点到文字插入点的距离
                    insert_pt = entity.dxf.insert
                    insert = Vec2(insert_pt.x, insert_pt.y)
                    distance = click_point.distance(insert)
                
                # 如果在容差范围内，添加到结果
                if distance <= tolerance:
                    # 处理图层名编码
                    layer_name = entity.dxf.layer
                    if isinstance(layer_name, str):
                        layer_name = layer_name.encode('utf-8', errors='ignore').decode('utf-8')
                    
                    entity_data = {
                        "handle": entity.dxf.handle,
                        "type": entity_type,
                        "layer": layer_name,
                        "distance": distance,
                        "params": {
                            # 通用属性：颜色和线宽
                            "color": {
                                "value": entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
                                "editable": True,
                                "type": "number",
                                "description": "颜色索引（0-256，256=随层）",
                                "min": 0,
                                "max": 256
                            },
                            "lineweight": {
                                "value": entity.dxf.lineweight if hasattr(entity.dxf, 'lineweight') else -1,
                                "editable": True,
                                "type": "number",
                                "description": "线宽（-1=随层，-2=随块，-3=默认）"
                            }
                        }
                    }
                    
                    # 提取参数并标注可编辑性
                    if entity_type == "LINE":
                        entity_data["params"].update({
                            "start": {
                                "value": list(entity.dxf.start),
                                "editable": True,
                                "type": "point",
                                "description": "起点坐标 [x, y, z]"
                            },
                            "end": {
                                "value": list(entity.dxf.end),
                                "editable": True,
                                "type": "point",
                                "description": "终点坐标 [x, y, z]"
                            }
                        })
                    elif entity_type == "CIRCLE":
                        entity_data["params"].update({
                            "center": {
                                "value": list(entity.dxf.center),
                                "editable": True,
                                "type": "point",
                                "description": "圆心坐标 [x, y, z]"
                            },
                            "radius": {
                                "value": entity.dxf.radius,
                                "editable": True,
                                "type": "number",
                                "description": "半径",
                                "min": 0.001
                            }
                        })
                    elif entity_type in ["TEXT", "MTEXT"]:
                        # 处理文本，确保可以 JSON 序列化
                        text_value = entity.dxf.text
                        # 移除无法编码的字符
                        if isinstance(text_value, str):
                            text_value = text_value.encode('utf-8', errors='ignore').decode('utf-8')
                        
                        entity_data["params"].update({
                            "text": {
                                "value": text_value,
                                "editable": True,
                                "type": "string",
                                "description": "文字内容"
                            },
                            "insert": {
                                "value": list(entity.dxf.insert) if hasattr(entity.dxf, 'insert') else None,
                                "editable": True,
                                "type": "point",
                                "description": "插入点坐标 [x, y, z]"
                            },
                            "height": {
                                "value": entity.dxf.height if hasattr(entity.dxf, 'height') else None,
                                "editable": True,
                                "type": "number",
                                "description": "文字高度",
                                "min": 0.1
                            }
                        })
                    elif entity_type == "ARC":
                        entity_data["params"].update({
                            "center": {
                                "value": list(entity.dxf.center),
                                "editable": True,
                                "type": "point",
                                "description": "圆心坐标 [x, y, z]"
                            },
                            "radius": {
                                "value": entity.dxf.radius,
                                "editable": True,
                                "type": "number",
                                "description": "半径",
                                "min": 0.001
                            },
                            "start_angle": {
                                "value": entity.dxf.start_angle,
                                "editable": True,
                                "type": "number",
                                "description": "起始角度（度）",
                                "min": 0,
                                "max": 360
                            },
                            "end_angle": {
                                "value": entity.dxf.end_angle,
                                "editable": True,
                                "type": "number",
                                "description": "结束角度（度）",
                                "min": 0,
                                "max": 360
                            }
                        })
                    elif entity_type == "ELLIPSE":
                        entity_data["params"].update({
                            "center": {
                                "value": list(entity.dxf.center),
                                "editable": True,
                                "type": "point",
                                "description": "椭圆中心坐标 [x, y, z]"
                            },
                            "major_axis": {
                                "value": list(entity.dxf.major_axis),
                                "editable": True,
                                "type": "point",
                                "description": "长轴向量 [x, y, z]"
                            },
                            "ratio": {
                                "value": entity.dxf.ratio,
                                "editable": True,
                                "type": "number",
                                "description": "短轴/长轴比例",
                                "min": 0.001,
                                "max": 1.0
                            },
                            "start_param": {
                                "value": entity.dxf.start_param if hasattr(entity.dxf, 'start_param') else 0,
                                "editable": True,
                                "type": "number",
                                "description": "起始参数"
                            },
                            "end_param": {
                                "value": entity.dxf.end_param if hasattr(entity.dxf, 'end_param') else 6.283185307179586,
                                "editable": True,
                                "type": "number",
                                "description": "结束参数"
                            }
                        })
                    elif entity_type == "SPLINE":
                        # 样条曲线的控制点
                        control_points = []
                        if hasattr(entity, 'control_points'):
                            control_points = [list(pt) for pt in entity.control_points]
                        
                        entity_data["params"].update({
                            "degree": {
                                "value": entity.dxf.degree if hasattr(entity.dxf, 'degree') else 3,
                                "editable": False,
                                "type": "number",
                                "description": "样条曲线阶数（只读）"
                            },
                            "control_points": {
                                "value": control_points,
                                "editable": True,
                                "type": "point_array",
                                "description": "控制点数组 [[x,y,z], ...]"
                            },
                            "knots": {
                                "value": list(entity.knots()) if hasattr(entity, 'knots') else [],
                                "editable": False,
                                "type": "array",
                                "description": "节点向量（只读）"
                            }
                        })
                    elif entity_type == "LWPOLYLINE":
                        # 轻量多段线的顶点
                        vertices = []
                        if hasattr(entity, 'get_points'):
                            vertices = [list(pt)[:2] for pt in entity.get_points('xy')]
                        
                        entity_data["params"].update({
                            "vertices": {
                                "value": vertices,
                                "editable": True,
                                "type": "point_array",
                                "description": "顶点数组 [[x,y], ...]"
                            },
                            "closed": {
                                "value": entity.closed,
                                "editable": True,
                                "type": "boolean",
                                "description": "是否闭合"
                            },
                            "const_width": {
                                "value": entity.dxf.const_width if hasattr(entity.dxf, 'const_width') else 0,
                                "editable": True,
                                "type": "number",
                                "description": "恒定宽度"
                            }
                        })
                    elif entity_type == "INSERT":
                        # 块引用
                        entity_data["params"].update({
                            "name": {
                                "value": entity.dxf.name,
                                "editable": False,
                                "type": "string",
                                "description": "块名称（只读）"
                            },
                            "insert": {
                                "value": list(entity.dxf.insert),
                                "editable": True,
                                "type": "point",
                                "description": "插入点 [x, y, z]"
                            },
                            "xscale": {
                                "value": entity.dxf.xscale if hasattr(entity.dxf, 'xscale') else 1.0,
                                "editable": True,
                                "type": "number",
                                "description": "X 缩放比例"
                            },
                            "yscale": {
                                "value": entity.dxf.yscale if hasattr(entity.dxf, 'yscale') else 1.0,
                                "editable": True,
                                "type": "number",
                                "description": "Y 缩放比例"
                            },
                            "zscale": {
                                "value": entity.dxf.zscale if hasattr(entity.dxf, 'zscale') else 1.0,
                                "editable": True,
                                "type": "number",
                                "description": "Z 缩放比例"
                            },
                            "rotation": {
                                "value": entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0,
                                "editable": True,
                                "type": "number",
                                "description": "旋转角度（度）"
                            }
                        })
                    elif entity_type == "LEADER":
                        # 引线
                        vertices = []
                        if hasattr(entity, 'vertices'):
                            vertices = [list(v) for v in entity.vertices]
                        
                        entity_data["params"].update({
                            "vertices": {
                                "value": vertices,
                                "editable": True,
                                "type": "point_array",
                                "description": "引线顶点 [[x,y,z], ...]"
                            },
                            "has_arrowhead": {
                                "value": entity.dxf.has_arrowhead if hasattr(entity.dxf, 'has_arrowhead') else True,
                                "editable": True,
                                "type": "boolean",
                                "description": "是否显示箭头"
                            }
                        })
                    
                    found_entities.append(entity_data)
            
            except Exception as e:
                LOG.warning(f"处理实体失败: {entity_type}, {e}")
                continue
        
        # 按距离排序
        found_entities.sort(key=lambda e: e["distance"])
        
        # 清理临时文件
        temp_file.unlink(missing_ok=True)
        
        LOG.info(f"总实体数: {total_entities}, 找到 {len(found_entities)} 个实体, 点击坐标: ({x}, {y}), 容差: {tolerance}")
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": {
                "entities": found_entities[:10],  # 最多返回 10 个
                "total": len(found_entities),
                "total_entities": total_entities,
                "click_point": {"x": x, "y": y},
                "tolerance": tolerance
            }
        })
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("查找实体失败")
        raise HTTPException(500, f"查找实体失败: {e}") from e


@router.post("/generate")
async def generate_from_image_edits(
    template_id: str = Form(...),
    modifications: str = Form(...)
):
    """
    根据图片编辑生成新 DXF
    
    复用 dxf_ondemand_api 的生成接口
    """
    from dxf_ondemand_api import generate_from_modifications
    return await generate_from_modifications(template_id, modifications)
