# DXF 转换 API 文档

**基础 URL**: `http://localhost:8080/api/convert`

---

## 1. DXF 转 MD

**端点**: `POST /dxf-to-txt`

将 DXF 文件转换为 R12 格式，生成 MD 文件（提示词 + R12 DXF 数据）。

### 请求

```json
{
  "dxf_url": "http://database.yuxindazhineng.com/team-bucket/xxx.dxf",
  "include_prompt": true
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dxf_url | string | 是 | DXF 文件 URL |
| include_prompt | bool | 否 | 是否包含提示词，默认 true |

### 响应

```json
{
  "output_url": "http://database.yuxindazhineng.com/team-bucket/dxf_converted/xxx_R12数据和提示词.md",
  "file_size_mb": 3.08
}
```

---

## 2. MD 转 DXF（URL）

**端点**: `POST /md-to-dxf`

从 MD 文件 URL 提取 R12 DXF 数据，生成 .dxf 文件。

### 请求

```json
{
  "txt_url": "http://database.yuxindazhineng.com/team-bucket/dxf_converted/xxx_R12数据和提示词.md"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| txt_url | string | 是 | MD 文件 URL |

### 响应

```json
{
  "output_url": "http://database.yuxindazhineng.com/team-bucket/dxf_converted/xxx_提取.dxf",
  "file_size_mb": 2.93
}
```

---

## 3. MD 转 DXF（上传）

**端点**: `POST /md-to-dxf/upload`

直接上传 MD 文件，提取 R12 DXF 数据并返回 DXF 下载链接。

### 请求

`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | .md 文件 |

### 响应

```json
{
  "code": 0,
  "message": "转换成功",
  "data": {
    "output_url": "http://database.yuxindazhineng.com/team-bucket/dxf_converted/xxx_提取.dxf",
    "file_size_mb": 0.01,
    "entity_count": 7,
    "dxf_version": "AC1009"
  }
}
```

---

## 错误响应

### 文件已存在（400）

```json
{
  "detail": "文件已存在，请更换文件名后重试"
}
```

### 未找到 DXF 数据（400）

```json
{
  "detail": "MD 文件中未找到 R12 DXF 数据"
}

### 服务器错误（500）

```json
{
  "detail": "转换失败: ..."
}
```

---

## 说明

- 自动将任意版本 DXF 转为 R12（AC1009）
- 编码 GBK（cp936），支持中文
- 兼容 `\r\n` 和 `\n` 换行
- 文件名唯一，同名返回 400，不覆盖
- 支持 10 种实体：LINE、CIRCLE、ARC、TEXT/MTEXT、POINT、ELLIPSE、SPLINE、LWPOLYLINE、INSERT、LEADER

---

**最后更新**: 2026-06-02
