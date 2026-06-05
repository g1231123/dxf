"""
CadLike 实体类
模仿 pyautocad 的各种图形实体
"""

import math
from typing import Union, List, Tuple, Optional
from .core import APoint


class AcadEntity:
    """
    CAD 实体基类
    
    所有图形实体的基类，提供通用的属性和方法。
    
    Attributes:
        Handle: 对象句柄（唯一标识）
        Layer: 图层名称
        Color: 颜色（ACI 索引）
        Linetype: 线型名称
        Lineweight: 线宽
    """
    
    def __init__(self, entity):
        """
        初始化实体
        
        Args:
            entity: 底层的 ezdxf 实体对象
        """
        self._entity = entity
        self._handle = str(id(entity))[-8:].upper()  # 模拟 Handle
    
    @property
    def Handle(self) -> str:
        """
        对象句柄 - 唯一标识符
        
        Returns:
            句柄字符串（十六进制）
        """
        return self._handle
    
    @property
    def EntityName(self) -> str:
        """
        实体类型名称
        
        Returns:
            类型名称字符串，如 "CIRCLE", "LINE", "LWPOLYLINE"
        """
        return self._entity.dxftype()
    
    @property
    def EntityType(self) -> int:
        """
        实体类型代码
        
        Returns:
            整数类型代码
        """
        # 返回 DXF 类型代码
        type_map = {
            'CIRCLE': 1,
            'ARC': 2,
            'LINE': 3,
            'LWPOLYLINE': 4,
            'TEXT': 5,
            'ELLIPSE': 6,
            'POINT': 7,
            'HATCH': 8,
        }
        return type_map.get(self.EntityName, 0)
    
    @property
    def Layer(self) -> str:
        """
        图层名称
        
        Returns:
            图层名字符串
        """
        return self._entity.dxf.layer
    
    @Layer.setter
    def Layer(self, value: str):
        """设置图层"""
        self._entity.dxf.layer = str(value)
    
    @property
    def Color(self) -> int:
        """
        颜色（ACI 索引）
        
        Returns:
            ACI 颜色索引（1-255）
            
        Note:
            常用颜色：
            1 = 红色, 2 = 黄色, 3 = 绿色, 4 = 青色
            5 = 蓝色, 6 = 品红, 7 = 白色/黑色
        """
        return self._entity.dxf.color
    
    @Color.setter
    def Color(self, value: int):
        """设置颜色"""
        self._entity.dxf.color = int(value)
    
    @property
    def TrueColor(self) -> Tuple[int, int, int]:
        """
        真彩色（RGB）
        
        Returns:
            RGB 元组 (r, g, b)
        """
        rgb = self._entity.dxf.get('true_color', None)
        if rgb:
            return ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)
        from .utils import aci_to_rgb
        return aci_to_rgb(self.Color)
    
    @TrueColor.setter
    def TrueColor(self, rgb: Tuple[int, int, int]):
        """设置真彩色"""
        r, g, b = rgb
        self._entity.dxf.true_color = (r << 16) | (g << 8) | b
    
    @property
    def Linetype(self) -> str:
        """
        线型名称
        
        Returns:
            线型名字符串，如 "Continuous", "Hidden", "Center"
        """
        return self._entity.dxf.linetype
    
    @Linetype.setter
    def Linetype(self, value: str):
        """设置线型"""
        self._entity.dxf.linetype = str(value)
    
    @property
    def Lineweight(self) -> float:
        """
        线宽
        
        Returns:
            线宽值（毫米）
        """
        return self._entity.dxf.lineweight
    
    @Lineweight.setter
    def Lineweight(self, value: float):
        """设置线宽"""
        self._entity.dxf.lineweight = float(value)
    
    @property
    def Visible(self) -> bool:
        """
        是否可见
        
        Returns:
            True = 可见, False = 隐藏
        """
        return not self._entity.dxf.invisible
    
    @Visible.setter
    def Visible(self, value: bool):
        """设置可见性"""
        self._entity.dxf.invisible = not value
    
    @property
    def PlotStyleName(self) -> str:
        """打印样式名称"""
        return self._entity.dxf.get('plotstyle_name', 'Normal')
    
    @PlotStyleName.setter
    def PlotStyleName(self, value: str):
        """设置打印样式"""
        self._entity.dxf.plotstyle_name = str(value)
    
    # =====================================================================
    # 变换方法
    # =====================================================================
    
    def Rotate(self, base_point: APoint, rotation_angle: float):
        """
        绕基点旋转
        
        Args:
            base_point: 旋转基点
            rotation_angle: 旋转角度（弧度）
            
        Examples:
            >>> circle.Rotate(APoint(100, 100, 0), math.pi/4)  # 旋转45度
        """
        self._entity.rotate(
            angle=rotation_angle,
            center=(base_point.x, base_point.y)
        )
    
    def Rotate_degrees(self, base_point: APoint, angle_deg: float):
        """
        绕基点旋转（角度为度）
        
        Args:
            base_point: 旋转基点
            angle_deg: 旋转角度（度）
        """
        self.Rotate(base_point, math.radians(angle_deg))
    
    def Move(self, from_point: APoint, to_point: APoint):
        """
        移动实体
        
        Args:
            from_point: 起始点
            to_point: 目标点
            
        Examples:
            >>> circle.Move(APoint(0, 0, 0), APoint(100, 100, 0))
        """
        dx = to_point.x - from_point.x
        dy = to_point.y - from_point.y
        dz = to_point.z - from_point.z
        self._entity.translate(dx, dy, dz)
    
    def ScaleEntity(self, base_point: APoint, scale_factor: float):
        """
        缩放实体
        
        Args:
            base_point: 缩放基点
            scale_factor: 缩放因子
            
        Examples:
            >>> circle.ScaleEntity(APoint(100, 100, 0), 2.0)  # 放大2倍
        """
        # ezdxf 缩放实现
        from ezdxf.math import Matrix44
        
        # 创建缩放矩阵
        matrix = Matrix44.scale(scale_factor, scale_factor, scale_factor)
        
        # 平移到原点，缩放，再平移回去
        self._entity.translate(-base_point.x, -base_point.y, -base_point.z)
        self._entity.transform(matrix)
        self._entity.translate(base_point.x, base_point.y, base_point.z)
    
    def Mirror(self, point1: APoint, point2: APoint):
        """
        镜像实体
        
        Args:
            point1: 镜像线第一点
            point2: 镜像线第二点
        """
        # 计算镜像线
        dx = point2.x - point1.x
        dy = point2.y - point1.y
        angle = math.atan2(dy, dx)
        
        # 旋转到水平，镜像，再旋转回去
        self.Rotate(point1, -angle)
        # 沿 X 轴镜像（通过缩放实现）
        self.ScaleEntity(point1, -1)
        self.Rotate(point1, angle)
    
    def Erase(self):
        """删除实体"""
        self._entity.delete()
    
    def Copy(self) -> "AcadEntity":
        """
        复制实体
        
        Returns:
            新的实体对象
        """
        # ezdxf 复制实现
        new_entity = self._entity.copy()
        return AcadEntity(new_entity)
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"{self.EntityName}(Handle={self.Handle})"
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"{self.EntityName}: Layer={self.Layer}, Color={self.Color}"


