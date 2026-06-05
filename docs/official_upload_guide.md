# 官方/用户上传区分方案

## 概述

通过 API Key 机制区分官方上传和用户上传，无需登录系统。

---

## 实现方式

### 1. API Key 配置

在 `config.py` 中配置官方 API Key：

```python
# 官方 API Key（用于标识官方上传）
OFFICIAL_API_KEY = os.environ.get("OFFICIAL_API_KEY", "yuxinda_official_2024")
```

**生产环境建议**：通过环境变量设置，避免硬编码：
```bash
export OFFICIAL_API_KEY="your_secure_api_key_here"
```

### 2. 数据库字段

在 `dxf_template` 表中添加 `is_official` 字段：

```sql
`is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户上传，1=官方上传'
```

- **0**: 用户上传（默认）
- **1**: 官方上传

### 3. 上传接口

**POST** `/template/upload`

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | ✅ | DXF 或 DWG 文件 |
| name | string | ❌ | 模板名称 |

#### 请求头（Header）

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| **X-API-Key** | string | ❌ | **官方 API Key，仅官方上传时通过服务端在请求头中传递** |

#### 示例

**用户上传**（前端直接调用，不提供 X-API-Key）：
```bash
curl -X POST "http://localhost:8080/template/upload" \
  -F "file=@用户模板.dxf" \
  -F "name=用户自定义模板"
```

**官方上传**（服务端调用，在请求头中传递 X-API-Key）：
```bash
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-API-Key: yuxinda_official_2024" \
  -F "file=@官方模板.dxf" \
  -F "name=官方标准模板"
```

#### 响应

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "...",
    "name": "官方标准模板",
    "is_official": true,
    "file_url": "...",
    "template_url": "..."
  }
}
```

---

## 查询接口

### 列表查询

**GET** `/template/list`

#### 新增参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| is_official | boolean | ❌ | 筛选条件：`true`=仅官方，`false`=仅用户，不传=全部 |

#### 示例

```bash
# 查询所有模板
curl "http://localhost:8080/template/list"

# 仅查询官方模板
curl "http://localhost:8080/template/list?is_official=true"

# 仅查询用户模板
curl "http://localhost:8080/template/list?is_official=false"

# 组合查询：官方模板 + 名称搜索
curl "http://localhost:8080/template/list?is_official=true&name=桥墩"
```

#### 响应

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "total": 10,
    "page": 1,
    "page_size": 20,
    "records": [
      {
        "id": "...",
        "name": "官方标准模板",
        "is_official": 1,
        "created_at": "2026-05-27T10:00:00"
      },
      {
        "id": "...",
        "name": "用户自定义模板",
        "is_official": 0,
        "created_at": "2026-05-27T09:00:00"
      }
    ]
  }
}
```

---

## 数据库迁移

### 新建表（已包含字段）

执行 `sql/init_dxf_template.sql`

### 已有表添加字段

执行 `sql/add_is_official_field.sql`：

```sql
ALTER TABLE `dxf_template` 
ADD COLUMN `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户上传，1=官方上传' AFTER `extent_max_y`,
ADD INDEX `idx_is_official` (`is_official`);
```

---

## 安全建议

1. **API Key 保密**
   - 不要在前端代码中硬编码
   - 仅在公司内部管理后台使用
   - 定期更换 API Key

2. **环境变量**
   ```bash
   # 生产环境
   export OFFICIAL_API_KEY="complex_random_key_2024"
   ```

3. **访问控制**
   - 官方上传接口仅对内部系统开放
   - 用户上传接口对外公开

4. **审计日志**
   - 记录所有官方上传操作
   - 监控 API Key 使用情况

---

## 前端集成示例

### 用户上传（前端直接调用）

```javascript
// 用户前端直接上传，不传 API Key
const formData = new FormData();
formData.append('file', file);
formData.append('name', '我的模板');

fetch('/template/upload', {
  method: 'POST',
  body: formData
});
```

### 官方上传（通过公司后端服务）

**架构**：
```
前端 → 公司后端 API → DXF 模板服务
```

**公司后端代码示例**（Node.js）：
```javascript
// 公司后端接收前端上传，转发到 DXF 模板服务
app.post('/admin/upload-official-template', upload.single('file'), async (req, res) => {
  const formData = new FormData();
  formData.append('file', req.file.buffer, req.file.originalname);
  formData.append('name', req.body.name);

  const response = await fetch('http://dxf-service:8080/template/upload', {
    method: 'POST',
    headers: {
      'X-API-Key': process.env.OFFICIAL_API_KEY  // 服务端传递，前端不可见
    },
    body: formData
  });

  const result = await response.json();
  res.json(result);
});
```

**前端调用公司后端**：
```javascript
// 前端调用公司自己的后端 API，不直接调用 DXF 模板服务
const formData = new FormData();
formData.append('file', file);
formData.append('name', '官方标准模板');

fetch('/admin/upload-official-template', {  // 调用公司后端
  method: 'POST',
  body: formData
});
```

### 筛选查询

```javascript
// 查询官方模板
fetch('/template/list?is_official=true')
  .then(res => res.json())
  .then(data => {
    console.log('官方模板:', data.data.records);
  });

// 查询用户模板
fetch('/template/list?is_official=false')
  .then(res => res.json())
  .then(data => {
    console.log('用户模板:', data.data.records);
  });
```

---

## 总结

- ✅ 无需登录系统
- ✅ 通过 API Key 简单区分
- ✅ 支持筛选查询
- ✅ 数据库字段标记
- ✅ 安全可控
