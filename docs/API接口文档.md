# DXF 模板服务 API 接口文档

**基础路径**: `/template`  
**版本**: 1.0

---

## 1. 上传模板

**POST** `/template/upload`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | ✅ | DXF 或 DWG 文件（最大 200MB） |
| name | string | ❌ | 模板名称，不传则使用文件名 |

### 请求头（官方上传，可选）

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-API-Key | string | ❌ | 官方 API Key |
| X-Timestamp | string | ❌ | 时间戳（Unix 时间戳） |
| X-Signature | string | ❌ | HMAC-SHA256 签名 |

### 请求示例

```bash
# 用户上传
curl -X POST "http://localhost:8080/template/upload" \
  -F "file=@template.dxf" \
  -F "name=我的模板"

# 官方上传
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-API-Key: yuxinda_official_2024" \
  -F "file=@template.dxf" \
  -F "name=官方模板"
```

### 响应数据

**注意**: 为避免响应过大，上传接口不返回完整的 `template` 数据，仅返回摘要信息。如需完整模板数据，请使用 `/template/template-json` 接口或直接访问 `template_url`。

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "a1b2c3d4e5f67890abcdef1234567890",
    "name": "官方模板",
    "original_filename": "template.dxf",
    "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../template.dxf",
    "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../template.json",
    "is_official": true,
    "dxf_version": "AC1027",
    "layer_count": 5,
    "block_count": 3,
    "entity_count": 128,
    "extent": {
      "min_x": 0.0,
      "min_y": 0.0,
      "max_x": 100.0,
      "max_y": 50.0,
      "width": 100.0,
      "height": 50.0
    },
    "created_at": "2026-05-27T10:30:00.123456"
  }
}
```

**获取完整模板数据的方式**:

1. 直接访问 `template_url`（推荐）
2. 调用 `/template/template-json?id=xxx` 接口

---

## 1.1 获取完整模板 JSON

**GET** `/template/template-json`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| id | string | ✅ | 模板 ID |

### 请求示例

```bash
curl "http://localhost:8080/template/template-json?id=a1b2c3d4e5f67890abcdef1234567890"
```

### 响应数据

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "template": {
      "version": "1.0",
      "id": "a1b2c3d4e5f67890abcdef1234567890",
      "name": "官方模板",
      "original_filename": "template.dxf",
      "dxf_version": "AC1027",
      "created_at": "2026-05-27T10:30:00.123456",
      "units": "4",
      "layers": [
        {
          "name": "0",
          "color": 7,
          "linetype": "Continuous",
          "is_on": true,
          "is_locked": false,
          "is_frozen": false
        }
      ],
      "blocks": [
        {
          "name": "BlockName",
          "base_point": [0.0, 0.0, 0.0],
          "entity_count": 5
        }
      ],
      "entities": [
        {
          "type": "LINE",
          "handle": "1A0",
          "layer": "0",
          "start": [0.0, 0.0, 0.0],
          "end": [100.0, 0.0, 0.0],
          "editable_params": {
            "handle": {
              "editable": false,
              "type": "string",
              "description": "实体句柄，不可修改"
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
            "start": {
              "editable": true,
              "type": "point",
              "description": "起点坐标 [x, y, z]"
            },
            "end": {
              "editable": true,
              "type": "point",
              "description": "终点坐标 [x, y, z]"
            }
          }
        },
        {
          "type": "CIRCLE",
          "handle": "1A5",
          "layer": "0",
          "center": [50.0, 25.0, 0.0],
          "radius": 10.0,
          "editable_params": {
            "center": {
              "editable": true,
              "type": "point",
              "description": "圆心坐标 [x, y, z]"
            },
            "radius": {
              "editable": true,
              "type": "number",
              "min": 0.001,
              "max": 10000000000.0,
              "description": "半径"
            }
          }
        },
        {
          "type": "TEXT",
          "handle": "1B0",
          "layer": "0",
          "insert": [20.0, 30.0, 0.0],
          "text": "示例文字",
          "height": 2.5,
          "editable_params": {
            "insert": {
              "editable": true,
              "type": "point",
              "description": "插入点坐标 [x, y, z]"
            },
            "text": {
              "editable": true,
              "type": "string",
              "max_length": 2048,
              "description": "文字内容"
            },
            "height": {
              "editable": true,
              "type": "number",
              "min": 0.001,
              "max": 1000000.0,
              "description": "文字高度"
            }
          }
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
          "point": "坐标点 [x, y, z]",
          "point_array": "坐标点数组，需遵守 min_points 约束",
          "angle": "角度值（度），0-360",
          "scale": "缩放比例 [x, y, z]",
          "color": "颜色索引 0-256",
          "boolean": "布尔值 true/false"
        }
      },
      "entity_summary": {
        "LINE": 45,
        "CIRCLE": 12,
        "TEXT": 28
      },
      "total_entities": 85
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
| is_official | boolean | ❌ | - | true=仅官方，false=仅用户，不传=全部 |

### 请求示例

```bash
# 查询所有模板
curl "http://localhost:8080/template/list"

# 查询第2页
curl "http://localhost:8080/template/list?page=2&page_size=10"

# 查询官方模板
curl "http://localhost:8080/template/list?is_official=true"

# 搜索名称包含"桥墩"的模板
curl "http://localhost:8080/template/list?name=桥墩"

