"""
CadLike 模型空间类
模仿 pyautocad 的 ModelSpace 对象
"""

import math
from typing import Union, List, Tuple, Optional

from .core import APoint


class ModelSpace:
    """
    CAD 模型空间类 - 模仿 pyautocad.model
    
    这是主要的绘图区域，提供所有 AddXXX 方法来创建图形实体。
    
    Attributes:
        (无公共属性，通过方法操作)
    
    Examples:
        >>> model = acad.model
        >>> 
        >>> # 绘制圆
        >>> circle = model.AddCircle(APoint(100, 100, 0), 50)
        >>> 
        >>> # 绘制直线
        >>> line = model.AddLine(APoint(0, 0, 0), APoint(100, 100, 0))
        >>> 
        >>> # 绘制多段线
        >>> pline = model.AddPolyline([APoint(0, 0), APoint(100, 0), APoint(100, 100)])
    """
    
    def __init__(self, acad, doc):
        """
        初始化模型空间
        
        Args:
            acad: 父 Autocad 对象
            doc: 父 Document 对象
        """
        self._acad = acad
        self._doc = doc
        self._msp = doc._ezdxf_doc.modelspace()
    
    # =========================================================================
    # 基本图形绘制方法
    # =========================================================================
    
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
            >>> print(circle.Area)  # 计算面积
        """
        from .entities import AcadCircle
        
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
            center: 圆心坐标
            radius: 半径
            start_angle: 起始角度（弧度）
            end_angle: 结束角度（弧度）
            
        Returns:
            AcadArc 对象
            
        Note:
            角度按弧度计算，逆时针方向。
            0 弧度 = X 轴正方向（右侧）
            
        Examples:
            >>> # 上半圆
            >>> arc = model.AddArc(APoint(100, 100, 0), 50, 0, math.pi)
            >>> 
            >>> # 90度弧（四分之一圆）
            >>> arc = model.AddArc(APoint(100, 100, 0), 50, 0, math.pi/2)
        """
        from .entities import AcadArc
        
        entity = self._msp.add_arc(
            center=(center.x, center.y),
            radius=radius,
            start_angle=math.degrees(start_angle),
            end_angle=math.degrees(end_angle)
        )
        return AcadArc(entity)
    
    def AddArc_degrees(self, center: APoint, radius: float,
                       start_angle: float, end_angle: float) -> "AcadArc":
        """
        添加圆弧（角度为度）
        
        Args:
            center: 圆心坐标
            radius: 半径
            start_angle: 起始角度（度）
            end_angle: 结束角度（度）
            
        Returns:
            AcadArc 对象
        """
        return self.AddArc(center, radius, 
                          math.radians(start_angle), 
                          math.radians(end_angle))
    
    def AddLine(self, start: APoint, end: APoint) -> "AcadLine":
        """
        添加直线
        
        Args:
            start: 起点
            end: 终点
            
        Returns:
            AcadLine 对象
            
        Examples:
            >>> line = model.AddLine(APoint(0, 0, 0), APoint(100, 100, 0))
            >>> line.Color = 1
        """
        from .entities import AcadLine
        
        entity = self._msp.add_line(
            start=(start.x, start.y),
            end=(end.x, end.y)
        )
        return AcadLine(entity)
    
    def AddPolyline(self, points: Union[List[APoint], List[float]]) -> "AcadPolyline":
        """
        添加多段线（轻量级多段线）
        
        Args:
            points: APoint 列表，或扁平坐标列表 [x1,y1,z1, x2,y2,z2, ...]
            
        Returns:
            AcadPolyline 对象
            
        Examples:
            >>> # 使用 APoint 列表
            >>> pline = model.AddPolyline([
            ...     APoint(0, 0, 0),
            ...     APoint(100, 0, 0),
            ...     APoint(100, 100, 0),
            ...     APoint(0, 100, 0),
            ...     APoint(0, 0, 0)  # 闭合
            ... ])
            >>> pline.Closed = True
            >>> 
            >>> # 使用扁平列表（兼容 pyautocad）
            >>> points = [0, 0, 0, 100, 0, 0, 100, 100, 0, 0, 100, 0]
            >>> pline = model.AddPolyline(points)
        """
        from .entities import AcadPolyline
        
        # 处理不同类型的输入
        if points and isinstance(points[0], APoint):
            # APoint 列表
            coords = [(p.x, p.y) for p in points]
        elif points and isinstance(points[0], (int, float)):
            # 扁平列表 [x1,y1,z1, x2,y2,z2, ...]
            coords = []
            for i in range(0, len(points) - 1, 3):
                if i + 1 < len(points):
                    coords.append((points[i], points[i+1]))
        else:
            coords = []
        
        entity = self._msp.add_lwpolyline(coords)
        return AcadPolyline(entity)
    
    def AddPoint(self, point: APoint) -> "AcadPoint":
        """
        添加点
        
        Args:
            point: 点坐标
            
        Returns:
            AcadPoint 对象
        """
        from .entities import AcadPoint
        
        entity = self._msp.add_point((point.x, point.y))
        return AcadPoint(entity)
    
    # =========================================================================
    # 文字和标注
    # =========================================================================
    
    def AddText(self, text: str, insert_point: APoint, height: float) -> "AcadText":
        """
        添加单行文字
        
        Args:
            text: 文字内容
            insert_point: 插入点
            height: 文字高度
            
        Returns:
            AcadText 对象
            
        Examples:
            >>> text = model.AddText("Hello World", APoint(100, 100, 0), 10)
            >>> text.Color = 1
            >>> text.Rotation = math.pi / 4  # 45度旋转
        """
        from .entities import AcadText
        
        entity = self._msp.add_text(
            text=text,
            height=height,
            dxfattribs={'insert': (insert_point.x, insert_point.y)}
        )
        return AcadText(entity)
    
    def AddMText(self, insert_point: APoint, width: float, text: str) -> "AcadMText":
        """
        添加多行文字（MText）
        
        Args:
            insert_point: 插入点
            width: 文字宽度（0表示自动换行）
            text: 文字内容
            
        Returns:
            AcadMText 对象
        """
        # ezdxf 添加 MText
        from .entities import AcadText  # 简化为 Text
        
        entity = self._msp.add_mtext(
            text=text,
            dxfattribs={
                'insert': (insert_point.x, insert_point.y),
                'width': width if width > 0 else None
            }
        )
        return AcadText(entity)  # 使用 Text 作为替代
    
    # =========================================================================
    # 椭圆和曲线
    # =========================================================================
    
    def AddEllipse(self, center: APoint, major_axis: APoint, 
                   radius_ratio: float) -> "AcadEllipse":
        """
        添加椭圆
        
        Args:
            center: 中心点
            major_axis: 主轴端点（定义长轴方向和长度）
            radius_ratio: 长短轴比例 (短轴/长轴)
            
        Returns:
            AcadEllipse 对象
            
        Examples:
            >>> center = APoint(100, 100, 0)
            >>> major = APoint(150, 100, 0)  # 长轴 50，水平方向
            >>> ellipse = model.AddEllipse(center, major, 0.5)  # 短轴是长轴的一半
        """
        from .entities import AcadEllipse
        
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
    
    def AddSpline(self, points: List[APoint]) -> "AcadSpline":
        """
        添加样条曲线
        
        Args:
            points: 控制点列表
            
        Returns:
            AcadSpline 对象（简化为多段线）
        """
        # ezdxf 使用多段线近似
        return self.AddPolyline(points)
    
    # =========================================================================
    # 填充和图案
    # =========================================================================
    
    def AddHatch(self, pattern_type: int, pattern_name: str, 
                 associativity: bool = True) -> "AcadHatch":
        """
        添加填充图案
        
        Args:
            pattern_type: 
                0 = 预定义图案
                1 = 用户定义
                2 = 自定义
            pattern_name: 图案名称（如 "SOLID", "ANSI31"）
            associativity: 是否关联边界
            
        Returns:
            AcadHatch 对象
            
        Examples:
            >>> hatch = model.AddHatch(0, "SOLID", True)
            >>> hatch.AppendLoop(0, [APoint(0,0), APoint(100,0), APoint(100,100)])
            >>> hatch.Evaluate()
        """
        from .entities import AcadHatch
        
        # ezdxf 创建 hatch
        if pattern_name.upper() == "SOLID":
            entity = self._msp.add_hatch(color=7)
        else:
            entity = self._msp.add_hatch(
                dxfattribs={'pattern_name': pattern_name}
            )
        
        return AcadHatch(entity)
    
    # =========================================================================
    # 矩形和多边形（便捷方法）
    # =========================================================================
    
    def AddRectangle(self, x: float, y: float, width: float, height: float,
                     rotation: float = 0.0) -> "AcadPolyline":
        """
        添加矩形（便捷方法）
        
        Args:
            x: 左下角 X
            y: 左下角 Y
            width: 宽度
            height: 高度
            rotation: 旋转角度（弧度）
            
        Returns:
            AcadPolyline 对象
            
        Examples:
            >>> rect = model.AddRectangle(50, 50, 100, 80)
            >>> rect.Color = 2
            >>> 
            >>> # 旋转矩形
            >>> rect = model.AddRectangle(50, 50, 100, 80, math.pi/4)
        """
        # 计算4个角点
        corners = [
            APoint(x, y, 0),
            APoint(x + width, y, 0),
            APoint(x + width, y + height, 0),
            APoint(x, y + height, 0),
            APoint(x, y, 0),  # 闭合
        ]
        
        pline = self.AddPolyline(corners)
        pline.Closed = True
        
        # 应用旋转
        if rotation != 0:
            center = APoint(x + width / 2, y + height / 2, 0)
            pline.Rotate(center, rotation)
        
        return pline
    
    def AddPolygon(self, center: APoint, radius: float, sides: int,
                   rotation: float = 0.0) -> "AcadPolyline":
        """
        添加正多边形（便捷方法）
        
        Args:
            center: 中心点
            radius: 外接圆半径
            sides: 边数（>= 3）
            rotation: 旋转角度（弧度）
            
        Returns:
            AcadPolyline 对象
            
        Examples:
            >>> # 三角形
            >>> tri = model.AddPolygon(APoint(100, 100, 0), 50, 3)
            >>> 
            >>> # 六边形
            >>> hex = model.AddPolygon(APoint(100, 100, 0), 50, 6)
        """
        if sides < 3:
            raise ValueError("Polygon must have at least 3 sides")
        
        # 计算顶点
        points = []
        angle_step = 2 * math.pi / sides
        
        for i in range(sides):
            angle = i * angle_step + rotation
            x = center.x + radius * math.cos(angle)
            y = center.y + radius * math.sin(angle)
            points.append(APoint(x, y, center.z))
        
        # 闭合
        points.append(points[0])
        
        pline = self.AddPolyline(points)
        pline.Closed = True
        
        return pline
    
    def __repr__(self) -> str:
        """字符串表示"""
        return "ModelSpace()"
