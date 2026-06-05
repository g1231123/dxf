"""
CadLike 使用示例
完全模仿 pyautocad 的 CAD 绘图库
"""

import math
from cadlike import Autocad, APoint, acRed, acGreen, acBlue

# =============================================================================
# 基本用法 - 与 pyautocad 完全相同
# =============================================================================

print("=" * 60)
print("CadLike 示例 - 模仿 pyautocad 的跨平台 CAD 库")
print("=" * 60)
print()

# 创建 Autocad 对象（不需要 AutoCAD 软件）
acad = Autocad()
print(f"✓ 创建 Autocad 对象: {acad}")

# 获取文档和模型空间
doc = acad.doc
model = acad.model
print(f"✓ 文档: {doc.Name}")
print()

# ============================================================================
# 绘制基本图形
# ============================================================================

print("-" * 60)
print("绘制基本图形")
print("-" * 60)

# 1. 绘制圆
circle = model.AddCircle(APoint(100, 100, 0), 50)
circle.Color = acRed  # 红色
circle.Layer = "0"
print(f"✓ 圆: Center={circle.Center}, Radius={circle.Radius}, Area={circle.Area:.2f}")

# 2. 绘制直线
line = model.AddLine(APoint(0, 0, 0), APoint(200, 0, 0))
line.Color = acGreen
print(f"✓ 直线: Length={line.Length:.2f}, Angle={math.degrees(line.Angle):.1f}°")

# 3. 绘制多段线（矩形）
rect_points = [
    APoint(50, 50, 0),
    APoint(150, 50, 0),
    APoint(150, 150, 0),
    APoint(50, 150, 0),
    APoint(50, 50, 0),  # 闭合
]
rect = model.AddPolyline(rect_points)
rect.Closed = True
rect.Color = acBlue
print(f"✓ 矩形: Closed={rect.Closed}, Vertices={rect.NumberOfVertices}")

# 4. 绘制圆弧
arc = model.AddArc(APoint(200, 200, 0), 30, 0, math.pi)
arc.Color = 2  # 黄色
print(f"✓ 圆弧: Radius={arc.Radius}, TotalAngle={math.degrees(arc.TotalAngle):.1f}°")

# 5. 绘制文字
text = model.AddText("CadLike 测试", APoint(100, 100, 0), 10)
text.Color = 5  # 蓝色
text.Rotation = math.pi / 6  # 30度旋转
print(f"✓ 文字: '{text.TextString}', Height={text.Height}")

# 6. 绘制椭圆
ellipse = model.AddEllipse(APoint(300, 100, 0), APoint(350, 100, 0), 0.5)
ellipse.Color = 6  # 品红
print(f"✓ 椭圆: MajorRadius={ellipse.MajorRadius:.2f}, MinorRadius={ellipse.MinorRadius:.2f}")

print()

# ============================================================================
# 图层操作
# ============================================================================

print("-" * 60)
print("图层操作")
print("-" * 60)

# 创建新图层
layer = doc.Layers.Add("MyLayer")
layer.Color = 3  # 绿色
layer.Linetype = "Continuous"
print(f"✓ 创建图层: {layer.Name}, Color={layer.Color}")

# 将圆移动到新图层
circle.Layer = "MyLayer"
print(f"✓ 圆已移动到图层: {circle.Layer}")

# 列出所有图层
print("\n所有图层:")
for lyr in doc.Layers:
    print(f"  - {lyr.Name} (Color={lyr.Color})")

print()

# ============================================================================
# 图形变换
# ============================================================================

print("-" * 60)
print("图形变换")
print("-" * 60)

# 移动图形
circle.Move(APoint(0, 0, 0), APoint(10, 10, 0))
print(f"✓ 移动圆到新位置: {circle.Center}")

# 旋转图形（绕中心点旋转45度）
rect.Rotate(APoint(100, 100, 0), math.pi / 4)
print(f"✓ 旋转矩形 45°")

# 缩放图形
circle.ScaleEntity(APoint(110, 110, 0), 1.5)
print(f"✓ 缩放圆 1.5x: 新半径={circle.Radius:.2f}")

print()

# ============================================================================
# 便捷方法
# ============================================================================

print("-" * 60)
print("便捷方法")
print("-" * 60)

# 绘制矩形（使用便捷方法）
rect2 = model.AddRectangle(200, 200, 80, 60)
rect2.Color = 4  # 青色
print(f"✓ 矩形 (便捷方法): 位置(200,200), 尺寸80x60")

# 绘制旋转矩形
rect3 = model.AddRectangle(350, 200, 60, 40, rotation=math.pi / 3)
rect3.Color = 5
print(f"✓ 旋转矩形: 旋转60°")

# 绘制正多边形
triangle = model.AddPolygon(APoint(100, 300, 0), 40, 3)
triangle.Color = 1
print(f"✓ 三角形: 外接圆半径=40")

hexagon = model.AddPolygon(APoint(200, 300, 0), 35, 6, rotation=math.pi / 6)
hexagon.Color = 2
print(f"✓ 六边形: 外接圆半径=35, 旋转30°")

print()

# ============================================================================
# APoint 高级用法
# ============================================================================

print("-" * 60)
print("APoint 高级用法")
print("-" * 60)

p1 = APoint(100, 100, 0)
p2 = APoint(200, 150, 0)

print(f"点 p1: {p1}")
print(f"点 p2: {p2}")
print(f"距离: {p1.distance_to(p2):.2f}")
print(f"角度: {math.degrees(p1.angle_to(p2)):.1f}°")

# 极坐标计算新点
p3 = p1.polar(math.pi / 4, 50)
print(f"p1 的极坐标点 (45°, 50单位): {p3}")

# 点的数学运算
p4 = p1 + APoint(10, 20, 0)
p5 = p2 - APoint(50, 50, 0)
print(f"p1 + (10,20): {p4}")
print(f"p2 - (50,50): {p5}")

# 缩放
p6 = p1 * 2
print(f"p1 * 2: {p6}")

# 中点
mid = p1.midpoint(p2)
print(f"p1 和 p2 的中点: {mid}")

print()

# ============================================================================
# 保存文件
# ============================================================================

print("-" * 60)
print("保存文件")
print("-" * 60)

# 保存为 DXF
doc.SaveAs("cadlike_example.dxf", 25)  # 25 = DXF 格式
print(f"✓ 已保存: cadlike_example.dxf")

# 也可以这样保存
doc.Name = "MyDrawing.dxf"
doc.Save()
print(f"✓ 另存为: {doc.Name}")

print()
print("=" * 60)
print("示例完成！")
print(f"文件保存在: {doc.Name}")
print("=" * 60)
