# PyAutoCAD 完整参考手册

## 1. 导入和初始化

```python
from pyautocad import Autocad, APoint
import win32com.client
import pythoncom

# COM 线程初始化（多线程环境必需）
pythoncom.CoInitialize()

# 连接 AutoCAD（如果不存在则创建）
acad = Autocad(create_if_not_exists=True)

# 获取文档和模型空间
doc = acad.doc
model = acad.model

# COM 清理（结束时调用）
pythoncom.CoUninitialize()
```

## 2. 核心对象

| 对象 | 获取方式 | 用途 |
|------|---------|------|
| `acad` | `Autocad()` | AutoCAD 应用程序对象 |
| `acad.doc` | `acad.doc` | 当前文档 |
| `acad.model` | `acad.model` | 模型空间（绘图区域）|
| `acad.app` | `acad.app` | 应用程序根对象 |

## 3. APoint - 坐标点

```python
from pyautocad import APoint

# 创建点（x, y, z）
p1 = APoint(100, 200, 0)          # 2D 点
p2 = APoint(100, 200, 50)       # 3D 点

# 访问坐标
x = p1.x
y = p1.y
z = p1.z
```

## 4. 绘制图形

### 4.1 圆 (Circle)
```python
center = APoint(100, 100, 0)
radius = 50

circle = model.AddCircle(center, radius)

# 设置属性
circle.Layer = "0"               # 图层
circle.Color = 1                  # 颜色 (1=红, 2=黄, 3=绿...)
circle.Linetype = "Continuous"    # 线型
circle.LinetypeScale = 1.0        # 线型比例

# 获取属性
handle = circle.Handle            # 对象句柄
area = circle.Area                # 面积
circumference = circle.Circumference  # 周长
center_point = circle.Center      # 圆心坐标
```

### 4.2 圆弧 (Arc)
```python
center = APoint(100, 100, 0)
radius = 50
start_angle = 0      # 起始角度（弧度）
end_angle = 1.57     # 结束角度（弧度，约90度）

arc = model.AddArc(center, radius, start_angle, end_angle)
arc.Layer = "0"
arc.Color = 2
```

### 4.3 直线/多段线 (Polyline)
```python
import win32com.client

# 方法一：使用 VARIANT 数组（推荐）
points = [0, 0, 0, 100, 0, 0, 100, 100, 0, 0, 100, 0]  # [x1,y1,z1, x2,y2,z2, ...]

points_vb = win32com.client.VARIANT(
    win32com.client.pythoncom.VT_ARRAY | win32com.client.pythoncom.VT_R8,
    points
)

pline = model.AddPolyline(points_vb)
pline.Closed = True       # 闭合多段线
pline.Layer = "0"
pline.Color = 3

# 方法二：逐个添加顶点（复杂图形）
from pyautocad import APoint

pline = model.AddPolyline(APoint(0, 0, 0))
pline.AppendVertex(APoint(100, 0, 0))
pline.AppendVertex(APoint(100, 100, 0))
pline.AppendVertex(APoint(0, 100, 0))
pline.Closed = True
```

### 4.4 矩形 (使用多段线)
```python
import math
from pyautocad import APoint

x, y = 50, 50
width, height = 100, 80
rotation = 30  # 旋转角度（度）

# 计算4个角点
corners = [
    APoint(x, y, 0),
    APoint(x + width, y, 0),
    APoint(x + width, y + height, 0),
    APoint(x, y + height, 0),
    APoint(x, y, 0),  # 闭合
]

# 创建闭合多段线
point_array = []
for p in corners:
    point_array.extend([p.x, p.y, p.z])

points_vb = win32com.client.VARIANT(
    win32com.client.pythoncom.VT_ARRAY | win32com.client.pythoncom.VT_R8,
    point_array
)

rect = model.AddPolyline(points_vb)
rect.Layer = "0"
rect.Color = 4
rect.Closed = True

# 旋转（以中心点为基点）
if rotation != 0:
    cx = x + width / 2
    cy = y + height / 2
    base_point = APoint(cx, cy, 0)
    rect.Rotate(base_point, math.radians(rotation))
```

### 4.5 文字 (Text)
```python
from pyautocad import APoint

insert_point = APoint(100, 100, 0)
text_content = "Hello AutoCAD"
height = 10  # 文字高度

text = model.AddText(text_content, insert_point, height)

# 设置属性
text.Layer = "0"
text.Color = 5
text.StyleName = "Standard"      # 文字样式
text.Rotation = 0                # 旋转角度（弧度）
text.HorizontalAlignment = 0     # 水平对齐 (0=左, 1=中, 2=右)
text.VerticalAlignment = 0       # 垂直对齐

# 获取属性
handle = text.Handle
position = text.InsertionPoint    # 插入点
```

### 4.6 椭圆 (Ellipse)
```python
from pyautocad import APoint
import math

cx, cy = 100, 100
rx, ry = 50, 30  # 长轴、短轴半径
rotation = 0     # 旋转角度

center = APoint(cx, cy, 0)
major_axis = APoint(cx + rx, cy, 0)  # 主轴端点
radius_ratio = ry / rx if rx > 0 else 1.0

ellipse = model.AddEllipse(center, major_axis, radius_ratio)
ellipse.Layer = "0"
ellipse.Color = 6

# 旋转
if rotation != 0:
    base_point = APoint(cx, cy, 0)
    ellipse.Rotate(base_point, math.radians(rotation))
```

