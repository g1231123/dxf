# -*- coding: utf-8 -*-
import os
import sys
import ezdxf
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, List, Optional, Union


class DXFToImageConverter:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.min_x = float('inf')
        self.min_y = float('inf')
        self.max_x = float('-inf')
        self.max_y = float('-inf')
        self.image = None
        self.pil_image = None
        self.draw = None
        self.scale = 1.0
        self.padding = 40
        self.geometric_entities = []
        self.text_entities = []

    def read_dxf(self, file_path: str) -> bool:
        """读取DXF文件"""
        try:
            self.doc = ezdxf.readfile(file_path)
            self.msp = self.doc.modelspace()
            print(f"成功读取DXF文件，找到 {len(self.msp)} 个实体")

            # 分离几何实体和文字实体
            self.separate_entities()

            # 计算包含文字的图形边界
            self.calculate_bounds()
            return True
        except Exception as e:
            print(f"读取DXF文件时出错: {e}")
            return False

    def separate_entities(self):
        """分离几何实体和文字实体"""
        self.geometric_entities = []
        self.text_entities = []

        for entity in self.msp:
            entity_type = entity.dxftype()
            if entity_type in ['TEXT', 'MTEXT']:
                self.text_entities.append(entity)
            else:
                self.geometric_entities.append(entity)

        print(f"找到 {len(self.geometric_entities)} 个几何实体和 {len(self.text_entities)} 个文字实体")

    def calculate_bounds(self):
        """计算包含文字的DXF图形边界"""
        all_entities = self.geometric_entities + self.text_entities

        for entity in all_entities:
            try:
                if hasattr(entity, 'get_bbox'):
                    bbox = entity.get_bbox()
                    if bbox is not None and isinstance(bbox, (list, tuple, np.ndarray)) and len(bbox) >= 2:
                        try:
                            # 安全提取坐标点（兼容标量、数组、嵌套数组）
                            def extract_coord(value):
                                if isinstance(value, np.ndarray):
                                    return float(value.flat[0]) if value.size > 0 else 0.0
                                elif isinstance(value, (list, tuple)):
                                    return float(value[0])
                                else:
                                    return float(value)

                            x1 = extract_coord(bbox[0][0])
                            y1 = extract_coord(bbox[0][1])
                            x2 = extract_coord(bbox[1][0])
                            y2 = extract_coord(bbox[1][1])

                            self.update_bounds(x1, y1)
                            self.update_bounds(x2, y2)
                        except Exception as e:
                            print(f"警告: 解析 bbox 坐标失败: {e}, bbox={bbox}")
                            continue

                # 处理特定实体类型
                entity_type = entity.dxftype()
                if entity_type == 'LINE':
                    self.update_bounds(entity.dxf.start[0], entity.dxf.start[1])
                    self.update_bounds(entity.dxf.end[0], entity.dxf.end[1])
                elif entity_type == 'CIRCLE':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    self.update_bounds(center[0] - radius, center[1] - radius)
                    self.update_bounds(center[0] + radius, center[1] + radius)
                elif entity_type == 'ARC':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    self.update_bounds(center[0] - radius, center[1] - radius)
                    self.update_bounds(center[0] + radius, center[1] + radius)
                elif entity_type in ['TEXT', 'MTEXT']:
                    self.handle_text_bounds(entity)
            except Exception as e:
                print(f"警告: 处理实体时出错: {e}")
                continue

        # 设置默认边界
        if (self.min_x == float('inf') or self.max_x == float('-inf') or
                self.min_y == float('inf') or self.max_y == float('-inf')):
            self.min_x, self.min_y = 0, 0
            self.max_x, self.max_y = 100, 100

        # 添加边距
        margin = max((self.max_x - self.min_x) * 0.05, 1.0)
        self.min_x -= margin
        self.max_x += margin
        self.min_y -= margin
        self.max_y += margin

        print(f"图形边界: X({self.min_x:.2f}, {self.max_x:.2f}), Y({self.min_y:.2f}, {self.max_y:.2f})")

    def handle_text_bounds(self, text_entity):
        """计算文字实体的边界（安全版）"""
        try:
            bbox = text_entity.get_bbox()
            if bbox is not None and isinstance(bbox, (list, tuple, np.ndarray)) and len(bbox) >= 2:
                def extract_coord(value):
                    if isinstance(value, np.ndarray):
                        return float(value.flat[0]) if value.size > 0 else 0.0
                    elif isinstance(value, (list, tuple)):
                        return float(value[0])
                    else:
                        return float(value)

                x1 = extract_coord(bbox[0][0])
                y1 = extract_coord(bbox[0][1])
                x2 = extract_coord(bbox[1][0])
                y2 = extract_coord(bbox[1][1])

                self.update_bounds(x1, y1)
                self.update_bounds(x2, y2)
        except Exception as e:
            # 备用方案：使用插入点
            if text_entity.dxftype() == 'TEXT':
                try:
                    insertion = text_entity.dxf.insert
                    self.update_bounds(insertion[0], insertion[1])
                except Exception as fallback_err:
                    print(f"警告: 文字实体边界处理失败，备用方案也无效: {fallback_err}")

    def update_bounds(self, x: float, y: float):
        """更新边界坐标"""
        # 确保处理数组类型的坐标
        if isinstance(x, np.ndarray):
            x = x.flatten()[0] if x.size > 0 else x
        if isinstance(y, np.ndarray):
            y = y.flatten()[0] if y.size > 0 else y

        self.min_x = min(self.min_x, float(x))
        self.min_y = min(self.min_y, float(y))
        self.max_x = max(self.max_x, float(x))
        self.max_y = max(self.max_y, float(y))

    def calculate_optimal_size(self, max_dimension: int = 1200) -> Tuple[int, int]:
        """根据内容宽高比计算最佳图像尺寸"""
        dxf_width = self.max_x - self.min_x
        dxf_height = self.max_y - self.min_y

        if dxf_width <= 0 or dxf_height <= 0:
            return 800, 600

        aspect_ratio = dxf_width / dxf_height

        if aspect_ratio > 1:  # 宽大于高
            width = min(max_dimension, int(max_dimension * 1.2))
            height = int(width / aspect_ratio)
        else:  # 高大于宽或正方形
            height = min(max_dimension, int(max_dimension * 1.2))
            width = int(height * aspect_ratio)

        # 确保最小尺寸
        width = max(400, width)
        height = max(300, height)

        return width, height

    def create_image(self, width: Optional[int] = None, height: Optional[int] = None,
                     bg_color: Tuple[int, int, int] = (255, 255, 255),
                     line_color: Tuple[int, int, int] = (0, 0, 0),
                     text_color: Tuple[int, int, int] = (0, 0, 0),
                     line_thickness: int = 1) -> np.ndarray:
        """创建图像并绘制带文字支持的DXF实体"""

        # 如果未指定尺寸，计算最佳尺寸
        if width is None or height is None:
            width, height = self.calculate_optimal_size()
        print(f"自动计算的图像尺寸: {width} x {height}")

        # 计算缩放比例以适应内容
        dxf_width = self.max_x - self.min_x
        dxf_height = self.max_y - self.min_y

        if dxf_width > 0 and dxf_height > 0:
            scale_x = (width - 2 * self.padding) / dxf_width
            scale_y = (height - 2 * self.padding) / dxf_height
            self.scale = min(scale_x, scale_y)
            print(f"缩放比例: {self.scale:.4f}")
        else:
            self.scale = 1.0

        # 首先创建OpenCV图像用于几何实体
        self.image = np.ones((height, width, 3), dtype=np.uint8)
        self.image[:] = bg_color

        # 首先绘制几何实体
        print("正在绘制几何实体...")
        for entity in self.geometric_entities:
            self.draw_geometric_entity(entity, line_color, line_thickness)

        # 转换为PIL图像用于文字渲染
        print("转换为PIL图像进行文字渲染...")
        self.pil_image = Image.fromarray(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB))
        self.draw = ImageDraw.Draw(self.pil_image)

        # 绘制文字实体
        print("正在绘制文字实体...")
        for entity in self.text_entities:
            self.draw_text_entity(entity, text_color)

        # 转换回OpenCV格式
        self.image = cv2.cvtColor(np.array(self.pil_image), cv2.COLOR_RGB2BGR)

        return self.image

    def draw_geometric_entity(self, entity, color: Tuple[int, int, int], thickness: int):
        """绘制单个几何实体"""
        try:
            entity_type = entity.dxftype()
            if entity_type == 'LINE':
                self.draw_line(entity, color, thickness)
            elif entity_type == 'CIRCLE':
                self.draw_circle(entity, color, thickness)
            elif entity_type == 'ARC':
                self.draw_arc(entity, color, thickness)
            elif entity_type == 'POINT':
                self.draw_point(entity, color, thickness)
            elif entity_type == 'LWPOLYLINE':
                self.draw_lwpolyline(entity, color, thickness)
            elif entity_type == 'POLYLINE':
                self.draw_polyline(entity, color, thickness)
            elif entity_type == 'SPLINE':
                self.draw_spline(entity, color, thickness)
            elif entity_type == 'ELLIPSE':
                self.draw_ellipse(entity, color, thickness)
            else:
                print(f"警告: 未处理的几何实体类型: {entity_type}")

        except Exception as e:
            print(f"绘制几何实体 {entity.dxftype()} 时出错: {e}")

    def draw_text_entity(self, text_entity, color: Tuple[int, int, int]):
        """使用PIL绘制文字实体"""
        try:
            if text_entity.dxftype() == 'TEXT':
                self.draw_single_text(text_entity, color)
            elif text_entity.dxftype() == 'MTEXT':
                self.draw_multi_text(text_entity, color)
        except Exception as e:
            print(f"绘制文字时出错: {e}")

    def draw_single_text(self, text_entity, color: Tuple[int, int, int]):
        """绘制单行文字"""
        try:
            text_content = text_entity.dxf.text
            if not text_content or not text_content.strip():
                return

            insertion = text_entity.dxf.insert
            height = text_entity.dxf.height

            # 转换为图像坐标
            x, y = self.dxf_to_image_coords(insertion[0], insertion[1])

            # 计算字体大小（缩放后）
            font_size = max(8, int(height * self.scale * 0.8))  # 稍小一些以适应更好

            # 尝试不同的字体以支持中文
            font_paths = [
                "simhei.ttf",  # Windows中文字体
                "msyh.ttf",  # 微软雅黑
                "arialuni.ttf",  # Arial Unicode
                "Arial.ttf"  # 常规Arial
            ]

            font = None
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except:
                    continue

            if font is None:
                try:
                    font = ImageFont.load_default()
                    print("使用默认字体（中文可能无法正确显示）")
                except:
                    print("没有可用的字体进行文字渲染")
                    return

            # 绘制文字
            self.draw.text((x, y), text_content, fill=color, font=font)
            print(f"文字已绘制: '{text_content}' 位于 ({x}, {y})")

        except Exception as e:
            print(f"绘制单行文字时出错: {e}")

    def draw_multi_text(self, mtext_entity, color: Tuple[int, int, int]):
        """绘制多行文字"""
        try:
            text_content = mtext_entity.text
            if not text_content or not text_content.strip():
                return

            insertion = mtext_entity.dxf.insert
            height = mtext_entity.dxf.char_height

            # 转换为图像坐标
            x, y = self.dxf_to_image_coords(insertion[0], insertion[1])

            # 计算字体大小
            font_size = max(8, int(height * self.scale * 0.8))

            # 尝试不同的字体
            font_paths = ["simhei.ttf", "msyh.ttf", "arialuni.ttf", "Arial.ttf"]
            font = None
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except:
                    continue

            if font is None:
                try:
                    font = ImageFont.load_default()
                except:
                    return

            # 分割文本为行并绘制
            lines = text_content.split('\\P')  # MTEXT使用\P作为行分隔符
            for i, line in enumerate(lines):
                if line and line.strip():
                    y_offset = i * font_size * 1.5  # 行间距
                    self.draw.text((x, y + y_offset), line, fill=color, font=font)
                    print(f"多行文字行已绘制: '{line}'")

        except Exception as e:
            print(f"绘制多行文字时出错: {e}")

    def dxf_to_image_coords(self, x: Union[float, np.ndarray], y: Union[float, np.ndarray]) -> Tuple[float, float]:
        """将DXF坐标转换为图像坐标（处理标量/数组输入，确保返回标量）"""
        # 处理NumPy数组类型的坐标
        if isinstance(x, np.ndarray):
            # 展平数组并取第一个有效值（避免空数组）
            x_flat = x.flatten()
            x = x_flat[0] if x_flat.size > 0 else 0.0
        if isinstance(y, np.ndarray):
            y_flat = y.flatten()
            y = y_flat[0] if y_flat.size > 0 else 0.0

        # 强制转换为标量浮点数
        x = float(x)
        y = float(y)

        # 坐标转换逻辑
        img_x = (x - self.min_x) * self.scale + self.padding
        img_y = (self.max_y - y) * self.scale + self.padding  # Y轴翻转
        return int(round(img_x)), int(round(img_y))  # 确保返回整数坐标

    def draw_line(self, line, color: Tuple[int, int, int], thickness: int):
        """绘制直线"""
        start = line.dxf.start
        end = line.dxf.end
        start_x, start_y = self.dxf_to_image_coords(start[0], start[1])
        end_x, end_y = self.dxf_to_image_coords(end[0], end[1])
        cv2.line(self.image, (start_x, start_y), (end_x, end_y), color, thickness)

    def draw_circle(self, circle, color: Tuple[int, int, int], thickness: int):
        """绘制圆形"""
        center = circle.dxf.center
        radius = circle.dxf.radius
        center_x, center_y = self.dxf_to_image_coords(center[0], center[1])
        radius_px = int(round(radius * self.scale))
        cv2.circle(self.image, (center_x, center_y), radius_px, color, thickness)

    def draw_arc(self, arc, color: Tuple[int, int, int], thickness: int):
        """绘制圆弧"""
        center = arc.dxf.center
        radius = arc.dxf.radius
        start_angle = arc.dxf.start_angle
        end_angle = arc.dxf.end_angle

        center_x, center_y = self.dxf_to_image_coords(center[0], center[1])
        radius_px = int(round(radius * self.scale))

        # 绘制圆弧
        cv2.ellipse(self.image, (center_x, center_y), (radius_px, radius_px), 0,
                    start_angle, end_angle, color, thickness)

    def draw_point(self, point, color: Tuple[int, int, int], thickness: int):
        """绘制点"""
        location = point.dxf.location
        x, y = self.dxf_to_image_coords(location[0], location[1])
        cv2.circle(self.image, (x, y), max(2, thickness), color, -1)

    def draw_lwpolyline(self, polyline, color: Tuple[int, int, int], thickness: int):
        """绘制轻量多段线"""
        points = list(polyline.get_points())
        if len(points) < 2:
            return

        image_points = []
        for point in points:
            x, y = self.dxf_to_image_coords(point[0], point[1])
            image_points.append((x, y))

        pts = np.array(image_points, np.int32)
        pts = pts.reshape((-1, 1, 2))

        if polyline.closed:
            cv2.polylines(self.image, [pts], True, color, thickness)
        else:
            cv2.polylines(self.image, [pts], False, color, thickness)

    def draw_polyline(self, polyline, color: Tuple[int, int, int], thickness: int):
        """绘制多段线"""
        points = list(polyline.points())
        if len(points) < 2:
            return

        image_points = []
        for point in points:
            x, y = self.dxf_to_image_coords(point[0], point[1])
            image_points.append((x, y))

        for i in range(len(image_points) - 1):
            cv2.line(self.image, image_points[i], image_points[i + 1], color, thickness)

    def draw_spline(self, spline, color: Tuple[int, int, int], thickness: int):
        """绘制样条曲线"""
        try:
            # 沿着样条曲线采样点
            points = list(spline.approximate(segments=20))
            if len(points) < 2:
                return

            image_points = []
            for point in points:
                x, y = self.dxf_to_image_coords(point[0], point[1])
                image_points.append((x, y))

            # 作为多段线绘制
            for i in range(len(image_points) - 1):
                cv2.line(self.image, image_points[i], image_points[i + 1], color, thickness)
        except:
            # 回退到控制点
            control_points = list(spline.get_control_points())
            if len(control_points) >= 2:
                image_points = []
                for point in control_points:
                    x, y = self.dxf_to_image_coords(point[0], point[1])
                    image_points.append((x, y))

                for i in range(len(image_points) - 1):
                    cv2.line(self.image, image_points[i], image_points[i + 1], color, thickness)

    def draw_ellipse(self, ellipse, color: Tuple[int, int, int], thickness: int):
        """绘制椭圆"""
        try:
            bbox = ellipse.get_bbox()
            # 明确检查边界框有效性
            if bbox is not None and len(bbox) >= 2:
                # 处理可能的数组类型坐标
                x1 = bbox[0][0] if not isinstance(bbox[0][0], np.ndarray) else bbox[0][0].flatten()[0]
                y1 = bbox[0][1] if not isinstance(bbox[0][1], np.ndarray) else bbox[0][1].flatten()[0]
                x2 = bbox[1][0] if not isinstance(bbox[1][0], np.ndarray) else bbox[1][0].flatten()[0]
                y2 = bbox[1][1] if not isinstance(bbox[1][1], np.ndarray) else bbox[1][1].flatten()[0]

                top_left = self.dxf_to_image_coords(x1, y1)
                bottom_right = self.dxf_to_image_coords(x2, y2)

                center_x = (top_left[0] + bottom_right[0]) // 2
                center_y = (top_left[1] + bottom_right[1]) // 2
                axis_x = (bottom_right[0] - top_left[0]) // 2
                axis_y = (bottom_right[1] - top_left[1]) // 2

                # 确保轴长为正数
                axis_x = max(1, axis_x)
                axis_y = max(1, axis_y)

                cv2.ellipse(self.image, (center_x, center_y), (axis_x, axis_y), 0, 0, 360, color, thickness)
        except Exception as e:
            print(f"绘制椭圆时出错: {e}")


