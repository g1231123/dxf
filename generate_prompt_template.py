import ezdxf
import json

file_path = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'
output_file = '/Users/czy/Desktop/测试道路平纵面_提示词模板.json'

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
entity_types = {}
editable_params = {}

for entity in msp:
    entity_type = entity.dxftype()
    
    if entity_type not in entity_types:
        entity_types[entity_type] = 0
    entity_types[entity_type] += 1
    
    # 提取可编辑参数
    if entity_type not in editable_params:
        editable_params[entity_type] = {
            "count": 0,
            "params": {}
        }
    
    editable_params[entity_type]["count"] += 1
    
    # 根据实体类型提取参数
    if entity_type == "LINE":
        editable_params[entity_type]["params"] = {
            "start": {
                "type": "point",
                "description": "起点坐标 [x, y, z]",
                "editable": True,
                "example": [0, 0, 0]
            },
            "end": {
                "type": "point",
                "description": "终点坐标 [x, y, z]",
                "editable": True,
                "example": [100, 100, 0]
            }
        }
    elif entity_type == "CIRCLE":
        editable_params[entity_type]["params"] = {
            "center": {
                "type": "point",
                "description": "圆心坐标 [x, y, z]",
                "editable": True,
                "example": [0, 0, 0]
            },
            "radius": {
                "type": "number",
                "description": "半径",
                "editable": True,
                "min": 0.001,
                "example": 50.0
            }
        }
    elif entity_type in ["TEXT", "MTEXT"]:
        editable_params[entity_type]["params"] = {
            "text": {
                "type": "string",
                "description": "文字内容",
                "editable": True,
                "example": "示例文字"
            },
            "insert": {
                "type": "point",
                "description": "插入点坐标 [x, y, z]",
                "editable": True,
                "example": [0, 0, 0]
            },
            "height": {
                "type": "number",
                "description": "文字高度",
                "editable": True,
                "min": 0.1,
                "example": 5.0
            }
        }
    elif entity_type == "ARC":
        editable_params[entity_type]["params"] = {
            "center": {
                "type": "point",
                "description": "圆心坐标 [x, y, z]",
                "editable": True,
                "example": [0, 0, 0]
            },
            "radius": {
                "type": "number",
                "description": "半径",
                "editable": True,
                "min": 0.001,
                "example": 50.0
            },
            "start_angle": {
                "type": "number",
                "description": "起始角度（度）",
                "editable": True,
                "min": 0,
                "max": 360,
                "example": 0
            },
            "end_angle": {
                "type": "number",
                "description": "结束角度（度）",
                "editable": True,
                "min": 0,
                "max": 360,
                "example": 90
            }
        }
    elif entity_type == "POINT":
        editable_params[entity_type]["params"] = {
            "location": {
                "type": "point",
                "description": "点坐标 [x, y, z]",
                "editable": True,
                "example": [0, 0, 0]
            }
        }

# 生成提示词模板
template = {
    "file_info": {
        "name": "测试道路平纵面，横断面",
        "version": doc.dxfversion,
        "total_entities": len(list(msp))
    },
    "entity_statistics": entity_types,
    "editable_parameters": editable_params,
    "usage": {
        "description": "DXF 实体编辑提示词模板",
        "instructions": [
            "1. 点击图片上的实体",
            "2. 查看实体的可编辑参数",
            "3. 修改参数值",
            "4. 生成新的 DXF 文件"
        ],
        "parameter_types": {
            "point": "坐标点 [x, y, z]，可修改任意坐标值",
            "number": "数值类型，需遵守 min/max 约束",
            "string": "文本类型，可输入任意文字"
        }
    }
}

# 保存为 JSON
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(template, f, ensure_ascii=False, indent=2)

print(f'\n✅ 提示词模板已生成！')
print(f'输出文件: {output_file}')
print(f'\n实体统计:')
for entity_type, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
    print(f'  {entity_type}: {count} 个')
