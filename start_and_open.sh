#!/bin/bash
# DXF 底图服务一键启动脚本

echo "🗺️  DXF + 底图服务启动工具"
echo "=================================="

# 检查端口是否被占用
echo "🔍 检查端口 8080..."
PID=$(lsof -ti:8080 2>/dev/null || netstat -anv | grep LISTEN | grep 8080 | awk '{print $9}' || echo "")
if [ ! -z "$PID" ]; then
    echo "⚠️  端口 8080 被占用，正在停止旧进程..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
fi

# 进入目录
cd "$(dirname "$0")"
echo "📁 工作目录: $(pwd)"

# 启动服务器
echo "🚀 启动 WebSocket 服务器..."
python3 -m uvicorn server:app --host 0.0.0.0 --port 8080 --reload > /tmp/dxf_server.log 2>&1 &
SERVER_PID=$!
echo "   进程 PID: $SERVER_PID"

# 等待服务器启动
echo "⏳ 等待服务器启动..."
for i in {1..15}; do
    sleep 0.5
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ 服务器已就绪!"
        break
    fi
    echo "   尝试 $i/15..."
done

# 检查服务器状态
if ! curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "❌ 服务器启动失败，查看日志:"
    cat /tmp/dxf_server.log
    exit 1
fi

# 打开浏览器
echo ""
echo "🌐 正在打开浏览器..."

# macOS 打开方式
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "   打开底图查看器..."
    open "http://localhost:8080/ui/slave_viewer_map.html"
    sleep 2
    echo "   打开主控端上传页面..."
    open "http://localhost:8080/ui/master_upload.html"
# Linux 打开方式
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:8080/ui/slave_viewer_map.html" &
    sleep 2
    xdg-open "http://localhost:8080/ui/master_upload.html" &
fi

echo ""
echo "=================================="
echo "✨ 服务已启动！"
echo ""
echo "📍 访问地址:"
echo "   底图查看器: http://localhost:8080/ui/slave_viewer_map.html"
echo "   主控端:     http://localhost:8080/ui/master_upload.html"
echo ""
echo "📖 使用步骤:"
echo "   1. 在主控端页面 (master_upload.html) 上传 DXF 文件"
echo "   2. 在底图查看器 (slave_viewer_map.html) 观察图形"
echo "   3. 如需配准，点击左侧面板「开始配准」按钮"
echo ""
echo "🛑 停止服务: kill $SERVER_PID"
echo "=================================="

# 保持脚本运行，显示日志
echo "📋 服务器日志 (按 Ctrl+C 停止):"
tail -f /tmp/dxf_server.log
