# 主控端 / 被控端 API 数据格式

WebSocket 地址: `ws://localhost:8080/ws/render`

> **架构说明**
> - **主控端** (`master_upload.html`)：上传 DXF/DWG 文件，发送 `parse` 请求，接收 `parsed` 广播结果
> - **被控端** (`slave_viewer.html`)：被动接收服务器广播的 `parsed` 消息，渲染 2D 图形并展示实体列表

---

## 新增：主控端请求数据

### parse - 解析 DXF/DWG 文件

主控端上传文件后发送，服务器解析完毕后**广播给所有连接的客户端**（含主控端和所有被控端）。

```json
{
  "type": "parse",
  "filename": "圆端型实体墩_构造图.dxf",
  "file_data": "<base64_encoded_dxf_or_dwg>"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值 `"parse"` |
| `filename` | string | 文件名，含扩展名 `.dxf` 或 `.dwg` |
| `file_data` | string | 文件的 Base64 编码（使用 `FileReader.readAsDataURL` 取逗号后部分） |

---

## 新增：服务器广播响应数据

### parsed - 解析结果（广播给所有端）

```json
{
  "type": "parsed",
  "filename": "圆端型实体墩_构造图.dxf",
  "entity_count": 19,
  "layers": ["0", "尺寸标注", "钢筋"],
  "shapes": [
    {
      "id": "line_1",
      "name": "2A",
      "type": "AddLine",
      "start_point": [0.0, 0.0, 0],
      "end_point": [200.0, 0.0, 0],
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "2A"
    },
    {
      "id": "circle_2",
      "name": "3B",
      "type": "AddCircle",
      "center": [100.0, 100.0, 0],
      "radius": 50.0,
      "color": "#FF0000",
      "layer": "0",
      "handle": "3B"
    },
    {
      "id": "arc_3",
      "name": "3C",
      "type": "AddArc",
      "center": [100.0, 100.0, 0],
      "radius": 50.0,
      "start_angle": 0.0,
      "end_angle": 180.0,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "3C"
    },
    {
      "id": "poly_4",
      "name": "3D",
      "type": "AddPolyline",
      "points": [[0,0,0], [100,0,0], [100,100,0]],
      "closed": false,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "3D"
    },
    {
      "id": "text_5",
      "name": "3E",
      "type": "AddText",
      "text": "正  面",
      "insert_point": [1300.0, 496.0, 0],
      "height": 3.0,
      "rotation": 0,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "3E"
    },
    {
      "id": "mtext_6",
      "name": "3F",
      "type": "AddMText",
      "text": "说明文字",
      "insert_point": [500.0, 300.0, 0],
      "height": 5.0,
      "rotation": 0,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "3F"
    },
    {
      "id": "ellipse_7",
      "name": "40",
      "type": "AddEllipse",
      "center": [200.0, 200.0, 0],
      "major_axis": [300.0, 200.0, 0],
      "radius_ratio": 0.5,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "40"
    },
    {
      "id": "insert_8",
      "name": "COLUMN",
      "type": "AddInsert",
      "block_name": "COLUMN",
      "insert_point": [0.0, 0.0, 0],
      "scale": [1, 1, 1],
      "rotation": 0,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "41"
    },
    {
      "id": "spline_9",
      "name": "42",
      "type": "AddSpline",
      "points": [[0,0,0], [50,80,0], [100,0,0]],
      "closed": false,
      "color": "#FFFFFF",
      "layer": "0",
      "handle": "42"
    }
  ]
}
```

#### shapes 字段说明

| `type` 值 | 实体类型 | 特有字段 |
|-----------|----------|----------|
| `AddLine` | 线段 | `start_point[x,y,0]`, `end_point[x,y,0]` |
| `AddCircle` | 圆 | `center[x,y,0]`, `radius` |
| `AddArc` | 弧 | `center[x,y,0]`, `radius`, `start_angle`, `end_angle` |
| `AddPolyline` | 多段线 | `points[[x,y,0],...]`, `closed` |
| `AddText` | 单行文字 | `insert_point[x,y,0]`, `text`, `height`, `rotation` |
| `AddMText` | 多行文字 | `insert_point[x,y,0]`, `text`, `height`, `rotation` |
| `AddEllipse` | 椭圆 | `center[x,y,0]`, `major_axis[x,y,0]`, `radius_ratio` |
| `AddInsert` | 块参照 | `insert_point[x,y,0]`, `block_name`, `scale[x,y,z]`, `rotation` |
| `AddSpline` | 样条曲线 | `points[[x,y,0],...]`, `closed` |

#### 所有 shape 公共字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 自增唯一 ID，格式 `类型_序号`，如 `line_1` |
| `name` | string | 实体名称（DXF Handle，等同于实体唯一标识） |
| `type` | string | 实体类型，`Add` 前缀，与 `ai_edit` shapes 格式完全一致 |
| `color` | string | HEX 颜色，如 `#FF0000` |
| `layer` | string | 所在图层名 |
| `handle` | string | DXF 原始 Handle（可用于 `export` edits 的 `target`） |

