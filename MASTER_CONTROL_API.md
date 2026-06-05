# CadLike 主控端使用文档

## 概述

主控端是 CadLike DXF 渲染服务的控制中心，负责：
- 上传和预览 DXF 文件
- 编辑和修改 CAD 图形
- AI 辅助绘图
- 导出处理后的文件

被控端实时接收并展示主控端的操作结果。

---

## 连接方式

### WebSocket 连接
- **地址**: `ws://localhost:8080/ws/render`
- **协议**: JSON 文本帧
- **连接成功**: 收到 `connected` 消息

```json
{
  "type": "connected",
  "msg": "WebSocket 渲染服务就绪",
  "total_clients": 1
}
```

---

## 主控端发送的请求

### 1. preview - DXF 文件预览

上传 DXF 文件并实时渲染为 PNG 图像，广播给所有连接的客户端。

**请求格式**:
```json
{
  "type": "preview",
  "file_data": "<base64_encoded_dxf>",
  "width": 800,
  "height": 600
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| type | string | ✓ | - | 固定值 "preview" |
| file_data | string | ✓ | - | DXF 文件的 base64 编码 |
| width | int | ✗ | 800 | 渲染图像宽度（像素） |
| height | int | ✗ | 600 | 渲染图像高度（像素） |

**响应**: 所有客户端收到 `preview` 消息
```json
{
  "type": "preview",
  "format": "png_base64",
  "data": "<base64_png_image>",
  "width": 800,
  "height": 600
}
```

---

### 2. export - 编辑 DXF 文件

对现有 DXF 文件进行批量编辑操作（移动、删除、改色、改层）。

**请求格式**:
```json
{
  "type": "export",
  "filename": "output.dxf",
  "file_data": "<base64_encoded_dxf>",
  "edits": [
    { "type": "move", "target": "1F", "x": 10, "y": 20 },
    { "type": "delete", "target": "2A" },
    { "type": "set_color", "target": "*", "color": "#FF0000" },
    { "type": "set_layer", "target": "1F", "layer": "Layer1" }
  ]
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | ✓ | 固定值 "export" |
| filename | string | ✓ | 输出文件名 |
| file_data | string | ✓ | 原始 DXF 文件的 base64 编码 |
| edits | array | ✓ | 编辑操作数组 |

**edits 操作类型**:

#### move - 移动图形
```json
{ "type": "move", "target": "1F", "x": 10, "y": 20 }
```
- `target`: Handle ID（如 "1F"）或 "*"（全部）
- `x`, `y`: 移动的偏移量

#### delete - 删除图形
```json
{ "type": "delete", "target": "2A" }
```
- `target`: 要删除的 Handle ID

#### set_color - 修改颜色
```json
{ "type": "set_color", "target": "*", "color": "#FF0000" }
```
- `target`: Handle ID 或 "*"
- `color`: 十六进制颜色值 #RRGGBB

#### set_layer - 修改图层
```json
{ "type": "set_layer", "target": "1F", "layer": "Layer1" }
```
- `target`: Handle ID
- `layer`: 目标图层名称

**响应**: 收到 `result` 消息
```json
{
  "type": "result",
  "status": "ok",
  "filename": "output.dxf",
  "format": "dxf_base64",
  "data": "<base64_dxf>",
  "engine_used": "ezdxf",
  "success_count": 3,
  "shape_count": 3,
  "size_bytes": 4096
}
```

---

### 3. ai_edit - AI 辅助绘图

在空白文件或现有 DXF 文件上绘制新图形。

**请求格式**:
```json
{
  "type": "ai_edit",
  "filename": "output.dxf",
  "file_data": null,
  "shapes": [
    {
      "id": "c1",
      "type": "AddCircle",
      "center": [100, 100, 0],
      "radius": 50,
      "color": "#FF0000",
      "layer": "0"
    },
    {
      "id": "l1",
      "type": "AddLine",
      "start_point": [0, 0, 0],
      "end_point": [200, 200, 0],
      "color": "#00FF00",
      "layer": "0"
    }
  ]
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | ✓ | 固定值 "ai_edit" |
| filename | string | ✓ | 输出文件名 |
| file_data | string/null | ✓ | null=新建文件，base64=在现有文件上叠加 |
| shapes | array | ✓ | 要绘制的图形数组 |

**支持的图形类型**:

#### AddCircle - 圆形
```json
{
  "id": "c1",
  "type": "AddCircle",
  "center": [100, 100, 0],
  "radius": 50,
  "color": "#FF0000",
  "layer": "0"
}
```

#### AddLine - 直线
```json
{
  "id": "l1",
  "type": "AddLine",
  "start_point": [0, 0, 0],
  "end_point": [200, 200, 0],
  "color": "#00FF00",
  "layer": "0"
}
```

#### AddRectangle - 矩形
```json
{
  "id": "r1",
  "type": "AddRectangle",
  "x": 50,
  "y": 50,
  "width": 100,
  "height": 80,
  "color": "#0000FF",
  "layer": "0"
}
```

#### AddText - 文字
```json
{
  "id": "t1",
  "type": "AddText",
  "text": "Hello CAD",
  "insert_point": [50, 150, 0],
  "height": 12,
  "color": "#000000",
  "layer": "0"
}
```

#### AddEllipse - 椭圆
```json
{
  "id": "e1",
  "type": "AddEllipse",
  "center": [100, 100, 0],
  "major_axis": [150, 100, 0],
  "radius_ratio": 0.6,
  "color": "#FF00FF",
  "layer": "0"
}
```

**处理流程**:
1. 收到 `started` 消息
```json
{ "type": "started", "filename": "output.dxf", "shape_count": 3 }
```

2. 收到 `progress` 消息（多次）
```json
{ "type": "progress", "pct": 50, "msg": "正在绘制图形..." }
```

3. 收到 `result` 消息
```json
{
  "type": "result",
  "status": "ok",
  "filename": "output.dxf",
  "format": "dxf_base64",
  "data": "<base64_dxf>",
  "engine_used": "ezdxf",
  "success_count": 3,
  "shape_count": 3,
  "size_bytes": 4096
}
```

---

## 响应消息类型

### connected - 连接成功
```json
{
  "type": "connected",
  "msg": "WebSocket 渲染服务就绪",
  "total_clients": 1
}
```

### preview - 预览结果（广播）
```json
{
  "type": "preview",
  "format": "png_base64",
  "data": "<base64_png>",
  "width": 800,
  "height": 600
}
```

### started - 开始处理
```json
{
  "type": "started",
  "filename": "output.dxf",
  "shape_count": 3
}
```

### progress - 处理进度
```json
{
  "type": "progress",
  "pct": 50,
  "msg": "正在绘制图形..."
}
```
- `pct`: 0-100 的进度百分比

### result - 处理结果
```json
{
  "type": "result",
  "status": "ok",
  "filename": "output.dxf",
  "format": "dxf_base64",
  "data": "<base64>",
  "engine_used": "ezdxf",
  "success_count": 3,
  "shape_count": 3,
  "size_bytes": 4096
}
```

**status 状态值**:
- `ok`: 全部成功
- `partial`: 部分成功
- `error`: 全部失败

**format 格式**:
- `png_base64`: PNG 图像
- `dxf_base64`: DXF 文件
- `dwg_base64`: DWG 文件

### error - 错误消息
```json
{
  "type": "error",
  "code": "PREVIEW_FAILED",
  "msg": "错误描述信息"
}
```

**错误码**:
| 错误码 | 说明 |
|--------|------|
| PREVIEW_FAILED | DXF 预览渲染失败 |
| RENDER_FAILED | 渲染引擎执行失败 |
| AI_EDIT_FAILED | AI 绘图操作失败 |
| INVALID_PARAMS | 参数缺失或格式错误 |
| FILE_NOT_FOUND | 文件不存在 |

---

## 使用示例

### JavaScript 示例

```javascript
// 连接 WebSocket
const ws = new WebSocket('ws://localhost:8080/ws/render');

ws.onopen = () => {
  console.log('已连接到渲染服务');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  switch(msg.type) {
    case 'connected':
      console.log('服务就绪，客户端数:', msg.total_clients);
      break;
      
    case 'preview':
      // 显示预览图像
      const img = document.getElementById('preview');
      img.src = `data:image/png;base64,${msg.data}`;
      break;
      
    case 'progress':
      console.log(`进度: ${msg.pct}% - ${msg.msg}`);
      break;
      
    case 'result':
      console.log('处理完成:', msg.filename);
      // 下载文件
      downloadBase64(msg.data, msg.filename);
      break;
      
    case 'error':
      console.error(`错误 [${msg.code}]: ${msg.msg}`);
      break;
  }
};

// 预览 DXF 文件
function previewDXF(fileBase64) {
  ws.send(JSON.stringify({
    type: 'preview',
    file_data: fileBase64,
    width: 1024,
    height: 768
  }));
}

// AI 绘图
function aiDraw() {
  ws.send(JSON.stringify({
    type: 'ai_edit',
    filename: 'my_drawing.dxf',
    file_data: null,
    shapes: [
      {
        id: 'circle1',
        type: 'AddCircle',
        center: [100, 100, 0],
        radius: 50,
        color: '#FF0000',
        layer: '0'
      }
    ]
  }));
}

// 编辑 DXF
function editDXF(fileBase64) {
  ws.send(JSON.stringify({
    type: 'export',
    filename: 'edited.dxf',
    file_data: fileBase64,
    edits: [
      { type: 'set_color', target: '*', color: '#0000FF' },
      { type: 'move', target: '1F', x: 10, y: 20 }
    ]
  }));
}
```

---

## 注意事项

1. **Base64 编码**: 所有文件数据必须使用 base64 编码
2. **坐标系统**: 使用 CAD 标准坐标系 [x, y, z]
3. **颜色格式**: 使用十六进制 #RRGGBB 格式
4. **Handle ID**: 通过预览或其他方式获取图形的 Handle ID
5. **广播机制**: preview 消息会广播给所有连接的客户端（主控端和被控端）
6. **异步处理**: ai_edit 和 export 是异步操作，通过 progress 和 result 消息跟踪进度

---

## 工作流程

### 典型工作流程
1. 主控端连接 WebSocket
2. 上传 DXF 文件预览（preview）
3. 被控端实时显示预览图像
4. 主控端发送编辑或绘图指令
5. 服务器处理并广播进度
6. 所有客户端收到最终结果

### 多客户端协作
- 主控端：发送指令，控制渲染
- 被控端：只读模式，实时展示结果
- 所有客户端都能看到相同的预览和结果

---

## 技术支持

- 渲染引擎: ezdxf + matplotlib
- 支持格式: DXF R12-R2018
- 图像格式: PNG (base64)
- 最大文件: 建议 < 10MB
