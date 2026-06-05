# DXF Render Service

DXF/DWG 文件处理服务，支持 **渲染预览、AI 实时绘图、格式转换**。

- **PNG/JPEG/PDF 渲染** (QGIS 引擎 - 可选)
- **AI 实时绘图** (WebSocket + ezdxf/CadLike，无需 AutoCAD)
- **格式转换** (DXF ↔ DWG)

```
[前端] --WebSocket--> [FastAPI] --ezdxf--> [DXF/DWG]
                |
                └--QGIS (可选)--> [PNG/JPEG/PDF]
```

## 特性

| 功能 | 引擎 | 跨平台 | 说明 |
|------|------|--------|------|
| AI 绘图 | `ezdxf` | ✓ | 不依赖 AutoCAD，纯 Python |
| AI 绘图 | `autocad` | ✗ | Windows + AutoCAD COM |
| 渲染预览 | `qgis` | ✓ | 需要 QGIS (可选) |
| 格式转换 | `ezdxf` + ODA | ✓ | DWG 需要 ODA Converter |

## 目录结构

```
dxf_render_service/
├── server.py              # FastAPI 主服务
├── ws_server.py           # WebSocket 实时绘图
├── cadlike/               # 模仿 pyautocad 的跨平台库
│   ├── __init__.py
│   ├── core.py            # Autocad, APoint
│   ├── modelspace.py      # AddCircle, AddLine, etc.
│   ├── entities.py        # 实体类
│   └── ...
├── test_ai_draw.html      # AI 绘图测试页面
├── test_autocad_windows.html  # Windows AutoCAD 测试
├── API.md                 # 完整 API 文档
└── requirements.txt       # Python 依赖
```

## 环境要求

**QGIS 和 AutoCAD 都是可选依赖**，服务可以在纯 Python 环境下运行。

### 必需
- Python 3.9+
- `pip install fastapi uvicorn ezdxf websockets python-multipart`

### 可选（增强功能）
| 依赖 | 用途 | 安装命令 |
|------|------|---------|
| QGIS | PNG/JPEG 渲染 | 按平台安装 QGIS |
| pyautocad | Windows AutoCAD COM | `pip install pyautocad pywin32` |
| ODA File Converter | DWG 导出 | [下载](https://www.opendesign.com/guestfiles/oda_file_converter) |

### 平台特定说明

| 平台 | 推荐解释器 | 说明 |
|------|-----------|------|
| **Windows (OSGeo4W)** | `C:\OSGeo4W\bin\python-qgis.bat` | 如果需要 QGIS 渲染 |
| **macOS** | 系统 Python3 即可 | AI 绘图无需 QGIS |
| **Linux** | `python3` | AI 绘图无需 QGIS |

## 快速启动

### 通用启动（跨平台，无需 QGIS）

```bash
cd dxf_render_service
pip install fastapi uvicorn ezdxf websockets python-multipart
python3 -m uvicorn server:app --host 0.0.0.0 --port 8080
```

### Windows（OSGeo4W，如果需要 QGIS 渲染）

```powershell
cd dxf_render_service
.\run_windows.bat
```

### Windows（vcpkg 自编译）

在 PowerShell 里：

```powershell
$env:QGIS_PREFIX_PATH = "C:\path\to\qgis\install"
$env:QGIS_PYTHON_PATH = "C:\path\to\qgis\install\python"
$env:PATH = "C:\path\to\qgis\install\bin;$env:PATH"
python -m pip install -r requirements.txt
python server.py
```

### macOS

```bash
cd dxf_render_service
chmod +x run_unix.sh
./run_unix.sh
```

### Linux

```bash
cd dxf_render_service
chmod +x run_unix.sh
./run_unix.sh
```

服务启动后：

- 测试页面：<http://localhost:8080/>
- Swagger UI：<http://localhost:8080/docs>
- 健康检查：<http://localhost:8080/health>

## API

### `POST /render/dxf`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `file` | file (multipart) | — | `.dxf` 文件 |
| `width` | int | 1024 | 输出宽度（64–8192） |
| `height` | int | 768 | 输出高度（64–8192） |
| `fmt` | string | `png` | `png` \| `jpeg` \| `pdf` |
| `background` | string | `#ffffff` | 背景色 |
| `crs` | string | — | 目标 CRS，如 `EPSG:3857`（可选） |

**返回**：图片或 PDF 二进制流。响应头 `X-Render-Meta` 包含元信息。

### `POST /render/dxf/meta`

只解析 DXF，返回要素数 / 子图层 / 范围。不渲染。

### `GET /health`

健康检查 + QGIS prefix path。

## 用 curl 测试

```bash
# 渲染成 PNG
curl -X POST http://localhost:8080/render/dxf \
  -F "file=@drawing.dxf" \
  -F "width=1920" \
  -F "height=1080" \
  -F "fmt=png" \
  --output render.png

# 只看元数据
curl -X POST http://localhost:8080/render/dxf/meta \
  -F "file=@drawing.dxf"
```

## 前端调用

```javascript
const fd = new FormData();
fd.append("file", dxfFile);
fd.append("width", 1920);
fd.append("height", 1080);
fd.append("fmt", "png");

const res = await fetch("http://localhost:8080/render/dxf", {
  method: "POST",
  body: fd,
});
const blob = await res.blob();
imgEl.src = URL.createObjectURL(blob);
```

## 进阶

- **样式**：在 `_load_dxf_layers` 后调用 `layer.loadNamedStyle("style.qml")`
- **裁切范围**：把 `bbox` 从前端传进来，覆盖 `_combined_extent`
- **缓存**：用文件哈希做 key，缓存到 Redis / 磁盘
- **并发**：`uvicorn server:app --workers N`，注意每个 worker 会各自 `initQgis()`

## 故障排查

| 报错 | 原因 | 解决 |
|------|------|------|
| `Failed to import PyQGIS` | python 不带 qgis 模块 | 换用 OSGeo4W / QGIS.app 自带 python |
| `No valid geometry layers in DXF` | DXF 没有 OGR 能识别的图层 | 用 QGIS 桌面端验证文件是否有效 |
| 渲染空白 | 图层 CRS 不正确或超出 extent | 试着不传 `crs`，让服务用图层原 CRS |
| 启动卡住 | `initQgis()` 加载插件慢 | 第一次启动属正常，几秒到十几秒 |
