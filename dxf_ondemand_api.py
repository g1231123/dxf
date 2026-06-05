"""
DXF 按需参数提取 API
不存储参数，实时从 DXF 文件提取
"""
from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import JSONResponse
import logging
import requests
import tempfile
from pathlib import Path

LOG = logging.getLogger("dxf_ondemand")

router = APIRouter(prefix="/template/ondemand", tags=["DXF On-Demand"])


def get_template_from_db(template_id: str):
    """获取模板信息"""
    from dxf_template_service import get_template_from_db as get_template
    return get_template(template_id)


@router.get("/layers")
async def get_layers(template_id: str):
    """
    获取 DXF 文件的图层列表（快速版本，返回常用图层）
    """
    try:
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 返回常用图层列表（不下载文件）
        # 用户可以直接输入图层名或选择常用图层
        common_layers = [
            {"name": "0", "description": "默认图层"},
            {"name": "墩身", "description": "墩身图层"},
            {"name": "标注", "description": "标注图层"},
            {"name": "尺寸", "description": "尺寸图层"},
            {"name": "文字", "description": "文字图层"},
            {"name": "轮廓", "description": "轮廓图层"},
            {"name": "中心线", "description": "中心线图层"},
        ]
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": {
                "layers": common_layers,
                "total": len(common_layers),
                "note": "这是常用图层列表，您也可以直接输入图层名"
            }
        })
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("获取图层失败")
        raise HTTPException(500, f"获取图层失败: {e}") from e


@router.get("/entities")
async def get_entities(
    template_id: str,
    layer: str = None,
    entity_type: str = None,
    limit: int = 100
):
    """
    按需获取实体参数
    
    参数:
    - template_id: 模板 ID
    - layer: 图层名称（可选）
    - entity_type: 实体类型（可选，如 LINE, TEXT, CIRCLE）
    - limit: 返回数量限制（默认 100）
    """
    try:
        import ezdxf
        
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 下载 DXF 文件
        response = requests.get(template["file_url"], timeout=60)
        if response.status_code != 200:
            raise HTTPException(500, "无法下载 DXF 文件")
        
        # 保存到临时文件
        temp_file = Path(tempfile.gettempdir()) / f"{template_id}.dxf"
        temp_file.write_bytes(response.content)
        
        # 读取实体
        doc = ezdxf.readfile(str(temp_file))
        msp = doc.modelspace()
        
        entities = []
        count = 0
        
        for entity in msp:
            # 筛选
            if layer and entity.dxf.layer != layer:
                continue
            if entity_type and entity.dxftype() != entity_type:
                continue
            
            # 提取参数
            entity_data = {
                "handle": entity.dxf.handle,
                "type": entity.dxftype(),
                "layer": entity.dxf.layer,
                "params": {}
            }
            
            # 根据类型提取参数
            if entity.dxftype() == "LINE":
                entity_data["params"] = {
                    "start": list(entity.dxf.start),
                    "end": list(entity.dxf.end)
                }
            elif entity.dxftype() == "CIRCLE":
                entity_data["params"] = {
                    "center": list(entity.dxf.center),
                    "radius": entity.dxf.radius
                }
            elif entity.dxftype() in ["TEXT", "MTEXT"]:
                entity_data["params"] = {
                    "text": entity.dxf.text,
                    "insert": list(entity.dxf.insert) if hasattr(entity.dxf, 'insert') else None,
                    "height": entity.dxf.height if hasattr(entity.dxf, 'height') else None
                }
            elif entity.dxftype() == "ARC":
                entity_data["params"] = {
                    "center": list(entity.dxf.center),
                    "radius": entity.dxf.radius,
                    "start_angle": entity.dxf.start_angle,
                    "end_angle": entity.dxf.end_angle
                }
            
            entities.append(entity_data)
            count += 1
            
            if count >= limit:
                break
        
        # 清理临时文件
        temp_file.unlink(missing_ok=True)
        
        return JSONResponse({
            "code": 0,
            "message": "查询成功",
            "data": {
                "entities": entities,
                "count": len(entities),
                "has_more": count >= limit
            }
        })
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("获取实体失败")
        raise HTTPException(500, f"获取实体失败: {e}") from e


