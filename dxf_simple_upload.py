"""
DXF 模板服务 - 简化上传版本
只上传文件到 MinIO，不解析实体
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
import uuid
import logging
from pathlib import Path
import tempfile

LOG = logging.getLogger("dxf_simple")

router = APIRouter(prefix="/template/simple", tags=["DXF Template Simple"])

WORK_DIR = Path(tempfile.gettempdir()) / "dxf_simple_service"
WORK_DIR.mkdir(exist_ok=True)


def upload_to_minio(file_path: Path, object_name: str):
    """上传文件到 MinIO"""
    from dxf_template_service import upload_to_minio as upload
    return upload(file_path, object_name, content_type="application/dxf")


def get_mysql_connection():
    """获取 MySQL 连接"""
    from dxf_template_service import get_mysql_connection as get_conn
    return get_conn()


@router.post("/upload")
async def simple_upload_dxf(
    file: UploadFile = File(..., description="DXF 或 DWG 文件"),
    name: str = Form(None, description="模板名称，不传则使用文件名"),
):
    """
    简化上传：只上传文件，不解析实体
    
    流程：
    1. 保存文件到临时目录
    2. 上传到 MinIO
    3. 保存基本信息到数据库
    4. 立即返回
    
    不做：
    - ❌ 不解析 DXF 实体
    - ❌ 不提取参数
    - ❌ 不生成 JSON
    """
    try:
        # 生成模板 ID
        template_id = uuid.uuid4().hex
        
        # 获取文件名
        original_filename = file.filename
        lower_name = original_filename.lower()
        
        # 检查文件类型
        if not (lower_name.endswith('.dxf') or lower_name.endswith('.dwg')):
            raise HTTPException(400, "只支持 DXF 或 DWG 文件")
        
        # 模板名称
        template_name = name if name else original_filename.rsplit('.', 1)[0]
        
        # 保存到临时文件
        temp_dir = WORK_DIR / template_id
        temp_dir.mkdir()
        temp_file = temp_dir / original_filename
        
        with open(temp_file, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        file_size = len(content)
        LOG.info(f"文件保存成功: {original_filename}, 大小: {file_size / 1024 / 1024:.2f} MB")
        
        # 上传到 MinIO
        object_name = f"dxf_templates/{template_id}/{original_filename}"
        file_url = upload_to_minio(temp_file, object_name)
        
        LOG.info(f"文件上传到 MinIO 成功: {file_url}")
        
        # 保存到数据库（简化版）
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO dxf_template (
                        id, name, original_filename, file_url, template_url,
                        dxf_version, layer_count, block_count, entity_count,
                        is_official, status, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                """
                cursor.execute(sql, (
                    template_id,
                    template_name,
                    original_filename,
                    file_url,
                    file_url,  # template_url 也指向原始文件
                    '',  # dxf_version 未知
                    0,   # layer_count
                    0,   # block_count
                    0,   # entity_count
                    0,   # is_official
                    'ready',  # status 直接设为 ready
                ))
            conn.commit()
            LOG.info(f"数据库保存成功: {template_id}")
        finally:
            conn.close()
        
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return JSONResponse({
            "code": 0,
            "message": "上传成功",
            "data": {
                "id": template_id,
                "name": template_name,
                "original_filename": original_filename,
                "file_url": file_url,
                "file_size": file_size,
                "status": "ready"
            }
        })
    
    except HTTPException:
        raise
    except Exception as e:
        LOG.exception("上传失败")
        raise HTTPException(500, f"上传失败: {e}") from e
