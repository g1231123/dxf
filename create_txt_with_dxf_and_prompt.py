import ezdxf

input_file = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'
output_file = '/Users/czy/Desktop/测试道路_R12数据和提示词.txt'

print(f'读取 DXF 文件: {input_file}')

# 读取原始 DXF
try:
    doc = ezdxf.readfile(input_file)
except:
    try:
        doc = ezdxf.readfile(input_file, encoding='gbk')
    except:
        doc = ezdxf.readfile(input_file, encoding='gb18030')

print(f'原始版本: {doc.dxfversion}')

# 创建 R12 文档
print('创建 R12 文档...')
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

print(f'已复制 {copied_count} 个实体')

# 保存为临时 DXF 文件
import tempfile
temp_dxf = tempfile.mktemp(suffix='.dxf')
new_doc.saveas(temp_dxf, encoding='cp936')

# 读取 R12 DXF 内容
with open(temp_dxf, 'r', encoding='cp936', errors='replace') as f:
    dxf_content = f.read()

# 删除临时文件
import os
os.remove(temp_dxf)

# 生成提示词
prompt = """
================================================================================
                        DXF R12 编辑提示词模板
================================================================================

文件信息：
  - 文件名：测试道路平纵面，横断面
  - DXF 版本：R12 (AC1009)
  - 编码：GBK (cp936)
  - 格式：ASCII DXF（纯文本）
  - 实体数量：{entity_count}

================================================================================
                        可编辑实体类型及参数
================================================================================

1. LINE（直线）
   可编辑参数：
   ✓ start - 起点坐标 [x, y, z]
     类型：point
     示例：[1000.0, 2000.0, 0.0]
   
   ✓ end - 终点坐标 [x, y, z]
     类型：point
     示例：[1500.0, 2500.0, 0.0]

2. CIRCLE（圆）
   可编辑参数：
   ✓ center - 圆心坐标 [x, y, z]
     类型：point
     示例：[1000.0, 2000.0, 0.0]
   
   ✓ radius - 半径
     类型：number
     约束：最小值 0.001
     示例：50.0

3. ARC（圆弧）
   可编辑参数：
   ✓ center - 圆心坐标 [x, y, z]
   ✓ radius - 半径（最小值 0.001）
   ✓ start_angle - 起始角度 0-360°
   ✓ end_angle - 结束角度 0-360°

4. TEXT/MTEXT（文字）
   可编辑参数：
   ✓ text - 文字内容（支持中文 GBK）
   ✓ insert - 插入点坐标 [x, y, z]
   ✓ height - 文字高度（最小值 0.1）

5. POINT（点）
   可编辑参数：
   ✓ location - 点坐标 [x, y, z]

================================================================================
                        不可编辑的属性（只读）
================================================================================

✗ handle - 实体句柄（系统生成，唯一标识）
✗ layer - 图层名称（建议不修改）
✗ color - 颜色索引
✗ linetype - 线型

================================================================================
                        参数类型说明
================================================================================

point（坐标点）
  格式：[x, y, z]
  说明：三维坐标，可修改任意值

number（数值）
  格式：浮点数或整数
  说明：可能有最小值/最大值约束

string（文本）
  格式：字符串
  说明：支持中文（GBK 编码）

================================================================================
                        编辑流程
================================================================================

1. 点击图片上的实体 → 系统自动识别实体类型
2. 查看可编辑参数 → 显示参数名称、类型、当前值、约束
3. 修改参数值 → 输入新值
4. 生成新 DXF → 保存为 R12 格式 + GBK 编码

================================================================================
                        R12 格式说明
================================================================================

⚠ R12 格式限制：
  - 不支持 INSERT（块引用）实体编辑
  - 不支持 LEADER（引线）实体编辑
  - 颜色值限制在 0-255
  - 必须使用 GBK 编码保存中文

✓ 优势：
  - 文件体积小（比新版本小 80%+）
  - 兼容性最好（所有 CAD 软件支持）
  - 解析速度快
  - 标准 ASCII 文本格式

================================================================================
                        以下是 R12 DXF 数据
================================================================================

""".format(entity_count=copied_count)

# 写入 TXT 文件：提示词 + DXF 数据
print(f'\n写入 TXT 文件: {output_file}')
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(prompt)
    f.write(dxf_content)

print(f'\n✅ TXT 文件（提示词 + R12 DXF 数据）已生成！')
print(f'输出文件: {output_file}')

# 文件大小
file_size = os.path.getsize(output_file) / (1024 * 1024)
print(f'文件大小: {file_size:.2f} MB')
