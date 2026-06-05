import ezdxf
import math
import numpy as np
import pandas as pd
from datetime import datetime
import os  # 用于路径操作
import logging
import json
import ast
from ezdxf.addons.drawing.properties import LayoutProperties
import inspect
import re
from ezdxf import units

from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec3, Z_AXIS
from ezdxf import const

print(f"EZDXF Version: {ezdxf.__version__}")


class CustomFormatter(logging.Formatter):
    """自定义 Formatter，为不同级别的日志添加颜色"""

    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'  # 可以为 WARNING 添加
    RESET = '\033[0m'

    # 定义日志格式字符串，这里我们不在格式字符串中直接包含颜色代码
    # 颜色将在 format 方法中根据级别动态添加
    # format_str = '%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s' # 这是您之前的格式
    format_str = '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - L%(lineno)d - %(message)s'  # <---- 修改：使用更详细的格式，包括logger名称和行号

    # 为不同级别定义不同的格式，包含颜色
    FORMATS = {
        logging.DEBUG: GREEN + format_str + RESET,
        logging.INFO: BLACK + format_str + RESET,  # PyCharm 默认背景是暗色，黑色可能看不清，可以考虑默认颜色或浅灰色
        # 如果PyCharm是浅色背景，黑色是OK的。
        # 或者用 RESET 直接使用终端默认颜色 for INFO
        # logging.INFO: format_str, # 如果黑色看不清，尝试不加颜色，使用终端默认
        logging.WARNING: YELLOW + format_str + RESET,
        logging.ERROR: RED + format_str + RESET,
        logging.CRITICAL: RED + format_str + RESET  # CRITICAL 也用红色
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.format_str)  # 获取对应级别的格式，否则用默认
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')  # 使用ISO 8601日期格式
        return formatter.format(record)


SHAPE_SHEET_MAP = {
    "line": {"sheet_name": "Lines", "headers": ["ID", "Start_X", "Start_Y", "End_X", "End_Y", "Layer_Name"]},
    "circle": {"sheet_name": "Circles", "headers": ["ID", "Center_X", "Center_Y", "Radius", "Layer_Name"]},
    "arc": {"sheet_name": "Arcs",
            "headers": ["ID", "Center_X", "Center_Y", "Radius", "Start_Angle", "Total_Angle", "Layer_Name"]},
    "Curves": {"sheet_name": "Curves",
               "headers": ["ID", "Curve_Type", "a", "b", "c", "d", "Start_X", "End_X", "Layer_Name"]},
    "polyline": {"sheet_name": "Polylines", "headers": ["Vertices", "LayerName"]},
    "hatch_circle": {"sheet_name": "圆形填充",
                     "headers": ["ID", "Vertices", "PatternName", "Scale", "Rotation", "LayerName"]},
    "hatch_quad": {"sheet_name": "四边形填充",
                   "headers": ["ID", "Vertices", "PatternName", "Scale", "Rotation", "LayerName"]},
    "annotation": {"sheet_name": "Annotations",
                   "headers": ["ID", "标注类型", "圆心X", "圆心Y", "半径", "文字位置X", "文字位置Y", "Rotation"]},
    "add_radius_dimension": {"sheet_name": "add_radius_dimension",
                             "headers": ["ID", "Dimension_Type", "Center_X", "Center_Y", "Radius", "Text_Position_X",
                                         "Text_Position_Y"]},
    "add_length_dimension": {"sheet_name": "add_length_dimension",
                             "headers": ["标注类型", "起始点X", "起始点Y", "结束点X", "结束点Y", "文字位置X", "文字位置Y", "字体大小", "颜色", "文字样式",
                                         "图层名称", "方向", "标注精度", "延伸线长度", "箭头样式", "箭头大小", "标注方向"]},
    "spline": {"sheet_name": "Splines", "headers": ["ID", "Points_JSON", "Layer_Name"]},
    "angular_dimension": {"sheet_name": "AngularDimensions",
                          "headers": ["ID", "Layer_Name", "DimStyle_Name", "Color",
                                      "Text_Style", "Text_Height", "Arrow_Size", "Precision",
                                      "Center_X", "Center_Y", "Center_Z",
                                      "P1_X", "P1_Y", "P1_Z",
                                      "P2_X", "P2_Y", "P2_Z",
                                      "Dim_Line_Location_X", "Dim_Line_Location_Y", "Dim_Line_Location_Z",
                                      "Text_Override"]},
    "unknown": {"sheet_name": "Unknown_Shapes",
                "headers": ["ID", "Shape_Guess", "Points_JSON", "Other_Params_JSON", "Layer", "Original_Command",
                            "Error_Info"]},

}
GLOBAL_ID_TEXT_HEIGHT = 7.0  # 或者您希望的固定值, e.g., 5.0, 10.0
ID_LABEL_LAYER_NAME = "ID"
ID_LABEL_COLOR = 2


# ++++++++++++++++++++++++++ 修改：ezdxf 绘制文字标注 (ID) ++++++++++++++++++++++++++
def add_id_label_ezdxf(msp, text_content: str, position: Vec3, layer: str = ID_LABEL_LAYER_NAME,
                       height: float = 2.5, rotation: float = 0):  # 移除 halign, valign 默认参数
    """
    在指定位置添加 ID 文本标签，使其几何中心大致在 position。
    """
    if not text_content:
        logging.debug(f"add_id_label_ezdxf: Text content is empty, skipping.")
        return
    try:
        ensure_layer_exists(msp.doc, layer)
        effective_style_name = "Standard_Text"
        if not msp.doc.styles.has_entry(effective_style_name):
            logging.warning(f"ID Label: 默认文字样式 '{effective_style_name}' 在DXF中不存在。将尝试 'Standard'。")
            effective_style_name = "Standard"
            if not msp.doc.styles.has_entry(effective_style_name):
                logging.error(f"ID Label: 备用文字样式 'Standard' 也不存在。ID标签可能无法正确显示。")

        text_entity = msp.add_text(
            str(text_content),
            dxfattribs={
                'layer': layer,
                'height': height,
                'style': effective_style_name,
                'rotation': rotation,
            }
        )
        text_entity.set_placement(
            position,  # 期望的几何中心点
            align=TextEntityAlignment.MIDDLE_CENTER
        )
        logging.info(f"ID Label '{text_content}' added at {position} on layer '{layer}' with height {height}.")
    except AssertionError as ae:
        logging.error(f"Error adding ID label '{text_content}' due to an assertion: {ae}. Position: {position}",
                      exc_info=True)
    except Exception as e:
        logging.error(f"Error adding ID label '{text_content}': {e}", exc_info=True)


# ++++++++++++++++++++++++++ 修改代码: 公共函数 - 添加图层创建辅助 ++++++++++++++++++++++++++

def ensure_layer_exists(doc, layer_name: str, color: int = None, linetype: str = None, lineweight: int = None):
    if not doc.layers.has_entry(layer_name):
        dxfattribs = {}
        dxfattribs['color'] = color if color is not None else 7  # 默认白色/黑色
        # --- 修改线型确定逻辑 --- <---------------- 修改开始 ----------------
        determined_linetype = 'CONTINUOUS'  # 默认线型
        if linetype is not None:  # 优先使用显式传递的 linetype 参数
            if doc.linetypes.has_entry(linetype.upper()):
                determined_linetype = linetype.upper()
            else:
                # 如果显式传递的线型不存在，记录警告，但仍然会尝试用它（可能在后续步骤中定义）或回退
                logging.warning(f"图层 '{layer_name}' 请求的线型参数 '{linetype}' 在文档中未定义。将尝试使用它或回退。")
                determined_linetype = linetype.upper()  # 尝试使用，下面会检查
        elif doc.linetypes.has_entry(layer_name.upper()):  # 如果未传递 linetype 参数，检查图层名本身是否是已定义的线型
            determined_linetype = layer_name.upper()
            logging.info(f"图层 '{layer_name}' 创建时，其名称匹配已定义线型 '{determined_linetype}'，将使用此线型。")
        # else determined_linetype 保持为 'CONTINUOUS'

        dxfattribs['linetype'] = determined_linetype
        # --- 修改线型确定逻辑结束 --- <---------------- 修改结束 ----------------

        if lineweight is not None:
            # 确保传入的 lineweight 是有效的DXF整数值 (-3, -2, -1, 或 0-211)
            if not (-3 <= lineweight <= 211):
                logging.warning(f"图层 '{layer_name}' 的线宽值 {lineweight} 无效，将使用默认线宽 (-3)。")
                dxfattribs['lineweight'] = -3  # Default
            else:
                dxfattribs['lineweight'] = lineweight
        else:
            # 如果未传递 lineweight，则使用DXF的默认值
            dxfattribs['lineweight'] = -3  # DEFAULT lineweight

        # 确保线型存在，如果不存在且是我们要特殊处理的，尝试再次定义 (作为后备)
        # 这个逻辑主要用于处理那些在 determined_linetype 步骤后，linetype 仍然不在 doc.linetypes 中的情况
        if dxfattribs['linetype'] != 'CONTINUOUS' and not doc.linetypes.has_entry(dxfattribs['linetype']):
            if dxfattribs['linetype'] == 'ACAD_ISO02W100':
                if 'ACAD_ISO02W100' not in doc.linetypes:  # 再次检查，以防万一
                    doc.linetypes.new(
                        name='ACAD_ISO02W100',
                        dxfattribs={
                            'description': 'ISO dash __ __ __ __',
                            'pattern': [0.75, 0.5, -0.25]
                        }
                    )
                    logging.info(f"后备：在 ensure_layer_exists 中添加了线型 ACAD_ISO02W100 (因之前未找到)")
            elif dxfattribs['linetype'] == 'ACAD_ISO04W100':  # <---- 添加对 ACAD_ISO04W100 的后备处理
                if 'ACAD_ISO04W100' not in doc.linetypes:
                    doc.linetypes.new(
                        name='ACAD_ISO04W100',
                        dxfattribs={
                            'description': 'ISO long-dash dot ____ . ____ . ____',
                            'pattern': [1.5, 1.0, -0.25, 0.0, -0.25]
                        }
                    )
                    logging.info(f"后备：在 ensure_layer_exists 中添加了线型 ACAD_ISO04W100 (因之前未找到)")
            else:  # 其他未知线型，只能用CONTINUOUS
                logging.warning(
                    f"图层 '{layer_name}' 的线型 '{dxfattribs['linetype']}' 未定义且非已知可后备类型，将使用 CONTINUOUS。")
                dxfattribs['linetype'] = 'CONTINUOUS'

        doc.layers.new(name=layer_name, dxfattribs=dxfattribs)
        logging.info(
            f"图层 '{layer_name}' 在 ensure_layer_exists 中被动态创建，颜色: {dxfattribs['color']}, 线型: {dxfattribs['linetype']},"
            f"线宽: {dxfattribs.get('lineweight', '未设置')} (即 {dxfattribs.get('lineweight', -3) / 100.0:.2f}mm)."
        )


def create_new_dxf_doc():
    """创建一个新的 ezdxf 文档对象"""
    logging.info("Creating new DXF document (R2010)...")
    doc = ezdxf.new('R2010')  # 原有代码

    # —— 以下为新增：注册虚线类型 ACAD_ISO02W100 ——
    if 'ACAD_ISO02W100' not in doc.linetypes:
        doc.linetypes.new(
            name='ACAD_ISO02W100',
            dxfattribs={
                'description': 'ISO dash __ __ __ __',  # Standard description from acadiso.lin
                'pattern': [0.75, 0.5, -0.25]  # Dash 0.5 unit, Space 0.25 unit. Total pattern length 0.75
            }
        )
        logging.info("已在 create_new_dxf_doc 中添加标准线型定义 ACAD_ISO02W100")

        # 您可能还需要 ACAD_ISO04W100 (ISO long-dash dot __ . __ . __)
        # Pattern from acadiso.lin: A,1.0,-.25,0,-.25 (Dash 1, Space 0.25, Dot, Space 0.25)
        # Total length = 1 + 0.25 + 0 + 0.25 = 1.5
    if 'ACAD_ISO04W100' not in doc.linetypes:
        doc.linetypes.new(
            name='ACAD_ISO04W100',
            dxfattribs={
                'description': 'ISO long-dash dot ____ . ____ . ____',
                'pattern': [1.5, 1.0, -0.25, 0.0, -0.25]
            }
        )
        logging.info("已在 create_new_dxf_doc 中添加标准线型定义 ACAD_ISO04W100")
    # —— 注册结束 ——

    return doc  # 原有返回


def save_dxf_doc(doc, filename_prefix="output_drawing"):
    """保存 DXF 文档到当前目录（不创建result文件夹）"""
    doc.header['$LWDISPLAY'] = 1
    # 直接使用当前目录作为输出路径，不创建子文件夹
    filename = f"{filename_prefix}.dxf"
    cad_file_path = os.path.abspath(filename)  # 获取绝对路径便于日志显示

    try:
        logging.info(f"Saving DXF document to: {cad_file_path}")
        doc.saveas(cad_file_path)
        logging.info(f"DXF file saved successfully: {cad_file_path}")
        return cad_file_path
    except Exception as e:
        logging.error(f"Error saving DXF file '{cad_file_path}': {e}")
        return None


# --- 在各个绘图函数中统一ID文字高度的获取 ---
def get_id_text_height(row, default_for_type=2.5):
    if GLOBAL_ID_TEXT_HEIGHT is not None:
        return GLOBAL_ID_TEXT_HEIGHT
    return float(row.get('ID_Text_Height', default_for_type))


