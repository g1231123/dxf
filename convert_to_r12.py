import ezdxf

# 输入文件
input_file = '/Users/czy/Desktop/测试道路平纵面，横断面.dxf'
# 输出文件
output_file = '/Users/czy/Desktop/测试道路平纵面，横断面_R12.dxf'

print(f'读取文件: {input_file}')

# 读取原始 DXF
try:
    doc = ezdxf.readfile(input_file)
except:
    try:
        doc = ezdxf.readfile(input_file, encoding='gbk')
    except:
        doc = ezdxf.readfile(input_file, encoding='gb18030')

print(f'原始版本: {doc.dxfversion}')

# 转换为 R12 版本
print(f'转换为 R12 格式...')
# 创建新的 R12 文档
new_doc = ezdxf.new('R12')

# 复制图层
for layer in doc.layers:
    if layer.dxf.name not in new_doc.layers:
        # R12 只支持 0-255 的颜色
        color = layer.dxf.color
        if color < 0 or color > 255:
            color = 7  # 默认白色
        new_doc.layers.add(layer.dxf.name, color=color)

# 复制实体到新文档
msp_old = doc.modelspace()
msp_new = new_doc.modelspace()

for entity in msp_old:
    try:
        # 复制实体
        msp_new.add_foreign_entity(entity)
    except Exception as e:
        print(f'跳过实体 {entity.dxftype()}: {e}')

# 保存为 R12 ASCII DXF，使用 GBK 编码
# 注意：R12 格式本身不支持 Unicode，必须用 GBK 保存中文
new_doc.saveas(output_file, encoding='cp936')  # cp936 = GBK

print(f'✅ 转换完成！')
print(f'输出文件: {output_file}')

# 验证
print('\n验证转换结果:')
doc_r12 = ezdxf.readfile(output_file, encoding='gbk')
print(f'新版本: {doc_r12.dxfversion}')
print(f'实体数量: {len(list(doc_r12.modelspace()))}')
