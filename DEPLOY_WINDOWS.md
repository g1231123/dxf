# Windows 部署指南 - 使用 AutoCAD COM (pyautocad)

## 环境要求

- **Windows 10/11** (64位)
- **AutoCAD 2018+** 已安装并运行
- **Python 3.9+**

## 安装步骤

### 1. 安装依赖

```bash
pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets
```

### 2. 启动 AutoCAD

先打开 AutoCAD 软件，保持运行状态。

### 3. 启动服务端

```bash
python server.py
```

### 4. 测试连接

服务端会自动检测 AutoCAD COM 接口：

```
[INFO] Using AutoCAD COM engine for AI drawing
```

## API 调用示例

请求会自动使用 AutoCAD COM 引擎：

```json
{
  "type": "ai_edit",
  "engine": "autocad",
  "shapes": [
    {
      "type": "circle",
      "geometry": {"cx": 100, "cy": 100, "r": 50},
      "style": {"stroke_color": "#FF0000"}
    },
    {
      "type": "text",
      "geometry": {"x": 100, "y": 100},
      "style": {"text": "客厅", "font_size": 14, "color": "#000000"}
    }
  ]
}
```

## 效果

- ✅ **文字直接显示**在 AutoCAD 中
- ✅ **实时预览**图形绘制过程
- ✅ **无需额外渲染**步骤

## 常见问题

### Q: 提示 "AutoCAD COM not available"
A: 确保 AutoCAD 已启动，且以管理员身份运行服务端

### Q: 文字显示为乱码
A: 设置 AutoCAD 字体为支持中文的字体（如 simsun.ttc）

### Q: 如何切换回 ezdxf
A: 请求中设置 `"engine": "ezdxf"` 或删除 engine 字段自动回退
