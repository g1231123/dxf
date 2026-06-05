import re

txt_file = '/Users/czy/Desktop/测试道路_R12数据和提示词.txt'
output_dxf = '/Users/czy/Desktop/测试道路_从TXT提取.dxf'

print(f'读取 TXT 文件: {txt_file}')

with open(txt_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 DXF 数据的开始位置（从 "  0\nSECTION" 开始）
dxf_start = content.find('  0\nSECTION')

if dxf_start == -1:
    print('❌ 未找到 DXF 数据！')
    exit(1)

# 提取 DXF 数据部分
dxf_content = content[dxf_start:]

print(f'找到 DXF 数据，起始位置: {dxf_start}')
print(f'DXF 数据长度: {len(dxf_content)} 字符')

# 保存为 DXF 文件（使用 GBK 编码）
with open(output_dxf, 'w', encoding='cp936') as f:
    f.write(dxf_content)

print(f'\n✅ DXF 文件已提取！')
print(f'输出文件: {output_dxf}')

# 验证
import os
file_size = os.path.getsize(output_dxf) / (1024 * 1024)
print(f'文件大小: {file_size:.2f} MB')

# 检查是否是有效的 DXF
with open(output_dxf, 'r', encoding='cp936') as f:
    first_lines = [f.readline().strip() for _ in range(10)]
    print(f'\n文件开头:')
    for line in first_lines[:6]:
        print(f'  {line}')

# 使用 ezdxf 验证
try:
    import ezdxf
    doc = ezdxf.readfile(output_dxf, encoding='cp936')
    print(f'\n✓ DXF 文件有效！')
    print(f'  版本: {doc.dxfversion}')
    print(f'  实体数: {len(list(doc.modelspace()))}')
except Exception as e:
    print(f'\n✗ DXF 文件验证失败: {e}')