def convert_dxf_to_image(dxf_file_path: str,
                         output_file_path: str = None,
                         width: Optional[int] = None,
                         height: Optional[int] = None,
                         bg_color: Tuple[int, int, int] = (255, 255, 255),
                         line_color: Tuple[int, int, int] = (0, 0, 0),
                         text_color: Tuple[int, int, int] = (0, 0, 0),
                         line_thickness: int = 1,
                         display_image: bool = False,
                         max_display_size: int = 1200) -> Optional[np.ndarray]:
    """
    将DXF文件转换为图像
    """
    print("DXF转图像转换器")
    print("=" * 30)

    # 检查文件是否存在
    if not os.path.isfile(dxf_file_path):
        print(f"错误: DXF文件不存在! {dxf_file_path}")
        return None

    # 检查PIL是否可用
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("错误: 需要PIL/Pillow库进行文字渲染。")
        print("请使用以下命令安装: pip install Pillow")
        return None

    # 创建转换器
    converter = DXFToImageConverter()

    # 读取DXF文件
    if not converter.read_dxf(dxf_file_path):
        return None

    # 创建图像
    print("正在创建图像...")
    try:
        image = converter.create_image(
            width=width,
            height=height,
            bg_color=bg_color,
            line_color=line_color,
            text_color=text_color,
            line_thickness=line_thickness
        )
    except Exception as e:
        print(f"创建图像时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

    # 保存图像
    if output_file_path:
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_file_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            # 中文路径安全写盘
            ext = os.path.splitext(output_file_path)[-1] or '.png'
            ok, buf = cv2.imencode(ext, image)
            if ok:
                with open(output_file_path, 'wb') as f:
                    f.write(buf.tobytes())
                print(f"图像已保存到: {output_file_path}")
            else:
                print(f"❌ imencode 失败，未写入 {output_file_path}")
        except Exception as e:
            print(f"保存图像时出错: {e}")
            return None

    print(f"最终图像尺寸: {image.shape[1]} x {image.shape[0]}")

    return image


# 保留原有的main函数用于向后兼容
def main():
    """主函数"""
    # 在这里直接设置文件路径
    dxf_file_path = "./result/刘家沟大桥_处理后.dxf"  # 修改为你的DXF文件路径
    output_file_path = "output6.png"  # 输出图像文件路径

    convert_dxf_to_image(
        dxf_file_path=dxf_file_path,
        output_file_path=output_file_path,
        line_thickness=1,
        display_image=False
    )


if __name__ == "__main__":
    main()