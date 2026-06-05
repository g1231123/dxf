# AI 实时绘图 WebSocket API 文档

> 通过 WebSocket 在 DXF/DWG 文件中实时绘制几何图形

---

## 连接地址

```
ws://103.39.221.54:10792/ws/render
```

---

## 消息类型概览

| 消息类型 | 方向 | 说明 |
|---------|------|------|
| `ai_edit` | 客户端 → 服务端 | 发送绘图指令 |
| `result` | 服务端 → 客户端 | 返回绘制结果（含修改后的文件） |
| `error` | 服务端 → 客户端 | 错误响应 |

---

## 一、画圆（Circle）

### 请求格式（极简版 - 只传 type）

只传 `type`，不传任何图形参数，自动画默认圆（圆心100,100，半径50）：

```json
{
  "type": "ai_edit"
}
```

等价于：
```json
{
  "type": "ai_edit",
  "shapes": [
    {
      "id": "default_circle",
      "type": "circle",
      "geometry": { "cx": 100.0, "cy": 100.0, "r": 50.0 },
      "style": { "stroke_color": "#FF0000" }
    }
  ]
}
```

### 请求格式（新建文件指定参数）

不传 `file_data` 时，自动创建新的空白 DXF 文件：

```json
{
  "type": "ai_edit",
  "shapes": [
    {
      "id": "circle_001",
      "type": "circle",
      "layer": "AI_CIRCLES",
      "geometry": {
        "cx": 100.0,
        "cy": 200.0,
        "r": 50.0
      },
      "style": {
        "stroke_color": "#FF0000",
        "stroke_width": 0.25
      }
    }
  ]
}
```

### 请求格式（编辑现有文件）

传 `file_data` 时，在现有文件基础上添加图形：

```json
{
  "type": "ai_edit",
  "file_data": "<base64编码的DXF/DWG文件内容>",
  "filename": "drawing.dxf",
  "output_format": "dxf",
  "shapes": [
    {
      "id": "circle_001",
      "type": "circle",
      "layer": "AI_CIRCLES",
      "geometry": {
        "cx": 100.0,
        "cy": 200.0,
        "r": 50.0
      },
      "style": {
        "stroke_color": "#FF0000",
        "stroke_width": 0.25
      }
    }
  ]
}
```

### 参数说明

#### 顶层参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `type` | string | ✓ | 固定值 `"ai_edit"` |
| `engine` | string | | 绘图引擎：`"autocad"` / `"ezdxf"` / 不传=自动选择 |
| `file_data` | string | | 原文件 Base64 编码内容（不传则新建空白文件） |
| `filename` | string | | 原始文件名（不传则默认 `ai_drawing.dxf`） |
| `output_format` | string | | 输出格式：`dxf`（默认）或 `dwg` |
| `shapes` | array | | 绘图指令数组（不传则默认画一个圆） |

#### Circle 图形参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `id` | string | | 随机生成 | 图形唯一ID，用于追踪 |
| `type` | string | | `"circle"` | 图形类型，不传默认画圆 |
| `layer` | string | | `"0"` | 目标图层名 |
| `geometry.cx` | number | | 100.0 | 圆心 X 坐标 |
| `geometry.cy` | number | | 100.0 | 圆心 Y 坐标 |
| `geometry.r` | number | | 50.0 | 半径 |
| `style.stroke_color` | string | | `"#FF0000"` | 圆边框颜色（HEX格式） |
| `style.stroke_width` | number | | 0.25 | 线宽（毫米） |

### 响应格式

```json
{
  "type": "result",
  "format": "dxf_base64",
  "filename": "ai_drawing.dxf",
  "data": "<base64编码的文件内容>",
  "size_bytes": 51200,
  "shape_count": 1,
  "success_count": 1,
  "error_count": 0,
  "details": [
    {
      "shape_id": "circle_001",
      "type": "circle",
      "handle": "1A2B3C",
      "status": "created",
      "center": [100.0, 200.0],
      "radius": 50.0
    }
  ]
}
```

> **文件名规则**：
> - 新建文件（不传 `file_data`）：`ai_drawing.dxf`
> - 编辑现有文件（传 `file_data`）：`{原文件名}_ai_edited.dxf`

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `format` | string | 输出格式：`dxf_base64` 或 `dwg_base64` |
| `data` | string | 绘制后的文件内容（Base64编码） |
| `size_bytes` | number | 文件大小（字节） |
| `shape_count` | number | 总共请求的图形数 |
| `success_count` | number | 成功创建的图形数 |
| `error_count` | number | 失败的图形数 |
| `engine_used` | string | 实际使用的引擎：`autocad` 或 `ezdxf` |
| `details` | array | 每个图形的详细结果 |
| `details[].shape_id` | string | 图形ID（与请求对应） |
| `details[].handle` | string | DXF 实体句柄（唯一标识） |
| `details[].status` | string | 状态：`created` / `error` / `skipped` |
| `details[].center` | [x, y] | 实际圆心坐标 |
| `details[].radius` | number | 实际半径 |

