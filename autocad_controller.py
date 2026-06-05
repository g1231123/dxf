"""
AutoCAD Controller - 模仿 pyautocad 的远程控制接口

此类模仿 pyautocad 的 API，但适用于服务端通过 WebSocket 远程控制 AutoCAD
可以在 macOS/Linux 服务端使用，控制 Windows 上的 AutoCAD
"""

from __future__ import annotations

import json
import uuid
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class APoint:
    """模仿 pyautocad.APoint 的坐标点类"""
    x: float
    y: float
    z: float = 0.0
    
    def __iter__(self):
        """支持解包: x, y, z = point"""
        return iter((self.x, self.y, self.z))
    
    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z}
    
    @classmethod
    def from_dict(cls, d: dict) -> "APoint":
        return cls(d["x"], d["y"], d.get("z", 0.0))


class AutoCADController:
    """
    模仿 pyautocad.Autocad 的控制器类
    
    此类提供与 pyautocad 类似的 API，但通过网络/WebSocket 与 AutoCAD 通信
    适用于：
    - macOS/Linux 服务端控制 Windows AutoCAD
    - 分布式部署场景
    - 需要跨平台控制的场景
    """
    
    def __init__(self, websocket_client=None):
        """
        初始化控制器
        
        Args:
            websocket_client: WebSocket 客户端实例，用于发送命令到 AutoCAD
        """
        self._ws = websocket_client
        self._doc_name: Optional[str] = None
        self._shapes: list[dict] = []  # 暂存的图形指令
        
    # =========================================================================
    # 模仿 pyautocad 的核心属性
    # =========================================================================
    
    @property
    def doc(self) -> "DocumentProxy":
        """返回文档代理对象（模仿 acad.doc）"""
        return DocumentProxy(self)
    
    @property
    def model(self) -> "ModelSpaceProxy":
        """返回模型空间代理对象（模仿 acad.model）"""
        return ModelSpaceProxy(self)
    
    @property
    def app(self) -> "ApplicationProxy":
        """返回应用程序代理对象（模仿 acad.app）"""
        return ApplicationProxy(self)
    
    # =========================================================================
    # 图形绘制方法（模仿 pyautocad 的 model.AddXXX 方法）
    # =========================================================================
    
    def AddCircle(self, center: APoint, radius: float) -> "ShapeProxy":
        """
        绘制圆（模仿 model.AddCircle）
        
        Args:
            center: 圆心坐标 (APoint)
            radius: 半径
            
        Returns:
            ShapeProxy: 图形代理对象
        """
        shape_id = f"c{uuid.uuid4().hex[:8]}"
        shape_data = {
            "id": shape_id,
            "type": "circle",
            "geometry": {
                "cx": center.x,
                "cy": center.y,
                "r": radius
            },
            "style": {
                "stroke_color": "#FF0000",
                "fill_color": None
            },
            "layer": "0"
        }
        self._shapes.append(shape_data)
        return ShapeProxy(self, shape_id, shape_data)
    
    def AddArc(self, center: APoint, radius: float, 
               start_angle: float, end_angle: float) -> "ShapeProxy":
        """绘制圆弧（弧度角度）"""
        shape_id = f"a{uuid.uuid4().hex[:8]}"
        shape_data = {
            "id": shape_id,
            "type": "arc",
            "geometry": {
                "cx": center.x,
                "cy": center.y,
                "r": radius,
                "start_angle": start_angle,
                "end_angle": end_angle
            },
            "style": {"stroke_color": "#FF0000"},
            "layer": "0"
        }
        self._shapes.append(shape_data)
        return ShapeProxy(self, shape_id, shape_data)
    
    def AddPolyline(self, points: list) -> "ShapeProxy":
        """
        绘制多段线
        
        Args:
            points: 点列表，可以是 APoint 列表或 VARIANT 数组
        """
        shape_id = f"p{uuid.uuid4().hex[:8]}"
        
        # 处理不同类型的输入
        if isinstance(points, list):
            if len(points) > 0 and isinstance(points[0], APoint):
                # APoint 列表
                coords = []
                for p in points:
                    coords.extend([p.x, p.y, p.z])
            else:
                # 普通数组 [x1,y1,z1, x2,y2,z2, ...]
                coords = points
        else:
            coords = []
        
        # 计算外接矩形作为几何信息
        if len(coords) >= 6:
            xs = coords[0::3]
            ys = coords[1::3]
            x, y = min(xs), min(ys)
            width = max(xs) - x
            height = max(ys) - y
        else:
            x, y, width, height = 0, 0, 0, 0
        
        shape_data = {
            "id": shape_id,
            "type": "rectangle",  # 简化为矩形类型
            "geometry": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "points": coords
            },
            "style": {"stroke_color": "#FF0000"},
            "layer": "0"
        }
        self._shapes.append(shape_data)
        return ShapeProxy(self, shape_id, shape_data)
    
    def AddText(self, text: str, insert_point: APoint, height: float) -> "ShapeProxy":
        """绘制文字"""
        shape_id = f"t{uuid.uuid4().hex[:8]}"
        shape_data = {
            "id": shape_id,
            "type": "text",
            "geometry": {
                "x": insert_point.x,
                "y": insert_point.y
            },
            "style": {
                "text": text,
                "font_size": height,
                "color": "#000000"
            },
            "layer": "0"
        }
        self._shapes.append(shape_data)
        return ShapeProxy(self, shape_id, shape_data)
    
    def AddEllipse(self, center: APoint, major_axis: APoint, 
                   radius_ratio: float) -> "ShapeProxy":
        """绘制椭圆"""
        shape_id = f"e{uuid.uuid4().hex[:8]}"
        rx = abs(major_axis.x - center.x)
        ry = rx * radius_ratio
        shape_data = {
            "id": shape_id,
            "type": "ellipse",
            "geometry": {
                "cx": center.x,
                "cy": center.y,
                "rx": rx,
                "ry": ry
            },
            "style": {"stroke_color": "#FF0000"},
            "layer": "0"
        }
        self._shapes.append(shape_data)
        return ShapeProxy(self, shape_id, shape_data)
    
    # =========================================================================
    # 批量执行方法
    # =========================================================================
    
    def execute(self, websocket: Any = None) -> list[dict]:
        """
        执行所有暂存的绘图指令
        
        Args:
            websocket: WebSocket 连接，如果初始化时已提供则可为 None
            
        Returns:
            执行结果列表
        """
        ws = websocket or self._ws
        if not ws:
            raise RuntimeError("WebSocket client not provided")
        
        # 发送绘制指令到 AutoCAD
        request = {
            "type": "ai_edit",
            "engine": "autocad",
            "output_format": "dxf",
            "shapes": self._shapes
        }
        
        # 这里应该通过 WebSocket 发送
        # ws.send(json.dumps(request))
        
        # 清空已执行的指令
        results = self._shapes.copy()
        self._shapes.clear()
        
        return results
    
    def get_shapes(self) -> list[dict]:
        """获取所有暂存的图形指令（用于手动发送）"""
        return self._shapes.copy()
    
    def clear(self):
        """清空暂存的指令"""
        self._shapes.clear()


