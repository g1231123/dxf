import ezdxf

input_file = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'
output_file = '/Users/czy/Desktop/测试道路平纵面，横断面_带提示词.dxf'

print(f'读取 DXF 文件: {input_file}')

# 读取 DXF
try:
    doc = ezdxf.readfile(input_file)
except:
    try:
        doc = ezdxf.readfile(input_file, encoding='gbk')
    except:
        doc = ezdxf.readfile(input_file, encoding='gb18030')

print(f'原始版本: {doc.dxfversion}')

# 提示词模板
prompt_template = """
=== DXF 编辑提示词模板 ===

支持编辑的实体类型：

1. LINE（直线）
   - start: 起点坐标 [x,y,z] (可编辑)
   - end: 终点坐标 [x,y,z] (可编辑)

2. CIRCLE（圆）
   - center: 圆心坐标 [x,y,z] (可编辑)
   - radius: 半径 (可编辑, 最小值0.001)

3. ARC（圆弧）
   - center: 圆心坐标 [x,y,z] (可编辑)
   - radius: 半径 (可编辑, 最小值0.001)
   - start_angle: 起始角度 0-360° (可编辑)
   - end_angle: 结束角度 0-360° (可编辑)

4. TEXT/MTEXT（文字）
   - text: 文字内容 (可编辑)
   - insert: 插入点坐标 [x,y,z] (可编辑)
   - height: 文字高度 (可编辑, 最小值0.1)

5. POINT（点）
   - location: 点坐标 [x,y,z] (可编辑)

不可编辑属性：
   - handle: 实体句柄 (只读)
   - layer: 图层名 (只读)
   - color: 颜色 (只读)

参数类型：
   - point: 坐标点 [x,y,z]
   - number: 数值（可能有最小/最大值约束）
   - string: 文本（支持中文GBK编码）

编辑流程：
   1. 点击图片上的实体
   2. 查看可编辑参数
   3. 修改参数值
   4. 生成新DXF文件

格式：R12 ASCII DXF + GBK编码
"""

# 在 HEADER 段添加自定义变量作为标记
doc.header['$USERI1'] = 20260528  # 标记：包含提示词模板（日期）
doc.header['$USERI2'] = 5  # 支持的实体类型数量
doc.header['$USERI3'] = 1  # LINE 可编辑
doc.header['$USERI4'] = 1  # CIRCLE 可编辑  
doc.header['$USERI5'] = 1  # TEXT 可编辑

# 添加注释到文件（作为 999 组码）
# 在 modelspace 添加一个不可见的 TEXT 实体存储提示词
msp = doc.modelspace()
prompt_text = msp.add_text(
    prompt_template,
    dxfattribs={
        'layer': '0',
        'height': 0.001,  # 极小的文字
        'insert': (0, 0, -99999),  # 放在很远的地方
        'color': 0  # 不可见
    }
)

# 保存文件
print(f'\n保存文件: {output_file}')
doc.saveas(output_file, encoding='cp936')

print(f'\n✅ 提示词已植入 DXF 文件！')
print(f'输出文件: {output_file}')

# 验证
print('\n验证提示词:')
doc2 = ezdxf.readfile(output_file, encoding='cp936')
print(f'$USERI1 = {doc2.header.get("$USERI1", "未找到")}')
print(f'$USERI2 = {doc2.header.get("$USERI2", "未找到")}')
