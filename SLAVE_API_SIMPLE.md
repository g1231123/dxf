# 被控端 API 数据格式

WebSocket 地址: `ws://localhost:8080/ws/render`

**说明**: 被控端只接收消息，不发送请求

---

## 响应数据

### connected - 连接成功

```json
{
  "type": "connected",
  "msg": "WebSocket 渲染服务就绪",
  "total_clients": 2
}
```

---

### preview - 预览结果（广播）

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