# =========================================================================
# 代理类（模仿 pyautocad 的对象结构）
# =========================================================================

class DocumentProxy:
    """文档代理（模仿 acad.doc）"""
    
    def __init__(self, controller: AutoCADController):
        self._ctrl = controller
        self._layers: dict[str, "LayerProxy"] = {}
    
    @property
    def Name(self) -> str:
        """返回文档名称"""
        return self._ctrl._doc_name or "Drawing1.dwg"
    
    @property
    def Layers(self) -> "LayersCollection":
        """返回图层集合"""
        return LayersCollection(self._ctrl)
    
    @property
    def ActiveLayer(self) -> "LayerProxy":
        """当前图层"""
        return LayerProxy(self._ctrl, "0")
    
    def SaveAs(self, filename: str, format_code: int = 24):
        """另存为（模仿 doc.SaveAs）"""
        # 24 = DWG, 25 = DXF
        format_type = "dwg" if format_code == 24 else "dxf"
        # 这里应该发送保存指令
        pass


class ModelSpaceProxy:
    """模型空间代理（模仿 acad.model）"""
    
    def __init__(self, controller: AutoCADController):
        self._ctrl = controller
    
    # 委托给 controller 的绘图方法
    def AddCircle(self, center: APoint, radius: float) -> "ShapeProxy":
        return self._ctrl.AddCircle(center, radius)
    
    def AddArc(self, center: APoint, radius: float, 
               start_angle: float, end_angle: float) -> "ShapeProxy":
        return self._ctrl.AddArc(center, radius, start_angle, end_angle)
    
    def AddPolyline(self, points: list) -> "ShapeProxy":
        return self._ctrl.AddPolyline(points)
    
    def AddText(self, text: str, insert_point: APoint, height: float) -> "ShapeProxy":
        return self._ctrl.AddText(text, insert_point, height)
    
    def AddEllipse(self, center: APoint, major_axis: APoint, 
                   radius_ratio: float) -> "ShapeProxy":
        return self._ctrl.AddEllipse(center, major_axis, radius_ratio)


