import ezdxf
from collections import defaultdict

input_file = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'
output_file = '/Users/czy/Desktop/测试道路_R12提示词模板.txt'

print(f'读取 DXF 文件: {input_file}')

# 读取 DXF
try:
    doc = ezdxf.readfile(input_file)
except:
    try:
        doc = ezdxf.readfile(input_file, encoding='gbk')
    except:
        doc = ezdxf.readfile(input_file, encoding='gb18030')

msp = doc.modelspace()

# 统计实体
entity_stats = defaultdict(int)
layer_stats = defaultdict(int)
sample_entities = defaultdict(list)

for entity in msp:
    entity_type = entity.dxftype()
    entity_stats[entity_type] += 1
    
    if hasattr(entity.dxf, 'layer'):
        layer_stats[entity.dxf.layer] += 1
    
    # 收集示例（每种类型最多3个）
    if len(sample_entities[entity_type]) < 3:
        sample_data = {}
        
        if entity_type == "LINE":
            sample_data = {
                "start": list(entity.dxf.start),
                "end": list(entity.dxf.end),
                "layer": entity.dxf.layer
            }
        elif entity_type == "CIRCLE":
            sample_data = {
                "center": list(entity.dxf.center),
                "radius": entity.dxf.radius,
                "layer": entity.dxf.layer
            }
        elif entity_type in ["TEXT", "MTEXT"]:
            sample_data = {
                "text": entity.dxf.text,
                "insert": list(entity.dxf.insert) if hasattr(entity.dxf, 'insert') else None,
                "height": entity.dxf.height if hasattr(entity.dxf, 'height') else None,
                "layer": entity.dxf.layer
            }
        elif entity_type == "ARC":
            sample_data = {
                "center": list(entity.dxf.center),
                "radius": entity.dxf.radius,
                "start_angle": entity.dxf.start_angle,
                "end_angle": entity.dxf.end_angle,
                "layer": entity.dxf.layer
            }
        elif entity_type == "POINT":
            sample_data = {
                "location": list(entity.dxf.location),
                "layer": entity.dxf.layer
            }
        
        if sample_data:
            sample_entities[entity_type].append(sample_data)