---

---

## 引擎选择

系统支持两种绘图引擎，**自动选择**或**手动指定**：

| 引擎 | 适用环境 | 说明 |
|------|---------|------|
| `autocad` | Windows + AutoCAD 运行中 | 直接在 AutoCAD 实例中绘图，支持实时预览 |
| `ezdxf` | 跨平台（Linux/macOS/Windows） | 纯 Python 库生成 DXF，无需 AutoCAD |

### 自动选择策略

1. 用户强制指定 `engine` 参数 → 使用该引擎
2. 尝试连接 AutoCAD COM → 成功则用 `autocad`
3. 失败 → 回退到 `ezdxf`

### 请求示例（强制指定引擎）

```json
{
  "type": "ai_edit",
  "engine": "autocad",
  "shapes": [
    {
      "type": "circle",
      "geometry": { "cx": 100, "cy": 100, "r": 50 }
    }
  ]
}
```

---

## 二、画圆弧（Arc）

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "arc_001",
      "type": "arc",
      "layer": "ARCS",
      "geometry": {
        "cx": 100.0,
        "cy": 200.0,
        "r": 50.0,
        "start_angle": 0,
        "end_angle": 90
      },
      "style": {
        "stroke_color": "#00FF00",
        "stroke_width": 0.5
      }
    }
  ]
}
```

### Arc 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.start_angle` | number | ✓ | 起始角度（度，0=3点钟方向，逆时针增长） |
| `geometry.end_angle` | number | ✓ | 终止角度（度） |

---

## 三、画直线/折线（Line）

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "line_001",
      "type": "line",
      "layer": "LINES",
      "geometry": {
        "points": [
          [100.0, 200.0],
          [150.0, 250.0],
          [200.0, 200.0]
        ],
        "closed": false
      },
      "style": {
        "stroke_color": "#0000FF",
        "stroke_width": 0.5
      }
    }
  ]
}
```

### Line 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.points` | array | ✓ | 顶点数组，格式 `[[x1,y1], [x2,y2], ...]`，至少2个点 |
| `geometry.closed` | boolean | | 是否闭合（`true`=多边形，`false`=折线，默认 `false`） |

---

## 四、画矩形（Rectangle）

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "rect_001",
      "type": "rectangle",
      "layer": "RECTS",
      "geometry": {
        "x": 100.0,
        "y": 200.0,
        "width": 50.0,
        "height": 30.0,
        "rotation": 30
      },
      "style": {
        "stroke_color": "#FF00FF"
      }
    }
  ]
}
```

### Rectangle 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.x` | number | ✓ | 左上角 X 坐标 |
| `geometry.y` | number | ✓ | 左上角 Y 坐标 |
| `geometry.width` | number | ✓ | 宽度 |
| `geometry.height` | number | ✓ | 高度 |
| `geometry.rotation` | number | | 旋转角度（度，顺时针，默认 0） |

---

## 五、画多边形（Polygon）支持挖孔

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "poly_001",
      "type": "polygon",
      "layer": "POLYGONS",
      "geometry": {
        "rings": [
          [
            [100.0, 100.0],
            [200.0, 100.0],
            [200.0, 200.0],
            [100.0, 200.0],
            [100.0, 100.0]
          ],
          [
            [130.0, 130.0],
            [170.0, 130.0],
            [170.0, 170.0],
            [130.0, 170.0],
            [130.0, 130.0]
          ]
        ]
      },
      "style": {
        "stroke_color": "#FF0000",
        "fill_color": "#FFFF00",
        "fill_opacity": 0.5
      }
    }
  ]
}
```

### Polygon 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.rings` | array | ✓ | 多环数组，第一环为外环，后续为内孔（挖空区域） |
| `style.fill_color` | string | | 填充颜色（HEX格式） |
| `style.fill_opacity` | number | | 填充透明度（0-1） |

---

## 六、画椭圆（Ellipse）

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "ellipse_001",
      "type": "ellipse",
      "layer": "ELLIPSES",
      "geometry": {
        "cx": 100.0,
        "cy": 200.0,
        "rx": 60.0,
        "ry": 30.0,
        "rotation": 45
      },
      "style": {
        "stroke_color": "#00FFFF"
      }
    }
  ]
}
```

### Ellipse 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.rx` | number | ✓ | X轴半径（长半轴） |
| `geometry.ry` | number | ✓ | Y轴半径（短半轴） |
| `geometry.rotation` | number | | 旋转角度（度，默认 0） |

