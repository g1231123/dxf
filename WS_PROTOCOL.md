# WebSocket AI 绘图协议 — AI 主控端 ↔ 渲染端通信

## 连接地址

```
ws://localhost:8080/ws/render
```

---

## 系统架构

```
┌─────────────────────────┐              ┌─────────────────────────┐
│      AI 主控端           │              │      渲染端（被控）      │
│     (Controller)         │◄──WebSocket──►│    (Controlled)         │
│                         │              │                         │
│ • 发起连接请求          │              │ • 等待连接              │
│ • 发送 CAD 绘图指令     │              │ • 接收并解析指令        │
│ • 调用 CadLike API      │              │ • 执行 ezdxf/pyautocad  │
│ • 接收渲染结果          │              │ • 返回 DXF/DWG 文件     │
│ • 控制绘图流程          │              │ • 报告执行状态          │
└─────────────────────────┘              └─────────────────────────┘
```

### 角色定义

| 角色 | 方向 | 职责 |
|------|------|------|
| **主控端 (Controller)** | → 发送指令 | AI 客户端，发送 `AddCircle`、`AddLine` 等绘图指令 |
| **被控端 (Controlled)** | ← 接收执行 | 渲染服务器，执行指令并返回结果文件 |
| | → 返回结果 | 被控端将绘制的 DXF 文件返回给主控端 |

---

## AI 绘图流程 (ai_edit)

```
AI 主控端 (客户端)                         渲染端 (服务端)
    │                                          │
    ├── WebSocket 连接 ───────────────────────►│
    │◄── { "type": "connected" } ──────────────┤  连接成功
    │                                          │
    ├── { "type": "ai_edit",                   │
    │     "shapes": [...],                     │
    │     "output_format": "dxf" } ──────────►│  发送绘图指令
    │                                          │
    │◄── { "type": "started" } ────────────────┤  任务开始
    │◄── { "type": "progress", "pct": 50 } ─────┤  绘制中...
    │◄── { "type": "result",                   │
    │      "format": "dxf_base64",             │
    │      "data": "...",                      │
    │      "engine_used": "ezdxf" } ───────────┤  返回 DXF
    │                                          │
    └── 断开连接 ───────────────────────────────┘
```

---

## 消息格式

| 消息 | 发送方 | 接收方 | 说明 |
|------|--------|--------|------|
| `connected` | 被控端 | 主控端 | 连接成功，被控端就绪 |
| `ai_edit` | 主控端 | 被控端 | 主控端发送绘图指令 |
| `started` | 被控端 | 主控端 | 被控端开始执行绘图 |
| `progress` | 被控端 | 主控端 | 被控端报告执行进度 |
| `result` | 被控端 | 主控端 | 被控端返回 DXF 文件 |
| `error` | 被控端 | 主控端 | 被控端报告执行错误 |

---

### 1. 连接握手 (被控端 → 主控端)

**响应** - 被控端发送给主控端
```json
{
  "type": "connected",
  "client_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_clients": 5,
  "msg": "WebSocket 渲染服务就绪"
}
```

---

### 2. AI 绘图请求 (主控端 → 被控端)

> 基于 **CadLike/pyautocad** API 设计，`shapes` 对应 `model.AddXXX()` 调用参数