# 生成提示词模板
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("=" * 80 + "\n")
    f.write("DXF R12 格式编辑提示词模板\n")
    f.write("=" * 80 + "\n\n")
    
    f.write(f"文件信息：\n")
    f.write(f"  文件名：测试道路平纵面，横断面\n")
    f.write(f"  DXF 版本：{doc.dxfversion}\n")
    f.write(f"  总实体数：{sum(entity_stats.values())}\n")
    f.write(f"  图层数：{len(layer_stats)}\n\n")
    
    f.write("=" * 80 + "\n")
    f.write("实体统计\n")
    f.write("=" * 80 + "\n\n")
    
    for entity_type, count in sorted(entity_stats.items(), key=lambda x: x[1], reverse=True):
        f.write(f"  {entity_type:15s} : {count:6d} 个\n")
    
    f.write("\n" + "=" * 80 + "\n")
    f.write("图层统计（前10个）\n")
    f.write("=" * 80 + "\n\n")
    
    for layer, count in sorted(layer_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
        f.write(f"  {layer:30s} : {count:6d} 个实体\n")
    
    f.write("\n" + "=" * 80 + "\n")
    f.write("可编辑实体类型及参数\n")
    f.write("=" * 80 + "\n\n")
    
    # LINE
    if "LINE" in entity_stats:
        f.write(f"1. LINE（直线） - 共 {entity_stats['LINE']} 个\n")
        f.write("   可编辑参数：\n")
        f.write("   ✓ start - 起点坐标 [x, y, z]\n")
        f.write("     类型：point\n")
        f.write("     说明：三维坐标，可修改任意值\n")
        if sample_entities["LINE"]:
            f.write(f"     示例：{sample_entities['LINE'][0]['start']}\n")
        f.write("\n")
        f.write("   ✓ end - 终点坐标 [x, y, z]\n")
        f.write("     类型：point\n")
        if sample_entities["LINE"]:
            f.write(f"     示例：{sample_entities['LINE'][0]['end']}\n")
        f.write("\n")
    
    # CIRCLE
    if "CIRCLE" in entity_stats:
        f.write(f"2. CIRCLE（圆） - 共 {entity_stats['CIRCLE']} 个\n")
        f.write("   可编辑参数：\n")
        f.write("   ✓ center - 圆心坐标 [x, y, z]\n")
        f.write("     类型：point\n")
        if sample_entities["CIRCLE"]:
            f.write(f"     示例：{sample_entities['CIRCLE'][0]['center']}\n")
        f.write("\n")
        f.write("   ✓ radius - 半径\n")
        f.write("     类型：number\n")
        f.write("     约束：最小值 0.001\n")
        if sample_entities["CIRCLE"]:
            f.write(f"     示例：{sample_entities['CIRCLE'][0]['radius']}\n")
        f.write("\n")
    
    # ARC
    if "ARC" in entity_stats:
        f.write(f"3. ARC（圆弧） - 共 {entity_stats['ARC']} 个\n")
        f.write("   可编辑参数：\n")
        f.write("   ✓ center - 圆心坐标 [x, y, z]\n")
        f.write("   ✓ radius - 半径（最小值 0.001）\n")
        f.write("   ✓ start_angle - 起始角度 0-360°\n")
        f.write("   ✓ end_angle - 结束角度 0-360°\n")
        if sample_entities["ARC"]:
            f.write(f"     示例：角度 {sample_entities['ARC'][0]['start_angle']:.1f}° 到 {sample_entities['ARC'][0]['end_angle']:.1f}°\n")
        f.write("\n")
    
    # TEXT/MTEXT
    text_count = entity_stats.get("TEXT", 0) + entity_stats.get("MTEXT", 0)
    if text_count > 0:
        f.write(f"4. TEXT/MTEXT（文字） - 共 {text_count} 个\n")
        f.write("   可编辑参数：\n")
        f.write("   ✓ text - 文字内容\n")
        f.write("     类型：string\n")
        f.write("     说明：支持中文（GBK 编码）\n")
        if sample_entities["TEXT"] or sample_entities["MTEXT"]:
            sample = sample_entities["TEXT"][0] if sample_entities["TEXT"] else sample_entities["MTEXT"][0]
            f.write(f"     示例：{sample['text']}\n")
        f.write("\n")
        f.write("   ✓ insert - 插入点坐标 [x, y, z]\n")
        f.write("   ✓ height - 文字高度（最小值 0.1）\n")
        f.write("\n")
    
    # POINT
    if "POINT" in entity_stats:
        f.write(f"5. POINT（点） - 共 {entity_stats['POINT']} 个\n")
        f.write("   可编辑参数：\n")
        f.write("   ✓ location - 点坐标 [x, y, z]\n")
        if sample_entities["POINT"]:
            f.write(f"     示例：{sample_entities['POINT'][0]['location']}\n")
        f.write("\n")
    
    f.write("=" * 80 + "\n")
    f.write("不可编辑的属性（只读）\n")
    f.write("=" * 80 + "\n\n")
    f.write("  ✗ handle - 实体句柄（系统生成，唯一标识）\n")
    f.write("  ✗ layer - 图层名称（建议不修改）\n")
    f.write("  ✗ color - 颜色索引\n")
    f.write("  ✗ linetype - 线型\n\n")
    
    f.write("=" * 80 + "\n")
    f.write("参数类型说明\n")
    f.write("=" * 80 + "\n\n")
    f.write("point（坐标点）\n")
    f.write("  格式：[x, y, z]\n")
    f.write("  说明：三维坐标，可修改任意值\n")
    f.write("  示例：[1000.0, 2000.0, 0.0]\n\n")
    
    f.write("number（数值）\n")
    f.write("  格式：浮点数或整数\n")
    f.write("  说明：可能有最小值/最大值约束\n")
    f.write("  示例：50.0, 3.5, 100\n\n")
    
    f.write("string（文本）\n")
    f.write("  格式：字符串\n")
    f.write("  说明：支持中文（GBK 编码）\n")
    f.write("  示例：桩号 K0+000, 测试文字\n\n")
    
    f.write("=" * 80 + "\n")
    f.write("编辑流程\n")
    f.write("=" * 80 + "\n\n")
    f.write("1. 点击图片上的实体\n")
    f.write("   → 系统自动识别实体类型\n\n")
    f.write("2. 查看可编辑参数\n")
    f.write("   → 显示参数名称、类型、当前值、约束\n\n")
    f.write("3. 修改参数值\n")
    f.write("   → 坐标：输入 [x, y, z] 格式\n")
    f.write("   → 数值：输入数字\n")
    f.write("   → 文字：直接输入文本\n\n")
    f.write("4. 生成新 DXF\n")
    f.write("   → 保存为 R12 格式 + GBK 编码\n\n")
    
    f.write("=" * 80 + "\n")
    f.write("示例修改（JSON 格式）\n")
    f.write("=" * 80 + "\n\n")
    
    if sample_entities["LINE"]:
        f.write("修改直线起点：\n")
        f.write('{\n')
        f.write('  "handle": "1A0",\n')
        f.write('  "changes": {\n')
        f.write(f'    "start": {sample_entities["LINE"][0]["start"]}\n')
        f.write('  }\n')
        f.write('}\n\n')
    
    if sample_entities["TEXT"] or sample_entities["MTEXT"]:
        sample = sample_entities["TEXT"][0] if sample_entities["TEXT"] else sample_entities["MTEXT"][0]
        f.write("修改文字内容和位置：\n")
        f.write('{\n')
        f.write('  "handle": "2B5",\n')
        f.write('  "changes": {\n')
        f.write('    "text": "新的文字内容",\n')
        if sample['insert']:
            f.write(f'    "insert": {sample["insert"]},\n')
        if sample['height']:
            f.write(f'    "height": {sample["height"]}\n')
        f.write('  }\n')
        f.write('}\n\n')
    
    f.write("=" * 80 + "\n")
    f.write("R12 格式说明\n")
    f.write("=" * 80 + "\n\n")
    f.write("⚠ R12 格式限制：\n")
    f.write("  - 不支持 INSERT（块引用）实体编辑\n")
    f.write("  - 不支持 LEADER（引线）实体编辑\n")
    f.write("  - 颜色值限制在 0-255\n")
    f.write("  - 必须使用 GBK 编码保存中文\n\n")
    
    f.write("✓ 优势：\n")
    f.write("  - 文件体积小（比新版本小 80%+）\n")
    f.write("  - 兼容性最好（所有 CAD 软件支持）\n")
    f.write("  - 解析速度快\n")
    f.write("  - 标准 ASCII 文本格式\n\n")
    
    f.write("=" * 80 + "\n")

print(f'\n✅ 提示词模板已生成！')
print(f'输出文件: {output_file}')
print(f'\n文件统计:')
print(f'  总实体数: {sum(entity_stats.values())}')
print(f'  实体类型: {len(entity_stats)} 种')
print(f'  图层数: {len(layer_stats)} 个')
