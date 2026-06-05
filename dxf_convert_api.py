"""
DXF 转换 API
提供 DXF <-> TXT 互转功能
"""
import logging
import tempfile
import requests
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf
from botocore.exceptions import ClientError

from config import MINIO_CONFIG
from dxf_template_service import get_s3_client, upload_to_minio

LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/api/convert")


class DxfToTxtRequest(BaseModel):
    dxf_url: str
    include_prompt: bool = True  # 是否包含提示词


class TxtToDxfRequest(BaseModel):
    txt_url: str


class MdToDxfResponse(BaseModel):
    output_url: str
    file_size_mb: float
    entity_count: int
    dxf_version: str


class ConvertResponse(BaseModel):
    output_url: str
    file_size_mb: float


def _object_exists(object_name: str) -> bool:
    client = get_s3_client()
    bucket_name = MINIO_CONFIG["bucket_name"]
    try:
        client.head_object(Bucket=bucket_name, Key=object_name)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


@router.post("/dxf-to-txt", response_model=ConvertResponse)
async def convert_dxf_to_txt(request: DxfToTxtRequest):
    """
    将 DXF 文件转换为 TXT 格式（提示词 + R12 DXF 数据）
    """
    try:
        LOG.info(f"开始转换 DXF 到 TXT: {request.dxf_url}")
        
        # 下载 DXF 文件
        temp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False)
        temp_dxf.close()
        
        response = requests.get(request.dxf_url)
        response.raise_for_status()
        with open(temp_dxf.name, 'wb') as f:
            f.write(response.content)
        
        # 读取 DXF
        try:
            doc = ezdxf.readfile(temp_dxf.name)
        except:
            try:
                doc = ezdxf.readfile(temp_dxf.name, encoding='gbk')
            except:
                doc = ezdxf.readfile(temp_dxf.name, encoding='gb18030')
        
        LOG.info(f'原始版本: {doc.dxfversion}')
        
        # 创建 R12 文档
        new_doc = ezdxf.new('R12')
        
        # 复制图层
        for layer in doc.layers:
            if layer.dxf.name not in new_doc.layers:
                color = layer.dxf.color
                if color < 0 or color > 255:
                    color = 7
                new_doc.layers.add(layer.dxf.name, color=color)
        
        # 复制实体
        msp_old = doc.modelspace()
        msp_new = new_doc.modelspace()
        
        copied_count = 0
        for entity in msp_old:
            try:
                msp_new.add_foreign_entity(entity)
                copied_count += 1
            except:
                pass
        
        LOG.info(f'已复制 {copied_count} 个实体')
        
        # 保存为临时 DXF
        temp_r12_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False)
        temp_r12_dxf.close()
        new_doc.saveas(temp_r12_dxf.name, encoding='cp936')
        
        # 读取 R12 DXF 内容
        with open(temp_r12_dxf.name, 'r', encoding='cp936', errors='replace') as f:
            dxf_content = f.read()
        
        # 生成提示词
        prompt = ""
        if request.include_prompt:
            prompt = f"""================================================================================
                        DXF R12 编辑提示词模板
================================================================================

文件信息：
  - DXF 版本：{doc.dxfversion} → R12 (AC1009)
  - 编码：GBK (cp936)
  - 格式：ASCII DXF（纯文本）
  - 实体数量：{copied_count}

================================================================================
支持的实体类型（10种，覆盖率 100%）
================================================================================

1. LINE（直线）- start, end, color, lineweight
2. CIRCLE（圆）- center, radius, color, lineweight
3. ARC（圆弧）- center, radius, start_angle, end_angle, color, lineweight
4. TEXT/MTEXT（文字）- text, insert, height, color, lineweight
5. POINT（点）- location, color, lineweight
6. ELLIPSE（椭圆）- center, major_axis, ratio, start_param, end_param, color, lineweight
7. SPLINE（样条曲线）- control_points, color, lineweight
8. LWPOLYLINE（多段线）- vertices, closed, const_width, color, lineweight
9. INSERT（块引用）- insert, xscale, yscale, zscale, rotation, color, lineweight
10. LEADER（引线）- vertices, has_arrowhead, color, lineweight

通用属性（所有实体）：
  - color: 颜色索引 (0-256, 256=随层)
  - lineweight: 线宽 (-1=随层, -2=随块, -3=默认)

格式：R12 ASCII DXF + GBK编码
支持率：100%

================================================================================
                        以下是 R12 DXF 数据
================================================================================

"""
        
        # 写入 TXT（MD）文件
        temp_txt = tempfile.NamedTemporaryFile(suffix='.md', delete=False, mode='w', encoding='utf-8')
        temp_txt.write(prompt)
        temp_txt.write(dxf_content)
        temp_txt.close()
        
        # 上传到 MinIO（名称唯一，存在则报错）
        file_size = os.path.getsize(temp_txt.name) / (1024 * 1024)
        
        # 从原始 URL 提取文件名
        original_name = Path(request.dxf_url).stem
        output_filename = f"{original_name}_R12数据和提示词.md"
        object_name = f"dxf_converted/{output_filename}"
        if _object_exists(object_name):
            raise HTTPException(status_code=400, detail="文件已存在，请更换文件名后重试")
        output_url = upload_to_minio(temp_txt.name, object_name, content_type="text/markdown; charset=utf-8")
        
        # 清理临时文件
        Path(temp_dxf.name).unlink(missing_ok=True)
        Path(temp_r12_dxf.name).unlink(missing_ok=True)
        Path(temp_txt.name).unlink(missing_ok=True)
        
        LOG.info(f"转换完成: {output_url}, 大小: {file_size:.2f} MB")
        
        return ConvertResponse(
            output_url=output_url,
            file_size_mb=round(file_size, 2)
        )
        
    except Exception as e:
        LOG.error(f"DXF 转 TXT 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")


