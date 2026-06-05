#!/usr/bin/env python3
"""测试 preview 功能的脚本"""
import asyncio
import base64
import io
import json
import sys
import tempfile
import os

# 创建一个简单的测试 DXF 文件
def create_test_dxf():
    try:
        import ezdxf
        doc = ezdxf.new()
        msp = doc.modelspace()
        # 添加一些图形
        msp.add_circle((0, 0), 50)
        msp.add_line((-50, -50), (50, 50))
        msp.add_rectangle((-30, -30), (30, 30))
        
        # 保存到内存
        buf = io.BytesIO()
        doc.write(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"创建 DXF 失败: {e}")
        return None

# 测试 WebSocket preview
async def test_preview():
    try:
        import websockets
    except ImportError:
        print("❌ 需要安装 websockets: pip install websockets")
        return False
    
    uri = "ws://localhost:8080/ws/render"
    
    # 创建测试 DXF
    dxf_bytes = create_test_dxf()
    if not dxf_bytes:
        print("❌ 无法创建测试 DXF")
        return False
    
    print(f"✓ 创建测试 DXF: {len(dxf_bytes)} bytes")
    
    # Base64 编码
    b64_data = base64.b64encode(dxf_bytes).decode('utf-8')
    print(f"✓ Base64 编码: {len(b64_data)} chars")
    
    # 准备消息
    msg = {
        "type": "preview",
        "file_data": b64_data,
        "width": 800,
        "height": 600
    }
    
    try:
        async with websockets.connect(uri) as ws:
            print(f"✓ 已连接: {uri}")
            
            # 等待 connected 消息
            init_msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"← 收到: {init_msg[:100]}...")
            
            # 发送 preview 请求
            await ws.send(json.dumps(msg))
            print(f"→ 发送 preview 请求 ({len(json.dumps(msg))} bytes)")
            
            # 等待响应
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            
            print(f"← 收到响应: {json.dumps(data, indent=2)[:500]}")
            
            if data.get("type") == "preview":
                print("✅ SUCCESS! 收到预览图片")
                return True
            elif data.get("type") == "error":
                print(f"❌ FAILED! 错误: {data.get('msg')}")
                return False
            else:
                print(f"⚠️  未知响应类型: {data.get('type')}")
                return False
                
    except asyncio.TimeoutError:
        print("❌ 超时")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试直接调用 ezdxf
def test_ezdxf_directly():
    print("\n=== 测试 ezdxf 直接读取 ===")
    try:
        import ezdxf
        import tempfile
        import os
        
        # 创建 DXF
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_circle((0, 0), 50)
        
        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dxf', delete=False) as f:
            doc.write(f)
            temp_path = f.name
        
        try:
            # 从文件读取
            doc2 = ezdxf.read(temp_path)
            print(f"✓ ezdxf.read(文件路径) 成功: {len(doc2.modelspace())} 个实体")
        finally:
            os.unlink(temp_path)
        
        # 测试从 bytes 读取
        buf = io.BytesIO()
        doc.write(buf)
        buf.seek(0)
        
        try:
            doc3 = ezdxf.read(buf)
            print(f"✓ ezdxf.read(BytesIO) 成功: {len(doc3.modelspace())} 个实体")
        except Exception as e:
            print(f"✗ ezdxf.read(BytesIO) 失败: {e}")
        
        return True
    except Exception as e:
        print(f"✗ ezdxf 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== DXF Render Service Preview 测试 ===\n")
    
    # 测试 ezdxf
    test_ezdxf_directly()
    
    print("\n=== 测试 WebSocket Preview ===")
    result = asyncio.run(test_preview())
    
    sys.exit(0 if result else 1)
