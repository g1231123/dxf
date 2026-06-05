# DXF 编辑器 API - 请求响应文档

**基础 URL**: `http://localhost:8080/api`

---

## 转换接口

### 1. DXF 转 TXT

**端点**: `POST /convert/dxf-to-txt`

#### 请求

```json
{
  "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf",
  "include_prompt": true
}
```

**参数说明**:
- `dxf_url`: DXF 文件的 URL
- `include_prompt`: 是否包含提示词模板（默认 true）

#### 响应

```json
{
  "output_url": "http://database.yuxindazhineng.com/bucket/file_R12数据和提示词.txt",
  "file_size_mb": 3.08
}
```

---

### 2. TXT 转 DXF

**端点**: `POST /convert/txt-to-dxf`

#### 请求

```json
{
  "txt_url": "http://database.yuxindazhineng.com/bucket/file_R12数据和提示词.txt"
}
```

#### 响应

```json
{
  "output_url": "http://database.yuxindazhineng.com/bucket/file_提取.dxf",
  "file_size_mb": 2.93
}
```

---

## 编辑接口

### 3. 生成预览图

**端点**: `POST /template/image/preview`

### 请求

```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  }
}
```

### 响应

```json
{
  "preview_url": "http://database.yuxindazhineng.com/bucket/preview.png",
  "width": 1920,
  "height": 1080
}
```

---

## 4. 获取 DXF 范围

**端点**: `POST /template/image/extent`

### 请求

```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  }
}
```

### 响应

```json
{
  "min_x": 0.0,
  "min_y": 0.0,
  "max_x": 100000.0,
  "max_y": 50000.0
}
```

---

## 5. 查询点击位置的实体

**端点**: `POST /template/image/entity-at`

### 请求

```json
{
  "template": {
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  },
  "x": 65432.51,
  "y": 6149.49,
  "tolerance": 500.0
}
```

### 响应

```json
{
  "entities": [
    {
      "handle": "37A64",
      "type": "CIRCLE",
      "layer": "测试道路纵断面设计线",
      "distance": 0.51,
      "params": {
        "color": {
          "value": 60,
          "editable": true,
          "type": "number",
          "description": "颜色索引（0-256，256=随层）",
          "min": 0,
          "max": 256
        },
        "lineweight": {
          "value": -1,
          "editable": true,
          "type": "number",
          "description": "线宽（-1=随层，-2=随块，-3=默认）"
        },
        "center": {
          "value": [65432.51, 6149.49, 0.0],
          "editable": true,
          "type": "point",
          "description": "圆心坐标 [x, y, z]"
        },
        "radius": {
          "value": 1.0,
          "editable": true,
          "type": "number",
          "description": "半径",
          "min": 0.001
        }
      }
    }
  ],
  "total_entities": 39775
}
```

---

## 6. 应用修改并生成新 DXF

**端点**: `POST /template/image/generate`

### 请求

```json
{
  "template": {
    "name": "测试道路",
    "dxf_url": "http://database.yuxindazhineng.com/bucket/file.dxf"
  },
  "modifications": [
    {
      "handle": "37A64",
      "changes": {
        "center": [65500.0, 6200.0, 0.0],
        "radius": 2.0,
        "color": 1
      }
    },
    {
      "handle": "347A7",
      "changes": {
        "start": [65500.0, 6000.0, 0.0],
        "end": [79600.0, 6000.0, 0.0],
        "color": 60,
        "lineweight": 20
      }
    }
  ]
}
```

### 响应

```json
{
  "dxf_url": "http://database.yuxindazhineng.com/bucket/测试道路_modified.dxf",
  "modified_count": 2
}
```

---

## 实体参数示例

### LINE（直线）

```json
{
  "handle": "347A7",
  "type": "LINE",
  "layer": "测试道路纵断面网格线",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "start": { "value": [65432.51, 5969.92, 0.0], "editable": true, "type": "point", "description": "起点坐标 [x, y, z]" },
    "end": { "value": [79590.52, 5969.92, 0.0], "editable": true, "type": "point", "description": "终点坐标 [x, y, z]" }
  }
}
```

### CIRCLE（圆）

```json
{
  "handle": "37A64",
  "type": "CIRCLE",
  "layer": "测试道路纵断面设计线",
  "params": {
    "color": { "value": 60, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "center": { "value": [65432.51, 6149.49, 0.0], "editable": true, "type": "point", "description": "圆心坐标 [x, y, z]" },
    "radius": { "value": 1.0, "editable": true, "type": "number", "description": "半径", "min": 0.001 }
  }
}
```

### ARC（圆弧）

```json
{
  "handle": "4C714",
  "type": "ARC",
  "layer": "测试道路路线分解",
  "params": {
    "color": { "value": 1, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": 20, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "center": { "value": [12364.28, 6257.68, 0.0], "editable": true, "type": "point", "description": "圆心坐标 [x, y, z]" },
    "radius": { "value": 3000.0, "editable": true, "type": "number", "description": "半径", "min": 0.001 },
    "start_angle": { "value": 105.0, "editable": true, "type": "number", "description": "起始角度（度）", "min": 0, "max": 360 },
    "end_angle": { "value": 122.79, "editable": true, "type": "number", "description": "结束角度（度）", "min": 0, "max": 360 }
  }
}
```

