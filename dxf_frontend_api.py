"""
DXF 模板服务 - 前端驱动版本
简化的 API，前端自己解析 DXF
"""
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import json
import uuid
import shutil
import logging
import requests
from pathlib import Path
import tempfile

LOG = logging.getLogger("dxf_frontend")

router = APIRouter(prefix="/template/v2", tags=["DXF Template V2"])

WORK_DIR = Path(tempfile.gettempdir()) / "dxf_frontend_service"
WORK_DIR.mkdir(exist_ok=True)


def get_template_from_db(template_id: str):
    """从数据库获取模板信息（简化版）"""
    from dxf_template_service import get_template_from_db as get_template
    return get_template(template_id)


def upload_to_minio(file_path: Path, object_name: str):
    """上传文件到 MinIO（简化版）"""
    from dxf_template_service import upload_to_minio as upload
    return upload(file_path, object_name, content_type="application/dxf")


@router.get("/file")
async def get_dxf_file(id: str):
    """
    获取原始 DXF 文件
    
    前端直接下载并解析 DXF，不需要后端提取参数
    """
    template = get_template_from_db(id)
    if not template:
        raise HTTPException(404, "模板不存在")
    
    # 重定向到 MinIO URL
    return RedirectResponse(template["file_url"])


@router.post("/generate")
async def generate_dxf_from_frontend(
    template_id: str = Form(..., description="模板 ID"),
    modifications: str = Form(..., description="修改内容（JSON 数组）"),
):
    """
    根据前端修改生成新 DXF
    
    前端只发送修改的参数，不是全部参数
    
    modifications 格式：
    [
      {
        "handle": "1A0",
        "type": "LINE",
        "changes": {
          "start": [100, 200, 0],
          "end": [300, 400, 0]
        }
      },
      {
        "handle": "1B5",
        "type": "TEXT",
        "changes": {
          "text": "新文字",
          "height": 5.0
        }
      }
    ]
    """
    try:
        import ezdxf
        
        # 解析修改内容
        try:
            mods = json.loads(modifications)
        except json.JSONDecodeError:
            raise HTTPException(400, "修改内容格式错误")
        
        if not isinstance(mods, list):
            raise HTTPException(400, "modifications 必须是数组")
        
        # 获取模板信息
        template = get_template_from_db(template_id)
        if not template:
            raise HTTPException(404, "模板不存在")
        
        # 创建工作目录
        job_id = uuid.uuid4().hex
        job_dir = WORK_DIR / job_id
        job_dir.mkdir()
        
        try:
            # 下载原始 DXF 文件
            LOG.info(f"下载原始 DXF: {template['file_url']}")
            response = requests.get(template["file_url"], timeout=120)
            if response.status_code != 200:
                raise HTTPException(500, f"无法下载 DXF 文件: HTTP {response.status_code}")
            
            # 保存到临时文件
            temp_dxf = job_dir / "template.dxf"
            temp_dxf.write_bytes(response.content)
            
            # 使用 ezdxf 打开 DXF 文件
            doc = ezdxf.readfile(str(temp_dxf))
            
            # 应用修改
            modified_count = 0
            for mod in mods:
                handle = mod.get("handle")
                changes = mod.get("changes", {})
                
                if not handle or not changes:
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
                        if "start" in changes:
                            entity.dxf.start = tuple(changes["start"])
                        if "end" in changes:
                            entity.dxf.end = tuple(changes["end"])
                    
                    elif entity_type == "CIRCLE":
                        if "center" in changes:
                            entity.dxf.center = tuple(changes["center"])
                        if "radius" in changes:
                            entity.dxf.radius = changes["radius"]
                    
                    elif entity_type == "ARC":
                        if "center" in changes:
                            entity.dxf.center = tuple(changes["center"])
                        if "radius" in changes:
                            entity.dxf.radius = changes["radius"]
                        if "start_angle" in changes:
                            entity.dxf.start_angle = changes["start_angle"]
                        if "end_angle" in changes:
                            entity.dxf.end_angle = changes["end_angle"]
                    
                    elif entity_type in ["TEXT", "MTEXT"]:
                        if "text" in changes:
                            entity.dxf.text = changes["text"]
                        if "insert" in changes:
                            entity.dxf.insert = tuple(changes["insert"])
                        if "height" in changes:
                            entity.dxf.height = changes["height"]
                        if "char_height" in changes:
                            entity.dxf.char_height = changes["char_height"]
                    
                    elif entity_type == "LWPOLYLINE":
                        if "points" in changes:
                            entity.set_points(changes["points"])
                    
                    elif entity_type == "INSERT":
                        if "insert" in changes:
                            entity.dxf.insert = tuple(changes["insert"])
                        if "xscale" in changes:
                            entity.dxf.xscale = changes["xscale"]
                        if "yscale" in changes:
                            entity.dxf.yscale = changes["yscale"]
                        if "rotation" in changes:
                            entity.dxf.rotation = changes["rotation"]
                    
                    modified_count += 1
                    LOG.info(f"修改实体: {handle} ({entity_type})")
                    
                except Exception as e:
                    LOG.warning(f"修改实体失败: {handle}, 错误: {e}")
                    continue
            
            # 保存 DXF 文件
            output_filename = template.get("name", "generated") + "_modified.dxf"
            output_path = job_dir / output_filename
            doc.saveas(str(output_path))
            
            # 上传到 MinIO
            object_name = f"dxf_generated/{job_id}/{output_filename}"
            file_url = upload_to_minio(output_path, object_name)
            
            LOG.info(f"生成 DXF 成功: {output_filename}, 修改了 {modified_count} 个实体")
            
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
        LOG.exception("生成 DXF 失败")
        raise HTTPException(500, f"生成失败: {e}") from e