**请求** (pyautocad/CadLike 风格 - 平铺参数)
```json
{
  "type": "ai_edit",
  "engine": "ezdxf",
  "output_format": "dxf",
  "filename": "ai_drawing.dxf",
  "file_data": null,
  "shapes": [
    {
      "id": "circle1",
      "type": "AddCircle",
      "center": [100, 100, 0],
      "radius": 50,
      "layer": "0",
      "color": "#FF0000"
    },
    {
      "id": "line1",
      "type": "AddLine",
      "start_point": [0, 0, 0],
      "end_point": [100, 100, 0],
      "layer": "0",
      "color": "#00FF00"
    },
    {
      "id": "pline1",
      "type": "AddPolyline",
      "points": [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]],
      "closed": true,
      "layer": "0",
      "color": "#0000FF"
    },
    {
      "id": "arc1",
      "type": "AddArc",
      "center": [100, 100, 0],
      "radius": 50,
      "start_angle": 0,
      "end_angle": 1.57,
      "layer": "0",
      "color": "#FFFF00"
    },
    {
      "id": "arc_deg",
      "type": "AddArcDegrees",
      "center": [200, 100, 0],
      "radius": 40,
      "start_angle": 0,
      "end_angle": 90,
      "layer": "0",
      "color": "#FFA500"
    },
    {
      "id": "point1",
      "type": "AddPoint",
      "point": [50, 50, 0],
      "layer": "0",
      "color": "#000000"
    },
    {
      "id": "text1",
      "type": "AddText",
      "text": "Hello CAD",
      "insert_point": [100, 100, 0],
      "height": 12,
      "layer": "0",
      "color": "#000000"
    },
    {
      "id": "mtext1",
      "type": "AddMText",
      "insert_point": [200, 200, 0],
      "width": 100,
      "text": "Multi-line\\nText",
      "layer": "0",
      "color": "#333333"
    },
    {
      "id": "ellipse1",
      "type": "AddEllipse",
      "center": [100, 100, 0],
      "major_axis": [150, 100, 0],
      "radius_ratio": 0.6,
      "layer": "0",
      "color": "#FF00FF"
    },
    {
      "id": "spline1",
      "type": "AddSpline",
      "points": [[0, 0, 0], [50, 100, 0], [100, 50, 0], [150, 150, 0]],
      "layer": "0",
      "color": "#00FFFF"
    },
    {
      "id": "rect1",
      "type": "AddRectangle",
      "x": 50,
      "y": 50,
      "width": 100,
      "height": 80,
      "rotation": 0,
      "layer": "0",
      "color": "#800080"
    },
    {
      "id": "polygon1",
      "type": "AddPolygon",
      "center": [300, 300, 0],
      "radius": 50,
      "sides": 6,
      "rotation": 0,
      "layer": "0",
      "color": "#008080"
    }
  ]
}
```

**参数说明**

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `type` | string | ✅ | 固定值 `"ai_edit"` |
| `engine` | string | 否 | `"ezdxf"` / `"autocad"` / `null`（自动） |
| `output_format` | string | 否 | `"dxf"`（默认）/ `"dwg"` |
| `filename` | string | 否 | 输出文件名，默认 `"ai_drawing.dxf"` |
| `file_data` | string | 否 | 现有文件 Base64，不传则创建新文件 |
| `shapes` | array | 否 | 绘图指令列表，对应 CadLike `model.AddXXX()` 调用 |

**Shape 类型** (对应 CadLike API)

| type | 参数 | 对应 CadLike 方法 |
|------|-----|-------------------|
| `AddCircle` | `center`, `radius`, `layer`, `color` | `AddCircle(APoint, radius)` |
| `AddLine` | `start_point`, `end_point`, `layer`, `color` | `AddLine(APoint, APoint)` |
| `AddPolyline` | `points`, `closed`, `layer`, `color` | `AddPolyline([APoint,...])` |
| `AddArc` | `center`, `radius`, `start_angle`, `end_angle`, `layer`, `color` | `AddArc(APoint, r, sa, ea)` |
| `AddArcDegrees` | `center`, `radius`, `start_angle`, `end_angle`, `layer`, `color` | `AddArc_degrees(APoint, r, sa, ea)` |
| `AddPoint` | `point`, `layer`, `color` | `AddPoint(APoint)` |
| `AddText` | `text`, `insert_point`, `height`, `layer`, `color` | `AddText(str, APoint, height)` |
| `AddMText` | `insert_point`, `width`, `text`, `layer`, `color` | `AddMText(APoint, width, text)` |
| `AddEllipse` | `center`, `major_axis`, `radius_ratio`, `layer`, `color` | `AddEllipse(c, ma, ratio)` |
| `AddSpline` | `points`, `layer`, `color` | `AddSpline([APoint,...])` |
| `AddHatch` | `pattern_type`, `pattern_name`, `layer`, `color` | `AddHatch(type, name)` |
| `AddRectangle` | `x`, `y`, `width`, `height`, `rotation`, `layer`, `color` | `AddRectangle(x, y, w, h, rot)` |
| `AddPolygon` | `center`, `radius`, `sides`, `rotation`, `layer`, `color` | `AddPolygon(c, r, sides, rot)` |

