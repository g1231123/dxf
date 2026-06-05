# DXF Render Service - API 文档

## 概览

- **基础URL**: `http://localhost:8080`
- **WebSocket**: `ws://localhost:8080/ws/render`
- **健康检查**: `GET /health`

---

## REST API

### 1. 健康检查

```
GET /health
```

**响应**:
```json
{
  "status": "ok",
  "qgis_available": false,
  "autocad_available": false,
  "work_dir": "/tmp/...",
  "dwg_converter": null
}
```

---

### 2. DXF 渲染 (PNG/JPEG)

```
POST /render/dxf
Content-Type: multipart/form-data
```

**参数**:

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `file` | File | ✓ | DXF 文件 |
| `format` | String | | `png` (默认), `jpeg`, `pdf` |
| `width` | Integer | | 宽度像素 (默认 1280) |
| `height` | Integer | | 高度像素 (默认 720) |

**curl 示例**:
```bash
curl -X POST http://localhost:8080/render/dxf \
  -F "file=@drawing.dxf" \
  -F "format=png" \
  -F "width=1920" \
  -F "height=1080" \
  --output preview.png
```

---

###################################################################orm-data
```

**参数**:

| 字段 | 类型 | �| 字段 | 类型 | �| 字段 | 类型 --| 字段 | 类型 | �| 字段 | �文件 |

---

### 4. DXF 元数据

```
POST /render/dPOST /a
Content-Type: multipart/form-data
```

**响应**响应**�件的图�**响应**响应�**响应**响应**�件的��**响应**响应**�件的帲染)

```
POST /data/upload
Content-Type: multipart/foCo-data
```

**参数**:

| 字段 | 类型 | 字段 | 类�---|------|------|
| `file` | File | ✓ |

**响应**:
```json
{
  "file_id": "uuid-string"  "file_id": "uuid-string"  ",  "file_at": "dxf",
  "bbox": [xmin, ymin, xmax, ymax]
}
```

---

## WebSocket API

### 连�### 连�### 连�### 连�### 连�### 连�### 连�###calhost:8080/ws/render');
```

### 消息类型

#### 1. AI 实时绘图 (`ai_edit`)

**发送**:
```json
{
  "type": "ai_edit",
  "type": "ai_edit",
�� (     // 可选: "autocad", "ezdxf", null=蛾 (     // 可选:mat": "dxf",     // 可选: "dxf", "dwg"
  "file_data": "base64...",   // 可选, 不传则创建新文件
  "f  ename": "drawing  "f  ename": "drawing  "f  ename": "drawing  "f  ename": "drawing  "f  ename": "drawing  "f  eometry": {"cx": 100, "cy": 100, "r": 50},
  "f  ename": "drawioke_color": "#FF0000", "stroke_width": 0.25},
      "layer": "0"
    },
    {
      "id": "line_1",
      "type": "line",
      "geometry": {"points": [[0      "geometry",
      "geometry": {"points": [[0"#00FF00"}
    },
                                                  le",                      ": 50, "y": 50, "width":                                                   le",                    {
                              ype": "text",
      "geometry": {"x      "geometry": {"x      "geometry": {"x      "geometry": {"x      "geometry": {0000"}
           {
                                        ,
       geometry": {"cx"       geometry": {r"       geometry": {:        geometry": {"cx"       geometry": {r"       geometry": {:        geometry": {"cx"       geometry"x": 100, "cy": 100, "rx": 50, "ry": 30}
    }
  ]
}
```

**响应**:
```json
{
  "type": "result",
  "format": "dxf_base64",
  "filename": "ai_drawing.dxf",
  "data": "base64-encoded-dxf-content",
  "size_bytes": 12345,
  "shape_count": 6,
  "success_count": 6,
  "error_count": 0,
  "engine_used": "ezdxf",
  "details": [
    {"shape_id": "circle_1", "status": "created"}
  ]
}
```

#### 2. 导出文件 (`export`)

****************************************,
  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "file_da  "fider`)

**发送**:
```json
{
  "type": "render  "type": "render  "type": "render  "type": "render  "type": "render  "type": "render  "type": "render  "typ    "type": bbo  "type": "render  "type": "render  "typ错误码

| 错误码 | 说明 |
|--------|------|
| `INVALID_PARAMS` | 参数错误 |
| `FILE_NOT_FOUND` | 文件不存在 |
| `UNSUPPORTED_FMT` | 不支持的格式 |
| `EXPORT_TIMEOUT` | 导出超时 |
| `EXPORT_F| LED` | �| `EXP�败 |
| `EZDXF_NOT_INSTALLED` | ezd| `EZDXF_NOT_INSTALL
## 支持的 Shape 类型

| 类型 | 必需字段 | 可选字段 |
|------|---------|---------|
| `circle` | `cx`, `cy`| `circle` | `cx`, `| | `circle` | `c, `st| `circle` | `cx`, `cy`|| | `circle`e` | | `circle` | `cx`, `cy`| `circle` | `cx`, `| `y`, `width`, `height` | `rotation` |
| `polygon` | `points` (数组) | - |
| `text` | `x`, `y` | `text`, `font_size`, `color` |
| `ellipse` | `cx`, `cy`, `rx`, `ry` | `rotation` |

---

## 引擎选择策略

| 引擎 | 平台要求 | 说明 |
|------|---------|------|
| `autocad` | Windows + AutoCAD | 直接操作 AutoCAD |
| `ezdxf` | 跨平台 | 纯 Python 生成 DXF |
| `auto` (null) | 自动选择 | 有 AutoCAD 用 COM，否则用 ezdxf |

---

## 前端测试页面

- `http://localhost:8080/ui/test_ai_draw.html` - AI 绘图测试
- `http://localhost:8080/ui/te- `http://localhost:8080/ui/te- `http��- `http://localhost:8080/ui/te- `http://d_w- `http://localhost:8080/ui/te- `h试