class ApplicationProxy:
    """应用程序代理（模仿 acad.app）"""
    
    def __init__(self, controller: AutoCADController):
        self._ctrl = controller
    
    @property
    def Documents(self) -> "DocumentsCollection":
        return DocumentsCollection(self._ctrl)


class ShapeProxy:
    """图形对象代理（模仿 circle, pline 等对象）"""
    
    def __init__(self, controller: AutoCADController, shape_id: str, data: dict):
        self._ctrl = controller
        self._id = shape_id
        self._data = data
        self._handle = shape_id  # 模仿 Handle 属性
    
    @property
    def Handle(self) -> str:
        """对象句柄（模仿 obj.Handle）"""
        return self._handle
    
    @property
    def Layer(self) -> str:
        """图层属性"""
        return self._data.get("layer", "0")
    
    @Layer.setter
    def Layer(self, value: str):
        self._data["layer"] = value
    
    @property
    def Color(self) -> int:
        """颜色属性"""
        color_map = {
            "#FF0000": 1, "#FFFF00": 2, "#00FF00": 3,
            "#00FFFF": 4, "#0000FF": 5, "#FF00FF": 6,
            "#FFFFFF": 7
        }
        return color_map.get(self._data.get("style", {}).get("stroke_color"), 1)
    
    @Color.setter
    def Color(self, value: int):
        color_map = {
            1: "#FF0000", 2: "#FFFF00", 3: "#00FF00",
            4: "#00FFFF", 5: "#0000FF", 6: "#FF00FF", 7: "#FFFFFF"
        }
        if "style" not in self._data:
            self._data["style"] = {}
        self._data["style"]["stroke_color"] = color_map.get(value, "#FF0000")
    
    @property
    def Closed(self) -> bool:
        """是否闭合（多段线用）"""
        return self._data.get("geometry", {}).get("closed", False)
    
    @Closed.setter
    def Closed(self, value: bool):
        if "geometry" not in self._data:
            self._data["geometry"] = {}
        self._data["geometry"]["closed"] = value
    
    def Rotate(self, base_point: APoint, angle: float):
        """旋转（弧度角度）"""
        import math
        # 这里应该更新几何坐标
        self._data["geometry"]["rotation"] = math.degrees(angle)
    
    def Move(self, from_point: APoint, to_point: APoint):
        """移动"""
        dx = to_point.x - from_point.x
        dy = to_point.y - from_point.y
        geo = self._data.get("geometry", {})
        if "cx" in geo:
            geo["cx"] += dx
            geo["cy"] += dy
        if "x" in geo:
            geo["x"] += dx
            geo["y"] += dy
    
    def ScaleEntity(self, base_point: APoint, scale: float):
        """缩放"""
        geo = self._data.get("geometry", {})
        if "r" in geo:
            geo["r"] *= scale
        if "width" in geo:
            geo["width"] *= scale
        if "height" in geo:
            geo["height"] *= scale