**通用参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `id` | string | 是 | Shape 唯一标识 |
| `type` | string | 是 | CadLike 方法名 |
| `layer` | string | 否 | 图层名，默认 `"0"` |
| `color` | string | 否 | HEX 颜色，如 `"#FF0000"` |

**CadLike 点格式**

```json
// APoint(x, y, z) → [x, y, z]
"center": [100, 100, 0]
"start_point": [0, 0, 0]
"insert_point": [50, 50, 0]
```

---

### 3. 任务开始 (被控端 → 主控端)

**响应** - 被控端收到指令后确认
```json
{
  "type": "started",
  "filename": "ai_drawing.dxf",
  "output_format": "dxf",
  "shape_count": 6,
  "engine_requested": "ezdxf"
}
```

---

### 4. 进度更新 (被控端 → 主控端)

**响应** - 被控端执行过程中报告进度
```json
{
  "type": "progress",
  "pct": 50,
  "msg": "绘制图形中..."
}
```

---

### 5. 绘图结果 (被控端 → 主控端)

**响应**
```json
{
  "type": "result",
  "format": "dxf_base64",
  "filename": "ai_drawing.dxf",
  "data": "U0VDR0lPTg0KICAyDQogI...",
  "size_bytes": 12345,
  "shape_count": 13,
  "success_count": 13,
  "error_count": 0,
  "engine_used": "ezdxf",
  "details": [
    {"shape_id": "circle1", "type": "AddCircle", "status": "created", "handle": "1A"},
    {"shape_id": "line1", "type": "AddLine", "status": "created", "handle": "2B"},
    {"shape_id": "pline1", "type": "AddPolyline", "status": "created", "handle": "3C"},
    {"shape_id": "arc1", "type": "AddArc", "status": "created", "handle": "4D"},
    {"shape_id": "arc_deg", "type": "AddArcDegrees", "status": "created", "handle": "5E"},
    {"shape_id": "point1", "type": "AddPoint", "status": "created", "handle": "6F"},
    {"shape_id": "text1", "type": "AddText", "status": "created", "handle": "7G"},
    {"shape_id": "mtext1", "type": "AddMText", "status": "created", "handle": "8H"},
    {"shape_id": "ellipse1", "type": "AddEllipse", "status": "created", "handle": "9I"},
    {"shape_id": "spline1", "type": "AddSpline", "status": "created", "handle": "10J"},
    {"shape_id": "hatch1", "type": "AddHatch", "status": "created", "handle": "11K"},
    {"shape_id": "rect1", "type": "AddRectangle", "status": "created", "handle": "12L"},
    {"shape_id": "polygon1", "type": "AddPolygon", "status": "created", "handle": "13M"}
  ]
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `format` | string | `dxf_base64` 或 `dwg_base64` |
| `data` | string | Base64 编码的文件内容 |
| `engine_used` | string | 实际使用的引擎：`ezdxf` / `autocad` |
| `success_count` | number | 成功绘制的图形数 |
| `error_count` | number | 失败的图形数 |
| `details` | array | 每个 shape 的执行结果 |

---

### 6. 错误响应 (被控端 → 主控端)

**响应** - 被控端执行失败时返回
```json
{
  "type": "error",
  "code": "EZDXF_NOT_INSTALLED",
  "msg": "AI绘图功能需要安装 ezdxf。运行: pip install ezdxf"
}
```

**错误码**

| code | 说明 |
|------|------|
| `INVALID_PARAMS` | 主控端参数错误 |
| `EZDXF_NOT_INSTALLED` | 被控端 ezdxf 未安装 |
| `AI_EDIT_FAILED` | 被控端绘图执行失败 |
| `FILE_TOO_LARGE` | 主控端文件超过 100MB |

---

## JavaScript 主控端示例

> 以下代码运行在 **AI 主控端**，用于控制渲染端执行绘图

```javascript
// ==================== 主控端代码 ====================
const ws = new WebSocket('ws://localhost:8080/ws/render');

// 主控端连接成功
ws.onopen = () => {
  console.log('[主控端] 已连接被控端（渲染服务器）');
};