#### 错误响应

```json
{
  "type": "error",
  "code": "PARSE_FAILED",
  "msg": "错误描述"
}
```

---

---

## 主控端工作流程

```
1. 主控端发送 parse 请求  →  服务器解析 DXF/DWG
2. 服务器广播 parsed 响应  →  主控端 + 被控端同时收到 shapes 数据
3. 主控端对 shapes 增删改  →  重新发送 ai_edit 请求
4. 服务器处理 ai_edit      →  生成新 DXF 文件返回给主控端
```

**parse 返回的 `shapes` 与 `ai_edit` 的 `shapes` 格式完全一致，可以直接修改后作为 `ai_edit` 的输入。**

---

## 原有请求数据

### 1. preview - 预览 DXF

```json
{
  "type": "preview",
  "file_data": "<base64_encoded_dxf>",
  "width": 800,
  "height": 600
}
```

---

### 2. export - 编辑 DXF

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

---

### 3. ai_edit - AI 绘图 / 修改

> `parse` 返回的 `shapes` 可直接修改后传入此接口。
> `file_data` 传 `null` 时创建新文件；传 Base64 数据时在原文件上叠加绘制。

```json
{
  "type": "ai_edit",
  "filename": "output.dxf",
  "file_data": null,
  "shapes": [
    {
      "id": "line_1",
      "name": "2A",
      "type": "AddLine",
      "start_point": [0, 0, 0],
      "end_point": [200, 0, 0],
      "color": "#FFFFFF",
      "layer": "0"
    },
    {
      "id": "circle_2",
      "name": "3B",
      "type": "AddCircle",
      "center": [100, 100, 0],
      "radius": 50,
      "color": "#FF0000",
      "layer": "0"
    },
    {
      "id": "arc_3",
      "name": "3C",
      "type": "AddArc",
      "center": [100, 100, 0],
      "radius": 50,
      "start_angle": 0,
      "end_angle": 180,
      "color": "#FFFFFF",
      "layer": "0"
    },
    {
      "id": "poly_4",
      "name": "3D",
      "type": "AddPolyline",
      "points": [[0,0,0], [100,0,0], [100,100,0]],
      "closed": true,
      "color": "#00FF00",
      "layer": "0"
    },
    {
      "id": "text_5",
      "name": "3E",
      "type": "AddText",
      "text": "单行文字",
      "insert_point": [50, 150, 0],
      "height": 5,
      "rotation": 0,
      "color": "#FFFF00",
      "layer": "0"
    },
    {
      "id": "mtext_6",
      "name": "3F",
      "type": "AddMText",
      "text": "多行文字\n第二行",
      "insert_point": [50, 200, 0],
      "height": 5,
      "rotation": 0,
      "color": "#FFFF00",
      "layer": "0"
    },
    {
      "id": "ellipse_7",
      "name": "40",
      "type": "AddEllipse",
      "center": [200, 200, 0],
      "major_axis": [300, 200, 0],
      "radius_ratio": 0.5,
      "color": "#FF00FF",
      "layer": "0"
    },
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
  ]
}
```

