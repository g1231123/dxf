#!/usr/bin/env python3
"""
DXF + 底图服务测试脚本
快速验证 slave_viewer_map.html 是否能正常工作
"""

import asyncio
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# 测试 DXF 数据（模拟北京附近的一些几何图形）
TEST_DXF_DATA = {
    "type": "parse",
    "filename": "test_beijing.dxf",
    "file_data": None  # 将使用模拟数据
}

# 模拟 shapes 数据（CGCS2000 坐标，北京附近）
TEST_SHAPES = [
    # 矩形建筑 - 天安门广场附近
    {
        "id": "rect_1",
        "name": "Building_A",
        "type": "AddRectangle",
        "x": 116.3912,
        "y": 39.9042,
        "width": 0.001,  # 约 100 米
        "height": 0.0008,
        "color": "#FF0000",
        "layer": "建筑"
    },
    # 圆形地标
    {
        "id": "circle_1",
        "name": "Landmark_1",
        "type": "AddCircle",
        "center": [116.3930, 39.9050, 0],
        "radius": 0.0005,
        "color": "#00FF00",
        "layer": "地标"
    },
    # 线段 - 道路
    {
        "id": "line_1",
        "name": "Road_1",
        "type": "AddLine",
        "start_point": [116.3900, 39.9030, 0],
        "end_point": [116.3950, 39.9070, 0],
        "color": "#0000FF",
        "layer": "道路"
    },
    # 文字标注
    {
        "id": "text_1",
        "name": "Label_1",
        "type": "AddText",
        "text": "测试区域",
        "insert_point": [116.3920, 39.9060, 0],
        "height": 0.0003,
        "rotation": 0,
        "color": "#FFFF00",
        "layer": "标注"
    },
    # 多段线 - 围栏
    {
        "id": "poly_1",
        "name": "Fence_1",
        "type": "AddPolyline",
        "points": [
            [116.3880, 39.9020, 0],
            [116.3960, 39.9020, 0],
            [116.3960, 39.9080, 0],
            [116.3880, 39.9080, 0]
        ],
        "closed": True,
        "color": "#FF00FF",
        "layer": "围栏"
    }
]

def check_server():
    """检查服务器是否运行"""
    import urllib.request
    try:
        urllib.request.urlopen('http://localhost:8080/health', timeout=2)
        return True
    except:
        return False

def start_server():
    """启动服务器"""
    print("🚀 启动 WebSocket 服务器...")
    subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'server:app', 
         '--host', '0.0.0.0', '--port', '8080'],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)

def open_browsers():
    """打开浏览器"""
    urls = [
        'http://localhost:8080/master_upload.html',
        'http://localhost:8080/slave_viewer_map.html'
    ]
    
    print("\n🌐 正在打开浏览器...")
    for url in urls:
        print(f"   打开: {url}")
        webbrowser.open(url)
        time.sleep(1)

def print_instructions():
    """打印使用说明"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    DXF + 底图服务测试指南                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1️⃣  在 master_upload.html 页面中上传任意 DXF 文件             ║
║                                                              ║
║  2️⃣  观察 slave_viewer_map.html 是否自动显示图形              ║
║                                                              ║
║  3️⃣  在 slave_viewer_map.html 中测试以下功能：                ║
║      • 切换底图（高德/天地图/OSM）                            ║
║      • 鼠标移动查看坐标                                       ║
║      • 点击实体查看高亮                                       ║
║      • 图层开关                                              ║
║      • 导出 GeoJSON/KML                                     ║
║                                                              ║
║  4️⃣  坐标系设置：                                             ║
║      • 如果 DXF 是 WGS84 经纬度，选择 "WGS84 (EPSG:4326)"      ║
║      • 如果 DXF 是局部坐标，选择 "局部坐标" 并观察效果          ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

按 Ctrl+C 停止服务器
    """)

def main():
    print("=" * 60)
    print("🗺️  DXF + 底图服务测试工具")
    print("=" * 60)
    
    # 检查服务器
    if not check_server():
        start_server()
        if not check_server():
            print("❌ 服务器启动失败，请手动启动:")
            print("   python3 -m uvicorn server:app --host 0.0.0.0 --port 8080")
            return 1
    
    print("✅ 服务器运行正常")
    
    # 打开浏览器
    open_browsers()
    
    # 打印说明
    print_instructions()
    
    # 保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 测试结束")
        return 0

if __name__ == '__main__':
    sys.exit(main())