// 主控端接收被控端消息
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  switch(msg.type) {
    case 'connected':
      // 被控端就绪，主控端发送绘图指令
      console.log('[主控端] 被控端就绪:', msg.msg);
      sendDrawCommand();  // 主控端发起绘图
      break;
      
    case 'started':
      // 被控端开始执行
      console.log('[主控端] 被控端开始绘制:', msg.filename);
      break;
      
    case 'progress':
      // 被控端报告进度
      console.log('[主控端] 被控端进度:', msg.pct + '%');
      break;
      
    case 'result':
      // 被控端返回结果，主控端处理
      console.log('[主控端] 被控端绘制完成，引擎:', msg.engine_used);
      downloadDXF(msg.data, msg.filename);  // 主控端保存文件
      break;
      
    case 'error':
      // 被控端报告错误
      console.error('[主控端] 被控端错误:', msg.code, msg.msg);
      break;
  }
};

// 主控端发送绘图指令 (pyautocad/CadLike 格式 - 平铺参数)
// 被控端收到后会调用 CadLike API 执行绘图
function sendDrawCommand() {
  ws.send(JSON.stringify({
    type: 'ai_edit',        // 主控端请求类型
    engine: 'ezdxf',        // 主控端指定引擎 (被控端会回退到可用引擎)
    output_format: 'dxf',   // 主控端要求输出格式
    shapes: [
      // 主控端调用 AddCircle(center, radius)
      {
        id: 'circle1',
        type: 'AddCircle',
        center: [100, 100, 0],
        radius: 50,
        layer: '0',
        color: '#FF0000'
      },
      // 主控端调用 AddLine(start_point, end_point)
      {
        id: 'line1',
        type: 'AddLine',
        start_point: [0, 0, 0],
        end_point: [100, 100, 0],
        layer: '0',
        color: '#00FF00'
      },
      // 主控端调用 AddPolyline(points, closed)
      {
        id: 'pline1',
        type: 'AddPolyline',
        points: [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]],
        closed: true,
        layer: '0',
        color: '#0000FF'
      },
      // 主控端调用 AddArc(center, radius, start_angle, end_angle)
      {
        id: 'arc1',
        type: 'AddArc',
        center: [200, 100, 0],
        radius: 40,
        start_angle: 0,
        end_angle: 1.57,
        layer: '0',
        color: '#FFFF00'
      },
      // 主控端调用 AddPoint(point)
      {
        id: 'point1',
        type: 'AddPoint',
        point: [50, 50, 0],
        layer: '0',
        color: '#000000'
      },
      // 主控端调用 AddText(text, insert_point, height)
      {
        id: 'text1',
        type: 'AddText',
        text: 'Hello CAD',
        insert_point: [150, 150, 0],
        height: 12,
        layer: '0',
        color: '#000000'
      },
      // 主控端调用 AddEllipse(center, major_axis, ratio)
      {
        id: 'ellipse1',
        type: 'AddEllipse',
        center: [300, 300, 0],
        major_axis: [350, 300, 0],
        radius_ratio: 0.6,
        layer: '0',
        color: '#FF00FF'
      },
      // 主控端调用 AddRectangle(x, y, w, h, rotation)
      {
        id: 'rect1',
        type: 'AddRectangle',
        x: 400,
        y: 400,
        width: 100,
        height: 80,
        rotation: 0,
        layer: '0',
        color: '#800080'
      }
    ]
  }));
}

// 下载 DXF
function downloadDXF(base64Data, filename) {
  const blob = new Blob(
    [Uint8Array.from(atob(base64Data), c => c.charCodeAt(0))],
    {type: 'application/dxf'}
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
}
```

---

## 引擎选择策略

> 主控端通过 `engine` 字段指定引擎，被控端会根据实际环境决定是否回退

| 引擎 | 平台 | 被控端要求 | 回退策略 |
|------|------|-----------|---------|
| `ezdxf` | 跨平台 | 被控端安装 ezdxf | 主推荐 |
| `autocad` | Windows | 被控端 Windows + AutoCAD | 不可用时被控端自动回退 ezdxf |
| `null` (自动) | - | 被控端自动选择 | 有 AutoCAD 用 COM，否则用 ezdxf |

**注意**: 
- macOS/Linux 被控端强制使用 `ezdxf`
- 主控端请求 `autocad` 时，若被控端不可用会自动降级到 `ezdxf`