@router.post("/generate")
async def generate_from_modifications(
    template_id: str = Form(...),
    modifications: str = Form(...)
):
    """
    根据修改生成新 DXF
    
    modifications 格式：
    [
      {"handle": "1A0", "changes": {"start": [100, 200, 0]}},
      {"handle": "1B5", "changes": {"text": "新文字"}}
    ]
    """
    try:
        import ezdxf
        import json
        import uuid
        import shutil
        
        mods = json.loads(modifications)
        
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 下载原始 DXF
        response = requests.get(template["file_url"], timeout=120)
        if response.status_code != 200:
            raise HTTPException(500, "无法下载 DXF 文件")
        
        # 创建工作目录
        job_id = uuid.uuid4().hex
        job_dir = Path(tempfile.gettempdir()) / f"dxf_job_{job_id}"
        job_dir.mkdir()
        
        try:
            temp_dxf = job_dir / "template.dxf"
            temp_dxf.write_bytes(response.content)
            
            # 打开 DXF（自动检测编码）
            try:
                doc = ezdxf.readfile(str(temp_dxf))
            except:
                try:
                    doc = ezdxf.readfile(str(temp_dxf), encoding='gbk')
                except:
                    try:
                        doc = ezdxf.readfile(str(temp_dxf), encoding='gb18030')
                    except:
                        doc = ezdxf.readfile(str(temp_dxf), errors='replace')
            
            # 应用修改
            modified_count = 0
            for mod in mods:
                handle = mod.get("handle")
                changes = mod.get("changes", {})
                
                if not handle or not changes:
                    continue
                
                try:
                    entity = doc.entitydb.get(handle)
                    if not entity:
                        continue
                    
                    entity_type = entity.dxftype()
                    
                    # 应用通用属性
                    if "color" in changes:
                        entity.dxf.color = changes["color"]
                    if "lineweight" in changes:
                        entity.dxf.lineweight = changes["lineweight"]
                    
                    # 应用实体特定修改
                    if entity_type == "LINE":
                        if "start" in changes:
                            entity.dxf.start = tuple(changes["start"])
                        if "end" in changes:
                            entity.dxf.end = tuple(changes["end"])
                    elif entity_type == "CIRCLE":
                        if "center" in changes:
                            entity.dxf.center = tuple(changes["center"])
                        if "radius" in changes:
                            entity.dxf.radius = changes["radius"]
                    elif entity_type in ["TEXT", "MTEXT"]:
                        if "text" in changes:
                            entity.dxf.text = changes["text"]
                        if "insert" in changes:
                            entity.dxf.insert = tuple(changes["insert"])
                        if "height" in changes:
                            entity.dxf.height = changes["height"]
                    elif entity_type == "ARC":
                        if "center" in changes:
                            entity.dxf.center = tuple(changes["center"])
                        if "radius" in changes:
                            entity.dxf.radius = changes["radius"]
                        if "start_angle" in changes:
                            entity.dxf.start_angle = changes["start_angle"]
                        if "end_angle" in changes:
                            entity.dxf.end_angle = changes["end_angle"]
                    elif entity_type == "ELLIPSE":
                        if "center" in changes:
                            entity.dxf.center = tuple(changes["center"])
                        if "major_axis" in changes:
                            entity.dxf.major_axis = tuple(changes["major_axis"])
                        if "ratio" in changes:
                            entity.dxf.ratio = changes["ratio"]
                        if "start_param" in changes:
                            entity.dxf.start_param = changes["start_param"]
                        if "end_param" in changes:
                            entity.dxf.end_param = changes["end_param"]
                    elif entity_type == "SPLINE":
                        if "control_points" in changes:
                            # 修改样条曲线控制点
                            control_points = changes["control_points"]
                            if hasattr(entity, 'set_control_points'):
                                entity.set_control_points([tuple(pt) for pt in control_points])
                    elif entity_type == "LWPOLYLINE":
                        if "vertices" in changes:
                            # 修改多段线顶点
                            vertices = changes["vertices"]
                            # 清除现有顶点并添加新顶点
                            entity.clear()
                            for pt in vertices:
                                if len(pt) == 2:
                                    entity.append((pt[0], pt[1]))
                                else:
                                    entity.append(tuple(pt))
                        if "closed" in changes:
                            entity.closed = changes["closed"]
                        if "const_width" in changes:
                            entity.dxf.const_width = changes["const_width"]
                    elif entity_type == "INSERT":
                        if "insert" in changes:
                            entity.dxf.insert = tuple(changes["insert"])
                        if "xscale" in changes:
                            entity.dxf.xscale = changes["xscale"]
                        if "yscale" in changes:
                            entity.dxf.yscale = changes["yscale"]
                        if "zscale" in changes:
                            entity.dxf.zscale = changes["zscale"]
                        if "rotation" in changes:
                            entity.dxf.rotation = changes["rotation"]
                    elif entity_type == "LEADER":
                        if "vertices" in changes:
                            # 修改引线顶点
                            vertices = changes["vertices"]
                            if hasattr(entity, 'set_vertices'):
                                entity.set_vertices([tuple(v) for v in vertices])
                        if "has_arrowhead" in changes:
                            entity.dxf.has_arrowhead = changes["has_arrowhead"]
                    
                    modified_count += 1
                except Exception as e:
                    LOG.warning(f"修改实体失败: {handle}, {e}")
            
            # 保存（保持原格式，使用 GBK 编码）
            output_filename = f"{template.get('name', 'output')}_modified.dxf"
            output_path = job_dir / output_filename
            doc.saveas(str(output_path), encoding='cp936')  # cp936 = GBK
            
            # 上传到 MinIO
            from dxf_template_service import upload_to_minio
            object_name = f"dxf_generated/{job_id}/{output_filename}"
            file_url = upload_to_minio(output_path, object_name)
            
            LOG.info(f"生成成功: {modified_count} 个实体被修改")
            
            return JSONResponse({
                "code": 0,
                "message": "生成成功",
                "data": {
                    "filename": output_filename,
                    "file_url": file_url,
                    "modified_count": modified_count
                }
            })
        
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("生成失败")
        raise HTTPException(500, f"生成失败: {e}") from e
