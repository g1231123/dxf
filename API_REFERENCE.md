# API 参考 - 请求/响应数据格式

## REST API

### 1. 健康检查

**请求**
```
GET /health
```

**响应**
```json
{
  "status": "ok",
  "qgis_available": false,
  "qgis_prefix": null,
  "autocad_available": false,
  "work_dir": "/tmp/...",
  "dwg_converter": null
}
```

---

### 2. DXF 渲染

**请求**
```
POST /render/dxf
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必需 | 示例 |
|------|------|------|------|
| `file` | File | ✓ | drawing.dxf |
| `width` | int | | 1920 |
| `height` | int | | 1080 |
| `fmt` | string | | png / jpeg / pdf |
| `background` | string | | #ffffff |

**响应**
- 成功: 图片二进制流 (Content-Type: image/png)
- 失败: `400 Bad Request`

---

### 3. DXF 元数据

**请求**
```
POST /render/dxf/meta
Content-Type: multipart/form-data

file: drawing.dxf
```

**响应**
```json
{
  "layers": ["0", "Layer1"],
  "entity_count": 150,
  "extent": [0, 0, 1000, 800]
}
```

---

### 4. DXF 转 DWG

**请求**
```
POST /convert/dwg
Content-Type: multipart/form-data

file: drawing.dxf
```

**响应**
- 成功: DWG 二进制流
- 失败: `400 Bad Request`

---

### 5. 文件上传

**请求**
```
POST /data/upload
Content-Type: multipart/form-data

file: drawing.dxf
```

**响应**
```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "drawing.dxf",
  "format": "dxf",
  "bbox": [0, 0, 1000, 800]
}
```

---

## WebSocket API

**连接**: `ws://localhost:8080/ws/render`

### 1. AI 绘图 (ai_edit)

**请求 (发送)**
```json
{
  "type": "ai_edit",
  "engine": "autocad",
  "output_format": "dxf",
  "filename": "drawing.dxf",
  "file_data": "base64...",
  "shapes": [
    {
      "id": "circle1",
      "type": "circle",
      "geometry": {"cx": 100, "cy": 100, "r": 50},
      "style": {"stroke_color": "#FF0000"},
      "layer": "0"
    },
    {
      "id": "line1",
      "type": "line",
      "geometry": {"points": [[0,0], [100,100]]},
      "style": {"stroke_color": "#00FF00"}
    },
    {
      "id": "rect1",
      "type": "rectangle",
      "geometry": {"x": 50, "y": 50, "width": 100, "height": 80}
    },
    {
      "id": "arc1",
      "type": "arc",
      "geometry": {"cx": 100, "cy": 100, "r": 50, "start_angle": 0, "end_angle": 90}
    },
    {
      "id": "text1",
      "type": "text",
      "geometry": {"x": 100, "y": 100},
      "style": {"text": "Hello", "font_size": 12}
    },
    {
      "id": "ellipse1",
      "type": "ellipse",
      "geometry": {"cx": 100, "cy": 100, "rx": 50, "ry": 30}
    }
  ]
}
```

**响应 (接收)**
```json
{
  "type": "connected",
  "client_id": "client-uuid",
  "total_clients": 5
}
```

```json
{
  "type": "started",
  "filename": "drawing.dxf",
  "output_format": "dxf",
  "shape_count": 6,
  "engine_requested": "autocad"
}
```

```json
{
  "type": "result",
  "format": "dxf_base64",
  "filename": "ai_drawing.dxf",
  "data": "base64-encoded-content",
  "size_bytes": 12345,
  "shape_count": 6,
  "success_count": 6,
  "error_count": 0,
  "engine_used": "ezdxf",
  "details": [
    {"shape_id": "circle1", "type": "circle", "status": "created"},
    {"shape_id": "line1", "type": "line", "status": "created"}
  ]
}
```

**错误响应**
```json
{
  "type": "error",
  "code": "EZDXF_NOT_INSTALLED",
  "msg": "AI绘图功能需要安装 ezdxf"
}
```

---

### 2. 导出文件 (export)

**请求**
```json
{
  "type": "export",
  "file_data": "base64...",
  "filename": "input.dxf",
  "output_format": "dxf",
  "edits": [
    {"op": "move", "handle": "1A2B", "dx": 10, "dy": 5}
  ]
}
```

**响应**
```json
{
  "type": "result",
  "format": "dxf_base64",
  "filename": "input.edited.dxf",
  "data": "base64...",
  "size_bytes": 12345,
  "elapsed_ms": 500
}
```

---

### 3. 渲染 PNG (render)

**请求**
```json
{
  "type": "render",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "width": 1280,
  "height": 720,
  "style": {"background": "white"},
  "view": {"bbox": [0, 0, 1000, 1000]}
}
```

**响应**
```json
{
  "type": "result",
  "format": "png_base64",
  "data": "base64...",
  "size_bytes": 45678,
  "width": 1280,
  "height": 720
}
```

---

### 4. 心跳

**请求**
```json
{"type": "ping"}
```

**响应**
```json
{"type": "pong", "ts": 1234567890.123}
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| `INVALID_PARAMS` | 参数错误 |
| `FILE_NOT_FOUND` | 文件不存在 |
| `UNSUPPORTED_FMT` | 不支持的格式 |
| `EXPORT_TIMEOUT` | 导出超时 |
| `EXPORT_FAILED` | 导出失败 |
| `AI_EDIT_FAILED` | AI 绘图失败 |
| `EZDXF_NOT_INSTALLED` | ezdxf 未安装 |
| `RENDER_FAILED` | 渲染失败 |
| `RENDER_TIMEOUT` | 渲染超时 |

---

## Shape 类型详解

### circle (圆)
```json
{
  "type": "circle",
  "geometry": {"cx": 100, "cy": 100, "r": 50}
}
```

### line (直线/多段线)
```json
{
  "type": "line",
  "geometry": {"points": [[0,0], [100,0], [100,100]]}
}
```

### rectangle (矩形)
```json
{
  "type": "rectangle",
  "geometry": {"x": 50, "y": 50, "width": 100, "height": 80, "rotation": 0}
}
```

### arc (圆弧)
```json
{
  "type": "arc",
  "geometry": {"cx": 100, "cy": 100, "r": 50, "start_angle": 0, "end_angle": 90}
}
```

### text (文字)
```json
{
  "type": "text",
  "geometry": {"x": 100, "y": 100},
  "style": {"text": "Hello", "font_size": 12, "color": "#000000"}
}
```

### ellipse (椭圆)
```json
{
  "type": "ellipse",
  "geometry": {"cx": 100, "cy": 100, "rx": 50, "ry": 30, "rotation": 0}
}
```
