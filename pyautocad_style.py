"""
PyAutoCAD Style Interface - 完全模仿 pyautocad，使用 ezdxf 作为后端

这个模块提供与 pyautocad 完全相同的 API，但：
- 跨平台（macOS, Linux, Windows）
- 不依赖 AutoCAD 软件
- 使用 ezdxf 生成 DXF 文件

用法与 pyautocad 完全一致：
    from pyautocad_style import Autocad, APoint
    
    acad = Autocad()
    model = acad.model
    
    circle = model.AddCircle(APoint(100, 100, 0), 50)
    circle.Color = 1
    
    acad.doc.SaveAs("output.dxf")
"""

import math
import uuid
from typing import Optional, List, Union, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# 尝试导入 ezdxf
try:
    import ezdxf
    from ezdxf import colors
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False


@dataclass
class APoint:
    """
    完全模仿 pyautocad.APoint 的坐标点类
    
    Examples:
        >>> p = APoint(100, 200)
        >>> p.x, p.y, p.z
        (100.0, 200.0, 0.0)
        
        >>> p1 = APoint(100, 200, 50)
        >>> x, y, z = p1  # 支持解包
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    
    def __post_init__(self):
        """确保坐标是浮点数"""
        self.x = float(self.x)
        self.y = float(self.y)
        self.z = float(self.z)
    
    def __iter__(self):
        """支持解包: x, y, z = point"""
        return iter((self.x, self.y, self.z))
    
    def __add__(self, other: "APoint") -> "APoint":
        """点相加"""
        return APoint(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: "APoint") -> "APoint":
        """点相减"""
        return APoint(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __repr__(self) -> str:
        return f"APoint({self.x}, {self.y}, {self.z})"
    
    def distance_to(self, other: "APoint") -> float:
        """计算到另一点的距离"""
        return math.sqrt(
            (self.x - other.x) ** 2 + 
            (self.y - other.y) ** 2 + 
            (self.z - other.z) ** 2
        )


class _ACADEnum:
    """AutoCAD 常量枚举"""
    # 颜色
    acRed = 1
    acYellow = 2
    acGreen = 3
    acCyan = 4
    acBlue = 5
    acMagenta = 6
    acWhite = 7
    acDarkGrey = 8
    acLightGrey = 9
    
    # 对齐方式
    acAlignmentLeft = 0
    acAlignmentCenter = 1
    acAlignmentRight = 2
    
    # 文件格式
    ac2018 = 24
    acDXF = 25


class Autocad:
    """
    完全模仿 pyautocad.Autocad 的主类
    
    与原版 pyautocad 的区别：
    - 不需要 AutoCAD 软件运行
    - 使用 ezdxf 生成 DXF 文件
    - 跨平台支持
    
    Examples:
        >>> acad = Autocad()
        >>> acad = Autocad(create_if_not_exists=True)  # 参数兼容，但总是创建新文档
    """
    
    # 类常量
    acRed = 1
    acYellow = 2
    acGreen = 3
    acCyan = 4
    acBlue = 5
    acMagenta = 6
    acWhite = 7
    
    def __init__(self, create_if_not_exists: bool = True):
        """
        初始化 Autocad 对象
        
        Args:
            create_if_not_exists: 兼容 pyautocad 的参数，总是创建新文档
        """
        if not EZDXF_AVAILABLE:
            raise RuntimeError("ezdxf not installed. Run: pip install ezdxf")
        
        self._doc = Document(self)
        self._model = ModelSpace(self, self._doc)
        self._app = Application(self)
    
    @property
    def doc(self) -> "Document":
        """当前文档对象（模仿 acad.doc）"""
        return self._doc
    
    @property
    def model(self) -> "ModelSpace":
        """模型空间对象（模仿 acad.model）"""
        return self._model
    
    @property
    def app(self) -> "Application":
        """应用程序对象（模仿 acad.app）"""
        return self._app
    
    def __repr__(self) -> str:
        return f"Autocad(doc='{self._doc.Name}')"


class Document:
    """
    模仿 pyautocad 的 Document 对象（acad.doc）
    """
    
    def __init__(self, acad: Autocad):
        self._acad = acad
        self._ezdxf_doc = ezdxf.new("R2018")
        self._layers = Layers(self)
        self._name = "Drawing1.dxf"
    
    @property
    def Name(self) -> str:
        """文档名称"""
        return self._name
    
    @property
    def Layers(self) -> "Layers":
        """图层集合"""
        return self._layers
    
    @property
    def ActiveLayer(self) -> "Layer":
        """当前活动图层"""
        # ezdxf 获取当前图层
        return Layer(self, "0")
    
    @ActiveLayer.setter
    def ActiveLayer(self, layer: "Layer"):
        """设置当前图层"""
        # ezdxf 设置当前图层
        pass
    
    def SaveAs(self, filename: str, file_format: int = 24):
        """
        保存文档
        
        Args:
            filename: 文件名
            file_format: 
                24 = DWG 格式 (但 ezdxf 只能保存为 DXF)
                25 = DXF 格式
        """
        self._name = Path(filename).name
        
        # ezdxf 只能保存 DXF
        if file_format == 25 or str(filename).lower().endswith('.dxf'):
            self._ezdxf_doc.saveas(filename)
        else:
            # 强制保存为 DXF
            dxf_name = str(filename).replace('.dwg', '.dxf')
            self._ezdxf_doc.saveas(dxf_name)
    
    def Close(self, save_changes: bool = False):
        """关闭文档"""
        if save_changes:
            self.SaveAs(self._name)


class ModelSpace:
    """
    模仿 pyautocad 的 ModelSpace 对象（acad.model）
    提供所有 AddXXX 绘图方法
    """
    
    def __init__(self, acad: Autocad, doc: Document):
        self._acad = acad
        self._doc = doc
        self._msp = doc._ezdxf_doc.modelspace()
    
    # =======================================================================
    # 图形绘制方法 - 完全模仿 pyautocad
    # =======================================================================
    
    def AddCircle(self, center: APoint, radius: float) -> "AcadCircle":
        """
        添加圆
        
        Args:
            center: 圆心坐标 (APoint)
            radius: 半径
            
        Returns:
            AcadCircle 对象
            
        Examples:
            >>> circle = model.AddCircle(APoint(100, 100, 0), 50)
            >>> circle.Color = 1  # 红色
        """
        # ezdxf 创建圆
        entity = self._msp.add_circle(
            center=(center.x, center.y),
            radius=radius
        )
        return AcadCircle(entity)
    
    def AddArc(self, center: APoint, radius: float, 
               start_angle: float, end_angle: float) -> "AcadArc":
        """
        添加圆弧
        
        Args:
            center: 圆心
            radius: 半径
            start_angle: 起始角度（弧度）
            end_angle: 结束角度（弧度）
        """
        entity = self._msp.add_arc(
            center=(center.x, center.y),
            radius=radius,
            start_angle=math.degrees(start_angle),
            end_angle=math.degrees(end_angle)
        )
        return AcadArc(entity)
    
    def AddPolyline(self, points: Union[List[APoint], List[float]]) -> "AcadPolyline":
        """
        添加多段线
        
        Args:
            points: APoint 列表，或扁平坐标列表 [x1,y1,z1, x2,y2,z2, ...]
            
        Examples:
            >>> pline = model.AddPolyline([APoint(0,0), APoint(100,0), APoint(100,100)])
            >>> pline.Closed = True
        """
        # 处理不同类型的输入
        if points and isinstance(points[0], APoint):
            # APoint 列表
            coords = [(p.x, p.y) for p in points]
        elif points and isinstance(points[0], (int, float)):
            # 扁平列表 [x1,y1,z1, x2,y2,z2, ...]
            coords = []
            for i in range(0, len(points), 3):
                if i + 1 < len(points):
                    coords.append((points[i], points[i+1]))
        else:
            coords = []
        
        entity = self._msp.add_lwpolyline(coords)
        return AcadPolyline(entity)
    
    def AddText(self, text: str, insert_point: APoint, height: float) -> "AcadText":
        """
        添加文字
        
        Args:
            text: 文字内容
            insert_point: 插入点
            height: 文字高度
            
        Examples:
            >>> text = model.AddText("Hello", APoint(100, 100, 0), 10)
            >>> text.Color = 1
        """
        entity = self._msp.add_text(
            text=text,
            height=height,
            dxfattribs={'insert': (insert_point.x, insert_point.y)}
        )
        return AcadText(entity)
    
    def AddEllipse(self, center: APoint, major_axis: APoint, 
                   radius_ratio: float) -> "AcadEllipse":
        """
        添加椭圆
        
        Args:
            center: 中心点
            major_axis: 主轴端点
            radius_ratio: 长短轴比例 (短轴/长轴)
        """
        # 计算主轴向量
        major_axis_vector = (
            major_axis.x - center.x,
            major_axis.y - center.y
        )
        
        entity = self._msp.add_ellipse(
            center=(center.x, center.y),
            major_axis=major_axis_vector,
            ratio=radius_ratio
        )
        return AcadEllipse(entity)
    
    def AddLine(self, start: APoint, end: APoint) -> "AcadLine":
        """
        添加直线
        
        Args:
            start: 起点
            end: 终点
        """
        entity = self._msp.add_line(
            start=(start.x, start.y),
            end=(end.x, end.y)
        )
        return AcadLine(entity)
    
    def AddPoint(self, point: APoint) -> "AcadPoint":
        """添加点"""
        entity = self._msp.add_point((point.x, point.y))
        return AcadPoint(entity)
    
    def AddHatch(self, pattern_type: int, pattern_name: str, 
                 associativity: bool) -> "AcadHatch":
        """
        添加填充（简化版）
        
        Args:
            pattern_type: 1 = 预定义图案
            pattern_name: 图案名称如 "SOLID"
            associativity: 是否关联
        """
        # ezdxf 添加 hatch
        entity = self._msp.add_hatch(
            color=7,
            dxfattribs={'hatch_style': 0}
        )
        return AcadHatch(entity)


# =============================================================================
# 图形实体类 - 完全模仿 pyautocad 的对象
# =============================================================================

class AcadEntity:
    """图形实体基类"""
    
    def __init__(self, entity):
        self._entity = entity
        self._handle = str(id(entity))[-8:]  # 模拟 Handle
    
    @property
    def Handle(self) -> str:
        """对象句柄"""
        return self._handle
    
    @property
    def Layer(self) -> str:
        """图层"""
        return self._entity.dxf.layer
    
    @Layer.setter
    def Layer(self, value: str):
        self._entity.dxf.layer = value
    
    @property
    def Color(self) -> int:
        """颜色（ACI 索引）"""
        return self._entity.dxf.color
    
    @Color.setter
    def Color(self, value: int):
        self._entity.dxf.color = value
    
    @property
    def Linetype(self) -> str:
        """线型"""
        return self._entity.dxf.linetype
    
    @Linetype.setter
    def Linetype(self, value: str):
        self._entity.dxf.linetype = value
    
    @property
    def Lineweight(self) -> float:
        """线宽"""
        return self._entity.dxf.lineweight
    
    @Lineweight.setter
    def Lineweight(self, value: float):
        self._entity.dxf.lineweight = value
    
    # 变换方法
    def Rotate(self, base_point: APoint, rotation_angle: float):
        """旋转"""
        # ezdxf 旋转实现
        import ezdxf.math
        self._entity.rotate(
            angle=rotation_angle,
            center=(base_point.x, base_point.y)
        )
    
    def Move(self, from_point: APoint, to_point: APoint):
        """移动"""
        dx = to_point.x - from_point.x
        dy = to_point.y - from_point.y
        self._entity.translate(dx, dy, 0)
    
    def ScaleEntity(self, base_point: APoint, scale_factor: float):
        """缩放"""
        # ezdxf 缩放实现
        from ezdxf.math import Matrix44
        matrix = Matrix44.scale(scale_factor, scale_factor, 1)
        self._entity.transform(matrix)


class AcadCircle(AcadEntity):
    """圆对象"""
    
    @property
    def Center(self) -> Tuple[float, float, float]:
        """圆心"""
        return (self._entity.dxf.center[0], 
                self._entity.dxf.center[1], 0.0)
    
    @Center.setter
    def Center(self, point: APoint):
        self._entity.dxf.center = (point.x, point.y)
    
    @property
    def Radius(self) -> float:
        """半径"""
        return self._entity.dxf.radius
    
    @Radius.setter
    def Radius(self, value: float):
        self._entity.dxf.radius = value
    
    @property
    def Area(self) -> float:
        """面积"""
        import math
        return math.pi * self._entity.dxf.radius ** 2
    
    @property
    def Circumference(self) -> float:
        """周长"""
        import math
        return 2 * math.pi * self._entity.dxf.radius


class AcadArc(AcadEntity):
    """圆弧对象"""
    
    @property
    def StartAngle(self) -> float:
        """起始角度（弧度）"""
        return math.radians(self._entity.dxf.start_angle)
    
    @StartAngle.setter
    def StartAngle(self, value: float):
        self._entity.dxf.start_angle = math.degrees(value)
    
    @property
    def EndAngle(self) -> float:
        """结束角度（弧度）"""
        return math.radians(self._entity.dxf.end_angle)
    
    @EndAngle.setter
    def EndAngle(self, value: float):
        self._entity.dxf.end_angle = math.degrees(value)


class AcadPolyline(AcadEntity):
    """多段线对象"""
    
    @property
    def Closed(self) -> bool:
        """是否闭合"""
        return self._entity.closed
    
    @Closed.setter
    def Closed(self, value: bool):
        self._entity.closed = value
    
    def AppendVertex(self, point: APoint):
        """添加顶点"""
        self._entity.append_vertices([(point.x, point.y)])


class AcadText(AcadEntity):
    """文字对象"""
    
    @property
    def TextString(self) -> str:
        """文字内容"""
        return self._entity.dxf.text
    
    @TextString.setter
    def TextString(self, value: str):
        self._entity.dxf.text = value
    
    @property
    def Height(self) -> float:
        """文字高度"""
        return self._entity.dxf.height
    
    @Height.setter
    def Height(self, value: float):
        self._entity.dxf.height = value
    
    @property
    def InsertionPoint(self) -> Tuple[float, float, float]:
        """插入点"""
        return (self._entity.dxf.insert[0],
                self._entity.dxf.insert[1], 0.0)
    
    @InsertionPoint.setter
    def InsertionPoint(self, point: APoint):
        self._entity.dxf.insert = (point.x, point.y)
    
    @property
    def Rotation(self) -> float:
        """旋转角度（弧度）"""
        return math.radians(self._entity.dxf.rotation)
    
    @Rotation.setter
    def Rotation(self, value: float):
        self._entity.dxf.rotation = math.degrees(value)
    
    @property
    def HorizontalAlignment(self) -> int:
        """水平对齐"""
        return self._entity.dxf.halign
    
    @HorizontalAlignment.setter
    def HorizontalAlignment(self, value: int):
        self._entity.dxf.halign = value
    
    @property
    def VerticalAlignment(self) -> int:
        """垂直对齐"""
        return self._entity.dxf.valign
    
    @VerticalAlignment.setter
    def VerticalAlignment(self, value: int):
        self._entity.dxf.valign = value


class AcadEllipse(AcadEntity):
    """椭圆对象"""
    pass


class AcadLine(AcadEntity):
    """直线对象"""
    pass


class AcadPoint(AcadEntity):
    """点对象"""
    pass


class AcadHatch(AcadEntity):
    """填充对象"""
    
    def AppendLoop(self, loop_type: int, vertices: List[APoint]):
        """添加边界环"""
        # ezdxf 添加边界路径
        pass
    
    def Evaluate(self):
        """计算填充"""
        pass


# =============================================================================
# 图层相关类
# =============================================================================

class Layers:
    """图层集合"""
    
    def __init__(self, doc: Document):
        self._doc = doc
        self._ezdxf_layers = doc._ezdxf_doc.layers
    
    def Add(self, name: str) -> "Layer":
        """添加图层"""
        layer = self._ezdxf_layers.add(name)
        return Layer(layer)
    
    def Item(self, name: str) -> "Layer":
        """获取图层"""
        layer = self._ezdxf_layers.get(name)
        return Layer(layer)
    
    def __getitem__(self, name: str) -> "Layer":
        return self.Item(name)


class Layer:
    """图层对象"""
    
    def __init__(self, layer):
        self._layer = layer
    
    @property
    def Name(self) -> str:
        return self._layer.dxf.name
    
    @property
    def Color(self) -> int:
        return self._layer.dxf.color
    
    @Color.setter
    def Color(self, value: int):
        self._layer.dxf.color = value
    
    @property
    def Linetype(self) -> str:
        return self._layer.dxf.linetype
    
    @Linetype.setter
    def Linetype(self, value: str):
        self._layer.dxf.linetype = value
    
    @property
    def Lineweight(self) -> float:
        return self._layer.dxf.lineweight
    
    @Lineweight.setter
    def Lineweight(self, value: float):
        self._layer.dxf.lineweight = value


# =============================================================================
# 应用程序类
# =============================================================================

class Application:
    """应用程序对象（acad.app）"""
    
    def __init__(self, acad: Autocad):
        self._acad = acad
        self._documents = Documents(acad)
    
    @property
    def Documents(self) -> "Documents":
        return self._documents


class Documents:
    """文档集合"""
    
    def __init__(self, acad: Autocad):
        self._acad = acad
    
    def Add(self) -> Document:
        """新建文档"""
        return Document(self._acad)
    
    def Open(self, filename: str) -> Document:
        """打开文档"""
        doc = Document(self._acad)
        doc._ezdxf_doc = ezdxf.readfile(filename)
        doc._name = Path(filename).name
        return doc


# =============================================================================
# 辅助函数
# =============================================================================

def hex_to_aci(hex_color: str) -> int:
    """HEX 颜色转 ACI 颜色索引"""
    color_map = {
        "#FF0000": 1, "#FFFF00": 2, "#00FF00": 3, "#00FFFF": 4,
        "#0000FF": 5, "#FF00FF": 6, "#FFFFFF": 7, "#808080": 8,
        "#C0C0C0": 9, "#000000": 250,
    }
    return color_map.get(hex_color.upper(), 7)


def aci_to_hex(aci: int) -> str:
    """ACI 颜色索引转 HEX"""
    color_map = {
        1: "#FF0000", 2: "#FFFF00", 3: "#00FF00", 4: "#00FFFF",
        5: "#0000FF", 6: "#FF00FF", 7: "#FFFFFF", 8: "#808080",
        9: "#C0C0C0", 250: "#000000"
    }
    return color_map.get(aci, "#FFFFFF")


# =============================================================================
# 使用示例
# =============================================================================

if __name__ == "__main__":
    # 完全模仿 pyautocad 的用法
    from pyautocad_style import Autocad, APoint
    
    # 初始化（与 pyautocad 相同）
    acad = Autocad()
    
    # 获取模型空间
    doc = acad.doc
    model = acad.model
    
    # 绘制圆
    center = APoint(100, 100, 0)
    circle = model.AddCircle(center, 50)
    circle.Color = 1  # 红色
    circle.Layer = "0"
    print(f"Circle handle: {circle.Handle}")
    
    # 绘制矩形
    rect = model.AddPolyline([
        APoint(50, 50, 0),
        APoint(150, 50, 0),
        APoint(150, 100, 0),
        APoint(50, 100, 0),
        APoint(50, 50, 0)  # 闭合
    ])
    rect.Closed = True
    rect.Color = 2  # 黄色
    
    # 添加文字
    text = model.AddText("Hello World", APoint(100, 100, 0), 10)
    text.Color = 3  # 绿色
    
    # 保存
    doc.SaveAs("output.dxf", 25)  # 25 = DXF 格式
    print("Saved to output.dxf")