#### ai_edit shapes 支持的类型

| `type` 值 | 说明 | 关键字段 |
|-----------|------|----------|
| `AddLine` | 线段 | `start_point[x,y,0]`, `end_point[x,y,0]` |
| `AddPolyline` | 多段线 | `points[[x,y,0],...]`, `closed` |
| `AddCircle` | 圆 | `center[x,y,0]`, `radius` |
| `AddArc` | 弧 | `center[x,y,0]`, `radius`, `start_angle`, `end_angle` |
| `AddEllipse` | 椭圆 | `center[x,y,0]`, `major_axis[x,y,0]`, `radius_ratio` |
| `AddText` | 单行文字 | `insert_point[x,y,0]`, `text`, `height`, `rotation` |
| `AddMText` | 多行文字（支持`\n`换行） | `insert_point[x,y,0]`, `text`, `height`, `rotation` |
| `AddRectangle` | 矩形（快捷方式） | `x`, `y`, `width`, `height` |
| `AddInsert` | 块参照 | `block_name`, `insert_point[x,y,0]`, `scale[x,y,z]`, `rotation` |

---

## 响应数据

### connected - 连接成功

```json
{
  "type": "connected",
  "msg": "WebSocket 渲染服务就绪",
  "total_clients": 1
}
```

---

### preview - 预览结果

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

### started - 开始处理

```json
{
  "type": "started",
  "filename": "output.dxf",
  "shape_count": 3
}
```

---

### progress - 处理进度

```json
{
  "type": "progress",
  "pct": 50,
  "msg": "正在绘制图形..."
}
```

---

### result - 处理结果

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

**status**: `ok` | `partial` | `error`  
**format**: `png_base64` | `dxf_base64` | `dwg_base64`

---

### error - 错误消息

```json
{
  "type": "error",
  "code": "PREVIEW_FAILED",
  "msg": "错误描述信息"
}
```

**错误码**: `PREVIEW_FAILED` | `RENDER_FAILED` | `AI_EDIT_FAILED` | `INVALID_PARAMS` | `FILE_NOT_FOUND`

---

## 底图服务集成（新增）

### 访问地址

| 页面 | URL | 说明 |
|------|-----|------|
| 底图查看器 | `http://localhost:8080/ui/slave_viewer_map.html` | **推荐** - DXF 叠加在线底图 |
| 纯 DXF 查看器 | `http://localhost:8080/ui/slave_viewer.html` | 无底图，纯 Canvas 渲染 |
| 主控端上传 | `http://localhost:8080/ui/master_upload.html` | 上传 DXF/DWG 文件 |

### 支持的底图

- **高德地图** - 国内推荐使用，默认开启
- **天地图** - 国家测绘局底图（需申请 Key）
- **OpenStreetMap** - 国际开源底图
- **无底图** - 仅显示 DXF 图形

### 坐标系支持

DXF 通常是局部 CAD 坐标，需要选择正确的坐标系才能在地图上正确显示：

| 坐标系 | EPSG | 适用场景 |
|--------|------|----------|
| WGS84 | 4326 | 国际标准经纬度 |
| Web墨卡托 | 3857 | 在线地图标准 |
| CGCS2000 | 4490/4508/4547 | 国家2000坐标系 |
| 局部坐标 | - | CAD 局部坐标（需配准） |

### 快速测试

```bash
# 1. 启动服务器
cd /Users/czy/Downloads/QGIS/dxf_render_service
python3 -m uvicorn server:app --host 0.0.0.0 --port 8080

# 2. 打开底图查看器
open http://localhost:8080/ui/slave_viewer_map.html

# 3. 打开主控端上传页面
open http://localhost:8080/ui/master_upload.html

# 4. 上传 DXF 文件，观察底图查看器自动显示
```

或使用一键测试脚本：
```bash
python3 test_map_service.py
```