# 组合查询
curl "http://localhost:8080/template/list?is_official=true&name=桥墩&page=1&page_size=10"
```

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
        "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../圆端型实体墩_构造图.dxf",
        "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../template.json",
        "dxf_version": "AC1027",
        "layer_count": 5,
        "block_count": 3,
        "entity_count": 128,
        "is_official": 1,
        "created_at": "2026-05-27T10:00:00"
      },
      {
        "id": "b2c3d4e5f67890abcdef1234567890a1",
        "name": "矩形实体墩",
        "original_filename": "矩形实体墩_构造图.dxf",
        "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/b2c3.../矩形实体墩_构造图.dxf",
        "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/b2c3.../template.json",
        "dxf_version": "AC1027",
        "layer_count": 4,
        "block_count": 2,
        "entity_count": 96,
        "is_official": 0,
        "created_at": "2026-05-26T15:20:00"
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

### 请求示例

```bash
curl "http://localhost:8080/template/detail?id=a1b2c3d4e5f67890abcdef1234567890"
```

### 响应数据

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "id": "a1b2c3d4e5f67890abcdef1234567890",
    "name": "圆端型实体墩",
    "original_filename": "圆端型实体墩_构造图.dxf",
    "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../圆端型实体墩_构造图.dxf",
    "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../template.json",
    "dxf_version": "AC1027",
    "layer_count": 5,
    "block_count": 3,
    "entity_count": 128,
    "extent_min_x": 0.0,
    "extent_min_y": 0.0,
    "extent_max_x": 100.0,
    "extent_max_y": 50.0,
    "is_official": 1,
    "created_at": "2026-05-27T10:00:00",
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

### 请求示例

```bash
curl -X DELETE "http://localhost:8080/template/delete?id=a1b2c3d4e5f67890abcdef1234567890"
```

### 响应数据

```json
{
  "code": 0,
  "message": "删除成功"
}
```

---

## 5. 查询 IP 白名单

**GET** `/admin/ip-whitelist/list`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求示例

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  "http://localhost:8080/admin/ip-whitelist/list"
```

### 响应数据

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "total": 3,
    "ips": [
      "127.0.0.1",
      "192.168.10.0/24",
      "192.168.10.100"
    ],
    "note": "内存存储，服务重启后恢复为配置文件默认值"
  }
}
```

---

## 6. 添加 IP 到白名单

**POST** `/admin/ip-whitelist/add`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求体

```json
{
  "ip": "192.168.10.200"
}
```

### 请求示例

```bash
curl -X POST "http://localhost:8080/admin/ip-whitelist/add" \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

### 响应数据

```json
{
  "code": 0,
  "message": "添加成功",
  "data": {
    "ip": "192.168.10.200",
    "total": 4
  }
}
```

---

## 7. 批量添加 IP

**POST** `/admin/ip-whitelist/add-batch`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求体

```json
{
  "ips": [
    "192.168.10.201",
    "192.168.10.202",
    "192.168.20.0/24"
  ]
}
```

### 请求示例

```bash
curl -X POST "http://localhost:8080/admin/ip-whitelist/add-batch" \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{
    "ips": ["192.168.10.201", "192.168.10.202", "192.168.20.0/24"]
  }'
```

### 响应数据

```json
{
  "code": 0,
  "message": "批量添加完成",
  "data": {
    "added": [
      "192.168.10.201",
      "192.168.10.202",
      "192.168.20.0/24"
    ],
    "existed": [],
    "total": 7
  }
}
```

---

## 8. 移除 IP

**DELETE** `/admin/ip-whitelist/remove`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求体

```json
{
  "ip": "192.168.10.200"
}
```

### 请求示例

```bash
curl -X DELETE "http://localhost:8080/admin/ip-whitelist/remove" \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

### 响应数据

```json
{
  "code": 0,
  "message": "移除成功",
  "data": {
    "ip": "192.168.10.200",
    "total": 6
  }
}
```

---

## 9. 检查 IP

**GET** `/admin/ip-whitelist/check`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ip | string | ✅ | 要检查的 IP |

### 请求示例

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  "http://localhost:8080/admin/ip-whitelist/check?ip=192.168.10.100"
```

### 响应数据

```json
{
  "code": 0,
  "message": "检查完成",
  "data": {
    "ip": "192.168.10.100",
    "in_whitelist": true,
    "matched_rule": "192.168.10.0/24"
  }
}
```

---

## 10. 重置白名单

**POST** `/admin/ip-whitelist/reset`

### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

### 请求示例

```bash
curl -X POST "http://localhost:8080/admin/ip-whitelist/reset" \
  -H "X-Admin-Key: yuxinda_official_2024"
```

### 响应数据

```json
{
  "code": 0,
  "message": "已重置为配置文件默认值",
  "data": {
    "old_count": 10,
    "current_count": 2,
    "default_ips": [
      "127.0.0.1",
      "::1"
    ]
  }
}
```

---

## 错误响应

所有接口在发生错误时返回以下格式：

```json
{
  "detail": "错误信息描述"
}
```

**常见错误码**：

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 403 | 无权限（管理接口） |
| 404 | 资源不存在 |
| 413 | 文件太大（超过 200MB） |
| 500 | 服务器内部错误 |