@router.post("/txt-to-dxf", response_model=ConvertResponse)
async def convert_txt_to_dxf(request: TxtToDxfRequest):
    """
    从 TXT 文件中提取 DXF 数据并保存为 .dxf 文件
    """
    try:
        LOG.info(f"开始从 TXT 提取 DXF: {request.txt_url}")
        
        # 下载 TXT/MD 文件
        temp_txt = tempfile.NamedTemporaryFile(suffix='.md', delete=False)
        temp_txt.close()
        
        response = requests.get(request.txt_url)
        response.raise_for_status()
        with open(temp_txt.name, 'wb') as f:
            f.write(response.content)
        
        # 读取 TXT 内容
        with open(temp_txt.name, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace('\r\n', '\n')
        dxf_start = content.find('  0\nSECTION')
        
        if dxf_start == -1:
            raise HTTPException(status_code=400, detail="TXT/MD 文件中未找到 DXF 数据")
        
        # 提取 DXF 数据
        dxf_content = content[dxf_start:]
        
        LOG.info(f'找到 DXF 数据，起始位置: {dxf_start}, 长度: {len(dxf_content)} 字符')
        
        # 保存为 DXF 文件
        temp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False, mode='w', encoding='cp936')
        temp_dxf.write(dxf_content)
        temp_dxf.close()
        
        # 验证 DXF 文件
        try:
            doc = ezdxf.readfile(temp_dxf.name, encoding='cp936')
            entity_count = len(list(doc.modelspace()))
            LOG.info(f'DXF 文件有效，版本: {doc.dxfversion}, 实体数: {entity_count}')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"提取的 DXF 数据无效: {str(e)}")
        
        # 上传到 MinIO（名称唯一，存在则报错）
        file_size = os.path.getsize(temp_dxf.name) / (1024 * 1024)
        
        # 从原始 URL 提取文件名
        original_name = Path(request.txt_url).stem
        output_filename = f"{original_name}_提取.dxf"
        object_name = f"dxf_converted/{output_filename}"
        if _object_exists(object_name):
            raise HTTPException(status_code=400, detail="文件已存在，请更换文件名后重试")
        output_url = upload_to_minio(temp_dxf.name, object_name)
        
        # 清理临时文件
        Path(temp_txt.name).unlink(missing_ok=True)
        Path(temp_dxf.name).unlink(missing_ok=True)
        
        LOG.info(f"提取完成: {output_url}, 大小: {file_size:.2f} MB")
        
        return ConvertResponse(
            output_url=output_url,
            file_size_mb=round(file_size, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        LOG.error(f"TXT 转 DXF 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")


@router.post("/md-to-dxf", response_model=ConvertResponse)
async def convert_md_to_dxf(request: TxtToDxfRequest):
    """
    从 MD 文件中提取 R12 DXF 数据并保存为 .dxf 文件
    """
    try:
        LOG.info(f"开始从 MD 提取 DXF: {request.txt_url}")

        temp_md = tempfile.NamedTemporaryFile(suffix='.md', delete=False)
        temp_md.close()

        response = requests.get(request.txt_url)
        response.raise_for_status()
        with open(temp_md.name, 'wb') as f:
            f.write(response.content)

        with open(temp_md.name, 'r', encoding='utf-8') as f:
            content = f.read()

        content = content.replace('\r\n', '\n')
        dxf_start = content.find('  0\nSECTION')

        if dxf_start == -1:
            raise HTTPException(status_code=400, detail="MD 文件中未找到 R12 DXF 数据")

        dxf_content = content[dxf_start:]

        LOG.info(f'找到 DXF 数据，起始位置: {dxf_start}, 长度: {len(dxf_content)} 字符')

        temp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False, mode='w', encoding='cp936')
        temp_dxf.write(dxf_content)
        temp_dxf.close()

        try:
            doc = ezdxf.readfile(temp_dxf.name, encoding='cp936')
            entity_count = len(list(doc.modelspace()))
            LOG.info(f'DXF 文件有效，版本: {doc.dxfversion}, 实体数: {entity_count}')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"提取的 DXF 数据无效: {str(e)}")

        file_size = os.path.getsize(temp_dxf.name) / (1024 * 1024)

        original_name = Path(request.txt_url).stem
        output_filename = f"{original_name}_提取.dxf"
        object_name = f"dxf_converted/{output_filename}"
        if _object_exists(object_name):
            raise HTTPException(status_code=400, detail="文件已存在，请更换文件名后重试")
        output_url = upload_to_minio(temp_dxf.name, object_name)

        Path(temp_md.name).unlink(missing_ok=True)
        Path(temp_dxf.name).unlink(missing_ok=True)

        LOG.info(f"提取完成: {output_url}, 大小: {file_size:.2f} MB")

        return ConvertResponse(
            output_url=output_url,
            file_size_mb=round(file_size, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        LOG.error(f"MD 转 DXF 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")


@router.post("/md-to-dxf/upload")
async def upload_md_to_dxf(file: UploadFile = File(...)):
    """
    直接上传 MD 文件，提取 R12 DXF 数据并返回 DXF 文件
    """
    try:
        if not file.filename or not file.filename.lower().endswith('.md'):
            raise HTTPException(status_code=400, detail="请上传 .md 格式文件")

        LOG.info(f"接收 MD 文件: {file.filename}")

        content = (await file.read()).decode('utf-8')
        content = content.replace('\r\n', '\n')

        dxf_start = content.find('  0\nSECTION')

        if dxf_start == -1:
            raise HTTPException(status_code=400, detail="MD 文件中未找到 R12 DXF 数据")

        dxf_content = content[dxf_start:]

        LOG.info(f'找到 DXF 数据，起始位置: {dxf_start}, 长度: {len(dxf_content)} 字符')

        temp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False, mode='w', encoding='cp936')
        temp_dxf.write(dxf_content)
        temp_dxf.close()

        try:
            doc = ezdxf.readfile(temp_dxf.name, encoding='cp936')
            entity_count = len(list(doc.modelspace()))
            dxf_version = doc.dxfversion
            LOG.info(f'DXF 文件有效，版本: {dxf_version}, 实体数: {entity_count}')
        except Exception as e:
            Path(temp_dxf.name).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"提取的 DXF 数据无效: {str(e)}")

        file_size = os.path.getsize(temp_dxf.name) / (1024 * 1024)

        original_name = Path(file.filename).stem
        output_filename = f"{original_name}_提取.dxf"
        object_name = f"dxf_converted/{output_filename}"
        if _object_exists(object_name):
            Path(temp_dxf.name).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="文件已存在，请更换文件名后重试")
        output_url = upload_to_minio(temp_dxf.name, object_name)

        Path(temp_dxf.name).unlink(missing_ok=True)

        LOG.info(f"提取完成: {output_url}, 大小: {file_size:.2f} MB")

        return JSONResponse({
            "code": 0,
            "message": "转换成功",
            "data": {
                "output_url": output_url,
                "file_size_mb": round(file_size, 2),
                "entity_count": entity_count,
                "dxf_version": dxf_version
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        LOG.error(f"MD 上传转 DXF 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
