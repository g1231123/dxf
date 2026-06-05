import ezdxf

file_path = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'

print('=== 测试 1: 默认编码 ===')
try:
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    count = 0
    for entity in msp:
        if count >= 5:
            break
        entity_type = entity.dxftype()
        layer = entity.dxf.layer
        print(f'{entity_type} - Layer: {layer}')
        if entity_type in ['TEXT', 'MTEXT']:
            print(f'  Text: {entity.dxf.text}')
        count += 1
except Exception as e:
    print(f'错误: {e}')

print('\n=== 测试 2: GBK 编码 ===')
try:
    doc = ezdxf.readfile(file_path, encoding='gbk')
    msp = doc.modelspace()
    count = 0
    for entity in msp:
        if count >= 5:
            break
        entity_type = entity.dxftype()
        layer = entity.dxf.layer
        print(f'{entity_type} - Layer: {layer}')
        if entity_type in ['TEXT', 'MTEXT']:
            print(f'  Text: {entity.dxf.text}')
        count += 1
except Exception as e:
    print(f'错误: {e}')

print('\n=== 测试 3: GB18030 编码 ===')
try:
    doc = ezdxf.readfile(file_path, encoding='gb18030')
    msp = doc.modelspace()
    count = 0
    for entity in msp:
        if count >= 5:
            break
        entity_type = entity.dxftype()
        layer = entity.dxf.layer
        print(f'{entity_type} - Layer: {layer}')
        if entity_type in ['TEXT', 'MTEXT']:
            print(f'  Text: {entity.dxf.text}')
        count += 1
except Exception as e:
    print(f'错误: {e}')