# ++++++++++++++++++++++++++ 修改代码: ezdxf 绘制直线 (添加ID标注) ++++++++++++++++++++++++++
def draw_lines_ezdxf(msp, lines_df):
    if lines_df is None or lines_df.empty:
        logging.info("没有直线数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(lines_df)} 条直线...")
    doc = msp.doc  # 获取文档对象

    for index, row in lines_df.iterrows():
        try:
            start_x = float(row['Start_X'])
            start_y = float(row['Start_Y'])
            start_z = float(row.get('Start_Z', 0.0))
            end_x = float(row['End_X'])
            end_y = float(row['End_Y'])
            end_z = float(row.get('End_Z', 0.0))
            line_id_full = str(row.get('ID', '')).strip()  # 获取完整ID
            layer_name = str(row.get('Layer_Name', '0'))
            if not layer_name: layer_name = '0'  # 如果为空则用默认图层0

            ensure_layer_exists(doc, layer_name)

            start_point_vec = Vec3(start_x, start_y, start_z)
            end_point_vec = Vec3(end_x, end_y, end_z)

            msp.add_line(start_point_vec, end_point_vec, dxfattribs={'layer': layer_name})
            logging.info(f"直线 (ID: {line_id_full}) 已绘制: {start_point_vec} -> {end_point_vec} 在图层 {layer_name}")

        except KeyError as e:
            logging.error(f"绘制直线 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except Exception as e:  # <----------新增--------- (捕获更广泛的异常)
            logging.error(f"绘制直线 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}",
                          exc_info=True)
    logging.info("直线绘制完成。")


# ++++++++++++++++++++++++++ 修改代码结束 ++++++++++++++++++++++++++

# ++++++++++++++++++++++++++ 修改代码: ezdxf 绘制圆 (添加ID标注) ++++++++++++++++++++++++++
def draw_circles_ezdxf(msp, circles_df):
    if circles_df is None or circles_df.empty:
        logging.info("没有圆形数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(circles_df)} 个圆...")
    doc = msp.doc

    for index, row in circles_df.iterrows():
        try:
            center_x = float(row['Center_X'])
            center_y = float(row['Center_Y'])
            center_z = float(row.get('Center_Z', 0.0))
            radius = float(row['Radius'])
            layer_name = str(row.get('Layer_Name', '0'))
            ensure_layer_exists(doc, layer_name)  # <---修改----------

            circle_id = str(row.get('ID', f'C_{index}'))  # 使用 C_ 前缀

            if radius <= 0:
                # ... (警告不变)
                continue

            center_point_tuple = (center_x, center_y, center_z)  # <----------修改处--------- (使用元组给 add_circle)
            msp.add_circle(center_point_tuple, radius, dxfattribs={'layer': layer_name})
            logging.info(f"圆 (ID: {circle_id}) 已绘制: Center {center_point_tuple}, Radius {radius}, Layer {layer_name}")

        except KeyError as e:
            logging.error(f"绘制圆 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except Exception as e:  # <----------新增---------
            logging.error(f"绘制圆 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}",
                          exc_info=True)
    logging.info("圆形绘制完成。")


# ++++++++++++++++++++++++++ 修改代码结束 ++++++++++++++++++++++++++


# ++++++++++++++++++++++++++ 修改代码: ezdxf 绘制圆弧 (添加ID标注) ++++++++++++++++++++++++++
def draw_arcs_ezdxf(msp, arcs_df):
    if arcs_df is None or arcs_df.empty:
        logging.info("没有圆弧数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(arcs_df)} 段圆弧...")
    doc = msp.doc

    for index, row in arcs_df.iterrows():
        try:
            center_x = float(row['Center_X'])
            center_y = float(row['Center_Y'])
            center_z = float(row.get('Center_Z', 0.0))
            radius = float(row['Radius'])
            start_angle_deg = float(row['Start_Angle'])
            total_angle_deg = float(
                row.get('Total_Angle', row.get('End_Angle', start_angle_deg) - start_angle_deg))  # 确保有默认值
            end_angle_deg = start_angle_deg + total_angle_deg
            layer_name = str(row.get('Layer_Name', '0'))

            ensure_layer_exists(doc, layer_name)  # <---修改----------
            arc_id = str(row.get('ID', f'A_{index}'))  # 使用 A_ 前缀

            center_point_vec = Vec3(center_x, center_y, center_z)  # <----------修改处---------
            msp.add_arc(center_point_vec, radius, start_angle_deg, end_angle_deg, dxfattribs={'layer': layer_name})
            logging.info(
                f"圆弧 (ID: {arc_id}) 已绘制: Center {center_point_vec}, R {radius}, Start {start_angle_deg}°, End {end_angle_deg}°, Layer {layer_name}")

        except KeyError as e:
            logging.error(f"绘制圆弧 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        # ... (其他 except 块不变)
    logging.info("圆弧绘制完成。")


# --- 辅助函数：计算 LWPOLYLINE 的包围盒中心 (近似) ---
def get_lwpolyline_bbox_center(points):
    if not points:
        return None
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    # Z值可以取第一个点的Z，或平均Z，或固定为0
    z = points[0][2] if len(points[0]) > 2 else 0.0
    return Vec3((min_x + max_x) / 2, (min_y + max_y) / 2, z)


# --- 辅助函数：计算 SPLINE 控制点的包围盒中心 (近似) ---
def get_spline_bbox_center(control_points_vec3):
    if not control_points_vec3:
        return None
    min_x = min(p.x for p in control_points_vec3)
    max_x = max(p.x for p in control_points_vec3)
    min_y = min(p.y for p in control_points_vec3)
    max_y = max(p.y for p in control_points_vec3)
    # Z值可以取第一个点的Z，或平均Z
    z = control_points_vec3[0].z
    return Vec3((min_x + max_x) / 2, (min_y + max_y) / 2, z)


# ++++++++++++++++++++++++++ 新增：ezdxf 填充功能 (Hatch) ++++++++++++++++++++++++++
def draw_hatch_ezdxf(msp, hatch_df):
    if hatch_df is None or hatch_df.empty:
        logging.info("没有填充数据可供处理。")
        return
    logging.info(f"开始处理 {len(hatch_df)} 个填充...")
    doc = msp.doc

    for index, row in hatch_df.iterrows():
        hatch_id = str(row.get('ID', f'Hatch_{index}'))
        try:
            pattern_name = str(row.get('PatternName', 'SOLID')).upper()  # 获取图案名称，转大写
            scale = float(row.get('Scale', 1.0))
            rotation_deg = float(row.get('Rotation', 0.0))  # <--- 获取旋转角度
            layer_name = str(row.get('LayerName', '0'))  # hatch 图层
            ensure_layer_exists(doc, layer_name)

            vertices_str = row.get('Vertices')
            boundary_vertices_tuples = []  # 存储 (x,y,z) 元组

            if not pd.notna(vertices_str) or not str(vertices_str).strip():
                logging.warning(f"填充 (ID: {hatch_id}): 'Vertices' 列为空或无效，跳过。")
                continue

            vertices_str = str(vertices_str).strip()

            try:
                # 尝试1：分号分隔点，逗号分隔坐标
                point_groups_str = vertices_str.split(';')
                if len(point_groups_str) >= 3:  # 至少需要三个点形成一个面
                    valid_points_found_type1 = True
                    temp_vertices = []
                    for pg_str in point_groups_str:
                        coords_str = pg_str.split(',')
                        if len(coords_str) == 2:  # x,y
                            temp_vertices.append((float(coords_str[0]), float(coords_str[1]), 0.0))
                        elif len(coords_str) >= 3:  # x,y,z
                            temp_vertices.append((float(coords_str[0]), float(coords_str[1]), float(coords_str[2])))
                        else:
                            valid_points_found_type1 = False
                            break
                    if valid_points_found_type1:
                        boundary_vertices_tuples = temp_vertices
                        logging.debug(f"填充 (ID: {hatch_id}): Vertices 解析为分号/逗号分隔格式。")
            except ValueError as e_val:  # float转换失败
                logging.debug(
                    f"填充 (ID: {hatch_id}): Vertices 尝试分号/逗号分隔格式解析失败 (ValueError: {e_val})，尝试JSON。原始: '{vertices_str}'")
                boundary_vertices_tuples = []  # 重置，尝试下一种
            except Exception as e_parse_type1:  # 其他解析错误
                logging.debug(
                    f"填充 (ID: {hatch_id}): Vertices 尝试分号/逗号分隔格式解析失败 (Exception: {e_parse_type1})，尝试JSON。原始: '{vertices_str}'")
                boundary_vertices_tuples = []  # 重置

            if not boundary_vertices_tuples:  # 如果第一种格式解析失败或未执行
                try:
                    # 尝试2：JSON 列表的列表/元组  e.g., "[[0,-300,0],[-330,0,0]]" or "[(0,-300,0),(-330,0,0)]"
                    parsed_verts = ast.literal_eval(vertices_str)  # 使用 ast.literal_eval 更安全
                    if isinstance(parsed_verts, list) and \
                            all(isinstance(p, (list, tuple)) and (2 <= len(p) <= 3) for p in parsed_verts):
                        for p_item in parsed_verts:
                            x = float(p_item[0])
                            y = float(p_item[1])
                            z = float(p_item[2]) if len(p_item) == 3 else 0.0
                            boundary_vertices_tuples.append((x, y, z))
                        logging.debug(f"填充 (ID: {hatch_id}): Vertices 解析为JSON列表的列表/元组格式。")
                    else:
                        # 尝试3：JSON 列表的字典 (虽然您的示例不是这种，但保留兼容性)
                        # e.g., "[{'x':0,'y':-300,'z':0}, {'x':-330,'y':0,'z':0}]"
                        if isinstance(parsed_verts, list) and \
                                all(isinstance(p, dict) and 'x' in p and 'y' in p for p in parsed_verts):
                            for p_dict in parsed_verts:
                                x = float(p_dict['x'])
                                y = float(p_dict['y'])
                                z = float(p_dict.get('z', 0.0))
                                boundary_vertices_tuples.append((x, y, z))
                            logging.debug(f"填充 (ID: {hatch_id}): Vertices 解析为JSON列表的字典格式。")
                        else:
                            logging.warning(
                                f"填充 (ID: {hatch_id}): 'Vertices' 格式无法通过已知JSON模式解析: '{vertices_str}'")
                            continue  # 跳过这个hatch
                except (ValueError, SyntaxError, TypeError) as e_json:
                    logging.warning(
                        f"填充 (ID: {hatch_id}): 'Vertices' 无法解析为分号/逗号分隔或JSON格式: '{vertices_str}'. 错误: {e_json}")
                    continue  # 跳过这个hatch

            if not boundary_vertices_tuples or len(boundary_vertices_tuples) < 3:
                logging.warning(f"填充 (ID: {hatch_id}): 解析后边界顶点数不足 ({len(boundary_vertices_tuples)})，跳过。")
                continue

            # 获取第一个顶点的Z坐标作为填充平面的Z值
            elevation_z = boundary_vertices_tuples[0][2]
            hatch_elevation_point = (0.0, 0.0, elevation_z)  # Elevation 是一个点 (DXF code 10, 20, 30)
            # 创建填充对象
            hatch = msp.add_hatch(
                color=const.BYLAYER,  # 填充颜色通常由图层或图案本身决定，这里可以设为BYLAYER
                dxfattribs={'layer': layer_name, 'elevation': hatch_elevation_point}  # 设置Z值为第一个点的Z
            )

            # 设置图案填充
            try:
                hatch.set_pattern_fill(
                    pattern_name,
                    color=const.BYLAYER,  # 图案线条颜色
                    scale=scale,
                    angle=rotation_deg  # DXF HATCH的图案角度是度数
                )
            except ezdxf.lldxf.const.DXFValueError as e_pat:
                logging.error(f"填充 (ID: {hatch_id}) 图案名称 '{pattern_name}' 无效: {e_pat}。尝试默认 SOLID。")
                hatch.set_pattern_fill("SOLID", scale=1.0, angle=rotation_deg)
            except Exception as e_set_pattern:  # 捕获其他可能的 set_pattern_fill 错误
                logging.error(f"填充 (ID: {hatch_id}) 设置图案 '{pattern_name}' 时出错: {e_set_pattern}。跳过此填充。")
                hatch.destroy()
                continue

            # 添加外部边界路径 (Polyline path)
            # is_closed=True 对于多段线边界是必要的
            try:
                hatch.paths.add_polyline_path(
                    boundary_vertices_tuples,
                    is_closed=True,
                )
                logging.info(
                    f"填充 (ID: {hatch_id}) 已创建: Pattern '{pattern_name}', Scale {scale}, Angle {rotation_deg}, Layer {layer_name}，包含 {len(boundary_vertices_tuples)} 个顶点。")
            except Exception as e_path:
                logging.error(f"填充 (ID: {hatch_id}) 添加边界路径时出错: {e_path}。跳过此填充。")
                hatch.destroy()
                continue


        except KeyError as e:
            logging.error(f"处理填充 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:
            logging.error(f"处理填充 (ID: {row.get('ID', '未知')}) 时数据转换错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"处理填充 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)
    #
    logging.info("填充处理完成。")


# ++++++++++++++++++++++++++ 填充功能结束 ++++++++++++++++++++++++++


# ================== 样条曲线 ==================
def draw_spline(msp, df):  # <--- 修改参数为 msp 和 df
    results = []
    if df is None or df.empty:
        logging.info("没有样条曲线数据。")
        return "没有样条曲线数据。"

    for index, row in df.iterrows():  # <----------修改处--------- (使用 index)
        spline_id = str(row.get('ID', f'Spline_{index}'))  # <----------修改处--------- (使用 index)
        try:
            layer_name = str(row.get('Layer_Name', '0'))  # 新增图层名称读取
            x_values_str = str(row.get('x', str(row.get('Points_JSON_x', ''))))  # 兼容旧列名和新JSON列
            y_values_str = str(row.get('y', str(row.get('Points_JSON_y', ''))))

            control_points = []
            # 尝试解析新格式 Points_JSON: "[(x1,y1,z1), (x2,y2,z2)]" or "[[x1,y1,z1], ...]"
            points_json_str = row.get('Points_JSON')
            if pd.notna(points_json_str):
                try:
                    parsed_points = ast.literal_eval(str(points_json_str))
                    if isinstance(parsed_points, list) and all(
                            isinstance(p, (list, tuple)) and len(p) >= 2 for p in parsed_points):
                        control_points = [Vec3(p[0], p[1], p[2] if len(p) > 2 else 0) for p in parsed_points]
                except (ValueError, SyntaxError) as e:
                    logging.warning(f"样条曲线 (ID: {spline_id}) Points_JSON 解析失败: {e}. 尝试旧格式x,y列。")

            if not control_points and pd.notna(x_values_str) and pd.notna(
                    y_values_str) and x_values_str and y_values_str:  # 如果JSON解析失败或不存在，尝试x,y列
                x_values = list(map(float, x_values_str.split(',')))
                y_values = list(map(float, y_values_str.split(',')))
                # 假设z值为0，或者您有z列
                z_values_str = str(row.get('z', ''))
                if z_values_str:
                    z_values = list(map(float, z_values_str.split(',')))
                    control_points = [Vec3(x, y, z) for x, y, z in zip(x_values, y_values, z_values)]
                else:
                    control_points = [Vec3(x, y, 0) for x, y in zip(x_values, y_values)]

            if not control_points or len(control_points) < 2:
                msg = f"ID {spline_id} 样条曲线控制点不足或解析失败，跳过。"
                results.append(msg)
                logging.warning(msg)
                continue

            msp.add_spline(control_points, dxfattribs={'layer': layer_name})
            results.append(f"ID {spline_id} 样条曲线绘制完成")
            logging.info(f"样条曲线 (ID: {spline_id}) 已绘制在图层 {layer_name}")

        except Exception as e:
            msg = f"ID {row.get('ID', '未知')} 绘制样条曲线错误: {str(e)}"
            results.append(msg)
            logging.error(msg)
    return "\n".join(results)
    # except Exception as e:
    #     return f"样条曲线读取错误: {str(e)}" # 这个外层 try/except 可以移到主调用函数


# ++++++++++++++++++++++++++ 椭圆弧 ++++++++++++++++++++++++++
def draw_ellipse_arc(msp, df):
    results = []
    if df is None or df.empty:
        logging.info("没有椭圆弧数据。")
        return "没有椭圆弧数据。"

    for _, row in df.iterrows():
        try:
            layer_name = str(row.get('Layer_Name', '0'))  # 新增图层名称读取
            center = (float(row['中心坐标_x']), float(row['中心坐标_y']))
            major_axis = (float(row['长轴向量_x']), float(row['长轴向量_y']))
            ratio = float(row['短轴与长轴比例'])
            start_angle = math.radians(float(row['起始角度']))
            end_angle = math.radians(float(row['结束角度']))
            layer_name = str(row.get('Layer_Name', '0'))

            # 创建椭圆并设置起始/结束参数
            ellipse = msp.add_ellipse(
                center=center,
                major_axis=major_axis,
                ratio=ratio,
                dxfattribs={'layer': layer_name}
            )
            ellipse.dxf.start_param = start_angle
            ellipse.dxf.end_param = end_angle

            logging.info(f"椭圆弧 (ID: {row.get('ID', '未知')}) 已绘制")
        except Exception as e:
            msg = f"ID {row.get('ID', '未知')} 错误: {str(e)}"
            results.append(msg)
            logging.error(msg)

    return "\n".join(results)


# ++++++++++++++++++++++++++ 公式曲线 ++++++++++++++++++++++++++
def draw_formula(msp, df):
    results = []
    if df is None or df.empty:
        logging.info("没有公式曲线数据。")
        return "没有公式曲线数据。"

    for _, row in df.iterrows():
        formula_id = str(row.get('ID', f'FormulaCurve_{_}'))  # <--- ID生成依赖行号
        try:
            # 新增数据校验
            layer_name = str(row.get('Layer_Name', '0'))  # 新增图层名称读取
            ensure_layer_exists(msp.doc, layer_name)  # <--- 确保图层存在

            x = float(row['起始x'])
            end_x_val = float(row['结束x'])
            step_val = float(row['步长'])

            if step_val <= 0:
                logging.error(f"公式曲线 (ID: {formula_id}): 步长 ({step_val}) 必须大于0。跳过。")  # <--- 补充日志
                results.append(f"ID {formula_id} 步长无效")
                continue
            if x > end_x_val:
                logging.error(f"公式曲线 (ID: {formula_id}): 起始x ({x}) 必须小于或等于结束x ({end_x_val})。跳过。")
                results.append(f"ID {formula_id} 起始x大于结束x")
                continue
            points = []
            formula_str = str(row['公式'])

            current_x = x
            while True:
                if current_x > end_x_val + 1e-9:  # 加一点容差避免浮点数比较问题
                    break

                # 确保即使 current_x 由于步长原因略微超过 end_x_val，
                # 如果差值很小，我们仍然计算 end_x_val 这一点。
                eval_x = min(current_x, end_x_val)

                try:
                    y = eval(formula_str, {"__builtins__": None, "math": math, "x": eval_x, "np": np})
                    # 检查y是否为有效的数值 (不是None，不是NaN，不是inf)
                    if y is None or math.isnan(y) or math.isinf(y):
                        logging.warning(f"公式曲线 (ID: {formula_id}): 在 x={eval_x} 处计算得到无效y值 ({y})。跳过此点。")
                    else:
                        points.append((eval_x, y))
                except Exception as eval_e:
                    logging.error(
                        f"公式曲线 (ID: {formula_id}): 在 x={eval_x} 处计算公式 '{formula_str}' 时出错: {eval_e}。停止为此曲线生成点。")
                    points = []  # 清空已计算的点，因为公式可能整体有问题
                    break  # 中断此曲线的点生成

                if eval_x == end_x_val:  # 如果已经计算了终点，则退出
                    break

                current_x += step_val
                if current_x > end_x_val and eval_x != end_x_val:  # 如果下一步将超过终点，且当前点不是终点
                    # 则下一次循环将计算精确的 end_x_val
                    current_x = end_x_val  # 强制下一次迭代计算终点

            # 绘制逻辑
            if len(points) > 1:
                msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
                results.append(f"ID {formula_id} 公式曲线绘制完成")
                logging.info(f"公式曲线 (ID: {formula_id}) 已绘制 {len(points)} 个点，图层 {layer_name}")
            elif len(points) == 1:
                msp.add_point(points[0], dxfattribs={'layer': layer_name})  # 需要Vec3，但add_point接受元组
                results.append(f"ID {formula_id} 公式曲线只有一个点，已绘制为 POINT")
                logging.info(f"公式曲线 (ID: {formula_id}) 只有一个点，已绘制为 POINT，图层 {layer_name}")
            else:  # len(points) == 0
                results.append(f"ID {formula_id} 公式曲线计算点不足 (<1)，无法绘制")
                logging.warning(f"公式曲线 (ID: {formula_id}) 点不足 (0个有效点)，无法绘制。")

        except Exception as e:
            msg = f"ID {row.get('ID', '未知')} 绘制公式曲线错误: {str(e)}"
            results.append(msg)
            logging.error(msg)
    return "\n".join(results)


# ++++++++++++++++++++++++++ 多线段拟合曲线 ++++++++++++++++++++++++++
def draw_polyfit(msp, df):
    results = []
    if df is None or df.empty:
        logging.info("没有多线段拟合曲线数据。")
        return "没有多线段拟合曲线数据。"

    for _, row in df.iterrows():
        try:
            layer_name = str(row.get('Layer_Name', '0'))  # 新增图层名称读取
            x_data = list(map(float, str(row['x数据']).split(',')))
            y_data = list(map(float, str(row['y数据']).split(',')))
            degree = int(row['多项式阶数'])
            num_points = int(row.get('生成点数', 100))  # 提供默认值
            layer_name = str(row.get('Layer_Name', '0'))
            polyfit_id = str(row.get('ID', f'Polyfit_{_}'))

            coeff = np.polyfit(x_data, y_data, degree)
            poly = np.poly1d(coeff)
            x_fit = np.linspace(min(x_data), max(x_data), num_points)
            points = list(zip(x_fit, poly(x_fit)))

            if len(points) > 1:
                msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
                results.append(f"ID {polyfit_id} 拟合曲线完成")
                logging.info(f"多项式拟合曲线 (ID: {polyfit_id}) 已绘制在图层 {layer_name}")

            else:
                results.append(f"ID {polyfit_id} 拟合曲线点数不足 (<2)")
                logging.warning(f"多项式拟合曲线 (ID: {polyfit_id}) 点数不足，无法绘制。")
        except Exception as e:
            msg = f"ID {row.get('ID', '未知')} 绘制多项式拟合曲线错误: {str(e)}"
            results.append(msg)
            logging.error(msg)
    return "\n".join(results)


def draw_clothoid(msp, df):
    results = []
    if df is None or df.empty:
        logging.info("没有缓和曲线数据。")
        return "没有缓和曲线数据。"

    for _, row in df.iterrows():
        clothoid_id = str(row.get('ID', f'Clothoid_{_}'))

        try:
            layer_name = str(row.get('Layer_Name', '0'))  # 新增图层名称读取
            start_point_str = str(row['起点坐标 (x, y)']).strip('()')
            start_point = tuple(map(float, start_point_str.split(',')))
            # ezdxf add_euler_spiral (缓和曲线的另一种实现) 期望角度是弧度
            # 但如果原始逻辑是用度，然后转弧度，保持一致
            direction_angle_deg = float(row['起点方向角度 (弧度)'])  # 假设 Excel 中是度
            direction_angle_rad = math.radians(direction_angle_deg)
            clothoid_length = float(row['缓和曲线长度'])
            # 缓和曲线通常以曲率或半径参数定义，这里是终点半径
            # ezdxf.add_euler_spiral 的参数是 A (参数) 和 length
            # A = sqrt(R*L)
            radius_end = float(row['终点半径'])  # 这是终点曲率圆的半径
            layer_name = str(row.get('Layer_Name', '0'))

            if radius_end <= 0 or clothoid_length <= 0:
                logging.warning(f"缓和曲线 (ID: {clothoid_id}) 参数无效 (半径或长度<=0)，跳过。")
                results.append(f"ID {clothoid_id} 参数无效")
                continue

            # 使用 ezdxf 的内置缓和曲线 (欧拉螺线) 功能可能更简单直接
            # 但如果需要完全复现您同事的计算逻辑：
            points = []
            step = clothoid_length / 100.0  # 分成100段，或者更小的步长
            if step == 0: step = 0.1  # 避免除零

            A_param = math.sqrt(abs(radius_end) * clothoid_length)  # A 参数必须为正
            if A_param == 0:
                logging.warning(f"缓和曲线 (ID: {clothoid_id}) A 参数为零，无法计算，跳过。")
                results.append(f"ID {clothoid_id} A参数为零")
                continue

            for s_param in np.arange(0, clothoid_length + step, step):  # 包含终点
                s_param = min(s_param, clothoid_length)  # 确保不超过总长度
                # 泰勒展开近似 (适用于 s/A 较小的情况)
                # theta = s_param**2 / (2 * A_param**2) # 转向角
                # x_local = s_param * (1 - theta**2 / 10 + theta**4 / 216 - theta**6 / 9360)
                # y_local = s_param * (theta / 3 - theta**3 / 42 + theta**5 / 1320 - theta**7 / 75600)

                # 您同事的公式（可能是某种简化或特定近似）
                x_local = s_param - (s_param ** 5 / (40 * A_param ** 4)) + (s_param ** 9 / (3456 * A_param ** 8))
                y_local = (s_param ** 3 / (6 * A_param ** 2)) - (s_param ** 7 / (336 * A_param ** 6)) + (
                        s_param ** 11 / (42240 * A_param ** 10))

                rotated_x = x_local * math.cos(direction_angle_rad) - y_local * math.sin(direction_angle_rad) + \
                            start_point[0]
                rotated_y = x_local * math.sin(direction_angle_rad) + y_local * math.cos(direction_angle_rad) + \
                            start_point[1]
                points.append((rotated_x, rotated_y))

            if len(points) > 1:
                msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
                results.append(f"ID {clothoid_id} 缓和曲线绘制完成")
                logging.info(f"缓和曲线 (ID: {clothoid_id}) 已绘制在图层 {layer_name}")

        except Exception as e:
            msg = f"ID {clothoid_id} 绘制缓和曲线错误: {str(e)}"  # <--- 使用已定义的 clothoid_id
            results.append(msg)
            logging.error(msg, exc_info=True)  # 添加 exc_info
    return "\n".join(results)


# ++++++++++++++++++++++++++ 修改代码结束 ++++++++++++++++++++++++++


def draw_ellipse_ezdxf(msp, df):  # <--- 修改参数为 msp 和 df
    """ 绘制椭圆 """
    if df is None or df.empty:
        logging.info("没有椭圆数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(df)} 个椭圆...")
    doc = msp.doc  # 获取文档对象以操作图层

    for index, row in df.iterrows():
        try:
            ellipse_id = str(row.get('ID', f'Ellipse_{index}'))
            # <------ 修改代码: 使用 ast.literal_eval 解析坐标元组字符串 ------>
            center_str = str(row['坐标'])  # 例如 "(10,20)" 或 "(10,20,0)"
            center_tuple = ast.literal_eval(center_str)
            center = Vec3(center_tuple)  # 转换为 Vec3，自动处理 2D/3D
            # <------ 修改代码结束 ------>
            major_axis_length = float(row['长轴'])
            minor_axis_length = float(row['短轴'])
            rotation_deg = float(row.get('旋转角度', 0.0))  # 默认为0度
            layer_name = str(row.get('layer_name', row.get('Layer_Name', '0')))  # 兼容不同列名

            if layer_name not in doc.layers:
                doc.layers.new(name=layer_name)
                logging.info(f"图层 '{layer_name}' 已为椭圆 (ID: {ellipse_id}) 创建。")

            # ezdxf add_ellipse 需要中心点、长轴向量（从中心点出发）和短长轴比例
            # 长轴向量：假设初始沿X轴，长度为长半轴，然后旋转
            major_radius = major_axis_length / 2.0
            # <------ 修改代码: 计算长轴向量 ------>
            # 初始长轴向量沿X轴
            major_axis_vec_unrotated = Vec3(major_radius, 0, 0)
            # 如果有旋转角度，则旋转长轴向量
            if rotation_deg != 0:
                major_axis_vec = major_axis_vec_unrotated.rotate_deg(rotation_deg)
            else:
                major_axis_vec = major_axis_vec_unrotated
            # <------ 修改代码结束 ------>

            ratio = minor_axis_length / major_axis_length if major_axis_length > 0 else 0

            if ratio <= 0 or ratio > 1:
                logging.warning(f"椭圆 (ID: {ellipse_id}) 的短长轴比例无效 ({ratio})，跳过。")
                continue

            msp.add_ellipse(
                center=center,
                major_axis=major_axis_vec,  # 这是从中心到长轴端点的向量
                ratio=ratio,
                dxfattribs={'layer': layer_name}
            )
            logging.info(
                f"椭圆 (ID: {ellipse_id}) 已绘制: Center {center}, MajorAxisLen {major_axis_length}, MinorAxisLen {minor_axis_length}, Rot {rotation_deg}°, Layer {layer_name}")
        except KeyError as e:
            logging.error(f"绘制椭圆 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:  # ast.literal_eval 可能抛出 ValueError
            logging.error(f"绘制椭圆 (ID: {row.get('ID', '未知')}) 时数据转换或解析错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"绘制椭圆 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)
    logging.info("椭圆绘制完成。")


# ++++++++++++++++++++++++++ 椭圆绘制结束 ++++++++++++++++++++++++++


# ++++++++++++++++++++++++++ 新增/修改：多段线 (来自同事代码，适配接口) ++++++++++++++++++++++++++
def draw_polyline_ezdxf(msp, df):  # <--- 修改参数为 msp 和 df
    """ 绘制多段线 """
    if df is None or df.empty:
        logging.info("没有多段线数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(df)} 条多段线...")
    doc = msp.doc

    for index, row in df.iterrows():
        polyline_id_full = str(row.get('ID', f'Polyline_{index}'))  # <---- 获取完整的ID字符串

        try:
            layer_name = str(row.get('layer_name', row.get('Layer_Name', '0')))
            ensure_layer_exists(doc, layer_name)

            points_str = str(row['顶点坐标列表'])
            raw_points = ast.literal_eval(points_str)
            points_vec3 = []
            if raw_points and isinstance(raw_points, list):
                for p_item in raw_points:
                    if isinstance(p_item, (list, tuple)):
                        if len(p_item) == 2:
                            points_vec3.append(Vec3(p_item[0], p_item[1], 0.0))
                        elif len(p_item) >= 3:
                            points_vec3.append(Vec3(p_item[0], p_item[1], p_item[2]))
                        else:
                            logging.warning(f"多段线 (ID: {polyline_id_full}) 的顶点 {p_item} 格式不正确，跳过此点。")
                    else:
                        logging.warning(
                            f"多段线 (ID: {polyline_id_full}) 的顶点列表包含非元组/列表项 {p_item}，跳过此点。")

            if not points_vec3:  # 如果转换后列表为空
                logging.warning(f"多段线 (ID: {polyline_id_full}) 的顶点数据解析后为空，跳过。数据: {points_str}")
                continue

            closed_str = str(row.get('是否封闭', '否')).lower()  # 获取并转小写，默认为'否'
            is_closed = (closed_str == '是' or closed_str == 'true')

            if not isinstance(points_vec3, list) or not all(
                    isinstance(p, Vec3) for p in points_vec3):  # <---- 修改：检查Vec3列表 ----
                logging.warning(
                    f"多段线 (ID: {polyline_id_full}) 的顶点数据格式不正确（未成功转为Vec3列表），跳过。数据: {points_str}")
                continue
            if len(points_vec3) < 2:
                logging.warning(f"多段线 (ID: {polyline_id_full}) 顶点数不足 (<2)，跳过。")
                continue

            points_for_lwpolyline = [(p.x, p.y, p.z) for p in points_vec3]  # <--- 确保是元组列表 ---

            msp.add_lwpolyline(points=points_for_lwpolyline, close=is_closed, dxfattribs={'layer': layer_name})
            logging.info(
                f"多段线 (ID: {polyline_id_full}) 已绘制: {len(points_vec3)} 个顶点, Closed={is_closed}, Layer {layer_name}")

        except KeyError as e:
            logging.error(f"绘制多段线 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except (ValueError, SyntaxError) as e:  # ast.literal_eval 可能抛出这些错误
            logging.error(f"绘制多段线 (ID: {row.get('ID', '未知')}) 时顶点数据解析错误: {e}。数据: {row.get('顶点坐标列表')}")
        except Exception as e:
            logging.error(f"绘制多段线 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)
    logging.info("多段线绘制完成。")


# ++++++++++++++++++++++++++ 新增/修改：矩形 (来自同事代码，适配接口) ++++++++++++++++++++++++++
def draw_rectangle_ezdxf(msp, df):  # <--- 修改参数为 msp 和 df
    """ 绘制矩形 (作为闭合的 LWPOLYLINE) """
    if df is None or df.empty:
        logging.info("没有矩形数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(df)} 个矩形...")
    doc = msp.doc

    for index, row in df.iterrows():
        rect_id = str(row.get('ID', f'Rect_{index}'))
        try:
            # <------ 修改代码: 使用 ast.literal_eval 解析中心坐标 ------>
            center_str = str(row['中心坐标'])
            center_tuple = ast.literal_eval(center_str)
            center = Vec3(center_tuple)  # 假设中心点是2D或3D
            # <------ 修改代码结束 ------>
            width = float(row['宽'])
            height = float(row['高'])
            rotation_deg = float(row.get('旋转角度', 0.0))  # 假设有旋转角度列，默认为0
            layer_name = str(row.get('layer_name', row.get('Layer_Name', '0')))

            if width <= 0 or height <= 0:
                logging.warning(f"矩形 (ID: {rect_id}) 的宽度或高度无效，跳过。")
                continue

            if not doc.layers.has_entry(layer_name):  # <--- 修正图层检查和创建
                doc.layers.new(name=layer_name)
                logging.info(f"图层 '{layer_name}' 已为矩形 (ID: {rect_id}) 创建。")

            half_w = width / 2.0
            half_h = height / 2.0

            # 定义相对于原点(0,0)的四个角点
            corners_local = [
                Vec3(-half_w, -half_h),  # 左下
                Vec3(half_w, -half_h),  # 右下
                Vec3(half_w, half_h),  # 右上
                Vec3(-half_w, half_h),  # 左上
            ]

            if rotation_deg != 0:
                rotated_corners_vec3 = [p.rotate_deg(rotation_deg, axis=Z_AXIS) for p in corners_local]
            else:
                rotated_corners_vec3 = corners_local

            # 将角点平移到实际中心点
            abs_corners_vec3 = [corner + center for corner in rotated_corners_vec3]

            msp.add_lwpolyline(
                abs_corners_vec3,
                close=True,
                dxfattribs={'layer': layer_name}
            )
            logging.info(
                f"矩形 (ID: {rect_id}) 已绘制: Center {center}, W {width}, H {height}, Rot {rotation_deg}°, Layer {layer_name}")
        except KeyError as e:
            logging.error(f"绘制矩形 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except (ValueError, SyntaxError) as e:
            logging.error(f"绘制矩形 (ID: {row.get('ID', '未知')}) 时数据转换或解析错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"绘制矩形 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)
    logging.info("矩形绘制完成。")


# ++++++++++++++++++++++++++ 新增/修改：点 (来自同事代码，适配接口) ++++++++++++++++++++++++++
def draw_point_ezdxf(msp, df):  # <--- 修改参数为 msp 和 df
    """绘制点"""
    if df is None or df.empty:
        logging.info("没有点数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(df)} 个点...")
    doc = msp.doc

    # 设置点的显示模式和大小（全局设置，只需一次）
    # 这些设置会影响 DXF 文件中所有 POINT 实体的显示方式
    if '$PDMODE' not in doc.header:  # 避免重复设置
        doc.header['$PDMODE'] = 35  # 例如，圆加一个叉 (值可以查DXF文档)
        # 64 可能是 AutoCAD 特定的显示模式，DXF中可能不同
        # 常见的 PDMODE: 0 (点), 1 (不显示), 2 (+), 3 (X), 4 (|)
        # 32 (圆), 33 (方块), 34 (圆+点), 35(方块+点), 36(圆+X)
        # 64 (圆内方块), 65 (圆内方块+点), ...
        doc.header['$PDSIZE'] = 1.0  # 点的绝对大小 (如果 $PDMODE > 0)
        # 如果 $PDSIZE < 0, 表示相对于屏幕的百分比
        logging.info(f"设置 DXF header: $PDMODE={doc.header['$PDMODE']}, $PDSIZE={doc.header['$PDSIZE']}")

    for index, row in df.iterrows():
        try:
            point_id = str(row.get('ID', f'Point_{index}'))
            x = float(row['x'])
            y = float(row['y'])
            z = float(row.get('z', 0.0))  # 假设有可选的z列
            layer_name = str(row.get('layer_name', row.get('Layer_Name', '0')))

            if layer_name not in doc.layers:
                doc.layers.new(name=layer_name)
                logging.info(f"图层 '{layer_name}' 已为点 (ID: {point_id}) 创建。")

            msp.add_point((x, y, z), dxfattribs={'layer': layer_name})
            logging.info(f"点 (ID: {point_id}) 已绘制: ({x},{y},{z}), Layer {layer_name}")
        except KeyError as e:
            logging.error(f"绘制点 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:
            logging.error(f"绘制点 (ID: {row.get('ID', '未知')}) 时数据转换错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"绘制点 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)
    logging.info("点绘制完成。")


# ++++++++主协调函数 ++++++++
def generate_all_elements_from_excel(excel_path: str):
    """
    读取 Excel 文件中的所有数据，并使用 ezdxf 生成包含所有图元的 DXF 文件。
    """
    logging.info(f"开始从 Excel 文件 '{excel_path}' 生成 DXF...")
    try:
        xls = pd.ExcelFile(excel_path)
    except FileNotFoundError:
        logging.error(f"Excel 文件未找到: {excel_path}")
        return
    except Exception as e:
        logging.error(f"读取 Excel 文件 '{excel_path}' 时出错: {e}")
        return

    doc = create_new_dxf_doc()
    msp = doc.modelspace()
    doc.header['$LTSCALE'] = 10.0  # <--- 新增：设置一个合适的全局线型比例，根据您的图形单位调整
    # CELTSCALE 是单个图元的线型比例，通常保持为1.0，让 $LTSCALE 控制全局
    doc.header['$CELTSCALE'] = 1.0

    # --- 1. 优先处理 Layers 表，定义所有在其中声明的图层及其属性 ---
    if "Layers" in xls.sheet_names:
        logging.info("读取并定义来自 'Layers' 表的图层...")
        try:
            layers_df_from_excel = xls.parse("Layers")
            for index, row in layers_df_from_excel.iterrows():
                layer_name = str(row.get('Layer_Name', '')).strip()
                if not layer_name:
                    logging.warning(f"Layers 表中发现空图层名，行: {index + 2}，跳过。")
                    continue

                layer_color_aci = 7  # 默认颜色
                if 'Color' in row and pd.notna(row['Color']):
                    try:
                        layer_color_aci = int(row['Color'])
                    except ValueError:
                        logging.warning(f"图层 '{layer_name}' 颜色 '{row['Color']}' 无效，使用默认值 7。")

                excel_linetype_name_raw = str(row.get('Linetype', 'CONTINUOUS')).strip()
                excel_linetype_name = excel_linetype_name_raw.upper()

                final_linetype_to_assign = 'CONTINUOUS'
                if excel_linetype_name in ['CONTINUOUS', 'BYLAYER', 'BYBLOCK']:
                    final_linetype_to_assign = excel_linetype_name
                elif doc.linetypes.has_entry(excel_linetype_name):  # 检查是否已在create_new_dxf_doc中定义
                    final_linetype_to_assign = excel_linetype_name
                else:
                    logging.warning(
                        f"图层 '{layer_name}' (来自 Layers 表) 请求的线型 '{excel_linetype_name}' "
                        f"(原始: '{excel_linetype_name_raw}') 在文档中未预定义。将依赖 ensure_layer_exists 或默认为 'CONTINUOUS'。"
                    )
                    if not doc.linetypes.has_entry(excel_linetype_name):  # 再次检查
                        logging.warning(
                            f"由于线型 '{excel_linetype_name}' 仍未找到，图层 '{layer_name}' 将使用 'CONTINUOUS'。")
                        # final_linetype_to_assign 保持 'CONTINUOUS'
                    else:  # 可能在某个动态过程中被创建了
                        final_linetype_to_assign = excel_linetype_name

                # --- 新增：读取和转换线宽 --- <---------------- 新增/修改开始 ----------------
                raw_lineweight = row.get('Lineweight')
                layer_lineweight_int = -3  # 默认为 DEFAULT (-3) 或者 BYLAYER (-1) 也可以考虑
                # -3 (DEFAULT) 通常对应一个较细的默认线宽

                if pd.notna(raw_lineweight) and str(raw_lineweight).strip() != "":
                    try:
                        # Excel 中的值可能是浮点数，代表毫米 (mm)
                        lineweight_mm = float(raw_lineweight)
                        if lineweight_mm >= 0:
                            # 转换为 DXF 的整数值 (mm * 100)并且需要确保结果是标准线宽值之一，或者非常接近。ezdxf 会自动将提供的值舍入到最接近的标准线宽值。
                            layer_lineweight_int = int(round(lineweight_mm * 100))
                            # 校验一下是否在合理范围内，例如 0 到 211 (对应 0.00mm 到 2.11mm)
                            if not (0 <= layer_lineweight_int <= 211):
                                logging.warning(
                                    f"图层 '{layer_name}' 的线宽值 {lineweight_mm}mm (转换后为 {layer_lineweight_int}) "
                                    f"超出了典型范围 (0-211)。将尝试使用，但可能被CAD软件调整。")
                        else:  # 如果Excel中是负值，可能表示 BYLAYER/BYBLOCK/DEFAULT
                            lw_int_check = int(lineweight_mm)
                            if lw_int_check in [-1, -2, -3]:
                                layer_lineweight_int = lw_int_check
                            else:
                                logging.warning(
                                    f"图层 '{layer_name}' 的线宽值 {lineweight_mm}mm 无效 (负值但非-1,-2,-3)，将使用默认线宽。")
                                layer_lineweight_int = -3  # Default
                    except ValueError:
                        logging.warning(
                            f"图层 '{layer_name}' 的线宽值 '{raw_lineweight}' 无法转换为数字，将使用默认线宽。")
                        layer_lineweight_int = -3  # Default
                # --- 新增：读取和转换线宽结束 --- <---------------- 新增/修改结束 ----------------

                ensure_layer_exists(doc, layer_name, color=layer_color_aci, linetype=final_linetype_to_assign,
                                    lineweight=layer_lineweight_int)  # <---- 修改 ----

                if doc.layers.has_entry(layer_name):  # 在 ensure_layer_exists 调用后，它肯定存在了
                    layer_obj = doc.layers.get(layer_name)
                    if layer_obj.dxf.color != layer_color_aci:
                        layer_obj.dxf.color = layer_color_aci
                        logging.info(f"图层 '{layer_name}' 颜色已更新为 {layer_color_aci} (来自Layers表)。")
                    if layer_obj.dxf.linetype.upper() != final_linetype_to_assign.upper():
                        # 再次确认 final_linetype_to_assign 是有效的
                        if doc.linetypes.has_entry(final_linetype_to_assign.upper()):
                            layer_obj.dxf.linetype = final_linetype_to_assign.upper()
                            logging.info(
                                f"图层 '{layer_name}' 线型已更新为 '{final_linetype_to_assign.upper()}' (来自Layers表)。")
                        elif final_linetype_to_assign.upper() != 'CONTINUOUS':  # 如果期望的不是CONTINUOUS但又不存在
                            logging.warning(
                                f"尝试更新图层 '{layer_name}' 线型为 '{final_linetype_to_assign.upper()}' 失败，因其未定义。维持现状或 'CONTINUOUS'。")
                    if layer_obj.dxf.lineweight != layer_lineweight_int:
                        layer_obj.dxf.lineweight = layer_lineweight_int
                        logging.info(
                            f"图层 '{layer_name}' 线宽已更新为 {layer_lineweight_int} (即 {layer_lineweight_int / 100.0:.2f}mm) (来自Layers表)。")

        except Exception as e:
            logging.error(f"处理 'Layers' 表时出错: {e}", exc_info=True)
    else:
        logging.info("Excel 文件中未找到 'Layers' 工作表。图层将按需创建或使用默认。")

    # 这些样式名应与 Excel 中 "文字样式" 列的内容对应
    text_styles_to_ensure = {
        "Standard_Text": {"font": "arial.ttf"},  # 一个基于 Arial 的标准样式
        "宋体": {"font": "simsun.ttc", "width": 0.75},  # <------ 修改代码: "width_factor" -> "width" ------
        "微软雅黑": {"font": "msyh.ttc"},
        "Standard": {"font": "simsun.ttc", "width": 0.75},  # <------ 修改代码: "width_factor" -> "width" ------
    }
    for style_name, style_attrs in text_styles_to_ensure.items():
        if not doc.styles.has_entry(style_name):
            try:
                # 对于TrueType字体，通常不需要指定 dxf.big_font
                doc.styles.new(style_name, dxfattribs=style_attrs)
                logging.info(f"文字样式 '{style_name}' (属性: {style_attrs}) 已创建。")
            except Exception as e_style_create:
                logging.error(f"创建文字样式 '{style_name}' 失败: {e_style_create}。")
        else:  # 如果样式已存在，可以选择是否强制更新其字体（通常不推荐，除非明确需要）
            existing_style = doc.styles.get(style_name)
            if 'font' in style_attrs and existing_style.dxf.font.lower() != style_attrs['font'].lower():
                logging.warning(
                    f"文字样式 '{style_name}' 已存在，但其字体 ('{existing_style.dxf.font}') 与期望 ('{style_attrs['font']}') 不同。")
                # 确保宽度因子也应用 (如果指定)
            if 'width_factor' in style_attrs and hasattr(existing_style.dxf, 'width') and existing_style.dxf.width != \
                    style_attrs['width_factor']:
                # existing_style.dxf.width = style_attrs['width_factor'] # 可以选择是否强制更新
                logging.warning(
                    f"文字样式 '{style_name}' 已存在，但其宽度因子 ({existing_style.dxf.width}) 与期望 ({style_attrs['width_factor']}) 不同。")

    # --- 更新 Standard DIMSTYLE 的默认值 ---
    try:
        std_dimstyle_name = "Standard"  # 这是 DIMSTYLE 名称
        std_text_style_name_for_dim = "Standard"  # <------ 修改代码 ------

        # 确保 "Standard" DIMSTYLE 存在或创建它
        if not doc.dimstyles.has_entry(std_dimstyle_name):
            standard_dimstyle = doc.dimstyles.new(std_dimstyle_name)
            logging.info(f"DIMSTYLE '{std_dimstyle_name}'不存在，已创建。")
        else:
            standard_dimstyle = doc.dimstyles.get(std_dimstyle_name)

        # 确保引用的文字样式存在
        if doc.styles.has_entry(std_text_style_name_for_dim):
            standard_dimstyle.dxf.dimtxsty = std_text_style_name_for_dim  # <------ 修改代码 ------
            logging.info(f"DIMSTYLE '{std_dimstyle_name}' 已设置为使用 TEXTSTYLE '{std_text_style_name_for_dim}'.")
        else:
            logging.warning(
                f"TEXTSTYLE '{std_text_style_name_for_dim}' 不存在，DIMSTYLE '{std_dimstyle_name}' 可能使用默认字体。")

        #     # 设置合理的默认值
        default_dim_text_height = 2.5
        default_dim_arrow_size = 1.8
        #
        if standard_dimstyle.dxf.dimtxt <= 1e-6:  # 如果文字高度太小
            standard_dimstyle.dxf.dimtxt = default_dim_text_height
            logging.info(
                f"Updated '{std_dimstyle_name}' DIMSTYLE default text height (dimtxt) to {default_dim_text_height}")
        if standard_dimstyle.dxf.dimasz <= 1e-6:  # 如果箭头大小太小
            standard_dimstyle.dxf.dimasz = default_dim_arrow_size
            logging.info(
                f"Updated '{std_dimstyle_name}' DIMSTYLE default arrow size (dimasz) to {default_dim_arrow_size}")
        standard_dimstyle.dxf.dimtad = 0  # 文字居中并打断尺寸线
        logging.debug(
            f"Standard DIMSTYLE 已更新: Text Style='{standard_dimstyle.dxf.dimtxsty}', Text Height={standard_dimstyle.dxf.dimtxt}, Arrow Size={standard_dimstyle.dxf.dimasz}")
    except Exception as e_std_dim:
        logging.error(f"Error trying to update 'Standard' DIMSTYLE: {e_std_dim}", exc_info=True)

    ensure_layer_exists(doc, ID_LABEL_LAYER_NAME, color=ID_LABEL_COLOR)  # 例如黄色

    # --- 2 绘制各种图元 ---
    sheet_function_map = {
        SHAPE_SHEET_MAP["line"]["sheet_name"]: draw_lines_ezdxf,
        SHAPE_SHEET_MAP["circle"]["sheet_name"]: draw_circles_ezdxf,
        SHAPE_SHEET_MAP["arc"]["sheet_name"]: draw_arcs_ezdxf,
        # 来自您同事的曲线函数 (假设它们接收 msp 和 DataFrame)
        "样条曲线": draw_spline,  # 假设 Sheet 名为 "样条曲线"
        "椭圆弧": draw_ellipse_arc,  # 假设 Sheet 名为 "椭圆弧"
        "公式曲线": draw_formula,  # 假设 Sheet 名为 "公式曲线"
        "多线段拟合曲线": draw_polyfit,  # 假设 Sheet 名为 "多线段拟合曲线"
        "缓和曲线": draw_clothoid,  # 假设 Sheet 名为 "缓和曲线"
        # 新增的函数
        "Ellipse": draw_ellipse_ezdxf,  # 假设您同事的 draw_ellipse 对应 "Ellipse" Sheet
        "Polyline": draw_polyline_ezdxf,  # 假设您同事的 draw_polyline 对应 "Polyline" Sheet
        "Rectangles": draw_rectangle_ezdxf,  # 假设您同事的 draw_rectangle 对应 "Rectangles" Sheet
        "Points": draw_point_ezdxf,  # 假设您同事的 draw_point 对应 "Points" Sheet
        # 填充
        SHAPE_SHEET_MAP["hatch_circle"]["sheet_name"]: draw_hatch_ezdxf,
        SHAPE_SHEET_MAP["hatch_quad"]["sheet_name"]: draw_hatch_ezdxf,
        SHAPE_SHEET_MAP["annotation"]["sheet_name"]: draw_annotations_ezdxf,
        SHAPE_SHEET_MAP["add_length_dimension"]["sheet_name"]: draw_length_dimensions_ezdxf,
        SHAPE_SHEET_MAP["add_radius_dimension"]["sheet_name"]: draw_radius_or_diameter_dimensions_ezdxf,
        SHAPE_SHEET_MAP["angular_dimension"]["sheet_name"]: draw_angular_dimensions_ezdxf,

    }
    enabled_sheets = [
        SHAPE_SHEET_MAP["line"]["sheet_name"],
        # SHAPE_SHEET_MAP["circle"]["sheet_name"],  # <--- 添加 Circles
    ]
    for sheet_name, draw_func in sheet_function_map.items():
        if sheet_name in xls.sheet_names:
            logging.info(f"读取工作表 '{sheet_name}'...")
            try:
                df = xls.parse(sheet_name)
                if df.empty:
                    logging.info(f"工作表 '{sheet_name}' 为空，跳过绘制。")
                    continue
                logging.info(f"开始绘制来自 '{sheet_name}' 的图元...")
                draw_func(msp, df)  # 调用对应的绘制函数
            except Exception as e:
                logging.error(f"处理工作表 '{sheet_name}' 时发生错误: {e}", exc_info=True)
        else:
            is_required_by_map = any(m["sheet_name"] == sheet_name for m in SHAPE_SHEET_MAP.values())
            if is_required_by_map:
                logging.warning(f"Excel 文件中未找到工作表 '{sheet_name}' (在 SHAPE_SHEET_MAP 中定义)。")
            else:
                logging.debug(f"Excel 文件中未找到可选工作表 '{sheet_name}'。")

    # 修改：从Excel文件名生成DXF文件名
    excel_filename = os.path.splitext(os.path.basename(excel_path))[0]
    save_dxf_doc(doc, excel_filename)
    logging.info("所有图元已处理并保存到 DXF 文件。")


# ++++++++++++++++++++++++++ 新增/修改：ezdxf 绘制文字标注 ++++++++++++++++++++++++++
def draw_annotations_ezdxf(msp, annotations_df):
    """使用 ezdxf 在模型空间中绘制文字标注 (MTEXT)"""
    if annotations_df is None or annotations_df.empty:
        logging.info("没有文字标注数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(annotations_df)} 个文字标注...")
    doc = msp.doc  # 获取文档对象以操作图层和文字样式

    for index, row in annotations_df.iterrows():
        anno_id = str(row.get('ID', f'Anno_{index}'))
        try:
            text_content = str(row['Annotation_Name'])  # <--- 对应您截图中的 "Annotation_Name"
            # distance = float(row['Distance']) # 'Distance' 通常不用来直接定位文字，除非有特殊含义
            font_size = float(row.get('Font_Size', 5))  # 默认文字高度
            font_color_index = int(row.get('Font_Color', 7))  # DXF 颜色索引 (ACI)
            layer_name = str(row.get('Layer_Name', '0'))
            position_x = float(row['Position_X'])
            position_y = float(row['Position_Y'])
            position_z = float(row.get('Position_Z', 0.0))  # 假设可选的Z坐标
            raw_rotation = row.get('Rotation')  # <---- 修改：获取 Rotation 列的值 ----
            rotation_deg = 0.0  # 默认不旋转
            if pd.notna(raw_rotation) and str(raw_rotation).strip() != '':  # <---- 修改：检查是否非空且非空字符串 ----
                try:
                    rotation_deg = float(raw_rotation)
                except ValueError:
                    logging.warning(f"文字标注 (ID: {anno_id}): Rotation 值 '{raw_rotation}' 无效，将使用默认值 0 度。")
                    rotation_deg = 0.0
            print(
                f"DEBUG: Annotation ID: {anno_id}, Raw Rotation from Excel: '{raw_rotation}', Parsed Rotation: {rotation_deg}")  # <--- 临时添加这行

            text_style_name_from_excel = str(row.get('Text_Style', '')).strip()  # <------ 修改代码 ------
            if text_style_name_from_excel and doc.styles.has_entry(text_style_name_from_excel):  # <------ 修改代码 ------
                text_style_name = text_style_name_from_excel
            elif doc.styles.has_entry("宋体"):  # <------ 修改代码: 默认尝试 "宋体" ------
                text_style_name = "宋体"
                if text_style_name_from_excel:  # 如果Excel指定了但没找到，给个警告
                    logging.warning(
                        f"文字标注 (ID: {anno_id}): Excel指定的样式 '{text_style_name_from_excel}' 未找到，将使用 '宋体'。")
            else:  # 如果连宋体都没有（理论上不该发生），再用 Standard
                text_style_name = "Standard"
                logging.warning(
                    f"文字标注 (ID: {anno_id}): 样式 '{text_style_name_from_excel}' 或 '宋体' 未找到，将使用 'Standard'。")

            if not text_content:  # 跳过空文本
                logging.warning(f"文字标注 (ID: {anno_id}) 内容为空，跳过。")
                continue

            ensure_layer_exists(doc, layer_name)

            insert_point = (position_x, position_y, position_z)

            # 使用 MTEXT 更灵活
            mtext = msp.add_mtext(text_content, dxfattribs={
                'layer': layer_name,
                'char_height': font_size,
                'style': text_style_name,
                'rotation': rotation_deg,
                'color': font_color_index,  # 可以设置颜色
                # 'attachment_point': ezdxf.const.MTEXT_TOP_LEFT, # 设置附着点
            })
            mtext.dxf.attachment_point = const.MTEXT_MIDDLE_CENTER  # <---- 修改：设置附着点为中中心 ----
            mtext.set_location(insert_point)  # 设置插入点

            logging.info(f"文字标注 (ID: {anno_id}) '{text_content}' 已绘制于 {insert_point}，图层 {layer_name}，高度 {font_size}")

        except KeyError as e:
            logging.error(f"绘制文字标注 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:
            logging.error(f"绘制文字标注 (ID: {row.get('ID', '未知')}) 时数据转换错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"绘制文字标注 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。", exc_info=True)
    logging.info("文字标注绘制完成。")


# ++++++++++++++++++++++++++ 新增/修改：ezdxf 绘制长度尺寸标注 ++++++++++++++++++++++++++
def draw_length_dimensions_ezdxf(msp, length_dims_df):
    if length_dims_df is None or length_dims_df.empty:
        logging.info("没有长度尺寸数据可供绘制。")  # <--- 补充日志
        return
    logging.info(f"开始绘制 {len(length_dims_df)} 个长度尺寸...")
    doc = msp.doc

    for index, row in length_dims_df.iterrows():
        dim_id = str(row.get('ID', f'LenDim_{index}'))  # <------修改代码------ (ID列可能不存在于您的Excel截图，做好兼容)
        try:
            p1x = float(row['起始点X'])
            p1y = float(row['起始点Y'])
            p1z = float(row.get('起始点Z', 0.0))  # 假设有可选的Z列
            p2x = float(row['结束点X'])
            p2y = float(row['结束点Y'])
            p2z = float(row.get('结束点Z', 0.0))

            pt1 = Vec3(p1x, p1y, p1z)
            pt2 = Vec3(p2x, p2y, p2z)
            base_vec = pt2 - pt1

            if base_vec.is_null:
                logging.warning(f"长度尺寸 (ID: {dim_id}) 的基线长度为零或向量模为零，跳过。")
                continue

            excel_text_style_name_input = str(row.get('文字样式', '')).strip()  # <------修改代码------
            actual_text_style_name_for_dim = "Standard"  # 后备的文字样式名

            if excel_text_style_name_input and doc.styles.has_entry(excel_text_style_name_input):
                actual_text_style_name_for_dim = excel_text_style_name_input
            elif doc.styles.has_entry("宋体"):  # 优先尝试 "宋体"
                actual_text_style_name_for_dim = "宋体"
                if excel_text_style_name_input:  # 如果Excel指定了但没找到
                    logging.warning(
                        f"尺寸标注(ID: {dim_id}): Excel指定的文字样式 '{excel_text_style_name_input}' 未找到，将使用 '{actual_text_style_name_for_dim}'。")
            elif doc.styles.has_entry("Standard_Text"):  # 备用
                actual_text_style_name_for_dim = "Standard_Text"
                logging.warning(
                    f"尺寸标注(ID: {dim_id}): 文字样式 '{excel_text_style_name_input}' 及 '宋体' 未找到，将使用 '{actual_text_style_name_for_dim}'。")
            else:  # 最后的后备，确保Standard存在
                if not doc.styles.has_entry("Standard"):
                    doc.styles.new("Standard", dxfattribs={"font": "txt.shx"})  # 创建一个最基础的
                actual_text_style_name_for_dim = "Standard"
                logging.warning(f"尺寸标注(ID: {dim_id}): 未找到任何合适的预定义文字样式，将使用基础 'Standard'。")

            # Excel 列名可能是 "尺寸样式名" (如果用户想直接指定)
            # 否则，我们基于文字样式名生成一个
            dim_style_name_input = str(row.get('尺寸样式名', '')).strip()  # <------修改代码------
            actual_dim_style_name = f"{actual_text_style_name_for_dim}_Dim_Len_{dim_id}"  # <---确保唯一性
            if dim_style_name_input and doc.dimstyles.has_entry(dim_style_name_input):
                actual_dim_style_name = dim_style_name_input
            else:
                actual_dim_style_name = f"{actual_text_style_name_for_dim}_Dim_{dim_id}"  # <------修改代码------ (确保唯一性，并与文字样式关联)
                if dim_style_name_input:
                    logging.warning(
                        f"尺寸标注(ID: {dim_id}): Excel指定的尺寸样式 '{dim_style_name_input}' 未找到，将创建/使用 '{actual_dim_style_name}'。")

            # <------修改代码------ (更全面地处理Excel列的空值和格式)
            # 字体大小
            raw_font_size_val = row.get('字体大小')
            dim_font_size = GLOBAL_ID_TEXT_HEIGHT if GLOBAL_ID_TEXT_HEIGHT is not None else 7.0  # <------修改代码------ (使用更显著的默认值或全局值)
            if pd.notna(raw_font_size_val):
                try:
                    val = float(raw_font_size_val)
                    if val > 0:
                        dim_font_size = val
                    else:
                        logging.warning(f"尺寸 (ID: {dim_id}): 字体大小 '{raw_font_size_val}' 无效 (<=0)，使用默认值 {dim_font_size}")
                except ValueError:
                    logging.warning(f"尺寸 (ID: {dim_id}): 字体大小 '{raw_font_size_val}' 无法转换为数字，使用默认值 {dim_font_size}")
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 字体大小为空，使用默认值 {dim_font_size}")

            # 箭头大小
            raw_arrow_size_val = row.get('箭头大小')
            dim_arrow_size = dim_font_size * 0.7 if dim_font_size > 0 else (
                GLOBAL_ID_TEXT_HEIGHT * 0.7 if GLOBAL_ID_TEXT_HEIGHT is not None else 5.0)  # <------修改代码------
            if pd.notna(raw_arrow_size_val):
                try:
                    val = float(raw_arrow_size_val)
                    if val > 0:
                        dim_arrow_size = val
                    else:
                        logging.warning(
                            f"尺寸 (ID: {dim_id}): 箭头大小 '{raw_arrow_size_val}' 无效 (<=0)，使用默认值 {dim_arrow_size}")
                except ValueError:
                    logging.warning(f"尺寸 (ID: {dim_id}): 箭头大小 '{raw_arrow_size_val}' 无法转换为数字，使用默认值 {dim_arrow_size}")
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 箭头大小为空，使用默认值 {dim_arrow_size}")

            # 标注精度
            raw_precision_val = row.get('标注精度')
            dim_precision = 2  # 默认精度
            if pd.notna(raw_precision_val):
                try:
                    val = int(raw_precision_val)
                    if 0 <= val <= 8:  # DXF dimdec 通常在0-8
                        dim_precision = val
                    else:
                        logging.warning(
                            f"尺寸 (ID: {dim_id}): 标注精度 '{raw_precision_val}' 超出有效范围(0-8)，使用默认值 {dim_precision}")
                except ValueError:
                    logging.warning(f"尺寸 (ID: {dim_id}): 标注精度 '{raw_precision_val}' 无法转换为整数，使用默认值 {dim_precision}")
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 标注精度为空，使用默认值 {dim_precision}")

            # 颜色 (ACI)
            raw_color_val = row.get('颜色')
            dim_color = const.BYLAYER  # 默认颜色
            if pd.notna(raw_color_val):
                try:
                    val = int(raw_color_val)
                    if 0 <= val <= 256:  # ACI颜色范围
                        dim_color = val
                    else:
                        logging.warning(f"尺寸 (ID: {dim_id}): 颜色索引 '{raw_color_val}' 超出有效范围(0-256)，使用默认值 BYLAYER")
                except ValueError:
                    logging.warning(f"尺寸 (ID: {dim_id}): 颜色 '{raw_color_val}' 无法转换为整数，使用默认值 BYLAYER")
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 颜色为空，使用默认值 BYLAYER")

            # 图层名称
            raw_layer_name = row.get('图层名称')
            layer_name = "DIMENSIONS"  # 默认图层
            if pd.notna(raw_layer_name) and str(raw_layer_name).strip():
                layer_name = str(raw_layer_name).strip()
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 图层名称为空，使用默认图层 '{layer_name}'")
            # <------修改代码结束------

            # 文字位置 (dim_line_point_from_excel) 和 偏移距离 (distance_for_aligned_dim_api) 的计算
            user_defined_location = None
            dim_line_location_specified_by_user = False  # <------修改代码------ (明确初始化)
            raw_text_pos_x = row.get('文字位置X')
            raw_text_pos_y = row.get('文字位置Y')

            if pd.notna(raw_text_pos_x) and pd.notna(raw_text_pos_y):  # 只有X和Y都非空才认为指定了
                try:
                    text_pos_x_excel = float(row['文字位置X'])
                    text_pos_y_excel = float(row['文字位置Y'])
                    text_pos_z_excel = float(
                        row.get('文字位置Z', (pt1.z + pt2.z) / 2.0 if pd.notna(pt1.z) and pd.notna(pt2.z) else 0.0))
                    # 进一步检查 text_pos_x/y_excel 是否为 NaN (如果 float('') 发生)
                    if not (math.isnan(text_pos_x_excel) or math.isnan(text_pos_y_excel)):
                        user_defined_location = Vec3(text_pos_x_excel, text_pos_y_excel, text_pos_z_excel)
                        dim_line_location_specified_by_user = True
                        logging.debug(f"尺寸 (ID: {dim_id}): 用户指定文字位置参考点 {user_defined_location}")
                    else:
                        logging.warning(f"尺寸 (ID: {dim_id}): 文字位置X或Y解析为NaN。将使用默认偏移。")

                except (KeyError, ValueError) as e_pos:
                    logging.warning(f"尺寸 (ID: {dim_id}): 文字位置数据缺失或格式错误: {e_pos}。将使用默认偏移。")
                    dim_line_location_specified_by_user = False  # 重置标志
            else:
                logging.debug(f"尺寸 (ID: {dim_id}): 用户未指定文字位置，将使用默认偏移。")

            # --- 尺寸类型创建逻辑 ---
            dim_type_from_excel = str(row.get('标注类型', '对齐')).lower().strip()  # <------修改代码------ (默认"对齐"更符合平行需求)
            direction_from_excel = str(row.get('方向', '自动')).lower().strip()
            # 默认使用对齐标注，除非明确指定为特定角度的线性标注
            use_aligned_dim = True
            linear_angle_rad = 0.0

            is_horizontal = abs(pt1.y - pt2.y) < 1e-6 and abs(pt1.z - pt2.z) < 1e-6  # 近似水平 (XY平面内)
            is_vertical = abs(pt1.x - pt2.x) < 1e-6 and abs(pt1.z - pt2.z) < 1e-6  # 近似垂直 (XY平面内)

            # <------修改代码------ (优先对齐，除非明确指定线性且有方向)
            if ("线性" in dim_type_from_excel or (
                    "长度" in dim_type_from_excel and direction_from_excel not in ["auto", "自动", ""])) \
                    and direction_from_excel not in ["auto", "自动", ""]:  # 必须有明确的非自动方向才算线性
                use_aligned_dim = False
                if direction_from_excel in ["水平", "0", "0.0"]:
                    linear_angle_rad = math.radians(0.0)
                elif direction_from_excel in ["垂直", "90", "90.0"]:
                    linear_angle_rad = math.radians(90.0)
                else:  # 尝试解析角度
                    try:
                        angle_val = float(direction_from_excel)
                        if not math.isnan(angle_val):
                            linear_angle_rad = math.radians(angle_val)
                        else:  # 方向解析为NaN，回退到对齐
                            use_aligned_dim = True
                            logging.warning(
                                f"尺寸 (ID: {dim_id}): 线性标注方向 '{direction_from_excel}' 解析为NaN，将使用对齐标注。")
                    except ValueError:  # 方向无法解析为角度，回退到对齐
                        use_aligned_dim = True
                        logging.warning(
                            f"尺寸 (ID: {dim_id}): 线性标注方向 '{direction_from_excel}' 无效，将使用对齐标注。")
            else:  # 其他所有情况（包括"对齐"、"长度"+"自动"、"长度"+空方向等）都使用对齐
                use_aligned_dim = True
                if "线性" in dim_type_from_excel and direction_from_excel in ["auto", "自动", ""]:
                    logging.info(f"尺寸 (ID: {dim_id}): 类型为'线性'但方向为'自动'，将使用对齐标注。")
            ensure_layer_exists(doc, layer_name,
                                color=dim_color if dim_color != const.BYLAYER else None)  # <------ 修改代码: 确保图层存在 ------

            # 确保 TEXTSTYLE (被 DIMSTYLE 引用) 存在
            if not doc.dimstyles.has_entry(actual_dim_style_name):
                logging.info(f"尺寸样式 '{actual_dim_style_name}' (ID: {dim_id}) 在DXF中不存在。将创建新的。")
                current_dimstyle_obj = doc.dimstyles.new(name=actual_dim_style_name)
            else:
                logging.info(f"尺寸样式 '{actual_dim_style_name}' (ID: {dim_id}) 已存在。将使用并更新其属性。")
                current_dimstyle_obj = doc.dimstyles.get(actual_dim_style_name)

            # 统一设置/覆盖 DIMSTYLE 属性 <------ 修改代码: 核心修改点 ------
            current_dimstyle_obj.dxf.dimtxsty = actual_text_style_name_for_dim  # 尺寸文字使用的文字样式名称
            current_dimstyle_obj.dxf.dimtxt = dim_font_size  # 文字高度
            current_dimstyle_obj.dxf.dimasz = dim_arrow_size  # 箭头大小
            current_dimstyle_obj.dxf.dimclrd = dim_color  # 尺寸线、界线、箭头颜色
            current_dimstyle_obj.dxf.dimclrt = dim_color  # 文字颜色 (若与dimclrd不同)
            current_dimstyle_obj.dxf.dimdec = dim_precision  # 精度
            current_dimstyle_obj.dxf.dimtad = 0  # 0 = Text centered and breaks dim line; 1 = Text above dim line

            # Excel 列 "延伸线长度" (N列) - dimexe (Extension line extension)
            raw_dimexe = row.get('延伸线长度')  # <------修改代码------
            if pd.notna(raw_dimexe):
                try:
                    current_dimstyle_obj.dxf.dimexe = float(raw_dimexe)
                except ValueError:
                    logging.warning(f"尺寸 (ID: {dim_id}): 延伸线长度 '{raw_dimexe}' 无效。")
            else:
                current_dimstyle_obj.dxf.dimexe = dim_arrow_size * 0.75  # 默认

            current_dimstyle_obj.dxf.dimexo = dim_arrow_size * 0.5  # 界线超出尺寸线的长度 (Offset from origin)
            current_dimstyle_obj.dxf.dimgap = dim_arrow_size * 0.25  # 文字与尺寸线间隙

            arrow_style_name = str(row.get('箭头样式', '')).strip()  # <------修改代码------
            if arrow_style_name:
                # ezdxf 内部会将 "箭头样式1" 映射到 AutoCAD 的箭头类型
                # 或者可以直接设置 DIMBLK, DIMBLK1, DIMBLK2, DIMSAH, DIMLDRBLK
                # 为了简单，如果Excel提供了，我们尝试设置dimblk
                # 注意：ezdxf 1.x 可能没有直接的 dimblk 映射，而是通过 builder.set_arrows
                # 对于更细致的箭头控制，可能需要用 builder.set_arrows(blk="...")
                # current_dimstyle_obj.dxf.dimblk = arrow_style_name # 谨慎使用，需确认ezdxf版本和支持
                logging.info(f"尺寸 (ID: {dim_id}): Excel指定箭头样式 '{arrow_style_name}'。ezdxf默认箭头行为。")

            # --- 绘制对齐或线性尺寸 (保持之前的健壮性) ---
            if use_aligned_dim:
                offset_distance = dim_font_size * 3.0  # 默认偏移
                if dim_line_location_specified_by_user and user_defined_location:
                    # 用户指定了点，计算该点到被测线的垂直距离作为偏移
                    ap_vec = user_defined_location - pt1
                    ab_vec = pt2 - pt1
                    if ab_vec.magnitude > 1e-9:
                        cross_product_mag = ap_vec.cross(ab_vec).magnitude
                        calculated_offset = cross_product_mag / ab_vec.magnitude
                        if not math.isnan(calculated_offset) and calculated_offset >= dim_font_size * 0.25:  # 允许更小的偏移
                            offset_distance = calculated_offset
                        # 检查 user_defined_location 是否包含 NaN (虽然理论上前面已处理)
                        if any(math.isnan(c) for c in user_defined_location.xyz):
                            logging.warning(
                                f"对齐尺寸 (ID: {dim_id}): 用户定义的文字位置包含NaN，无法计算偏移。将使用默认偏移。")
                            # offset_distance 保持默认值
                        else:
                            cross_product_mag = ap_vec.cross(ab_vec).magnitude
                            calculated_offset = cross_product_mag / ab_vec.magnitude
                            if not math.isnan(calculated_offset) and calculated_offset >= dim_font_size * 0.5:
                                offset_distance = calculated_offset
                            elif math.isnan(calculated_offset):
                                logging.warning(
                                    f"对齐尺寸 (ID: {dim_id}): 计算出的偏移为 NaN。将使用默认偏移 {offset_distance:.3f}。")
                            else:  # calculated_offset is a number but too small
                                logging.warning(
                                    f"对齐尺寸 (ID: {dim_id}): 用户指定位置计算出的偏移 ({calculated_offset:.3f}) 过小。将使用默认偏移 {offset_distance:.3f}。")
                    else:  # ab_vec.magnitude 太小或为0
                        if any(math.isnan(c) for c in user_defined_location.xyz):
                            logging.warning(
                                f"对齐尺寸 (ID: {dim_id}): 基线长度过小且用户定义的文字位置包含NaN。将使用默认偏移。")
                            # offset_distance 保持默认值
                        elif user_defined_location is not None:  # 确保它不是 None
                            calculated_offset = user_defined_location.distance(pt1)
                            if not math.isnan(calculated_offset) and calculated_offset >= dim_font_size * 0.5:
                                offset_distance = calculated_offset
                            elif math.isnan(calculated_offset):
                                logging.warning(
                                    f"对齐尺寸 (ID: {dim_id}): 距离计算为 NaN。将使用默认偏移 {offset_distance:.3f}。")
                            else:
                                logging.warning(
                                    f"对齐尺寸 (ID: {dim_id}): 距离 ({calculated_offset:.3f}) 过小。将使用默认偏移 {offset_distance:.3f}。")
                else:  # 用户未指定位置，使用默认偏移
                    logging.debug(f"对齐尺寸 (ID: {dim_id}): 使用默认偏移 {offset_distance:.3f}")

                dim = msp.add_aligned_dim(
                    p1=pt1, p2=pt2,
                    distance=offset_distance,
                    dimstyle=actual_dim_style_name,
                    dxfattribs={'layer': layer_name}
                )
                logging.info(f"对齐长度尺寸 (ID: {dim_id}, Offset: {offset_distance:.3f}) 已绘制。")
            else:  # 线性标注
                default_offset_val = dim_font_size * 2.0  # <------修改代码------
                dim_line_base_point = mid_point_base = (pt1 + pt2) / 2
                # 计算线性标注的基点 (dim_line_location)
                # 如果用户指定了文字位置，并且是线性标注，这个点可以作为尺寸线通过的点 (base)
                if dim_line_location_specified_by_user and user_defined_location:
                    dim_line_base_point = user_defined_location
                    logging.debug(f"线性尺寸 (ID: {dim_id}): 使用用户指定的文字位置 {user_defined_location} 作为基点。")
                else:
                    # 自动计算偏移方向
                    # 对于水平标注 (angle=0), 偏移通常在Y方向 对于垂直标注 (angle=90), 偏移通常在X方向
                    # 对于任意角度线性标注，偏移方向垂直于标注线方向
                    dim_line_dir_rad = linear_angle_rad
                    offset_normal_rad = dim_line_dir_rad + math.pi / 2  # 垂直于尺寸线方向
                    offset_vec_dir = Vec3.from_angle(offset_normal_rad, length=1)

                    # 确保偏移方向与被测线段有区分度，避免重叠
                    # 简单的策略：检查点积，如果方向太接近，反转偏移
                    base_line_dir_vec = (pt2 - pt1).normalize_or_zero()
                    if abs(offset_vec_dir.dot(base_line_dir_vec)) > 0.95:  # 如果偏移方向与基线太平行
                        offset_vec_dir = offset_vec_dir.rotate_deg(90)  # 再旋转90度

                    dim_line_base_point = mid_point_base + offset_vec_dir * default_offset_val
                    logging.debug(
                        f"线性尺寸 (ID: {dim_id}): 自动计算基点 {dim_line_base_point}，偏移方向 {offset_vec_dir}")

                dim = msp.add_linear_dim(
                    base=dim_line_base_point,
                    p1=pt1, p2=pt2, angle=linear_angle_rad,
                    dimstyle=actual_dim_style_name,
                    dxfattribs={'layer': layer_name}
                )
                logging.info(
                    f"线性长度尺寸 (ID: {dim_id}, Base: {dim_line_base_point}, Angle: {math.degrees(linear_angle_rad):.1f}°) 已绘制。")

        except KeyError as e:
            logging.error(f"绘制长度尺寸 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:  # <----------新增---------
            logging.error(f"绘制长度尺寸 (ID: {row.get('ID', '未知')}) 时数据转换错误: {e}。行数据: {row.to_dict()}",
                          exc_info=True)
        except Exception as e:  # <----------新增---------
            logging.error(f"绘制长度尺寸 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。行数据: {row.to_dict()}",
                          exc_info=True)
    logging.info("长度尺寸绘制完成。")


# ++++++++++++++++++++++++++ 新增：ezdxf 绘制半径/直径尺寸标注 ++++++++++++++++++++++++++
def draw_radius_or_diameter_dimensions_ezdxf(msp, radius_dims_df):
    if radius_dims_df is None or radius_dims_df.empty:
        logging.info(
            f"工作表 '{SHAPE_SHEET_MAP['add_radius_dimension']['sheet_name']}' 为空，跳过绘制。")  # <------修改代码------ (更明确的日志)
        return
    logging.info(f"开始绘制 {len(radius_dims_df)} 个半径/直径尺寸...")
    doc = msp.doc

    for index, row in radius_dims_df.iterrows():
        dim_id = str(row.get('ID', f'RadDim_{index}'))
        try:
            # <------修改代码------ (严格的类型检查放在前面)
            # Excel 列 "标注类型" (B列)
            dim_type_str_excel_raw = row.get('标注类型')  # 获取原始值，不做lower()和strip()，用于日志
            dim_type_str_excel = str(dim_type_str_excel_raw).lower().strip()  # 先获取Excel原始值

            is_radius_dim = "半径" in dim_type_str_excel or "radius" in dim_type_str_excel
            is_diameter_dim = "直径" in dim_type_str_excel or "diameter" in dim_type_str_excel

            if not (is_radius_dim or is_diameter_dim):
                logging.error(
                    f"半径/直径标注 (ID: {dim_id}): Excel中的标注类型({dim_type_str_excel_raw}) 无效。应为半径或直径跳过此行。" )
                continue  # 直接跳过这一行数据的处理
            # <------修改代码结束------

            # --- 坐标和半径读取 (严格按照Excel列名) ---
            try:
                center_x = float(row['圆心X'])
                center_y = float(row['圆心Y'])
                center_z = float(row.get('圆心Z', 0.0))
                radius_value = float(row['半径'])
                raw_text_pos_x = row.get('文字位置X')
                raw_text_pos_y = row.get('文字位置Y')
                raw_text_pos_z = row.get('文字位置Z', 0.0)
            except (KeyError, ValueError) as e:
                logging.error(f"半径/直径标注 (ID: {dim_id}): 必要的几何数据缺失或格式错误: {e}。跳过。")
                continue

            if radius_value <= 0:
                logging.warning(f"半径/直径标注 (ID: {dim_id}) 半径无效 ({radius_value})，跳过。")
                continue

            # Excel 列 "图层名称" (H列)
            raw_layer_name = row.get('图层名称')
            layer_name = "DIMENSIONS_RADIUS"  # 更具体的默认图层名
            if pd.notna(raw_layer_name) and str(raw_layer_name).strip():
                layer_name = str(raw_layer_name).strip()
            else:
                logging.debug(f"半径/直径标注 (ID: {dim_id}): 图层名称为空，使用默认图层 '{layer_name}'")

            # Excel 列 "文字样式" (J列) - 用于DIMSTYLE的文字样式
            excel_text_style_name_input = str(row.get('文字样式', '')).strip()
            actual_text_style_name_for_dim = "Standard"  # 后备

            if excel_text_style_name_input and doc.styles.has_entry(excel_text_style_name_input):
                actual_text_style_name_for_dim = excel_text_style_name_input
            elif doc.styles.has_entry("宋体"):
                actual_text_style_name_for_dim = "宋体"
                if excel_text_style_name_input:
                    logging.warning(
                        f"半径/直径标注(ID: {dim_id}): Excel指定的文字样式 '{excel_text_style_name_input}' 未找到，将使用 '{actual_text_style_name_for_dim}'。")
            # ... (其他文字样式后备逻辑同上)

            # 尺寸样式名 - 基于文字样式生成，确保唯一性
            actual_dim_style_name = f"{actual_text_style_name_for_dim}_Dim_Rad_{dim_id}"  # <------修改代码------

            # 字体大小, 箭头大小, 颜色, 精度 - 这些列在您的半径标注Excel截图中没有，
            # 所以我们将使用基于GLOBAL_ID_TEXT_HEIGHT或通用默认值。
            # 如果将来Excel中添加这些列，这里的逻辑需要更新。
            current_dim_font_size = GLOBAL_ID_TEXT_HEIGHT if GLOBAL_ID_TEXT_HEIGHT is not None else 7.0
            current_dim_arrow_size = current_dim_font_size * 0.7 if current_dim_font_size > 0 else 5.0
            dim_color = const.BYLAYER  # 默认
            dim_precision = 2  # 默认
            # <------修改代码结束------

            ensure_layer_exists(doc, layer_name, color=dim_color if dim_color != const.BYLAYER else None)

            # --- 获取或创建 DIMSTYLE ---
            if not doc.dimstyles.has_entry(actual_dim_style_name):
                logging.info(f"尺寸样式 '{actual_dim_style_name}' (ID: {dim_id}) 在DXF中不存在。将创建新的。")
                current_dimstyle_obj = doc.dimstyles.new(name=actual_dim_style_name)
            else:
                logging.info(f"尺寸样式 '{actual_dim_style_name}' (ID: {dim_id}) 已存在。将使用并更新其属性。")
                current_dimstyle_obj = doc.dimstyles.get(actual_dim_style_name)

            # --- 应用属性到 DIMSTYLE ---
            current_dimstyle_obj.dxf.dimtxsty = actual_text_style_name_for_dim
            current_dimstyle_obj.dxf.dimtxt = current_dim_font_size
            current_dimstyle_obj.dxf.dimasz = current_dim_arrow_size
            current_dimstyle_obj.dxf.dimclrd = dim_color
            current_dimstyle_obj.dxf.dimclrt = dim_color
            current_dimstyle_obj.dxf.dimdec = dim_precision
            current_dimstyle_obj.dxf.dimtad = 1  # 对于半径/直径，文字通常在尺寸线上方或外部 (ACAD: Above dimension line)

            # --- 计算几何点 ---
            center_pt_vec = Vec3(center_x, center_y, center_z)
            # measurement_point: 圆周上的一点 (任意角度，例如0度)
            measurement_pt_on_circle = center_pt_vec + Vec3.from_angle(math.radians(0), length=radius_value)

            # --- 处理 leader_point (文字位置) ---
            leader_pt_vec = None
            text_pos_x_val, text_pos_y_val, text_pos_z_val = None, None, center_z

            can_parse_text_pos = False
            if pd.notna(raw_text_pos_x) and pd.notna(raw_text_pos_y):
                try:
                    text_pos_x_val = float(raw_text_pos_x)
                    text_pos_y_val = float(raw_text_pos_y)
                    text_pos_z_val = float(raw_text_pos_z if pd.notna(raw_text_pos_z) else center_z)

                    if not (math.isnan(text_pos_x_val) or math.isnan(text_pos_y_val)):
                        leader_pt_vec = Vec3(text_pos_x_val, text_pos_y_val, text_pos_z_val)
                        can_parse_text_pos = True
                    else:
                        logging.warning(
                            f"半径/直径标注 (ID: {dim_id}): 文字位置X或Y ('{raw_text_pos_x}', '{raw_text_pos_y}') 解析为NaN。")
                except ValueError:
                    logging.warning(
                        f"半径/直径标注 (ID: {dim_id}): 文字位置X或Y ('{raw_text_pos_x}', '{raw_text_pos_y}') 无法转换为数字。")

            if can_parse_text_pos:
                leader_pt_vec = Vec3(text_pos_x_val, text_pos_y_val, text_pos_z_val)
                logging.debug(f"半径/直径标注 (ID: {dim_id}): 用户指定leader点 {leader_pt_vec}")
            else:
                logging.warning(f"半径/直径标注 (ID: {dim_id}): 文字位置无效或未提供，将自动计算leader点。")
                # 自动计算 leader_point: 从圆心指向 measurement_pt_on_circle 再向外延伸
                # 方向是从圆心到测量点
                dir_to_measurement = (measurement_pt_on_circle - center_pt_vec).normalize()
                # leader点通常在测量点之外，沿此方向
                leader_offset_dist = current_dim_font_size * 1.5  # 偏移文字高度的1.5倍，确保文字不与圆周重叠
                leader_pt_vec = measurement_pt_on_circle + dir_to_measurement * leader_offset_dist

            # --- 绘制标注 (基于 is_radius_dim, is_diameter_dim) ---
            if is_radius_dim:
                direction_vec_from_center_to_leader = leader_pt_vec - center_pt_vec
                if direction_vec_from_center_to_leader.magnitude < 1e-6:  # leader点与圆心重合
                    def_angle_rad = math.radians(45)  # 使用默认角度
                else:
                    def_angle_rad = direction_vec_from_center_to_leader.angle  # 获取弧度

                measurement_point_on_circle = center_pt_vec + Vec3.from_angle(def_angle_rad, radius_value)

                dim = msp.add_radius_dim(center=center_pt_vec, radius=radius_value, angle=def_angle_rad,
                                         dxfattribs={'layer': layer_name})  # <------修改代码------

                logging.info(
                    f"半径尺寸 (ID: {dim_id}, Style: {actual_dim_style_name}) 已绘制。Measurement point: {measurement_point_on_circle}")

            elif is_diameter_dim:
                direction_vec_from_center_to_leader = leader_pt_vec - center_pt_vec
                if direction_vec_from_center_to_leader.magnitude < 1e-6:
                    def_angle_rad = math.radians(45)
                else:
                    def_angle_rad = direction_vec_from_center_to_leader.angle  # 获取弧度
                dir_diam = Vec3.from_angle(def_angle_rad, 1)  # 单位向量

                p1_diam = center_pt_vec + dir_diam * radius_value
                p2_diam = center_pt_vec - dir_diam * radius_value

                dim = msp.add_diameter_dim_2p(
                    p1=p1_diam, p2=p2_diam,  # 直径的两个端点
                    dimstyle=actual_dim_style_name,
                    dxfattribs={'layer': layer_name}
                )
                logging.info(f"直径尺寸 (ID: {dim_id}, Style: {actual_dim_style_name}) 已绘制。")
            # (这里的 else 分支不再需要，因为前面已经 continue 了)

        except KeyError as e:
            logging.error(f"绘制半径/直径尺寸 (ID: {row.get('ID', '未知')}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:
            logging.error(f"绘制半径/直径尺寸 (ID: {row.get('ID', '未知')}) 时数据转换错误: {e}。行数据: {row.to_dict()}")
        except Exception as e:
            logging.error(f"绘制半径/直径尺寸 (ID: {row.get('ID', '未知')}) 时发生未知错误: {e}。", exc_info=True)
    logging.info("半径/直径尺寸绘制完成。")


def draw_angular_dimensions_ezdxf(msp, angular_dims_df):
    if angular_dims_df is None or angular_dims_df.empty:
        logging.info("没有角度尺寸数据可供绘制。")
        return
    logging.info(f"开始绘制 {len(angular_dims_df)} 个角度尺寸...")
    doc = msp.doc

    for index, row in angular_dims_df.iterrows():
        dim_id = str(row.get('ID', f'AngDim_{index}'))
        try:
            # --- 几何点 ---
            try:
                center_x = float(row['Center_X'])
                center_y = float(row['Center_Y'])
                raw_center_z = row.get('Center_Z')
                center_z = float(raw_center_z) if pd.notna(raw_center_z) and str(raw_center_z).strip() != "" else 0.0

                p1_x = float(row['P1_X'])
                p1_y = float(row['P1_Y'])
                raw_p1_z = row.get('P1_Z')
                p1_z = float(raw_p1_z) if pd.notna(raw_p1_z) and str(raw_p1_z).strip() != "" else 0.0

                p2_x = float(row['P2_X'])
                p2_y = float(row['P2_Y'])
                raw_p2_z = row.get('P2_Z')
                p2_z = float(raw_p2_z) if pd.notna(raw_p2_z) and str(raw_p2_z).strip() != "" else 0.0

            except (KeyError, ValueError) as e:
                logging.error(f"角度标注 (ID: {dim_id}): 必要的几何坐标数据缺失或格式错误: {e}。跳过。")
                continue

            apex_pt = Vec3(center_x, center_y, center_z)
            leg1_pt = Vec3(p1_x, p1_y, p1_z)
            leg2_pt = Vec3(p2_x, p2_y, p2_z)

            if any(math.isnan(c) for c in apex_pt.xyz) or \
                    any(math.isnan(c) for c in leg1_pt.xyz) or \
                    any(math.isnan(c) for c in leg2_pt.xyz):
                logging.error(
                    f"角度标注 (ID: {dim_id}): 输入坐标包含NaN值。顶点: {apex_pt}, 腿1: {leg1_pt}, 腿2: {leg2_pt}。跳过。")
                continue

            if apex_pt.isclose(leg1_pt) or apex_pt.isclose(leg2_pt) or leg1_pt.isclose(leg2_pt):
                logging.warning(f"角度标注 (ID: {dim_id}): 定义角度的三个点过于接近或重合。跳过。")
                continue

            vec_apex_to_leg1 = leg1_pt - apex_pt
            vec_apex_to_leg2 = leg2_pt - apex_pt
            if vec_apex_to_leg1.is_null or vec_apex_to_leg2.is_null or vec_apex_to_leg1.is_parallel(vec_apex_to_leg2):
                logging.warning(f"角度标注 (ID: {dim_id}): 从角顶点到边上的点的向量为零或平行。跳过。")
                continue

            # --- 样式和属性 ---
            layer_name = str(row.get('Layer_Name', "DIMENSIONS_ANGULAR"))
            ensure_layer_exists(doc, layer_name)

            excel_text_style_name_raw = row.get('Text_Style')
            excel_text_style_name = str(excel_text_style_name_raw).strip() if pd.notna(
                excel_text_style_name_raw) else ""
            actual_text_style_name = "Standard"
            if excel_text_style_name and doc.styles.has_entry(excel_text_style_name):
                actual_text_style_name = excel_text_style_name
            elif doc.styles.has_entry("宋体"):
                actual_text_style_name = "宋体"
                if excel_text_style_name: logging.warning(
                    f"角度标注 (ID: {dim_id}): 文字样式 '{excel_text_style_name}' 未找到，使用 '{actual_text_style_name}'。")

            dim_style_name_input_raw = row.get('DimStyle_Name')
            dim_style_name_input = str(dim_style_name_input_raw).strip() if pd.notna(dim_style_name_input_raw) else ""

            if dim_style_name_input and dim_style_name_input.lower() != 'nan' and doc.dimstyles.has_entry(
                    dim_style_name_input):
                actual_dim_style_name = dim_style_name_input
            elif dim_style_name_input and dim_style_name_input.lower() != 'nan':
                actual_dim_style_name = dim_style_name_input
                logging.warning(
                    f"角度标注 (ID: {dim_id}): Excel指定的尺寸样式 '{dim_style_name_input}' 未找到，将创建新的同名样式。")
            else:
                actual_dim_style_name = f"DIM_ANG_{actual_text_style_name}_{dim_id}"
                if dim_style_name_input_raw is not None and str(dim_style_name_input_raw).lower() == 'nan':
                    logging.info(
                        f"角度标注 (ID: {dim_id}): DimStyle_Name 为空或'nan'，动态生成样式名 '{actual_dim_style_name}'。")

            if not doc.dimstyles.has_entry(actual_dim_style_name):
                dim_style = doc.dimstyles.new(name=actual_dim_style_name)
                logging.info(f"角度标注 (ID: {dim_id}): 创建新尺寸样式 '{actual_dim_style_name}'。")
            else:
                dim_style = doc.dimstyles.get(actual_dim_style_name)
                logging.info(f"角度标注 (ID: {dim_id}): 使用已存在尺寸样式 '{actual_dim_style_name}'。")

            dim_style.dxf.dimtxsty = actual_text_style_name

            raw_text_height = row.get('Text_Height')
            dim_text_height = GLOBAL_ID_TEXT_HEIGHT if GLOBAL_ID_TEXT_HEIGHT is not None else 3.5
            if pd.notna(raw_text_height) and str(raw_text_height).strip() != "":
                try:
                    val = float(raw_text_height)
                    if val > 1e-6: dim_text_height = val
                except ValueError:
                    logging.warning(
                        f"角度标注 (ID: {dim_id}): 无效的字体大小 '{raw_text_height}'，使用默认 {dim_text_height}。")
            dim_style.dxf.dimtxt = dim_text_height

            raw_arrow_size = row.get('Arrow_Size')
            dim_arrow_size = dim_text_height * 0.7
            if pd.notna(raw_arrow_size) and str(raw_arrow_size).strip() != "":
                try:
                    val = float(raw_arrow_size)
                    if val > 1e-6: dim_arrow_size = val
                except ValueError:
                    logging.warning(
                        f"角度标注 (ID: {dim_id}): 无效的箭头大小 '{raw_arrow_size}'，使用默认 {dim_arrow_size}。")
            dim_style.dxf.dimasz = dim_arrow_size

            raw_color = row.get('Color')
            dim_color_aci = const.BYLAYER
            if pd.notna(raw_color) and str(raw_color).strip() != "":
                try:
                    val = int(float(raw_color))
                    if 0 <= val <= 256:
                        dim_color_aci = val
                    else:
                        logging.warning(f"角度标注 (ID: {dim_id}): 颜色索引 '{raw_color}' 无效，使用BYLAYER。")
                except ValueError:
                    logging.warning(f"角度标注 (ID: {dim_id}): 颜色值 '{raw_color}' 无效，使用BYLAYER。")
            dim_style.dxf.dimclrd = dim_color_aci
            dim_style.dxf.dimclrt = dim_color_aci

            raw_precision = row.get('Precision')
            dim_adec = 2
            if pd.notna(raw_precision) and str(raw_precision).strip() != "":
                try:
                    val = int(float(raw_precision))
                    if 0 <= val <= 8:
                        dim_adec = val
                    else:
                        logging.warning(
                            f"角度标注 (ID: {dim_id}): 角度精度 '{raw_precision}' 无效，使用默认 {dim_adec}。")
                except ValueError:
                    logging.warning(f"角度标注 (ID: {dim_id}): 角度精度值 '{raw_precision}' 无效，使用默认 {dim_adec}。")
            dim_style.dxf.dimadec = dim_adec
            dim_style.dxf.dimaunit = 0

            # --- 确保尺寸界线显示 -
            dim_style.dxf.dimse1 = 0
            dim_style.dxf.dimse2 = 0

            dim_style.dxf.dimexo = 0
            dim_style.dxf.dimexe = dim_arrow_size * 0.5

            dim_style.dxf.dimtad = 0
            dim_style.dxf.dimcen = 0

            base_for_api = None
            raw_dl_x, raw_dl_y, raw_dl_z = row.get('Dim_Line_Location_X'), row.get('Dim_Line_Location_Y'), row.get(
                'Dim_Line_Location_Z')

            dl_x_val = float(raw_dl_x) if pd.notna(raw_dl_x) and str(raw_dl_x).strip() != "" else None
            dl_y_val = float(raw_dl_y) if pd.notna(raw_dl_y) and str(raw_dl_y).strip() != "" else None
            dl_z_val = float(raw_dl_z) if pd.notna(raw_dl_z) and str(
                raw_dl_z).strip() != "" else apex_pt.z  # Default Z to apex_pt's Z

            if dl_x_val is not None and dl_y_val is not None:
                base_for_api = Vec3(dl_x_val, dl_y_val, dl_z_val)
                logging.debug(f"角度标注 (ID: {dim_id}): 用户指定尺寸线位置 (API base) {base_for_api}")
                if any(math.isnan(c) for c in base_for_api.xyz):  # Check if user-provided loc resulted in NaN
                    logging.warning(f"角度标注 (ID: {dim_id}): 用户指定的尺寸线位置包含NaN: {base_for_api}，将自动计算。")
                    base_for_api = None

            if base_for_api is None:
                logging.debug(f"角度标注 (ID: {dim_id}): 自动计算尺寸线位置 (API base)...")
                try:
                    norm_vec1 = vec_apex_to_leg1.normalize()
                except ZeroDivisionError:
                    norm_vec1 = Vec3.ZERO
                try:
                    norm_vec2 = vec_apex_to_leg2.normalize()
                except ZeroDivisionError:
                    norm_vec2 = Vec3.ZERO

                bisector_sum = norm_vec1 + norm_vec2
                try:
                    bisector_dir = bisector_sum.normalize()
                except ZeroDivisionError:
                    logging.warning(f"角度标注 (ID: {dim_id}): 角平分线向量为零。尝试使用与vec1正交的方向。")
                    if not vec_apex_to_leg1.is_null:
                        bisector_dir = vec_apex_to_leg1.orthogonal().normalize()
                    elif not vec_apex_to_leg2.is_null:
                        bisector_dir = vec_apex_to_leg2.orthogonal().normalize()  # Fallback to vec2 if vec1 is null
                    else:
                        bisector_dir = Vec3.X_AXIS  # Ultimate fallback
                        logging.error(f"角度标注 (ID: {dim_id}): 无法确定角平分线方向，使用X轴。")

                auto_offset_dist_base = dim_text_height * 2.5  # 例如文字高度的2.5倍
                if auto_offset_dist_base < dim_text_height * 1.5:  # 至少是文字高度的1.5倍
                    auto_offset_dist_base = dim_text_height * 1.5
                if auto_offset_dist_base == 0: auto_offset_dist_base = 5  # 避免为0的情况

                if math.isnan(auto_offset_dist_base) or any(math.isnan(c) for c in bisector_dir.xyz) or any(
                        math.isnan(c) for c in apex_pt.xyz):
                    logging.error(
                        f"角度标注 (ID: {dim_id}): 自动计算尺寸线位置所需参数包含NaN。Apex:{apex_pt}, Bisector:{bisector_dir}, OffsetDist:{auto_offset_dist_base}。跳过。")
                    continue
                base_for_api = apex_pt + bisector_dir * auto_offset_dist_base
                logging.debug(f"角度标注 (ID: {dim_id}): 自动计算尺寸线位置 (API base) {base_for_api}")

            location_for_api = None
            text_override = str(row.get('Text_Override', "<>")).strip()

            dim_override_obj = msp.add_angular_dim_3p(
                base=base_for_api,
                center=apex_pt,
                p1=leg1_pt,
                p2=leg2_pt,
                location=location_for_api,  # 设为 None，让 ezdxf 自动处理文本位置
                dimstyle=actual_dim_style_name,
                text="<>",  # 让 ezdxf 尝试计算
                dxfattribs={'layer': layer_name}
            )

            if dim_override_obj:
                dim_override_obj.render()  # 首先让 ezdxf 渲染

                dimension_entity = dim_override_obj.dimension
                logging.debug(f"Dimension entity: {dimension_entity.dxf.handle}")
                logging.debug(f"  Defpoint (vertex): {dimension_entity.dxf.defpoint}")  # 角顶点
                logging.debug(f"  Defpoint2 (leg1 end): {dimension_entity.dxf.defpoint2}")  # 第一条边上的点
                logging.debug(f"  Defpoint3 (leg2 end): {dimension_entity.dxf.defpoint3}")  # 第二条边上的点
                logging.debug(f"  Defpoint4 (dimarc loc): {dimension_entity.dxf.defpoint4}")  # 尺寸弧线通过的点 (对应API的base)

                try:
                    msp.add_line(apex_pt, leg1_pt, dxfattribs={'layer': layer_name})
                    msp.add_line(apex_pt, leg2_pt, dxfattribs={'layer': layer_name})
                    logging.info(f"角度标注 (ID: {dim_id}): 已绘制角边辅助线")
                except Exception as e:
                    logging.warning(f"角度标注 (ID: {dim_id}): 绘制角边辅助线失败: {e}")

                rendered_text = dimension_entity.dxf.text

                # 检查渲染后的文本是否是我们不期望的 "nan" 或未被替换的 "<>"
                if rendered_text.strip().lower() == "nan" or rendered_text.strip() == "<>":
                    v_center_p1 = leg1_pt - apex_pt
                    v_center_p2 = leg2_pt - apex_pt

                    # 计算角度 (0-360度，逆时针)
                    angle_rad = v_center_p1.angle_between(v_center_p2)
                    angle_deg_calculated = math.degrees(angle_rad)

                    # 根据 DIMADEC (精度) 格式化
                    current_dim_adec = dim_style.dxf.get("dimadec", 2)
                    text_format_string = f"{{:.{current_dim_adec}f}}"
                    manual_text = text_format_string.format(angle_deg_calculated)

                    logging.warning(f"角度标注 (ID: {dim_id}): ezdxf 渲染文本为 '{rendered_text}'. "
                                    f"手动计算角度为 {angle_deg_calculated:.{current_dim_adec}f}°, "
                                    f"将文本覆盖为 '{manual_text}'.")
                    dimension_entity.dxf.text = manual_text  # 直接覆盖文本
                    # 通常在 render 之后修改 dxf.text 是有效的，CAD软件会读取这个最终值

                logging.info(  # 日志现在会显示最终的文本
                    f"角度标注 (ID: {dim_id}) 已绘制。顶点(center): {apex_pt}, 边点1(p1): {leg1_pt}, 边点2(p2): {leg2_pt}, "
                    f"尺寸线点(base): {base_for_api}, 文本: '{dimension_entity.dxf.text}', 图层: {layer_name}")
            else:
                logging.error(f"角度标注 (ID: {dim_id}): add_angular_dim_3p 未能返回对象。")

        except KeyError as e:
            logging.error(f"绘制角度标注 (ID: {dim_id}) 时缺少列: {e}。行数据: {row.to_dict()}")
        except ValueError as e:
            logging.error(f"绘制角度标注 (ID: {dim_id}) 时数据转换错误: {e}。行数据: {row.to_dict()}", exc_info=True)
        except Exception as e:
            logging.error(f"绘制角度标注 (ID: {dim_id}) 时发生未知错误: {e}。行数据: {row.to_dict()}", exc_info=True)

    logging.info("角度尺寸标注绘制完成。")


if __name__ == "__main__":
    # 配置日志
    # 1. 获取根 logger 或您想配置的特定 logger
    # logger = logging.getLogger() # 获取根 logger
    logger = logging.getLogger("ezdxf_drawer1")  # 或者获取一个命名的 logger，与您日志输出中的模块名对应

    # 如果要配置根logger，通常这样做：
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # 设置根 logger 的级别

    # 2. 创建一个 StreamHandler (输出到控制台)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)  # Handler 可以有自己的级别，通常不高于 logger 的级别

    # 3. 将自定义 Formatter 应用到 Handler
    ch.setFormatter(CustomFormatter())

    # 4. 将 Handler 添加到 Logger
    # root_logger.addHandler(ch) # 如果配置根 logger

    # 最简单的全局配置方式：
    if not root_logger.hasHandlers():  # 只在没有 handler 时添加，避免重复（如果脚本被多次导入执行）
        root_logger.addHandler(ch)
    else:  # 如果已有 handler，尝试替换 formatter
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):  # 通常控制台输出是 StreamHandler
                handler.setFormatter(CustomFormatter())
                handler.setLevel(logging.DEBUG)  # 确保 handler 能处理 DEBUG 级别
        root_logger.setLevel(logging.INFO)  # 确保根 logger 至少是 INFO

    # 指定 Excel 文件路径 (与 cad_main.py 中的 test_excel_file 对应)
    excel_file_to_process = r"result/观测数据处理后.xlsx"
    # excel_file_to_process = r"D:\work\task\symbol_excel\excel\道路纵截面设计图_填入数据后.xlsx"
    # excel_file_to_process = r"D:\mcpmcp\符号2.xlsx"
    # 确保路径正确，或者使用绝对路径
    excel_file_to_process = os.path.abspath(excel_file_to_process)

    if os.path.exists(excel_file_to_process):
        generate_all_elements_from_excel(excel_file_to_process)
    else:
        logging.error(f"主程序无法找到 Excel 文件: {excel_file_to_process}")

# ++++++++++++++++++++++++++ 主协调函数结束 ++++++++++++++++++++++++++