"""
CadLike 核心类
APoint 和 Autocad 主类
"""

import math
from dataclasses import dataclass
from typing import Union, Tuple, Optional, List


@dataclass
class APoint:
    """
    CAD 坐标点类 - 完全模仿 pyautocad.APoint
    
    支持 2D 和 3D 坐标，提供完整的数学运算支持。
    
    Attributes:
        x: X 坐标
        y: Y 坐标
        z: Z 坐标（默认为 0）
    
    Examples:
        >>> p = APoint(100, 200)
        >>> p.x, p.y, p.z
        (100.0, 200.0, 0.0)
        
        >>> p1 = APoint(100, 200, 50)
        >>> x, y, z = p1  # 支持解包
        
        >>> p2 = p + APoint(10, 20)  # 支持加法
        >>> p3 = p - APoint(10, 20)  # 支持减法
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
        if not isinstance(other, APoint):
            raise TypeError(f"Cannot add APoint with {type(other)}")
        return APoint(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: "APoint") -> "APoint":
        """点相减"""
        if not isinstance(other, APoint):
            raise TypeError(f"Cannot subtract APoint with {type(other)}")
        return APoint(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __mul__(self, scalar: float) -> "APoint":
        """数乘"""
        return APoint(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def __rmul__(self, scalar: float) -> "APoint":
        """数乘（反向）"""
        return self.__mul__(scalar)
    
    def __truediv__(self, scalar: float) -> "APoint":
        """数除"""
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return APoint(self.x / scalar, self.y / scalar, self.z / scalar)
    
    def __eq__(self, other) -> bool:
        """相等比较"""
        if not isinstance(other, APoint):
            return False
        return (abs(self.x - other.x) < 1e-9 and 
                abs(self.y - other.y) < 1e-9 and 
                abs(self.z - other.z) < 1e-9)
    
    def __repr__(self) -> str:
        """字符串表示"""
        if self.z == 0:
            return f"APoint({self.x}, {self.y})"
        return f"APoint({self.x}, {self.y}, {self.z})"
    
    def __str__(self) -> str:
        """格式化输出"""
        if self.z == 0:
            return f"({self.x:.4f}, {self.y:.4f})"
        return f"({self.x:.4f}, {self.y:.4f}, {self.z:.4f})"
    
    def distance_to(self, other: "APoint") -> float:
        """
        计算到另一点的距离
        
        Args:
            other: 另一点
            
        Returns:
            距离值
        """
        return math.sqrt(
            (self.x - other.x) ** 2 + 
            (self.y - other.y) ** 2 + 
            (self.z - other.z) ** 2
        )
    
    def distance_to_xy(self, other: "APoint") -> float:
        """
        计算到另一点的 XY 平面距离（忽略 Z）
        
        Args:
            other: 另一点
            
        Returns:
            XY 平面距离
        """
        return math.sqrt(
            (self.x - other.x) ** 2 + 
            (self.y - other.y) ** 2
        )
    
    def angle_to(self, other: "APoint") -> float:
        """
        计算到另一点的角度（弧度）
        
        Args:
            other: 另一点
            
        Returns:
            角度（弧度）
        """
        dx = other.x - self.x
        dy = other.y - self.y
        return math.atan2(dy, dx)
    
    def angle_to_degrees(self, other: "APoint") -> float:
        """
        计算到另一点的角度（度）
        
        Args:
            other: 另一点
            
        Returns:
            角度（度）
        """
        return math.degrees(self.angle_to(other))
    
    def polar(self, angle: float, distance: float) -> "APoint":
        """
        根据极坐标计算新点
        
        Args:
            angle: 角度（弧度）
            distance: 距离
            
        Returns:
            新点
        """
        return APoint(
            self.x + distance * math.cos(angle),
            self.y + distance * math.sin(angle),
            self.z
        )
    
    def polar_degrees(self, angle_deg: float, distance: float) -> "APoint":
        """
        根据极坐标计算新点（角度为度）
        
        Args:
            angle_deg: 角度（度）
            distance: 距离
            
        Returns:
            新点
        """
        return self.polar(math.radians(angle_deg), distance)
    
    def translate(self, dx: float, dy: float, dz: float = 0.0) -> "APoint":
        """
        平移点
        
        Args:
            dx: X 方向位移
            dy: Y 方向位移
            dz: Z 方向位移
            
        Returns:
            新点
        """
        return APoint(self.x + dx, self.y + dy, self.z + dz)
    
    def rotate(self, angle: float, origin: Optional["APoint"] = None) -> "APoint":
        """
        绕原点旋转点
        
        Args:
            angle: 旋转角度（弧度）
            origin: 旋转原点，默认为 (0,0,0)
            
        Returns:
            旋转后的新点
        """
        if origin is None:
            origin = APoint(0, 0, 0)
        
        # 平移到原点
        dx = self.x - origin.x
        dy = self.y - origin.y
        
        # 旋转
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        new_x = origin.x + dx * cos_a - dy * sin_a
        new_y = origin.y + dx * sin_a + dy * cos_a
        
        return APoint(new_x, new_y, self.z)
    
    def rotate_degrees(self, angle_deg: float, 
                       origin: Optional["APoint"] = None) -> "APoint":
        """
        绕原点旋转点（角度为度）
        
        Args:
            angle_deg: 旋转角度（度）
            origin: 旋转原点
            
        Returns:
            旋转后的新点
        """
        return self.rotate(math.radians(angle_deg), origin)
    
    def scale(self, factor: float, origin: Optional["APoint"] = None) -> "APoint":
        """
        缩放点
        
        Args:
            factor: 缩放因子
            origin: 缩放原点
            
        Returns:
            缩放后的新点
        """
        if origin is None:
            origin = APoint(0, 0, 0)
        
        dx = self.x - origin.x
        dy = self.y - origin.y
        dz = self.z - origin.z
        
        return APoint(
            origin.x + dx * factor,
            origin.y + dy * factor,
            origin.z + dz * factor
        )
    
    def midpoint(self, other: "APoint") -> "APoint":
        """
        计算中点
        
        Args:
            other: 另一点
            
        Returns:
            中点
        """
        return APoint(
            (self.x + other.x) / 2,
            (self.y + other.y) / 2,
            (self.z + other.z) / 2
        )
    
    def to_tuple(self) -> Tuple[float, float, float]:
        """转换为元组"""
        return (self.x, self.y, self.z)
    
    def to_tuple_2d(self) -> Tuple[float, float]:
        """转换为 2D 元组"""
        return (self.x, self.y)
    
    @classmethod
    def from_tuple(cls, t: Tuple[float, ...]) -> "APoint":
        """从元组创建"""
        if len(t) >= 3:
            return cls(t[0], t[1], t[2])
        elif len(t) == 2:
            return cls(t[0], t[1], 0.0)
        elif len(t) == 1:
            return cls(t[0], 0.0, 0.0)
        return cls(0.0, 0.0, 0.0)
    
    @classmethod
    def origin(cls) -> "APoint":
        """返回原点"""
        return cls(0.0, 0.0, 0.0)


class Autocad:
    """
    CAD 应用程序主类 - 完全模仿 pyautocad.Autocad
    
    此类是 CadLike 库的入口点，提供与 pyautocad 完全相同的 API。
    但不需要 AutoCAD 软件运行，使用 ezdxf 作为后端。
    
    Attributes:
        doc: 当前文档对象
        model: 模型空间对象
        app: 应用程序对象
    
    Examples:
        >>> from cadlike import Autocad, APoint
        >>> acad = Autocad()
        >>> model = acad.model
        >>> circle = model.AddCircle(APoint(100, 100, 0), 50)
        >>> acad.doc.SaveAs("output.dxf")
    
    Note:
        create_if_not_exists 参数仅用于与 pyautocad 兼容，
        实际上总是会创建一个新文档。
    """
    
    def __init__(self, create_if_not_exists: bool = True):
        """
        初始化 Autocad 对象
        
        Args:
            create_if_not_exists: 兼容 pyautocad 的参数，
                                 实际上总是会创建新文档
        """
        # 延迟导入以避免循环依赖
        from .document import Document
        from .modelspace import ModelSpace
        from .application import Application
        
        self._doc = Document(self)
        self._model = ModelSpace(self, self._doc)
        self._app = Application(self)
    
    @property
    def doc(self) -> "Document":
        """
        当前文档对象（模仿 acad.doc）
        
        Returns:
            Document 对象
        """
        return self._doc
    
    @property
    def model(self) -> "ModelSpace":
        """
        模型空间对象（模仿 acad.model）
        
        Returns:
            ModelSpace 对象
        """
        return self._model
    
    @property
    def app(self) -> "Application":
        """
        应用程序对象（模仿 acad.app）
        
        Returns:
            Application 对象
        """
        return self._app
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Autocad(doc='{self._doc.Name}')"
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"CadLike Autocad - {self._doc.Name}"