class LayerProxy:
    """图层代理"""
    
    def __init__(self, controller: AutoCADController, name: str):
        self._ctrl = controller
        self._name = name
    
    @property
    def Name(self) -> str:
        return self._name
    
    @property
    def Color(self) -> int:
        return 7
    
    @Color.setter
    def Color(self, value: int):
        pass  # 模拟设置


class LayersCollection:
    """图层集合"""
    
    def __init__(self, controller: AutoCADController):
        self._ctrl = controller
    
    def Add(self, name: str) -> LayerProxy:
        """添加图层"""
        return LayerProxy(self._ctrl, name)
    
    def Item(self, name: str) -> LayerProxy:
        """获取图层"""
        return LayerProxy(self._ctrl, name)


class DocumentsCollection:
    """文档集合"""
    
    def __init__(self, controller: AutoCADController):
        self._ctrl = controller
    
    def Open(self, filename: str) -> DocumentProxy:
        """打开文档"""
        return DocumentProxy(self._ctrl)
    
    def Add(self) -> DocumentProxy:
        """新建文档"""
        return DocumentProxy(self._ctrl)


# =========================================================================
# 辅助函数
# =========================================================================

def hex_to_aci(hex_color: str) -> int:
    """HEX 颜色转 AutoCAD ACI 颜色号"""
    color_map = {
        "#FF0000": 1, "#FFFF00": 2, "#00FF00": 3, "#00FFFF": 4,
        "#0000FF": 5, "#FF00FF": 6, "#FFFFFF": 7, "#808080": 8,
        "#C0C0C0": 9, "#000000": 250,
    }
    return color_map.get(hex_color.upper(), 7)


def aci_to_hex(aci: int) -> str:
    """AutoCAD ACI 颜色号转 HEX"""
    color_map = {
        1: "#FF0000", 2: "#FFFF00", 3: "#00FF00", 4: "#00FFFF",
        5: "#0000FF", 6: "#FF00FF", 7: "#FFFFFF", 8: "#808080",
        9: "#C0C0C0", 250: "#000000"
    }
    return color_map.get(aci, "#FFFFFF")


# =========================================================================
# 使用示例
# =========================================================================

if __name__ == "__main__":
    # 示例：使用 AutoCADController
    
    # 初始化（实际使用时需要提供 WebSocket 客户端）
    controller = AutoCADController()
    
    # 获取模型空间（模仿 acad.model）
    model = controller.model
    
    # 绘制圆（模仿 model.AddCircle）
    center = APoint(100, 100, 0)
    circle = model.AddCircle(center, 50)
    circle.Color = 1  # 红色
    circle.Layer = "0"
    print(f"Created circle: {circle.Handle}")
    
    # 绘制矩形
    from autocad_controller import APoint
    rect = model.AddPolyline([
        APoint(50, 50, 0),
        APoint(150, 50, 0),
        APoint(150, 100, 0),
        APoint(50, 100, 0),
        APoint(50, 50, 0)
    ])
    rect.Closed = True
    rect.Color = 2  # 黄色
    
    # 添加文字
    text = model.AddText("Hello", APoint(100, 100, 0), 10)
    text.Color = 3  # 绿色
    
    # 获取所有图形数据
    shapes = controller.get_shapes()
    print(f"Total shapes: {len(shapes)}")
    print(json.dumps(shapes, indent=2, ensure_ascii=False))
