# DXF 模板服务完整文档

**版本**: 1.0  
**更新时间**: 2026-05-27

---

## 目录

1. [服务概述](#服务概述)
2. [核心功能](#核心功能)
3. [API 接口](#api-接口)
4. [官方/用户上传区分](#官方用户上传区分)
5. [IP 白名单管理](#ip-白名单管理)
6. [安全认证方案](#安全认证方案)
7. [数据库设计](#数据库设计)
8. [部署配置](#部署配置)
9. [常见问题](#常见问题)

---

## 服务概述

### 功能简介

DXF 模板服务用于上传 DXF/DWG 文件，解析成结构化的 JSON 模板，并存储到 MinIO 和 MySQL 数据库中。

### 技术栈

- **Web 框架**: FastAPI
- **DXF 解析**: ezdxf
- **对象存储**: MinIO (S3 兼容)
- **数据库**: MySQL
- **Python 版本**: 3.12+

### 服务地址

- **基础路径**: `/template`
- **管理路径**: `/admin/ip-whitelist`

---

## 核心功能

### 1. DXF/DWG 文件解析

- 支持 DXF 和 DWG 格式
- 自动提取图层、块、实体等信息
- 生成结构化 JSON 模板
- 标记可编辑参数及其约束

### 2. 官方/用户上传区分

- 官方上传：公司内部管理的标准模板
- 用户上传：普通用户自定义模板
- 支持三种认证方式：IP 白名单、API Key、时间戳签名

### 3. 模板管理

- 上传模板
- 分页查询（支持名称搜索、官方/用户筛选）
- 查看详情
- 删除模板

### 4. 动态 IP 白名单

- 内存存储，不写数据库
- 支持动态添加/移除
- 服务重启后恢复默认值

---

## API 接口

### 模板管理接口

#### 1. 上传模板

**POST** `/template/upload`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | ✅ | DXF 或 DWG 文件（最大 200MB） |
| name | string | ❌ | 模板名称，不传则使用文件名 |

**请求头（官方上传）**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-API-Key | string | ❌ | 官方 API Key |
| X-Timestamp | string | ❌ | 时间戳（配合签名使用） |
| X-Signature | string | ❌ | HMAC-SHA256 签名 |

**示例**:

```bash
# 用户上传
curl -X POST "http://localhost:8080/template/upload" \
  -F "file=@用户模板.dxf" \
  -F "name=我的模板"

# 官方上传（通过 API Key）
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-API-Key: yuxinda_official_2024" \
  -F "file=@官方模板.dxf" \
  -F "name=官方标准模板"
```

**响应**:

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "a1b2c3d4e5f67890",
    "name": "官方标准模板",
    "original_filename": "官方模板.dxf",
    "file_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../官方模板.dxf",
    "template_url": "http://minio.yuxindazhineng.com/team-bucket/dxf_templates/a1b2.../template.json",
    "is_official": true,
    "template": {
      "version": "1.0",
      "dxf_version": "AC1027",
      "layers": [...],
      "blocks": [...],
      "entities": [
        {
          "type": "LINE",
          "handle": "1A0",
          "layer": "墩身",
          "start": [0.0, 0.0, 0.0],
          "end": [100.0, 0.0, 0.0],
          "editable_params": {
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
        }
      ],
      "extent": {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 100.0,
        "max_y": 50.0
      }
    }
  }
}
```

---

#### 2. 查询模板列表

**GET** `/template/list`

**请求参数**:

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| page | int | ❌ | 1 | 页码 |
| page_size | int | ❌ | 20 | 每页数量 |
| name | string | ❌ | - | 模板名称（模糊搜索） |
| is_official | boolean | ❌ | - | true=仅官方，false=仅用户，不传=全部 |

**示例**:

```bash
# 查询所有模板
curl "http://localhost:8080/template/list"

# 查询官方模板
curl "http://localhost:8080/template/list?is_official=true"

# 搜索名称包含"桥墩"的官方模板
curl "http://localhost:8080/template/list?is_official=true&name=桥墩"
```

**响应**:

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "total": 25,
    "page": 1,
    "page_size": 20,
    "records": [
      {
        "id": "a1b2c3d4e5f67890",
        "name": "圆端型实体墩",
        "original_filename": "圆端型实体墩_构造图.dxf",
        "file_url": "http://minio.yuxindazhineng.com/...",
        "template_url": "http://minio.yuxindazhineng.com/...",
        "dxf_version": "AC1027",
        "layer_count": 5,
        "block_count": 3,
        "entity_count": 128,
        "is_official": 1,
        "created_at": "2026-05-27T10:00:00"
      }
    ]
  }
}
```

---

#### 3. 查询模板详情

**GET** `/template/detail`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| id | string | ✅ | 模板 ID |

**示例**:

```bash
curl "http://localhost:8080/template/detail?id=a1b2c3d4e5f67890"
```

**响应**:

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "id": "a1b2c3d4e5f67890",
    "name": "圆端型实体墩",
    "original_filename": "圆端型实体墩_构造图.dxf",
    "file_url": "http://minio.yuxindazhineng.com/...",
    "template_url": "http://minio.yuxindazhineng.com/...",
    "dxf_version": "AC1027",
    "layer_count": 5,
    "block_count": 3,
    "entity_count": 128,
    "extent_min_x": 0.0,
    "extent_min_y": 0.0,
    "extent_max_x": 100.0,
    "extent_max_y": 50.0,
    "is_official": 1,
    "created_at": "2026-05-27T10:00:00"
  }
}
```

---

#### 4. 删除模板

**DELETE** `/template/delete`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| id | string | ✅ | 模板 ID |

**示例**:

```bash
curl -X DELETE "http://localhost:8080/template/delete?id=a1b2c3d4e5f67890"
```

**响应**:

```json
{
  "code": 0,
  "message": "删除成功"
}
```

---

### IP 白名单管理接口

**基础路径**: `/admin/ip-whitelist`  
**权限要求**: 所有接口需要 `X-Admin-Key` 请求头

#### 1. 查询白名单

**GET** `/admin/ip-whitelist/list`

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  http://localhost:8080/admin/ip-whitelist/list
```

**响应**:

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "total": 3,
    "ips": ["127.0.0.1", "192.168.10.0/24", "192.168.10.100"],
    "note": "内存存储，服务重启后恢复为配置文件默认值"
  }
}
```

---

#### 2. 添加 IP

**POST** `/admin/ip-whitelist/add`

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/add \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

---

#### 3. 批量添加

**POST** `/admin/ip-whitelist/add-batch`

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/add-batch \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ips": ["192.168.10.201", "192.168.10.202"]}'
```

---

#### 4. 移除 IP

**DELETE** `/admin/ip-whitelist/remove`

```bash
curl -X DELETE http://localhost:8080/admin/ip-whitelist/remove \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

---

#### 5. 检查 IP

**GET** `/admin/ip-whitelist/check?ip=xxx`

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  "http://localhost:8080/admin/ip-whitelist/check?ip=192.168.10.100"
```

---

#### 6. 重置为默认值

**POST** `/admin/ip-whitelist/reset`

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/reset \
  -H "X-Admin-Key: yuxinda_official_2024"
```

---

## 官方/用户上传区分

### 认证方式

支持三种认证方式，**满足任一即可**标记为官方上传：

#### 方式一：IP 白名单（推荐）

**适用场景**: 公司内网固定 IP

**配置**:

```bash
export OFFICIAL_IP_WHITELIST="192.168.10.0/24,10.0.0.0/8"
```

**优点**:
- ✅ 无需传递任何凭证
- ✅ 自动识别
- ✅ 配置简单

**使用**:

```bash
# 从白名单 IP 上传，自动识别为官方
curl -F "file=@official.dxf" http://192.168.10.100:8080/template/upload
```

---

#### 方式二：API Key

**适用场景**: 通过公司后端服务调用

**配置**:

```bash
export OFFICIAL_API_KEY="yuxinda_official_2024"
```

**使用**:

```bash
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-API-Key: yuxinda_official_2024" \
  -F "file=@official.dxf"
```

**架构**:

```
前端 → 公司后端 API → DXF 模板服务（带 X-API-Key）
```

---

#### 方式三：时间戳签名（最安全）

**适用场景**: 高安全要求、防重放攻击

**配置**:

```bash
export SIGNATURE_SECRET="yuxinda_secret_2024"
export SIGNATURE_EXPIRY="300"  # 5分钟有效期
```

**签名算法**:

```
signature = HMAC-SHA256(secret, timestamp + file_hash)
```

**Python 示例**:

```python
import hmac
import hashlib
import time

def generate_signature(secret, file_hash=""):
    timestamp = str(int(time.time()))
    message = f"{timestamp}{file_hash}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return timestamp, signature

# 使用
timestamp, signature = generate_signature("yuxinda_secret_2024")
```

**使用**:

```bash
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-Timestamp: 1716782400" \
  -H "X-Signature: a1b2c3d4..." \
  -F "file=@official.dxf"
```

---

### 认证流程

```
1. 检查 IP 白名单 → 通过 ✅ → is_official = true
   ↓ 不通过
2. 检查 API Key → 通过 ✅ → is_official = true
   ↓ 不通过
3. 检查时间戳签名 → 通过 ✅ → is_official = true
   ↓ 不通过
4. is_official = false（用户上传）
```

---

## IP 白名单管理

### 静态配置（配置文件）

编辑 `config.py` 或设置环境变量：

```bash
# 单个 IP
export OFFICIAL_IP_WHITELIST="192.168.10.100"

# 多个 IP
export OFFICIAL_IP_WHITELIST="192.168.10.100,192.168.10.101"

# CIDR 网段
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"

# 混合配置
export OFFICIAL_IP_WHITELIST="127.0.0.1,192.168.10.0/24,10.0.0.0/8"
```

### 动态管理（API 接口）

**特点**:
- 内存存储，不写数据库
- 支持实时添加/移除
- 服务重启后恢复默认值

**常用操作**:

```bash
# 临时添加测试 IP
curl -X POST http://localhost:8080/admin/ip-whitelist/add \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.250"}'

# 查询当前白名单
curl -H "X-Admin-Key: yuxinda_official_2024" \
  http://localhost:8080/admin/ip-whitelist/list

# 测试完成后移除
curl -X DELETE http://localhost:8080/admin/ip-whitelist/remove \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.250"}'
```

---

## 安全认证方案

### 方案对比

| 方案 | 安全性 | 复杂度 | 适用场景 |
|------|--------|--------|----------|
| IP 白名单 | ⭐⭐⭐ | ⭐ | 内网固定 IP |
| API Key | ⭐⭐⭐⭐ | ⭐⭐ | 后端服务调用 |
| 时间戳签名 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 高安全要求 |

### 推荐组合

**内网环境**:
```bash
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
```

**外网环境**:
```bash
export OFFICIAL_API_KEY="your_secure_key"
export SIGNATURE_SECRET="your_signature_secret"
```

**混合环境**:
```bash
# 内网自动识别 + 外网签名验证
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
export SIGNATURE_SECRET="your_signature_secret"
```

---

## 数据库设计

### 表结构

```sql
CREATE TABLE IF NOT EXISTS `dxf_template` (
    `id` VARCHAR(64) NOT NULL COMMENT '模板ID (UUID)',
    `name` VARCHAR(255) NOT NULL COMMENT '模板名称',
    `original_filename` VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `file_url` VARCHAR(512) NOT NULL COMMENT '原始文件的 MinIO URL',
    `template_url` VARCHAR(512) NOT NULL COMMENT '模板 JSON 的 MinIO URL',
    `dxf_version` VARCHAR(32) DEFAULT NULL COMMENT 'DXF 版本',
    `layer_count` INT DEFAULT 0 COMMENT '图层数量',
    `block_count` INT DEFAULT 0 COMMENT '块数量',
    `entity_count` INT DEFAULT 0 COMMENT '实体数量',
    `extent_min_x` DOUBLE DEFAULT NULL COMMENT '范围最小X',
    `extent_min_y` DOUBLE DEFAULT NULL COMMENT '范围最小Y',
    `extent_max_x` DOUBLE DEFAULT NULL COMMENT '范围最大X',
    `extent_max_y` DOUBLE DEFAULT NULL COMMENT '范围最大Y',
    `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户，1=官方',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_name` (`name`),
    INDEX `idx_original_filename` (`original_filename`),
    INDEX `idx_is_official` (`is_official`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 初始化

```bash
# 新建表
mysql -u yxdzn -p draw_design < sql/init_dxf_template.sql

# 已有表添加 is_official 字段
mysql -u yxdzn -p draw_design < sql/add_is_official_field.sql
```

---

## 部署配置

### 环境变量

```bash
# 网络模式
export NETWORK_MODE="external"  # internal/external

# MySQL 配置
export MYSQL_HOST="www.yuxindazhineng.com"
export MYSQL_PORT="3306"
export MYSQL_DATABASE="draw_design"
export MYSQL_USER="yxdzn"
export MYSQL_PASSWORD="Zn@2024#Safe"

# MinIO 配置
export MINIO_ENDPOINT="database.yuxindazhineng.com"
export MINIO_ACCESS_KEY="yuxinda_admin"
export MINIO_SECRET_KEY="yuxinda_admin01"
export MINIO_BUCKET="team-bucket"
export MINIO_PUBLIC_URL="http://minio.yuxindazhineng.com"

# 官方上传认证
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
export OFFICIAL_API_KEY="yuxinda_official_2024"
export SIGNATURE_SECRET="yuxinda_secret_2024"
export SIGNATURE_EXPIRY="300"
```

### 启动服务

```bash
# 外网模式
NETWORK_MODE=external bash run_qgis_mac.sh

# 内网模式
NETWORK_MODE=internal bash run_qgis_mac.sh
```

### Docker 部署

```yaml
version: '3.8'
services:
  dxf-service:
    image: dxf-template-service:latest
    environment:
      - NETWORK_MODE=external
      - MYSQL_HOST=www.yuxindazhineng.com
      - MINIO_ENDPOINT=database.yuxindazhineng.com
      - OFFICIAL_IP_WHITELIST=192.168.10.0/24
      - OFFICIAL_API_KEY=yuxinda_official_2024
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
```

---

## 常见问题

### 1. 上传失败：文件太大

**问题**: `413 Request Entity Too Large`

**解决**:
- 当前限制 200MB
- 修改 `MAX_UPLOAD_BYTES` 配置

---

### 2. 中文乱码

**问题**: DXF 文件中的中文显示为乱码

**解决**:
- 服务已自动尝试多种编码（UTF-8、GBK、GB2312 等）
- 如仍有问题，检查 DXF 文件编码

---

### 3. IP 白名单不生效

**问题**: 配置了白名单，但 `is_official` 仍为 `false`

**排查**:

```bash
# 1. 检查当前 IP
curl http://localhost:8080/admin/ip-whitelist/check?ip=YOUR_IP \
  -H "X-Admin-Key: yuxinda_official_2024"

# 2. 检查配置
echo $OFFICIAL_IP_WHITELIST

# 3. 重启服务
systemctl restart dxf-service
```

---

### 4. 数据库连接失败

**问题**: `Can't connect to MySQL server`

**排查**:

```bash
# 测试连接
mysql -h www.yuxindazhineng.com -u yxdzn -p

# 检查网络模式
echo $NETWORK_MODE

# 检查防火墙
telnet www.yuxindazhineng.com 3306
```

---

### 5. MinIO 上传失败

**问题**: `上传失败: No module named 'minio'`

**解决**:

```bash
# 安装依赖
pip install boto3 botocore s3transfer

# 或重新安装
pip install -r requirements.txt
```

---

## 附录

### 支持的实体类型

| 实体类型 | 说明 | 主要属性 |
|----------|------|----------|
| LINE | 直线 | start, end |
| CIRCLE | 圆 | center, radius |
| ARC | 圆弧 | center, radius, start_angle, end_angle |
| TEXT | 单行文字 | insert, text, height |
| MTEXT | 多行文字 | insert, text, char_height |
| LWPOLYLINE | 轻量多段线 | points, is_closed |
| POLYLINE | 多段线 | points, is_closed |
| INSERT | 块引用 | insert, block_name, scale |
| DIMENSION | 标注 | dimension_type |
| HATCH | 填充 | pattern_name |
| ELLIPSE | 椭圆 | center, major_axis |
| SPLINE | 样条曲线 | control_points |

### 可编辑参数类型

| 类型 | 说明 | 约束字段 |
|------|------|----------|
| number | 数值类型 | min, max |
| string | 字符串类型 | max_length |
| point | 坐标点 [x, y, z] | 无 |
| point_array | 坐标点数组 | min_points |
| angle | 角度值（度） | min, max |
| scale | 缩放比例 [x, y, z] | min, max |
| color | 颜色索引 | 0-256 |
| boolean | 布尔值 | true/false |

---

## 联系方式

- **技术支持**: support@yuxindazhineng.com
- **文档更新**: 2026-05-27
- **版本**: v1.0
