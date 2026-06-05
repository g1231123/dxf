# -*- coding: utf-8 -*-
import traceback

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple
import math
import os
import glob

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 尝试导入ezdxf_drawer1，如果不存在则跳过
try:
    from ezdxf_drawer1 import generate_all_elements_from_excel

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("未找到ezdxf_drawer1模块，将跳过DXF文件生成")

# 尝试导入dxf_to_image，如果不存在则跳过
try:
    from dxf_to_img import convert_dxf_to_image

    HAS_DXF = True
except ImportError:
    HAS_DXF = False
    logger.warning("未找到dxf_to_image模块，将跳过DXF文件生成")


class DataProcessor:
    def __init__(self, template_path: str, output_path: str):
        """初始化，读取模板文件和设置输出路径"""
        logger.info(f"正在读取模板文件: {template_path}")
        try:
            self.template_excel = pd.ExcelFile(template_path)
            self.output_path = output_path
            # 读取各工作表数据
            self.layers_df = self._parse_sheet('Layers')
            self.lines_df = self._parse_sheet('Lines')
            self.circles_df = self._parse_sheet('Circles')
            self.arcs_df = self._parse_sheet('Arcs')
            self.polyline_df = self._parse_sheet('Polyline')
            self.rectangles_df = self._parse_sheet('Rectangles')
            self.annotations_df = self._parse_sheet('Annotations')

            # 新增：提取工作基点数据
            self.work_base_data = self._extract_work_base_data()
            # 用于决定虚线起点
            self.work_base_points_coords = []
            logger.info("模板文件读取成功")
        except Exception as e:
            logger.error(f"读取模板文件失败: {str(e)}")
            raise

    def _parse_sheet(self, sheet_name: str) -> pd.DataFrame:
        """尝试读取工作表，不存在则返回空DataFrame"""
        try:
            return self.template_excel.parse(sheet_name)
        except ValueError:
            logger.warning(f"未找到名为 '{sheet_name}' 的工作表，将创建空表。")
            return pd.DataFrame()

    def _extract_work_base_data(self) -> Dict[str, pd.DataFrame]:
        """从模板中提取图层名为'工作基点'的所有数据"""
        work_base_data = {
            'Lines': self.lines_df[self.lines_df['Layer_Name'] == '工作基点'].copy(),
            'Circles': self.circles_df[self.circles_df['Layer_Name'] == '工作基点'].copy(),
            'Arcs': self.arcs_df[self.arcs_df['Layer_Name'] == '工作基点'].copy(),
            'Polyline': self.polyline_df[self.polyline_df['Layer_Name'] == '工作基点'].copy(),
            'Rectangles': self.rectangles_df[self.rectangles_df['Layer_Name'] == '工作基点'].copy(),
            'Annotations': self.annotations_df[self.annotations_df['Layer_Name'] == '工作基点'].copy()
        }
        logger.info(f"提取到工作基点数据: Lines-{len(work_base_data['Lines'])}, Circles-{len(work_base_data['Circles'])}, etc.")
        return work_base_data

    def _calculate_center(self, row: pd.Series, sheet_name: str) -> Tuple[float, float]:
        """计算几何图形的中心点坐标"""
        if sheet_name == 'Circles':
            return (row['Center_X'], row['Center_Y'])
        elif sheet_name == 'Polyline':
            vertices = eval(row['顶点坐标列表'])
            x_coords = [v[0] for v in vertices]
            y_coords = [v[1] for v in vertices]
            return (sum(x_coords) / len(x_coords), sum(y_coords) / len(y_coords))
        elif sheet_name == 'Lines':
            return ((row['Start_X'] + row['End_X']) / 2,
                    (row['Start_Y'] + row['End_Y']) / 2)
        elif sheet_name == 'Arcs':
            return (row['Center_X'], row['Center_Y'])
        elif sheet_name == 'Rectangles':
            center = eval(row['中心坐标'])
            return center
        else:
            return (0, 0)

    def process_data(self, target_types: List[str], guanhhao_mileage_data: List[Dict[str, str]],
                     work_base_points: List[Dict[str, str]] = None):
        """
        处理数据：提取匹配测点类型的数据，修改坐标后写入新文件，并添加直线
        """
        logger.info(f"开始处理数据，目标测点类型: {target_types}，数据量: {len(guanhhao_mileage_data)}")
        # 1. 提取模板中与测点类型匹配的所有数据
        matched_data = self._extract_all_matched_data(target_types)
        # 2. 按规则修改坐标并追加数据
        updated_centers = self._update_and_append_coordinates(matched_data, guanhhao_mileage_data)
        # 3. 添加工作基点数据（新增功能）
        if work_base_points:
            self._add_work_base_points(updated_centers, work_base_points, guanhhao_mileage_data)
        # 4. 添加直线到Lines表
        self._add_line_to_lines(updated_centers)
        # 5. 写入新Excel文件
        self._write_to_new_excel()
        logger.info("数据处理完成，已写入新Excel文件")

    def _extract_all_matched_data(self, target_types: List[str]) -> Dict[str, pd.DataFrame]:
        """提取模板中所有表中与测点类型匹配的数据"""
        logger.info(f"正在提取所有表中与测点类型 {target_types} 匹配的数据")
        matched_data = {
            'Lines': self.lines_df[self.lines_df['Layer_Name'].isin(target_types)].copy(),
            'Circles': self.circles_df[self.circles_df['Layer_Name'].isin(target_types)].copy(),
            'Arcs': self.arcs_df[self.arcs_df['Layer_Name'].isin(target_types)].copy(),
            'Polyline': self.polyline_df[self.polyline_df['Layer_Name'].isin(target_types)].copy(),
            'Rectangles': self.rectangles_df[self.rectangles_df['Layer_Name'].isin(target_types)].copy(),
            'Annotations': self.annotations_df[self.annotations_df['Layer_Name'].isin(target_types)].copy()
        }
        for sheet_name, df in matched_data.items():
            logger.info(f"表 {sheet_name} 中找到 {len(df)} 条匹配数据")
        return matched_data

    def _update_and_append_coordinates(self, matched_data: Dict[str, pd.DataFrame],
                                       guanhhao_data: List[Dict[str, str]]) -> List[Tuple[float, float]]:
        """更新坐标并追加数据，保持图形间的相对位置关系，同时处理模板中的多条同类数据"""
        logger.info(f"开始更新并追加 {len(guanhhao_data)} 组坐标数据")
        all_centers = []
        start_x, start_y = -2, 10  # 圆的基准位置

        # 检查模板中是否有圆的数据
        has_circle_template = not matched_data['Circles'].empty

        for i, data in enumerate(guanhhao_data):
            new_data_group = {sheet: [] for sheet in matched_data.keys()}

            # 计算本组数据的基准位置（圆的中心位置）
            base_x = start_x - 5 * i
            base_y = start_y + 25 * i

            # 1. 处理圆（如果有）
            if has_circle_template:
                # 追加模板中所有匹配的圆数据（而不只是第一条）
                for _, circle_row in matched_data['Circles'].iterrows():
                    circle_data = circle_row.copy()
                    original_center = (circle_data['Center_X'], circle_data['Center_Y'])

                    # 计算偏移量
                    x_offset = base_x - original_center[0]
                    y_offset = base_y - original_center[1]

                    # 更新圆的位置
                    circle_data['Center_X'] += x_offset
                    circle_data['Center_Y'] += y_offset
                    circle_data['Layer_Name'] = 'data'
                    circle_data['ID'] = f'Circle_{len(self.circles_df) + len(new_data_group["Circles"]) + 1}'
                    new_data_group['Circles'].append(circle_data.to_dict())

            # 2. 处理其他图形，保持与圆的相对位置
            for sheet_name in ['Lines', 'Arcs', 'Polyline', 'Rectangles']:
                if matched_data[sheet_name].empty:
                    continue

                # 处理模板中所有匹配的该类图形数据
                for _, template_row in matched_data[sheet_name].iterrows():
                    row_data = template_row.copy()
                    original_center = self._calculate_center(row_data, sheet_name)

                    if has_circle_template:
                        # 计算相对于第一个圆的偏移量
                        first_circle_center = (matched_data['Circles'].iloc[0]['Center_X'],
                                               matched_data['Circles'].iloc[0]['Center_Y'])
                        original_offset_x = original_center[0] - first_circle_center[0]
                        original_offset_y = original_center[1] - first_circle_center[1]

                        # 应用相同的偏移量到新位置
                        new_center_x = base_x + original_offset_x
                        new_center_y = base_y + original_offset_y
                    else:
                        # 没有圆数据时使用绝对位置
                        new_center_x = base_x
                        new_center_y = base_y

                    # 更新图形坐标
                    self._adjust_shape_position(row_data, sheet_name, new_center_x, new_center_y)
                    row_data[
                        'ID'] = f'{sheet_name[:-1]}_{len(getattr(self, f"{sheet_name.lower()}_df")) + len(new_data_group[sheet_name]) + 1}'
                    new_data_group[sheet_name].append(row_data.to_dict())

            # 3. 处理标注（特殊逻辑）
            if not matched_data['Annotations'].empty:
                for _, annotation_row in matched_data['Annotations'].iterrows():
                    anno_data = annotation_row.copy()
                    anno_data['Position_X'] = start_x + 40 - 5 * i
                    anno_data['Position_Y'] = base_y
                    anno_data['Annotation_Name'] = data.get('冠号里程', '')
                    anno_data['ID'] = f'Annotation_{len(self.annotations_df) + len(new_data_group["Annotations"]) + 1}'
                    new_data_group['Annotations'].append(anno_data.to_dict())

            # 将本组数据追加到结果中
            for sheet_name, items in new_data_group.items():
                if items:
                    df = getattr(self, f"{sheet_name.lower()}_df")
                    setattr(self, f"{sheet_name.lower()}_df", pd.concat([df, pd.DataFrame(items)], ignore_index=True))

            all_centers.append((base_x, base_y))

        logger.info(f"成功追加 {len(guanhhao_data)} 组完整图形数据，包含所有模板匹配项")
        return all_centers

    def _add_work_base_points(self, centers: List[Tuple[float, float]],
                              work_base_points: List[Dict[str, str]],
                              guanhhao_data: List[Dict[str, str]]):
        """添加工作基点数据到相应位置（修正里程比较逻辑）"""
        logger.info("开始处理工作基点数据...")

        if not centers or not work_base_points or not guanhhao_data:
            logger.warning("缺少必要数据，无法添加工作基点")
            return

        def parse_mileage(mileage_str):
            """解析里程字符串，返回实际数值（处理000=1000的情况）"""
            try:
                if '+' in mileage_str:
                    parts = mileage_str.split('+')
                    main_part = parts[0][-3:] if len(parts[0]) > 3 else parts[0]  # 取冠号后3位
                    last_part = parts[1]
                else:
                    main_part = mileage_str[-6:-3] if len(mileage_str) >= 6 else '0'
                    last_part = mileage_str[-3:]

                # 处理最后3位（000=1000，090=1090）
                last_num = int(last_part)
                if last_num < 100:  # 小于100的数值需要加1000
                    last_num += 1000

                return int(main_part) * 1000 + last_num
            except Exception as e:
                logger.error(f"解析里程'{mileage_str}'出错: {str(e)}")
                return 0

        # 准备表一里程数据（带实际数值）
        table1_mile_data = []
        for point, center in zip(guanhhao_data, centers):
            if '里程(m)' not in point:
                continue
            true_value = parse_mileage(point['里程(m)'])
            table1_mile_data.append({
                'true_value': true_value,
                'center': center,
                'raw': point['里程(m)']
            })

        # 排序表一数据（确保按里程顺序）
        table1_mile_data.sort(key=lambda x: x['true_value'])

        # 根据表一数据数量决定工作基点的添加方式
        work_base_positions = []

        if len(table1_mile_data) == 2:
            # 表一只有两条数据时，添加两次工作基点（起点和终点）
            work_base_positions = [table1_mile_data[0], table1_mile_data[1]]
            logger.info("表一只有两条数据，添加起点和终点两个工作基点")
        elif len(table1_mile_data) >= 3:
            # 表一超过三条数据时，添加起点、中间点和终点三个工作基点
            start_point = table1_mile_data[0]
            end_point = table1_mile_data[-1]

            # 计算中间点的里程和坐标
            mid_mileage = (start_point['true_value'] + end_point['true_value']) // 2
            mid_x = (start_point['center'][0] + end_point['center'][0]) // 2
            mid_y = (start_point['center'][1] + end_point['center'][1]) // 2

            # 查找最接近中间里程的实际数据点
            mid_point = min(table1_mile_data, key=lambda x: abs(x['true_value'] - mid_mileage))
            print(mid_point)

            work_base_positions = [start_point, mid_point, end_point]
            logger.info("表一超过三条数据，添加起点、中间点和终点三个工作基点")
        else:
            logger.warning("表一数据不足，无法添加工作基点")
            return

        # 步骤1：计算原始模板中的相对位置关系
        original_relations = {}
        circle_center = None

        # 查找原始工作基点圆心的位置
        if not self.work_base_data['Circles'].empty:
            circle_row = self.work_base_data['Circles'].iloc[0]
            circle_center = (circle_row['Center_X'], circle_row['Center_Y'])
            logger.info(f"原始工作基点圆心位置: {circle_center}")

        if circle_center:
            # 计算其他工作基点图形与圆心的原始偏移量
            for sheet_name, df in self.work_base_data.items():
                if sheet_name == 'Circles':
                    continue

                for _, row in df.iterrows():
                    shape_center = self._calculate_center(row, sheet_name)
                    original_relations[f"{sheet_name}_{row['ID']}"] = {
                        'x_offset': shape_center[0] - circle_center[0],
                        'y_offset': shape_center[1] - circle_center[1],
                        'row': row.copy(),
                        'sheet_name': sheet_name
                    }

        # 为每个工作基点位置添加数据
        for i, position in enumerate(work_base_positions):
            print(work_base_positions)
            try:
                target_value = position['true_value']
                target_raw = position['raw']
                logger.info(f"处理工作基点位置 {i + 1}，里程: {target_raw} → 实际值: {target_value}")

                # 初始化坐标变量
                base_x, base_y = 0, 0

                # 计算工作基点位置（根据原逻辑调整）
                if i == 0:  # 起点
                    base_x, base_y = position['center'][0] - 28, position['center'][1]
                elif i == len(work_base_positions) - 1:  # 终点
                    base_x, base_y = position['center'][0] - 28, position['center'][1]
                else:  # 中间点
                    base_x, base_y = position['center'][0] - 28, position['center'][1]

                # 步骤3：调整所有工作基点图形的位置
                for sheet_name, df in self.work_base_data.items():
                    if df.empty:
                        continue

                    new_data = df.copy()

                    for index, row in new_data.iterrows():
                        if sheet_name == 'Circles':
                            # 圆心直接使用新坐标
                            new_data.at[index, 'Center_X'] = base_x
                            new_data.at[index, 'Center_Y'] = base_y
                            new_data.at[index, 'Layer_Name'] = 'data'
                        else:
                            # 其他图形保持原始相对位置
                            relation_key = f"{sheet_name}_{row['ID']}"
                            if relation_key in original_relations:
                                relation = original_relations[relation_key]
                                new_x = base_x + relation['x_offset']
                                new_y = base_y + relation['y_offset']

                                # 根据图形类型更新坐标
                                if sheet_name == 'Lines':
                                    new_data.at[index, 'Start_X'] += (
                                            new_x - self._calculate_center(row, sheet_name)[0])
                                    new_data.at[index, 'Start_Y'] += (
                                            new_y - self._calculate_center(row, sheet_name)[1])
                                    new_data.at[index, 'End_X'] += (new_x - self._calculate_center(row, sheet_name)[0])
                                    new_data.at[index, 'End_Y'] += (new_y - self._calculate_center(row, sheet_name)[1])
                                    new_data.at[index, 'Layer_Name'] = 'data'
                                elif sheet_name == 'Arcs':
                                    new_data.at[index, 'Center_X'] = new_x
                                    new_data.at[index, 'Center_Y'] = new_y
                                    new_data.at[index, 'Layer_Name'] = 'data'
                                elif sheet_name == 'Polyline':
                                    # 多段线：更新所有顶点坐标
                                    vertices = eval(row['顶点坐标列表'])
                                    original_center = self._calculate_center(row, sheet_name)
                                    x_offset = base_x - original_center[0]
                                    y_offset = base_y - original_center[1]
                                    new_vertices = [(x + x_offset, y + y_offset) for x, y in vertices]
                                    new_data.at[index, '顶点坐标列表'] = str(new_vertices)
                                    new_data.at[index, 'Layer_Name'] = 'data'
                                elif sheet_name == 'Rectangles':
                                    # 矩形：更新中心坐标
                                    center = eval(row['中心坐标'])
                                    original_center = self._calculate_center(row, sheet_name)
                                    x_offset = base_x - original_center[0]
                                    y_offset = base_y - original_center[1]
                                    new_center = (center[0] + x_offset, center[1] + y_offset)
                                    new_data.at[index, '中心坐标'] = str(new_center)
                                    new_data.at[index, 'Layer_Name'] = 'data'
                                elif sheet_name == 'Annotations':
                                    # 标注文字 更新x坐标
                                    new_data.at[index, 'Position_X'] = base_x - 57
                                    new_data.at[index, 'Position_Y'] = base_y
                                    # 更新标注内容，使用对应的点号信息
                                    point_num = work_base_points[i]['点号'] if i < len(
                                        work_base_points) else "JMQGW00"
                                    new_data.at[index, 'Annotation_Name'] = f"工作基点{point_num}"

                            new_data.at[
                                index, 'ID'] = f'WorkBase_{sheet_name[:-1]}_{len(getattr(self, f"{sheet_name.lower()}_df")) + 1}'

                    # 追加到工作表
                    current_df = getattr(self, f"{sheet_name.lower()}_df")
                    setattr(self, f"{sheet_name.lower()}_df",
                            pd.concat([current_df, new_data], ignore_index=True))

                logger.info(f"工作基点组已放置到 ({base_x:.2f}, {base_y:.2f})，保持相对位置关系")
                self.work_base_points_coords.append((base_x, base_y))

            except Exception as e:
                logger.error(f"处理工作基点时出错: {str(e)}")
                continue

        logger.info("工作基点及其关联图形处理完成")

    def _adjust_shape_position(self, shape_data: pd.Series, shape_type: str,
                               new_center_x: float, new_center_y: float):
        """调整图形位置到新中心点，保持形状不变"""
        original_center = self._calculate_center(shape_data, shape_type)
        x_offset = new_center_x - original_center[0]
        y_offset = new_center_y - original_center[1]

        if shape_type == 'Lines':
            shape_data['Start_X'] += x_offset
            shape_data['Start_Y'] += y_offset
            shape_data['End_X'] += x_offset
            shape_data['End_Y'] += y_offset
            shape_data['Layer_Name'] = 'data'
        elif shape_type == 'Arcs':
            shape_data['Center_X'] += x_offset
            shape_data['Center_Y'] += y_offset
            shape_data['Layer_Name'] = 'data'
        elif shape_type == 'Polyline':
            vertices = eval(shape_data['顶点坐标列表'])
            shape_data['顶点坐标列表'] = str([(x + x_offset, y + y_offset) for x, y in vertices])
            shape_data['Layer_Name'] = 'data'
        elif shape_type == 'Rectangles':
            center = eval(shape_data['中心坐标'])
            shape_data['中心坐标'] = str((center[0] + x_offset, center[1] + y_offset))
            shape_data['Layer_Name'] = 'data'

    def _add_line_to_lines(self, centers: List[Tuple[float, float]]):
        """在Lines表中添加从(0,0)到最后一个中心点的直线"""
        if not centers:
            logger.warning("中心点列表为空，无法添加直线")
            return
        last_x, last_y = centers[-1]
        # 获取最小的 base_y
        min_point = min(self.work_base_points_coords, key=lambda point: point[1])
        # 添加虚线
        self.create_dashed_line((min_point[0], min_point[1]), (last_x - 28, last_y))

        new_line = {
            'ID': f'LINE_{len(self.lines_df) + 1}',
            'Layer_Name': '0',
            'Start_X': 0,
            'Start_Y': 0,
            'End_X': last_x - 5,
            'End_Y': last_y + 25,
            'Linetype': 'Continuous'
        }
        self.lines_df = pd.concat([self.lines_df, pd.DataFrame([new_line])], ignore_index=True)
        logger.info(f"已添加直线，起点(0,0)，终点({last_x}, {last_y})")

    def create_dashed_line(self, start_point, end_point, segment_length=5, gap_length=2):
        """
        在两点之间创建虚线
        :param start_point: 起点坐标 (x, y)
        :param end_point: 终点坐标 (x, y)
        :param segment_length: 每段虚线长度
        :param gap_length: 虚线间隔长度
        """
        try:
            start_x, start_y = start_point
            end_x, end_y = end_point

            # 计算两点之间的距离
            total_length = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
            if total_length == 0:
                return []

            # 计算单位向量
            dx = (end_x - start_x) / total_length
            dy = (end_y - start_y) / total_length

            current_length = 0
            segment_count = 0

            while current_length < total_length:
                # 计算线段起点
                seg_start_x = start_x + current_length * dx
                seg_start_y = start_y + current_length * dy

                # 计算线段终点（不超过总长度）
                seg_end_length = min(current_length + segment_length, total_length)
                seg_end_x = start_x + seg_end_length * dx
                seg_end_y = start_y + seg_end_length * dy

                # 添加线段到Lines表
                new_line = {
                    'ID': f'虚线_{len(self.lines_df) + segment_count + 1}',
                    'Layer_Name': 'dashed',
                    'Start_X': seg_start_x,
                    'Start_Y': seg_start_y,
                    'End_X': seg_end_x,
                    'End_Y': seg_end_y,
                    'Linetype': 'Dashed'
                }
                self.lines_df = pd.concat(
                    [self.lines_df, pd.DataFrame([new_line])],
                    ignore_index=True
                )
                segment_count += 1

                # 移动到下一个线段起点（跳过间隔）
                current_length = seg_end_length + gap_length
            logger.info(f"已添加虚线，包含 {segment_count} 个线段，起点{start_point}，终点({end_point})")
        except Exception as e:
            logger.error(f"添加虚线时出错{str(e)}")

    def _write_to_new_excel(self):
        """将处理后的数据写入新Excel文件"""
        logger.info(f"开始写入新Excel文件: {self.output_path}")
        with pd.ExcelWriter(self.output_path, engine='openpyxl') as writer:
            for sheet_name in ['Layers', 'Lines', 'Circles', 'Arcs',
                               'Polyline', 'Rectangles', 'Annotations']:
                df = getattr(self, f"{sheet_name.lower()}_df")
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        logger.info("新Excel文件写入完成")

        # 打印Excel文件保存路径
        print(f"\n{'=' * 80}")
        print(f"📊 Excel结果文件已生成:")
        print(f"📍 文件位置: {os.path.abspath(self.output_path)}")
        print(f"📁 所在目录: {os.path.dirname(os.path.abspath(self.output_path))}")
        print(f"{'=' * 80}\n")


