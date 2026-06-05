import ezdxf
from collections import defaultdict

file_path = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'

print(f'读取 DXF 文件: {file_path}')

# 读取 DXF
try:
    doc = ezdxf.readfile(file_path)
except:
    try:
        doc = ezdxf.readfile(file_path, encoding='gbk')
    except:
        doc = ezdxf.readfile(file_path, encoding='gb18030')

msp = doc.modelspace()

# 统计实体类型
entity_stats = defaultdict(int)
entity_samples = defaultdict(list)

print(f'\n文件版本: {doc.dxfversion}')
print(f'总实体数: {len(list(msp))}')

# 遍历实体
for entity in msp:
    entity_type = entity.dxftype()
    entity_stats[entity_type] += 1
    
    # 收集前3个样本
    if len(entity_samples[entity_type]) < 3:
        sample = {
            'type': entity_type,
            'handle': entity.dxf.handle,
            'layer': entity.dxf.layer if hasattr(entity.dxf, 'layer') else 'N/A',
            'color': entity.dxf.color if hasattr(entity.dxf, 'color') else 'N/A',
            'lineweight': entity.dxf.lineweight if hasattr(entity.dxf, 'lineweight') else 'N/A'
        }
        
        # 根据类型添加特定参数
        if entity_type == 'LINE':
            sample['start'] = list(entity.dxf.start)
            sample['end'] = list(entity.dxf.end)
        elif entity_type == 'CIRCLE':
            sample['center'] = list(entity.dxf.center)
            sample['radius'] = entity.dxf.radius
        elif entity_type == 'ARC':
            sample['center'] = list(entity.dxf.center)
            sample['radius'] = entity.dxf.radius
            sample['start_angle'] = entity.dxf.start_angle
            sample['end_angle'] = entity.dxf.end_angle
        elif entity_type in ['TEXT', 'MTEXT']:
            sample['text'] = entity.dxf.text[:50] if len(entity.dxf.text) > 50 else entity.dxf.text
            sample['height'] = entity.dxf.height if hasattr(entity.dxf, 'height') else 'N/A'
        elif entity_type == 'ELLIPSE':
            sample['center'] = list(entity.dxf.center)
            sample['major_axis'] = list(entity.dxf.major_axis)
            sample['ratio'] = entity.dxf.ratio
        elif entity_type == 'SPLINE':
            sample['degree'] = entity.dxf.degree if hasattr(entity.dxf, 'degree') else 'N/A'
            if hasattr(entity, 'control_points'):
                sample['control_points_count'] = len(list(entity.control_points))
        elif entity_type == 'POINT':
            sample['location'] = list(entity.dxf.location)
        
        entity_samples[entity_type].append(sample)

# 打印统计
print('\n' + '=' * 80)
print('实体类型统计')
print('=' * 80)
for entity_type, count in sorted(entity_stats.items(), key=lambda x: x[1], reverse=True):
    print(f'{entity_type:20s} : {count:6d} 个')

# 打印样本
print('\n' + '=' * 80)
print('实体样本（每种类型前3个）')
print('=' * 80)

for entity_type in sorted(entity_stats.keys()):
    if entity_samples[entity_type]:
        print(f'\n【{entity_type}】')
        for i, sample in enumerate(entity_samples[entity_type], 1):
            print(f'\n  样本 {i}:')
            for key, value in sample.items():
                if key == 'type':
                    continue
                if isinstance(value, list) and len(value) == 3:
                    print(f'    {key:20s}: [{value[0]:.2f}, {value[1]:.2f}, {value[2]:.2f}]')
                elif isinstance(value, float):
                    print(f'    {key:20s}: {value:.2f}')
                else:
                    print(f'    {key:20s}: {value}')

# 检查支持的实体类型
print('\n' + '=' * 80)
print('编辑器支持情况')
print('=' * 80)

supported = ['LINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'ELLIPSE', 'SPLINE', 'POINT']
for entity_type in sorted(entity_stats.keys()):
    status = '✓ 支持' if entity_type in supported else '✗ 不支持'
    print(f'{entity_type:20s} : {status}')

print('\n' + '=' * 80)
print('可编辑参数汇总')
print('=' * 80)

params_info = {
    'LINE': ['start', 'end', 'color', 'lineweight'],
    'CIRCLE': ['center', 'radius', 'color', 'lineweight'],
    'ARC': ['center', 'radius', 'start_angle', 'end_angle', 'color', 'lineweight'],
    'TEXT/MTEXT': ['text', 'insert', 'height', 'color', 'lineweight'],
    'ELLIPSE': ['center', 'major_axis', 'ratio', 'start_param', 'end_param', 'color', 'lineweight'],
    'SPLINE': ['control_points', 'color', 'lineweight'],
    'POINT': ['location', 'color', 'lineweight']
}

for entity_type, params in params_info.items():
    print(f'\n{entity_type}:')
    for param in params:
        print(f'  - {param}')
