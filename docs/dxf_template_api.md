# DXF 模板服务 API 文档

## 概述

DXF 模板服务用于上传 DXF/DWG 文件，解析成结构化的 JSON 模板。

**基础路径**: `/template`

---

## 1. 上传模板

**POST** `/template/upload`

**Content-Type**: `multipart/form-data`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | ✅ | DXF 或 DWG 文件（最大 200MB） |
| name | string | ❌ | 模板名称，不传则使用文件名（去掉后缀） |

### 响应数据

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "a1b2c3d4e5f67890abcdef1234567890",
    "name": "圆端型实体墩",
    "original_filename": "圆端型实体墩_构造图.dxf",
    "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../圆端型实体墩_构造图.dxf",
    "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../template.json",
    "template": {
      "version": "1.0",
      "id": "a1b2c3d4e5f67890abcdef1234567890",
      "name": "圆端型实体墩",
      "original_filename": "圆端型实体墩_构造图.dxf",
      "dxf_version": "AC1027",
      "created_at": "2026-05-25T11:30:00.123456",
      "units": "4",
      "layers": [
        {
          "name": "0",
          "color": 7,
          "linetype": "Continuous",
          "is_on": true,
          "is_locked": false,
          "is_frozen": false
        },
        {
          "name": "墩身",
          "color": 1,
          "linetype": "Continuous",
          "is_on": true,
          "is_locked": false,
          "is_frozen": false
        }
      ],
      "blocks": [
        {
          "name": "钢筋符号",
          "base_point": [0.0, 0.0, 0.0],
          "entity_count": 5
        }
      ],
      "text_styles": [
        {
          "name": "Standard",
          "font": "txt",
          "height": 0.0
        }
      ],
      "dimension_styles": [
        {
          "name": "Standard"
        }
      ],
      "linetypes": [
        {
          "name": "Continuous",
          "description": "Solid line"
        },
        {
          "name": "DASHED",
          "description": "__ __ __ __"
        }
      ],
      "entities": [
        {
          "type": "LINE",
          "handle": "1A0",
          "layer": "墩身",
          "start": [0.0, 0.0, 0.0],
          "end": [100.0, 0.0, 0.0],
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，系统生成，不可修改"
            },
            "type": {
              "editable": false,
              "type": "string",
              "description": "实体类型，不可修改"
            },
            "layer": {
              "editable": true,
              "type": "string",
              "description": "所属图层，可修改为已存在的图层名"
            },
            "color": {
              "editable": true,
              "type": "color",
              "min": 0,
              "max": 256,
              "description": "颜色索引，0=ByBlock, 256=ByLayer, 1-255=固定颜色"
            },
            "linetype": {
              "editable": true,
              "type": "string",
              "description": "线型名称"
            },
            "start": {
              "editable": true,
              "type": "point",
              "description": "起点坐标 [x, y, z]，可任意修改"
            },
            "end": {
              "editable": true,
              "type": "point",
              "description": "终点坐标 [x, y, z]，可任意修改"
            }
          }
        },
        {
          "type": "CIRCLE",
          "handle": "1A5",
          "layer": "墩身",
          "center": [50.0, 25.0, 0.0],
          "radius": 10.0,
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，系统生成，不可修改"
            },
            "type": {
              "editable": false,
              "type": "string",
              "description": "实体类型，不可修改"
            },
            "layer": {
              "editable": true,
              "type": "string",
              "description": "所属图层，可修改为已存在的图层名"
            },
            "color": {
              "editable": true,
              "type": "color",
              "min": 0,
              "max": 256,
              "description": "颜色索引"
            },
            "center": {
              "editable": true,
              "type": "point",
              "description": "圆心坐标 [x, y, z]，可任意修改"
            },
            "radius": {
              "editable": true,
              "type": "number",
              "min": 0.001,
              "max": 10000000000.0,
              "description": "半径，必须大于0"
            }
          }
        },
        {
          "type": "TEXT",
          "handle": "1B0",
          "layer": "标注",
          "insert": [20.0, 30.0, 0.0],
          "text": "桥墩高度 H=15m",
          "height": 2.5,
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，系统生成，不可修改"
            },
            "type": {
              "editable": false,
              "type": "string",
              "description": "实体类型，不可修改"
            },
            "layer": {
              "editable": true,
              "type": "string",
              "description": "所属图层"
            },
            "insert": {
              "editable": true,
              "type": "point",
              "description": "插入点坐标 [x, y, z]，可任意修改"
            },
            "text": {
              "editable": true,
              "type": "string",
              "max_length": 2048,
              "description": "文字内容，可任意修改"
            },
            "height": {
              "editable": true,
              "type": "number",
              "min": 0.001,
              "max": 1000000.0,
              "description": "文字高度，必须大于0"
            },
            "rotation": {
              "editable": true,
              "type": "angle",
              "min": 0,
              "max": 360,
              "description": "旋转角度（度），0-360"
            }
          }
        },
        {
          "type": "LWPOLYLINE",
          "handle": "1C0",
          "layer": "轮廓",
          "points": [[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]],
          "is_closed": true,
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，系统生成，不可修改"
            },
            "type": {
              "editable": false,
              "type": "string",
              "description": "实体类型，不可修改"
            },
            "layer": {
              "editable": true,
              "type": "string",
              "description": "所属图层"
            },
            "points": {
              "editable": true,
              "type": "point_array",
              "min_points": 2,
              "description": "顶点坐标数组，至少2个点"
            },
            "is_closed": {
              "editable": true,
              "type": "boolean",
              "description": "是否闭合"
            },
            "const_width": {
              "editable": true,
              "type": "number",
              "min": 0,
              "max": 1000000.0,
              "description": "统一线宽，0表示无宽度"
            }
          }
        },
        {
          "type": "INSERT",
          "handle": "1D0",
          "layer": "0",
          "insert": [80.0, 40.0, 0.0],
          "block_name": "钢筋符号",
          "scale": [1.0, 1.0, 1.0],
          "rotation": 0.0,
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，系统生成，不可修改"
            },
            "type": {
              "editable": false,
              "type": "string",
              "description": "实体类型，不可修改"
            },
            "block_name": {
              "editable": false,
              "type": "string",
              "description": "块名称，不可修改（需使用已定义的块）"
            },
            "insert": {
              "editable": true,
              "type": "point",
              "description": "插入点坐标 [x, y, z]，可任意修改"
            },
            "scale": {
              "editable": true,
              "type": "scale",
              "min": 0.001,
              "max": 1000000.0,
              "description": "缩放比例 [x, y, z]，必须大于0"
            },
            "rotation": {
              "editable": true,
              "type": "angle",
              "min": 0,
              "max": 360,
              "description": "旋转角度（度），0-360"
            }
          }
        }
      ],
      "extent": {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 100.0,
        "max_y": 50.0,
        "width": 100.0,
        "height": 50.0
      },
      "editable_rules": {
        "description": "参数编辑规则说明",
        "param_types": {
          "number": "数值类型，需遵守 min/max 约束",
          "string": "字符串类型，可能有 max_length 约束",
          "point": "坐标点 [x, y, z]，可任意修改",
          "point_array": "坐标点数组，需遵守 min_points 约束",
          "angle": "角度值（度），通常 0-360",
          "scale": "缩放比例 [x, y, z]，需遵守 min/max 约束",
          "color": "颜色索引 0-256",
          "boolean": "布尔值 true/false"
        }
      },
      "entity_summary": {
        "LINE": 45,
        "CIRCLE": 12,
        "TEXT": 28,
        "LWPOLYLINE": 35,
        "INSERT": 8
      },
      "total_entities": 128
    }
  }
}
```

---

## 2. 查询模板列表

**GET** `/template/list`

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| page | int | ❌ | 1 | 页码 |
| page_size | int | ❌ | 20 | 每页数量 |
| name | string | ❌ | - | 模板名称（模糊搜索） |

### 响应数据

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "total": 25,
    "page": 1,
    "page_size": 10,
    "records": [
      {
        "id": "a1b2c3d4e5f67890abcdef1234567890",
        "name": "圆端型实体墩",
        "original_filename": "圆端型实体墩_构造图.dxf",
        "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../圆端型实体墩_构造图.dxf",
        "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../template.json",
        "dxf_version": "AC1027",
        "layer_count": 5,
        "block_count": 3,
        "entity_count": 128,
        "created_at": "2026-05-25T11:30:00"
      },
      {
        "id": "b2c3d4e5f67890abcdef1234567890a1",
        "name": "矩形实体墩",
        "original_filename": "矩形实体墩_构造图.dxf",
        "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/b2c3d4e5.../矩形实体墩_构造图.dxf",
        "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/b2c3d4e5.../template.json",
        "dxf_version": "AC1027",
        "layer_count": 4,
        "block_count": 2,
        "entity_count": 96,
        "created_at": "2026-05-24T15:20:00"
      }
    ]
  }
}
```