### 4.7 多边形/填充 (Hatch)
```python
# Hatch 用于填充多边形
import win32com.client
from pyautocad import APoint

# 外轮廓点
exterior = [
    APoint(0, 0, 0),
    APoint(100, 0, 0),
    APoint(100, 100, 0),
    APoint(0, 100, 0),
]

# 创建填充
hatch = model.AddHatch(1, "SOLID", True)  # 1=颜色, "SOLID"=填充图案, True=关联性

# 添加外环边界
outer_loop = []
for p in exterior:
    outer_loop.append(p)

hatch.AppendLoop(0, outer_loop)  # 0=外环
hatch.Evaluate()  # 计算填充
hatch.Layer = "0"
```

## 5. 图层管理

```python
# 添加新图层
layer_name = "MyLayer"
try:
    layer = doc.Layers.Add(layer_name)
except:
    layer = doc.Layers.Item(layer_name)  # 图层已存在

# 设置图层属性
layer.Color = 1                    # 图层颜色
layer.LineType = "Continuous"      # 线型
layer.LineWeight = 0.25            # 线宽

# 设置当前图层
doc.ActiveLayer = layer
```

## 6. 颜色代码 (ACI)

| 代码 | 颜色 |
|------|------|
| 1 | 红色 (Red) |
| 2 | 黄色 (Yellow) |
| 3 | 绿色 (Green) |
| 4 | 青色 (Cyan) |
| 5 | 蓝色 (Blue) |
| 6 | 品红 (Magenta) |
| 7 | 白色/黑色 (White/Black) |
| 8 | 深灰 (Dark Gray) |
| 9 | 浅灰 (Light Gray) |

## 7. 图形变换

### 7.1 旋转 (Rotate)
```python
import math

base_point = APoint(100, 100, 0)   # 旋转基点
angle_rad = math.radians(45)       # 旋转角度（转换为弧度）

circle.Rotate(base_point, angle_rad)
pline.Rotate(base_point, angle_rad)
text.Rotate(base_point, angle_rad)
```

### 7.2 移动 (Move)
```python
from_point = APoint(0, 0, 0)
to_point = APoint(100, 100, 0)

circle.Move(from_point, to_point)
```

### 7.3 缩放 (ScaleEntity)
```python
base_point = APoint(100, 100, 0)
scale_factor = 2.0  # 放大2倍

circle.ScaleEntity(base_point, scale_factor)
```

## 8. 文档操作

```python
# 保存文档
doc.Save()

# 另存为
doc.SaveAs("C:/path/to/file.dwg", 24)  # 24=ACAD2018格式

# 另存为 DXF
doc.SaveAs("C:/path/to/file.dxf", 25)  # 25=DXF格式

# 关闭文档
doc.Close(save_changes=False)  # False=不保存

# 打开文档
doc = acad.app.Documents.Open("C:/path/to/file.dwg")

# 新建文档
doc = acad.app.Documents.Add()
```

## 9. 完整示例

```python
from pyautocad import Autocad, APoint
import win32com.client
import pythoncom
import math

# 初始化 COM
pythoncom.CoInitialize()

try:
    # 连接 AutoCAD
    acad = Autocad(create_if_not_exists=True)
    doc = acad.doc
    model = acad.model
    
    print(f"Connected to: {doc.Name}")
    
    # 1. 绘制圆
    circle = model.AddCircle(APoint(100, 100, 0), 50)
    circle.Color = 1  # 红色
    
    # 2. 绘制矩形（带旋转）
    points = [50, 50, 0, 150, 50, 0, 150, 100, 0, 50, 100, 0, 50, 50, 0]
    points_vb = win32com.client.VARIANT(
        win32com.client.pythoncom.VT_ARRAY | win32com.client.pythoncom.VT_R8,
        points
    )
    rect = model.AddPolyline(points_vb)
    rect.Closed = True
    rect.Color = 2
    rect.Rotate(APoint(100, 75, 0), math.radians(30))
    
    # 3. 添加文字
    text = model.AddText("Hello World", APoint(100, 100, 0), 20)
    text.Color = 3
    
    # 4. 保存
    doc.SaveAs("C:/test_output.dwg", 24)
    print("Saved successfully!")
    
finally:
    pythoncom.CoUninitialize()
```

## 10. 错误处理

```python
try:
    acad = Autocad(create_if_not_exists=True)
except Exception as e:
    print(f"AutoCAD not running: {e}")
    
try:
    circle = model.AddCircle(APoint(0, 0, 0), 50)
except Exception as e:
    print(f"Failed to create circle: {e}")
```

## 11. 注意事项

1. **COM 初始化**：多线程环境必须调用 `pythoncom.CoInitialize()`
2. **AutoCAD 必须运行**：否则会抛出异常
3. **Windows 专用**：pyautocad 只能在 Windows 上使用
4. **保存格式**：24=DWG, 25=DXF
5. **角度单位**：AutoCAD 使用弧度，需用 `math.radians()` 转换