---

## 七、画文字（Text）

### 请求格式

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "drawing.dxf",
  "shapes": [
    {
      "id": "text_001",
      "type": "text",
      "layer": "TEXTS",
      "geometry": {
        "x": 100.0,
        "y": 200.0,
        "rotation": 0
      },
      "style": {
        "text": "标注文字",
        "font_size": 12,
        "color": "#000000"
      }
    }
  ]
}
```

### Text 特有参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `geometry.x` | number | ✓ | 文字位置 X |
| `geometry.y` | number | ✓ | 文字位置 Y |
| `geometry.rotation` | number | | 旋转角度（度，默认 0） |
| `style.text` | string | ✓ | 文字内容 |
| `style.font_size` | number | | 字体大小（像素，默认 12） |
| `style.color` | string | | 文字颜色（HEX，默认 `#000000`） |

---

## 八、批量绘制示例

```json
{
  "type": "ai_edit",
  "file_data": "<base64...>",
  "filename": "plan.dxf",
  "output_format": "dxf",
  "shapes": [
    {
      "id": "center_circle",
      "type": "circle",
      "layer": "CENTER_MARKS",
      "geometry": { "cx": 150, "cy": 150, "r": 5 },
      "style": { "stroke_color": "#FF0000", "stroke_width": 0.5 }
    },
    {
      "id": "boundary_line",
      "type": "line",
      "layer": "BOUNDARY",
      "geometry": {
        "points": [[100, 100], [200, 100], [200, 200], [100, 200]],
        "closed": true
      },
      "style": { "stroke_color": "#0000FF" }
    },
    {
      "id": "label",
      "type": "text",
      "layer": "LABELS",
      "geometry": { "x": 150, "y": 150 },
      "style": { "text": "中心点", "font_size": 14, "color": "#333333" }
    }
  ]
}
```

---

## 九、错误响应

```json
{
  "type": "error",
  "code": "AI_EDIT_FAILED",
  "msg": "参数错误：圆半径必须大于0"
}
```

### 错误码对照表

| 错误码 | HTTP | 说明 |
|--------|:----:|------|
| `INVALID_PARAMS` | 422 | 参数缺失或格式错误 |
| `EZDXF_NOT_INSTALLED` | 500 | ezdxf 未安装，无法使用 AI 绘图功能 |
| `AUTOCAD_NOT_AVAILABLE` | 500 | AutoCAD COM 不可用（仅限 Windows + AutoCAD 运行中） |
| `AI_EDIT_FAILED` | 500 | AI 实时绘图失败（参数错误或 DXF 处理异常） |
| `UNSUPPORTED_FMT` | 400 | 不支持的文件格式（output_format 必须是 dxf 或 dwg） |

---

## 十、JavaScript 调用示例

### 示例1：新建文件画圆（无需上传）

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/render');

ws.onopen = () => {
  // 直接发送画圆指令，不传 file_data，自动创建新文件
  ws.send(JSON.stringify({
    type: 'ai_edit',
    shapes: [
      {
        id: 'circle_1',
        type: 'circle',
        layer: 'CIRCLES',
        geometry: { cx: 100, cy: 100, r: 50 },
        style: { stroke_color: '#FF0000' }
      }
    ]
  }));
};
```

### 示例2：在现有文件上添加圆

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/render');

// 读取现有文件并转为 base64
const fileBuffer = await file.arrayBuffer();
const fileBase64 = btoa(String.fromCharCode(...new Uint8Array(fileBuffer)));

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'ai_edit',
    file_data: fileBase64,  // 上传现有文件
    filename: 'input.dxf',
    shapes: [
      {
        id: 'circle_1',
        type: 'circle',
        layer: 'CIRCLES',
        geometry: { cx: 100, cy: 100, r: 50 },
        style: { stroke_color: '#FF0000' }
      }
    ]
  }));
};
```

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'result') {
    console.log('绘制成功:', msg.filename);
    console.log('创建的图形:', msg.details);
    
    // 下载结果文件
    const blob = new Blob(
      [Uint8Array.from(atob(msg.data), c => c.charCodeAt(0))],
      { type: 'application/dxf' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = msg.filename;
    a.click();
  }
  
  if (msg.type === 'error') {
    console.error('错误:', msg.code, msg.msg);
  }
};
```

---

*文档版本: 2025-05-20 | 对应服务: ws_server.py ai_edit*