# =============================================================================
# 具体实体类
# =============================================================================

class AcadCircle(AcadEntity):
    """
    圆实体
    
    Attributes:
        Center: 圆心坐标 (x, y, z)
        Radius: 半径
        Diameter: 直径
        Area: 面积
        Circumference: 周长
    """
    
    @property
    def Center(self) -> Tuple[float, float, float]:
        """圆心坐标"""
        center = self._entity.dxf.center
        return (center[0], center[1], 0.0)
    
    @Center.setter
    def Center(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置圆心"""
        if isinstance(point, APoint):
            self._entity.dxf.center = (point.x, point.y)
        else:
            self._entity.dxf.center = (point[0], point[1])
    
    @property
    def Radius(self) -> float:
        """半径"""
        return self._entity.dxf.radius
    
    @Radius.setter
    def Radius(self, value: float):
        """设置半径"""
        self._entity.dxf.radius = float(value)
    
    @property
    def Diameter(self) -> float:
        """直径"""
        return self._entity.dxf.radius * 2
    
    @Diameter.setter
    def Diameter(self, value: float):
        """设置直径"""
        self._entity.dxf.radius = float(value) / 2
    
    @property
    def Area(self) -> float:
        """面积"""
        r = self._entity.dxf.radius
        return math.pi * r * r
    
    @property
    def Circumference(self) -> float:
        """周长"""
        r = self._entity.dxf.radius
        return 2 * math.pi * r
    
    def Offset(self, distance: float) -> "AcadCircle":
        """
        偏移（创建同心圆）
        
        Args:
            distance: 偏移距离（正 = 向外，负 = 向内）
            
        Returns:
            新的圆对象
        """
        new_radius = self.Radius + distance
        if new_radius <= 0:
            raise ValueError("Offset distance too large")
        
        # 创建新圆
        from .core import APoint
        center = APoint(*self.Center)
        return self.__class__(self._entity.copy())


class AcadArc(AcadEntity):
    """
    圆弧实体
    
    Attributes:
        Center: 圆心
        Radius: 半径
        StartAngle: 起始角度（弧度）
        EndAngle: 结束角度（弧度）
        TotalAngle: 总角度
    """
    
    @property
    def Center(self) -> Tuple[float, float, float]:
        """圆心坐标"""
        center = self._entity.dxf.center
        return (center[0], center[1], 0.0)
    
    @Center.setter
    def Center(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置圆心"""
        if isinstance(point, APoint):
            self._entity.dxf.center = (point.x, point.y)
        else:
            self._entity.dxf.center = (point[0], point[1])
    
    @property
    def Radius(self) -> float:
        """半径"""
        return self._entity.dxf.radius
    
    @Radius.setter
    def Radius(self, value: float):
        """设置半径"""
        self._entity.dxf.radius = float(value)
    
    @property
    def StartAngle(self) -> float:
        """起始角度（弧度）"""
        return math.radians(self._entity.dxf.start_angle)
    
    @StartAngle.setter
    def StartAngle(self, value: float):
        """设置起始角度（弧度）"""
        self._entity.dxf.start_angle = math.degrees(value)
    
    @property
    def EndAngle(self) -> float:
        """结束角度（弧度）"""
        return math.radians(self._entity.dxf.end_angle)
    
    @EndAngle.setter
    def EndAngle(self, value: float):
        """设置结束角度（弧度）"""
        self._entity.dxf.end_angle = math.degrees(value)
    
    @property
    def TotalAngle(self) -> float:
        """总角度（弧度）"""
        start = self.StartAngle
        end = self.EndAngle
        if end < start:
            end += 2 * math.pi
        return end - start
    
    @property
    def ArcLength(self) -> float:
        """弧长"""
        return self.Radius * self.TotalAngle


class AcadPolyline(AcadEntity):
    """
    多段线实体（轻量级多段线）
    
    Attributes:
        Closed: 是否闭合
        Length: 总长度
        Area: 面积（闭合时有效）
        NumberOfVertices: 顶点数
    """
    
    @property
    def Closed(self) -> bool:
        """是否闭合"""
        return self._entity.closed
    
    @Closed.setter
    def Closed(self, value: bool):
        """设置闭合状态"""
        self._entity.closed = bool(value)
    
    @property
    def Length(self) -> float:
        """总长度"""
        return self._entity.length
    
    @property
    def Area(self) -> float:
        """面积（仅闭合时有效）"""
        if not self.Closed:
            return 0.0
        return self._entity.get_area()
    
    @property
    def NumberOfVertices(self) -> int:
        """顶点数"""
        return len(self._entity)
    
    def AppendVertex(self, point: APoint):
        """
        添加顶点
        
        Args:
            point: 新顶点坐标
        """
        self._entity.append_vertices([(point.x, point.y)])
    
    def GetPointAt(self, index: int) -> Tuple[float, float, float]:
        """
        获取指定索引的顶点
        
        Args:
            index: 顶点索引（从0开始）
            
        Returns:
            顶点坐标 (x, y, z)
        """
        if 0 <= index < len(self._entity):
            pt = self._entity[index]
            return (pt[0], pt[1], 0.0)
        raise IndexError(f"Index {index} out of range")
    
    def SetPointAt(self, index: int, point: APoint):
        """
        设置指定索引的顶点
        
        Args:
            index: 顶点索引
            point: 新坐标
        """
        if 0 <= index < len(self._entity):
            self._entity[index] = (point.x, point.y)
        else:
            raise IndexError(f"Index {index} out of range")


class AcadLine(AcadEntity):
    """
    直线实体
    
    Attributes:
        StartPoint: 起点
        EndPoint: 终点
        Length: 长度
        Angle: 角度（弧度）
        Delta: 增量 (dx, dy, dz)
    """
    
    @property
    def StartPoint(self) -> Tuple[float, float, float]:
        """起点坐标"""
        start = self._entity.dxf.start
        return (start[0], start[1], start[2] if len(start) > 2 else 0.0)
    
    @StartPoint.setter
    def StartPoint(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置起点"""
        if isinstance(point, APoint):
            self._entity.dxf.start = (point.x, point.y, point.z)
        else:
            self._entity.dxf.start = point
    
    @property
    def EndPoint(self) -> Tuple[float, float, float]:
        """终点坐标"""
        end = self._entity.dxf.end
        return (end[0], end[1], end[2] if len(end) > 2 else 0.0)
    
    @EndPoint.setter
    def EndPoint(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置终点"""
        if isinstance(point, APoint):
            self._entity.dxf.end = (point.x, point.y, point.z)
        else:
            self._entity.dxf.end = point
    
    @property
    def Length(self) -> float:
        """长度"""
        start = self._entity.dxf.start
        end = self._entity.dxf.end
        return math.sqrt(
            (end[0] - start[0])**2 + 
            (end[1] - start[1])**2
        )
    
    @property
    def Angle(self) -> float:
        """角度（弧度）"""
        start = self._entity.dxf.start
        end = self._entity.dxf.end
        return math.atan2(end[1] - start[1], end[0] - start[0])
    
    @property
    def Delta(self) -> Tuple[float, float, float]:
        """增量 (dx, dy, dz)"""
        start = self._entity.dxf.start
        end = self._entity.dxf.end
        return (
            end[0] - start[0],
            end[1] - start[1],
            (end[2] if len(end) > 2 else 0.0) - (start[2] if len(start) > 2 else 0.0)
        )


class AcadText(AcadEntity):
    """
    单行文字实体
    
    Attributes:
        TextString: 文字内容
        InsertionPoint: 插入点
        Height: 文字高度
        Rotation: 旋转角度（弧度）
        WidthFactor: 宽度因子
        ObliqueAngle: 倾斜角度
        HorizontalAlignment: 水平对齐
        VerticalAlignment: 垂直对齐
    """
    
    @property
    def TextString(self) -> str:
        """文字内容"""
        return self._entity.dxf.text
    
    @TextString.setter
    def TextString(self, value: str):
        """设置文字内容"""
        self._entity.dxf.text = str(value)
    
    @property
    def InsertionPoint(self) -> Tuple[float, float, float]:
        """插入点坐标"""
        insert = self._entity.dxf.insert
        return (insert[0], insert[1], 0.0)
    
    @InsertionPoint.setter
    def InsertionPoint(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置插入点"""
        if isinstance(point, APoint):
            self._entity.dxf.insert = (point.x, point.y)
        else:
            self._entity.dxf.insert = (point[0], point[1])
    
    @property
    def Height(self) -> float:
        """文字高度"""
        return self._entity.dxf.height
    
    @Height.setter
    def Height(self, value: float):
        """设置文字高度"""
        self._entity.dxf.height = float(value)
    
    @property
    def Rotation(self) -> float:
        """旋转角度（弧度）"""
        return math.radians(self._entity.dxf.rotation)
    
    @Rotation.setter
    def Rotation(self, value: float):
        """设置旋转角度（弧度）"""
        self._entity.dxf.rotation = math.degrees(value)
    
    @property
    def WidthFactor(self) -> float:
        """宽度因子"""
        return self._entity.dxf.width_factor
    
    @WidthFactor.setter
    def WidthFactor(self, value: float):
        """设置宽度因子"""
        self._entity.dxf.width_factor = float(value)
    
    @property
    def ObliqueAngle(self) -> float:
        """倾斜角度（弧度）"""
        return math.radians(self._entity.dxf.oblique)
    
    @ObliqueAngle.setter
    def ObliqueAngle(self, value: float):
        """设置倾斜角度（弧度）"""
        self._entity.dxf.oblique = math.degrees(value)
    
    @property
    def HorizontalAlignment(self) -> int:
        """水平对齐 (0=左, 1=中, 2=右)"""
        return self._entity.dxf.halign
    
    @HorizontalAlignment.setter
    def HorizontalAlignment(self, value: int):
        """设置水平对齐"""
        self._entity.dxf.halign = int(value)
    
    @property
    def VerticalAlignment(self) -> int:
        """垂直对齐"""
        return self._entity.dxf.valign
    
    @VerticalAlignment.setter
    def VerticalAlignment(self, value: int):
        """设置垂直对齐"""
        self._entity.dxf.valign = int(value)
    
    @property
    def StyleName(self) -> str:
        """文字样式名称"""
        return self._entity.dxf.style
    
    @StyleName.setter
    def StyleName(self, value: str):
        """设置文字样式"""
        self._entity.dxf.style = str(value)


class AcadEllipse(AcadEntity):
    """
    椭圆实体
    
    Attributes:
        Center: 中心点
        MajorAxis: 主轴端点
        MinorAxis: 副轴端点
        MajorRadius: 长轴半径
        MinorRadius: 短轴半径
        RadiusRatio: 半径比（短轴/长轴）
        StartAngle: 起始角度
        EndAngle: 结束角度
    """
    
    @property
    def Center(self) -> Tuple[float, float, float]:
        """中心点坐标"""
        center = self._entity.dxf.center
        return (center[0], center[1], 0.0)
    
    @Center.setter
    def Center(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置中心点"""
        if isinstance(point, APoint):
            self._entity.dxf.center = (point.x, point.y)
        else:
            self._entity.dxf.center = (point[0], point[1])
    
    @property
    def MajorAxis(self) -> Tuple[float, float]:
        """主轴向量"""
        return self._entity.dxf.major_axis
    
    @MajorAxis.setter
    def MajorAxis(self, vector: Tuple[float, float]):
        """设置主轴向量"""
        self._entity.dxf.major_axis = vector
    
    @property
    def RadiusRatio(self) -> float:
        """半径比（短轴/长轴）"""
        return self._entity.dxf.ratio
    
    @RadiusRatio.setter
    def RadiusRatio(self, value: float):
        """设置半径比"""
        self._entity.dxf.ratio = float(value)
    
    @property
    def StartAngle(self) -> float:
        """起始角度（弧度）"""
        return self._entity.dxf.start_param
    
    @StartAngle.setter
    def StartAngle(self, value: float):
        """设置起始角度（弧度）"""
        self._entity.dxf.start_param = float(value)
    
    @property
    def EndAngle(self) -> float:
        """结束角度（弧度）"""
        return self._entity.dxf.end_param
    
    @EndAngle.setter
    def EndAngle(self, value: float):
        """设置结束角度（弧度）"""
        self._entity.dxf.end_param = float(value)
    
    @property
    def MajorRadius(self) -> float:
        """长轴半径"""
        axis = self._entity.dxf.major_axis
        return math.sqrt(axis[0]**2 + axis[1]**2)
    
    @property
    def MinorRadius(self) -> float:
        """短轴半径"""
        return self.MajorRadius * self.RadiusRatio


class AcadPoint(AcadEntity):
    """
    点实体
    
    Attributes:
        Coordinates: 坐标 (x, y, z)
    """
    
    @property
    def Coordinates(self) -> Tuple[float, float, float]:
        """点坐标"""
        loc = self._entity.dxf.location
        return (loc[0], loc[1], loc[2] if len(loc) > 2 else 0.0)
    
    @Coordinates.setter
    def Coordinates(self, point: Union[APoint, Tuple[float, float, float]]):
        """设置坐标"""
        if isinstance(point, APoint):
            self._entity.dxf.location = (point.x, point.y, point.z)
        else:
            self._entity.dxf.location = point


class AcadHatch(AcadEntity):
    """
    填充实体
    
    Attributes:
        PatternName: 图案名称
        PatternScale: 图案比例
        PatternAngle: 图案角度
        Associative: 是否关联边界
    """
    
    @property
    def PatternName(self) -> str:
        """图案名称"""
        return self._entity.dxf.pattern_name
    
    @PatternName.setter
    def PatternName(self, value: str):
        """设置图案名称"""
        self._entity.dxf.pattern_name = str(value)
    
    @property
    def PatternScale(self) -> float:
        """图案比例"""
        return self._entity.dxf.pattern_scale
    
    @PatternScale.setter
    def PatternScale(self, value: float):
        """设置图案比例"""
        self._entity.dxf.pattern_scale = float(value)
    
    @property
    def PatternAngle(self) -> float:
        """图案角度（弧度）"""
        return math.radians(self._entity.dxf.pattern_angle)
    
    @PatternAngle.setter
    def PatternAngle(self, value: float):
        """设置图案角度（弧度）"""
        self._entity.dxf.pattern_angle = math.degrees(value)
    
    def AppendLoop(self, loop_type: int, vertices: List[APoint]):
        """
        添加边界环
        
        Args:
            loop_type: 环类型（0=外环，1=内环）
            vertices: 顶点列表
        """
        # 转换为路径
        from ezdxf.entities import BoundaryPath
        path = BoundaryPath()
        
        for vertex in vertices:
            if isinstance(vertex, APoint):
                path.add_vertex((vertex.x, vertex.y))
            else:
                path.add_vertex((vertex[0], vertex[1]))
        
        self._entity.append_path(path)
    
    def Evaluate(self):
        """计算填充（对 ezdxf 来说是空操作）"""
        pass
    
    @property
    def Area(self) -> float:
        """填充面积"""
        # ezdxf hatch 面积计算
        return self._entity.get_area()