def find_data_files():
    """在当前路径中查找Excel数据文件，排除观测示意图模板"""
    # 查找所有Excel文件
    excel_files = glob.glob("*.xlsx") + glob.glob("*.xls")

    if not excel_files:
        logger.error(f"未找到Excel文件")
        return []

    # 排除观测示意图模板文件
    template_patterns = [
        "观测示意图模板.xlsx",
        "观测示意图模板.xls",
        "*模板*.xlsx",
        "*模板*.xls"
    ]

    filtered_files = []
    for file_path in excel_files:
        file_name = os.path.basename(file_path)
        is_template = any(
            pattern.replace("*", "") in file_name.lower()
            for pattern in template_patterns
        )

        # 特别排除观测示意图模板
        if "观测示意图模板" in file_name:
            continue
        # 也可以排除其他包含"模板"的文件
        elif "模板" in file_name:
            continue
        else:
            filtered_files.append(file_path)

    logger.info(f"找到 {len(filtered_files)} 个数据文件（已排除模板文件）")
    return filtered_files


def find_template_file():
    """在当前路径中查找观测示意图模板文件"""

    # 可能的模板文件名
    template_names = [
        "观测示意图模板.xlsx",
        "观测示意图模板.xls",
        "模板.xlsx",
        "模板.xls"
    ]

    for template_name in template_names:
        template_path = template_name  # 在当前路径查找
        if os.path.exists(template_path):
            logger.info(f"找到模板文件: {template_path}")
            return template_path

    # 如果没有找到标准名称，查找包含"模板"的文件
    template_files = glob.glob("*模板*.xlsx") + glob.glob("*模板*.xls")
    if template_files:
        logger.info(f"找到模板文件: {template_files[0]}")
        return template_files[0]

    return None


