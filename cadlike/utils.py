"""
CadLike 工具函数
"""

import math
from typing import Union, Tuple, Optional


def hex_to_aci(hex_color: str) -> int:
    """
    HEX 颜色转 AutoCAD ACI 颜色索引
    
    Args:
        hex_color: HEX 颜色字符串，如 "#FF0000"
        
    Returns:
        ACI 颜色索引 (1-255)
        
    Examples:
        >>> hex_to_aci("#FF0000")
        1
        >>> hex_to_aci("#00FF00")
        3
    """
    from .constants import HEX_TO_ACI
    return HEX_TO_ACI.get(hex_color.upper(), 7)


def aci_to_hex(aci: int) -> str:
    """
    AutoCAD ACI 颜色索引转 HEX
    
    Args:
        aci: ACI 颜色索引 (1-255)
        
    Returns:
        HEX 颜色字符串
        
    Examples:
        >>> aci_to_hex(1)
        '#FF0000'
        >>> aci_to_hex(3)
        '#00FF00'
    """
    from .constants import ACI_TO_HEX
    return ACI_TO_HEX.get(aci, "#FFFFFF")


def rgb_to_aci(r: int, g: int, b: int) -> int:
    """
    RGB 颜色转最接近的 ACI 颜色
    
    Args:
        r: 红色 (0-255)
        g: 绿色 (0-255)
        b: 蓝色 (0-255)
        
    Returns:
        最接近的 ACI 颜色索引
    """
    from .constants import ACI_COLOR_MAP
    
    min_distance = float('inf')
    closest_aci = 7
    
    for aci, (cr, cg, cb) in ACI_COLOR_MAP.items():
        distance = math.sqrt((r - cr)**2 + (g - cg)**2 + (b - cb)**2)
        if distance < min_distance:
            min_distance = distance
            closest_aci = aci
    
    return closest_aci


def aci_to_rgb(aci: int) -> Tuple[int, int, int]:
    """
    ACI 颜色索引转 RGB
    
    Args:
        aci: ACI 颜色索引
        
    Returns:
        RGB 元组 (r, g, b)
    """
    from .constants import ACI_COLOR_MAP
    return ACI_COLOR_MAP.get(aci, (255, 255, 255))


def degrees_to_radians(degrees: float) -> float:
    """
    角度转弧度
    
    Args:
        degrees: 角度值
        
    Returns:
        弧度值
        
    Examples:
        >>> degrees_to_radians(90)
        1.5707963267948966
        >>> degrees_to_radians(180)
        3.141592653589793
    """
    return degrees * math.pi / 180.0


def radians_to_degrees(radians: float) -> float:
    """
    弧度转角度
    
    Args:
        radians: 弧度值
        
    Returns:
        角度值
        
    Examples:
        >>> radians_to_degrees(math.pi / 2)
        90.0
        >>> radians_to_degrees(math.pi)
        180.0
    """
    return radians * 180.0 / math.pi


def normalize_angle(angle: float) -> float:
    """
    规范化角度到 0-360 度范围
    
    Args:
        angle: 输入角度（度）
        
    Returns:
        规范化后的角度（0-360）
    """
    while angle < 0:
        angle += 360
    while angle >= 360:
        angle -= 360
    return angle


def calculate_distance(x1: float, y1: float, z1: float,
                     x2: float, y2: float, z2: float) -> float:
    """
    计算两点间距离
    
    Args:
        x1, y1, z1: 第一点坐标
        x2, y2, z2: 第二点坐标
        
    Returns:
        距离值
    """
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)


def calculate_area(points: list) -> float:
    """
    计算多边形面积（使用 Shoelace 公式）
    
    Args:
        points: 点列表，每个点是 (x, y) 元组或 APoint
        
    Returns:
        面积值
    """
    if len(points) < 3:
        return 0.0
    
    # 统一转换为元组
    pts = []
    for p in points:
        if hasattr(p, 'x'):
            pts.append((p.x, p.y))
        else:
            pts.append((p[0], p[1]))
    
    # 确保闭合
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    
    # Shoelace 公式
    area = 0.0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i+1][1]
        area -= pts[i+1][0] * pts[i][1]
    
    return abs(area) / 2.0


def calculate_centroid(points: list) -> Tuple[float, float]:
    """
    计算多边形质心
    
    Args:
        points: 点列表
        
    Returns:
        (cx, cy) 质心坐标
    """
    if len(points) == 0:
        return (0.0, 0.0)
    
    # 统一转换为坐标
    xs = []
    ys = []
    for p in points:
        if hasattr(p, 'x'):
            xs.append(p.x)
            ys.append(p.y)
        else:
            xs.append(p[0])
            ys.append(p[1])
    
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def format_point(x: float, y: float, z: float = 0.0, 
                 precision: int = 6) -> str:
    """
    格式化点坐标为字符串
    
    Args:
        x, y, z: 坐标值
        precision: 小数精度
        
    Returns:
        格式化字符串
    """
    if z == 0.0:
        return f"({x:.{precision}f}, {y:.{precision}f})"
    return f"({x:.{precision}f}, {y:.{precision}f}, {z:.{precision}f})"


def parse_point_string(point_str: str) -> Optional[Tuple[float, float, float]]:
    """
    从字符串解析点坐标
    
    Args:
        point_str: 点字符串，如 "(100.0, 200.0, 0.0)"
        
    Returns:
        (x, y, z) 元组或 None
    """
    try:
        # 移除括号
        point_str = point_str.strip().strip('()')
        parts = [float(p.strip()) for p in point_str.split(',')]
        
        if len(parts) == 2:
            return (parts[0], parts[1], 0.0)
        elif len(parts) >= 3:
            return (parts[0], parts[1], parts[2])
    except (ValueError, IndexError):
        pass
    
    return None