### TEXT/MTEXT（文字）

```json
{
  "handle": "34D5B",
  "type": "MTEXT",
  "layer": "测试道路纵断面纵标尺",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "text": { "value": "50", "editable": true, "type": "string", "description": "文字内容" },
    "insert": { "value": [65500.0, 6000.0, 0.0], "editable": true, "type": "point", "description": "插入点坐标 [x, y, z]" },
    "height": { "value": 5.0, "editable": true, "type": "number", "description": "文字高度", "min": 0.1 }
  }
}
```

### POINT（点）

```json
{
  "handle": "34739",
  "type": "POINT",
  "layer": "DXT",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "location": { "value": [5252.28, 1739.92, 150.0], "editable": true, "type": "point", "description": "点坐标 [x, y, z]" }
  }
}
```

### ELLIPSE（椭圆）

```json
{
  "handle": "XXXXX",
  "type": "ELLIPSE",
  "layer": "图层名",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "center": { "value": [1000.0, 2000.0, 0.0], "editable": true, "type": "point", "description": "椭圆中心坐标 [x, y, z]" },
    "major_axis": { "value": [100.0, 0.0, 0.0], "editable": true, "type": "point", "description": "长轴向量 [x, y, z]" },
    "ratio": { "value": 0.5, "editable": true, "type": "number", "description": "短轴/长轴比例", "min": 0.001, "max": 1.0 },
    "start_param": { "value": 0, "editable": true, "type": "number", "description": "起始参数" },
    "end_param": { "value": 6.283185307179586, "editable": true, "type": "number", "description": "结束参数" }
  }
}
```

### SPLINE（样条曲线）

```json
{
  "handle": "XXXXX",
  "type": "SPLINE",
  "layer": "图层名",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "degree": { "value": 3, "editable": false, "type": "number", "description": "样条曲线阶数（只读）" },
    "control_points": { "value": [[0,0,0], [100,100,0], [200,0,0]], "editable": true, "type": "point_array", "description": "控制点数组 [[x,y,z], ...]" },
    "knots": { "value": [0, 0, 0, 1, 1, 1], "editable": false, "type": "array", "description": "节点向量（只读）" }
  }
}
```

### LWPOLYLINE（多段线）

```json
{
  "handle": "34D52",
  "type": "LWPOLYLINE",
  "layer": "测试道路纵断面纵标尺",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "vertices": { "value": [[0, 0], [100, 100], [200, 0]], "editable": true, "type": "point_array", "description": "顶点数组 [[x,y], ...]" },
    "closed": { "value": false, "editable": true, "type": "boolean", "description": "是否闭合" },
    "const_width": { "value": 0, "editable": true, "type": "number", "description": "恒定宽度" }
  }
}
```

### INSERT（块引用）

```json
{
  "handle": "344A5",
  "type": "INSERT",
  "layer": "测试道路线路信息",
  "params": {
    "color": { "value": 256, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -1, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "name": { "value": "BLOCK_NAME", "editable": false, "type": "string", "description": "块名称（只读）" },
    "insert": { "value": [1000.0, 2000.0, 0.0], "editable": true, "type": "point", "description": "插入点 [x, y, z]" },
    "xscale": { "value": 1.0, "editable": true, "type": "number", "description": "X 缩放比例" },
    "yscale": { "value": 1.0, "editable": true, "type": "number", "description": "Y 缩放比例" },
    "zscale": { "value": 1.0, "editable": true, "type": "number", "description": "Z 缩放比例" },
    "rotation": { "value": 0, "editable": true, "type": "number", "description": "旋转角度（度）" }
  }
}
```

### LEADER（引线）

```json
{
  "handle": "4C6F3",
  "type": "LEADER",
  "layer": "测试道路路线分解",
  "params": {
    "color": { "value": 4, "editable": true, "type": "number", "description": "颜色索引（0-256，256=随层）", "min": 0, "max": 256 },
    "lineweight": { "value": -3, "editable": true, "type": "number", "description": "线宽（-1=随层，-2=随块，-3=默认）" },
    "vertices": { "value": [[0,0,0], [100,100,0], [200,100,0]], "editable": true, "type": "point_array", "description": "引线顶点 [[x,y,z], ...]" },
    "has_arrowhead": { "value": true, "editable": true, "type": "boolean", "description": "是否显示箭头" }
  }
}
```

---

## 参数类型说明

| 类型 | 格式 | 示例 |
|-----|------|------|
| `point` | `[x, y, z]` | `[1000.0, 2000.0, 0.0]` |
| `number` | 数值 | `50.0`, `256` |
| `string` | 字符串 | `"桩号 K0+000"` |
| `boolean` | 布尔值 | `true`, `false` |
| `point_array` | `[[x,y,z], ...]` | `[[0,0,0], [100,100,0]]` |
| `array` | `[...]` | `[1, 2, 3, 4]` |