def process_data_file(data_file_path, template_path=None, output_path=None):
    """
    处理数据文件的主函数

    Args:
        data_file_path: 数据文件路径
        template_path: 模板文件路径，如果为None则自动在当前路径中查找
        output_path: 输出文件路径，如果为None则自动生成
    """
    # 自动查找模板文件
    if template_path is None:
        template_path = find_template_file()
        if template_path is None:
            logger.error("未找到观测示意图模板文件")
            print("❌ 错误: 未找到观测示意图模板文件")
            print("   请在当前路径中放置'观测示意图模板.xlsx'文件")
            return False

    # 检查模板文件是否存在
    if not os.path.exists(template_path):
        logger.error(f"模板文件不存在: {template_path}")
        print(f"❌ 错误: 模板文件不存在: {template_path}")
        return False

    # 如果未指定输出路径，自动生成
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(data_file_path))[0]
        output_path = f"{base_name}_处理后.xlsx"

    try:
        # 读取数据文件 - 支持.xls和.xlsx格式
        excel_file = pd.ExcelFile(data_file_path)
        sheet_names = excel_file.sheet_names
        result_df = pd.DataFrame()
        work_base_points = []

        # 处理第一个数据表（原逻辑）
        for sheet_name in sheet_names:
            df = excel_file.parse(sheet_name)
            if all(column in df.columns for column in ['冠号', '里程(m)', '测点类型']):
                df['里程(m)'] = df['里程(m)'].astype(str)
                df['里程(m)'] = df['里程(m)'].str[:-3] + '+' + df['里程(m)'].str[-3:]
                df['冠号里程'] = df['冠号'] + df['里程(m)']

                def modify_type(value):
                    index = value.find('观测')
                    return value[:index + 2] + '点' if index != -1 else value

                # 将桥台观测标和墩身观测标替换为桥墩台观测点
                df['测点类型'] = df['测点类型'].replace(['桥台观测标', '墩身观测标'], '桥墩台观测点')

                df['测点类型'] = df['测点类型'].apply(modify_type)

                df = df.drop_duplicates(subset='里程(m)')
                result_df = pd.concat([result_df, df[['测点类型', '冠号里程', '里程(m)']]], ignore_index=True)

            # 新增：处理第二个数据表（工作基点数据）
            elif '点号' in df.columns and '里程' in df.columns:
                work_base_points = df[['点号', '里程']].to_dict(orient='records')

        if not result_df.empty:
            logger.info('所有测点类型列和冠号里程列的数据：')
            logger.info(str(result_df))
            guanhhao_mileage_data = result_df.to_dict(orient='records')
            target_types = result_df['测点类型'].unique().tolist()

            processor = DataProcessor(template_path, output_path)
            processor.process_data(target_types, guanhhao_mileage_data, work_base_points)
            logger.info(f"数据处理完成，结果已保存至 {output_path}")

            # 利用处理好的数据输出dxf文件
            dxf_output_path = None
            if HAS_EZDXF:
                try:
                    # 尝试只传递一个参数（Excel文件路径）
                    generate_all_elements_from_excel(output_path)
                    logger.info(f"工作表 {output_path} 数据绘制完成")

                    # 在当前路径生成DXF文件
                    dxf_filename = os.path.splitext(os.path.basename(output_path))[0] + ".dxf"
                    dxf_output_path = dxf_filename

                    # 检查是否生成了DXF文件
                    temp_dxf_path = os.path.splitext(output_path)[0] + ".dxf"
                    if os.path.exists(temp_dxf_path) and temp_dxf_path != dxf_output_path:
                        import shutil
                        shutil.move(temp_dxf_path, dxf_output_path)
                        logger.info(f"DXF文件已移动到: {dxf_output_path}")
                    elif os.path.exists(dxf_output_path):
                        logger.info(f"DXF文件已存在于: {dxf_output_path}")
                    else:
                        # 如果ezdxf_drawer1模块支持指定输出路径，可以这样调用
                        try:
                            # 尝试使用修改后的函数，支持输出路径参数
                            generate_all_elements_from_excel(output_path, dxf_output_path)
                            logger.info(f"DXF文件直接生成到: {dxf_output_path}")
                        except TypeError:
                            # 如果函数不支持输出路径参数，使用默认方式
                            generate_all_elements_from_excel(output_path)
                            if os.path.exists(temp_dxf_path):
                                import shutil
                                shutil.move(temp_dxf_path, dxf_output_path)
                                logger.info(f"DXF文件已移动到: {dxf_output_path}")

                    if os.path.exists(dxf_output_path):
                        # 打印DXF文件保存路径
                        print(f"\n{'=' * 80}")
                        print(f"📐 DXF图形文件已生成:")
                        print(f"📍 文件位置: {os.path.abspath(dxf_output_path)}")
                        print(f"📁 所在目录: {os.path.dirname(os.path.abspath(dxf_output_path))}")
                        print(f"{'=' * 80}\n")
                    else:
                        print(f"⚠️  DXF文件可能已生成，但未在预期位置找到: {dxf_output_path}")
                        print("请检查ezdxf_drawer1模块的默认输出路径")

                except Exception as e:
                    logger.error(f"生成DXF文件时出错: {str(e)}")
                    print(f"❌ 生成DXF文件时出错: {str(e)}")
            else:
                logger.info("警告: 未找到ezdxf_drawer1模块，跳过DXF文件生成")

            # 利用处理好的数据输出图片文件
            img_output_path = None
            if HAS_DXF and dxf_output_path and os.path.exists(dxf_output_path):
                try:
                    # 在当前路径生成图片文件
                    img_filename = os.path.splitext(os.path.basename(output_path))[0] + ".png"
                    img_output_path = img_filename
                    print(dxf_output_path,img_output_path)
                    # 使用修复版的转换函数
                    raw = convert_dxf_to_image(dxf_output_path, img_output_path)
                    print(f"[调试] convert_dxf_to_image 原始返回值类型: {type(raw)}  值: {raw!r}")
                    success = raw is not None and isinstance(raw, np.ndarray) and raw.size > 0

                    if success:
                        logger.info(f"dxf文件 {dxf_output_path} 转换为image完成")
                        # 打印图片文件保存路径
                        # 自己写盘
                        # cv2.imwrite(img_output_path, raw)
                        print(f"\n{'=' * 80}")
                        print(f"🖼️ 图片文件已生成:")
                        print(f"📍 文件位置: {os.path.abspath(img_output_path)}")
                        print(f"📁 所在目录: {os.path.dirname(os.path.abspath(img_output_path))}")
                        print(f"{'=' * 80}\n")
                    else:
                        logger.warning(f"dxf文件转换失败，但程序继续执行")
                        print(f"⚠️  DXF转图片失败，但程序继续执行")
                except Exception as e:
                    logger.error(f"生成图片文件时出错: {str(e)}")
                    traceback.print_exc()  # ✅ 打印完整堆栈
                    print(f"⚠️  生成图片文件时出错: {str(e)}，但程序继续执行")
        else:
            logger.warning("未在数据文件中找到包含'冠号'、'里程(m)'和'测点类型'列的数据表")
            print("⚠️ 警告: 未在数据文件中找到包含'冠号'、'里程(m)'和'测点类型'列的数据表")
            return False

        return True

    except Exception as e:
        logger.error(f"处理数据文件时出错: {str(e)}", exc_info=True)
        print(f"❌ 处理数据文件时出错: {str(e)}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    data_files = find_data_files()
    if data_files:
        for data_file in data_files:
            print(f"\n{'=' * 80}")
            print(f"开始处理数据文件: {data_file}")
            process_data_file(data_file)
            print(f"数据文件 {data_file} 处理结束")
            print(f"{'=' * 80}\n")
    else:
        print("未找到任何数据文件，请将Excel数据文件放在当前目录下")