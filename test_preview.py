#!/usr/bin/env python3
"""测试 preview 功能的脚本"""
import base64
import io
import sys

# 测试 base64 解码
print("测试1: base64 解码")
test_b64 = "SGVsbG8gV29ybGQh"  # "Hello World!"
try:
    decoded = base64.b64decode(test_b64)
    print(f"  ✓ 成功: {type(decoded)}, len={len(decoded)}")
except Exception as e:
    print(f"  ✗ 失败: {e}")

# 测试 io.BytesIO
print("\n测试2: io.BytesIO")
try:
    buf = io.BytesIO(decoded)
    print(f"  ✓ 成功: {type(buf)}")
    print(f"  内容: {buf.read()}")
except Exception as e:
    print(f"  ✗ 失败: {e}")

# 测试 ezdxf
print("\n测试3: ezdxf 读取")
try:
    import ezdxf
    # 创建一个简单的 DXF 内存文件
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_circle((0, 0), 50)
    
    # 保存到内存
    buf = io.BytesIO()
    doc.write(buf)
    buf.seek(0)
    
    # 重新读取
    doc2 = ezdxf.read(buf)
    print(f"  ✓ 成功: 实体数量 = {len(doc2.modelspace())}")
except Exception as e:
    print(f"  ✗ 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试完成")