---

## 3. 查询模板详情

**GET** `/template/detail`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| id | string | ✅ | 模板 ID |

### 响应数据

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "id": "a1b2c3d4e5f67890abcdef1234567890",
    "name": "圆端型实体墩",
    "original_filename": "圆端型实体墩_构造图.dxf",
    "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../圆端型实体墩_构造图.dxf",
    "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2c3d4.../template.json",
    "dxf_version": "AC1027",
    "layer_count": 5,
    "block_count": 3,
    "entity_count": 128,
    "extent_min_x": 0.0,
    "extent_min_y": 0.0,
    "extent_max_x": 100.0,
    "extent_max_y": 50.0,
    "created_at": "2026-05-25T11:30:00",
    "updated_at": null
  }
}
```

---

## 4. 删除模板

**DELETE** `/template/delete`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| id | string | ✅ | 模板 ID |

### 响应数据

```json
{
  "code": 0,
  "message": "删除成功"
}
```

---

## 错误响应

```json
{
  "detail": "错误信息描述"
}
```

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误（如缺少文件名、文件格式不正确） |
| 404 | 模板不存在 |
| 413 | 文件太大（超过 200MB） |
| 500 | 服务器内部错误 |

---

## 支持的实体类型

| 实体类型 | 说明 | 主要属性 |
|----------|------|----------|
| LINE | 直线 | start, end |
| CIRCLE | 圆 | center, radius |
| ARC | 圆弧 | center, radius, start_angle, end_angle |
| TEXT | 单行文字 | insert, text, height, rotation |
| MTEXT | 多行文字 | insert, text, char_height, width |
| LWPOLYLINE | 轻量多段线 | points, is_closed, const_width |
| POLYLINE | 多段线 | points, is_closed |
| INSERT | 块引用 | insert, block_name, scale, rotation |
| DIMENSION | 标注 | dimension_type, text_override |
| HATCH | 填充 | pattern_name, pattern_scale, pattern_angle |
| ELLIPSE | 椭圆 | center, major_axis, ratio |
| SPLINE | 样条曲线 | control_points, degree |

---

## 可编辑参数类型说明

| 类型 | 说明 | 约束字段 |
|------|------|----------|
| `number` | 数值类型 | `min`, `max` |
| `string` | 字符串类型 | `max_length` |
| `point` | 坐标点 `[x, y, z]` | 无 |
| `point_array` | 坐标点数组 | `min_points` |
| `angle` | 角度值（度） | `min`, `max`（通常 0-360） |
| `scale` | 缩放比例 `[x, y, z]` | `min`, `max` |
| `color` | 颜色索引 | `min: 0`, `max: 256` |
| `boolean` | 布尔值 | `true`/`false` |
