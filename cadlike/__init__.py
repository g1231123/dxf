"""
CadLike - 模仿 pyautocad 的跨平台 CAD 库

完全不依赖 AutoCAD 软件，使用 ezdxf 作为后端，提供与 pyautocad 完全相同的 API。

用法与 pyautocad 完全一致：
    from cadlike import Autocad, APoint
    
    acad = Autocad()
    model = acad.model
    
    # 绘制圆
    circle = model.AddCircle(APoint(100, 100, 0), 50)
    circle.Color = 1
    circle.Layer = "0"
    
    # 添加文字
    text = model.AddText("Hello", APoint(100, 100, 0), 10)
    
    # 保存
    acad.doc.SaveAs("output.dxf")
"""

__version__ = "1.0.0"
__author__ = "AI Assistant"

# 核心类
from .core import Autocad, APoint
from .document import Document, Documents
from .modelspace import ModelSpace
from .entities import (
    AcadEntity,
    AcadCircle,
    AcadArc,
    AcadPolyline,
    AcadLine,
    AcadText,
    AcadEllipse,
    AcadPoint,
    AcadHatch,
)
from .layers import Layer, Layers
from .application import Application

# 工具函数
from .utils import hex_to_aci, aci_to_hex, degrees_to_radians, radians_to_degrees

# 常量
from .constants import acRed, acYellow, acGreen, acCyan, acBlue, acMagenta, acWhite

__all__ = [
    # 主类
    "Autocad",
    "APoint",
    "Document",
    "Documents",
    "ModelSpace",
    "Application",
    
    # 实体类
    "AcadEntity",
    "AcadCircle",
    "AcadArc",
    "AcadPolyline",
    "AcadLine",
    "AcadText",
    "AcadEllipse",
    "AcadPoint",
    "AcadHatch",
    
    # 图层
    "Layer",
    "Layers",
    
    # 工具
    "hex_to_aci",
    "aci_to_hex",
    "degrees_to_radians",
    "radians_to_degrees",
    
    # 常量
    "acRed",
    "acYellow",
    "acGreen",
    "acCyan",
    "acBlue",
    "acMagenta",
    "acWhite",
]
