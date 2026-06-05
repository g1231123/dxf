# IP 白名单配置指南

## 概述

IP 白名单是最简单的官方上传识别方式，适用于公司内网环境。

**原理**：服务器自动识别请求来源 IP，如果在白名单内，自动标记为官方上传。

---

## 配置方式

### 方式一：环境变量（推荐）

```bash
# 单个 IP
export OFFICIAL_IP_WHITELIST="192.168.10.100"

# 多个 IP（逗号分隔）
export OFFICIAL_IP_WHITELIST="192.168.10.100,192.168.10.101,192.168.10.102"

# CIDR 网段
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"

# 混合配置
export OFFICIAL_IP_WHITELIST="127.0.0.1,::1,192.168.10.100,192.168.10.0/24,10.0.0.0/8"
```

### 方式二：修改配置文件

编辑 `config.py`：

```python
OFFICIAL_IP_WHITELIST = os.environ.get(
    "OFFICIAL_IP_WHITELIST",
    "192.168.10.100,192.168.10.0/24"  # 修改这里
)
```

---

## 支持的格式

### 1. 单个 IPv4 地址

```bash
export OFFICIAL_IP_WHITELIST="192.168.10.100"
```

匹配：`192.168.10.100`

### 2. 单个 IPv6 地址

```bash
export OFFICIAL_IP_WHITELIST="::1,fe80::1"
```

匹配：`::1`（本地回环）

### 3. CIDR 网段（仅支持 /24）

```bash
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
```

匹配：`192.168.10.0` ~ `192.168.10.255`

### 4. 多个配置（逗号分隔）

```bash
export OFFICIAL_IP_WHITELIST="127.0.0.1,192.168.10.100,192.168.10.0/24"
```

---

## 常见场景配置

### 场景一：本地开发

```bash
# 仅本地测试
export OFFICIAL_IP_WHITELIST="127.0.0.1,::1"
```

### 场景二：公司内网

```bash
# 公司内网 C 段
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
```

### 场景三：多办公室

```bash
# 北京办公室 + 上海办公室
export OFFICIAL_IP_WHITELIST="192.168.10.0/24,192.168.20.0/24"
```

### 场景四：特定服务器

```bash
# 仅允许特定服务器
export OFFICIAL_IP_WHITELIST="192.168.10.100,192.168.10.101"
```

### 场景五：混合环境

```bash
# 本地 + 内网 + 特定服务器
export OFFICIAL_IP_WHITELIST="127.0.0.1,192.168.10.0/24,10.0.5.100"
```

---

## 如何获取当前 IP

### 方法一：命令行

```bash
# Linux/Mac
curl ifconfig.me

# 或
curl ip.sb

# 或查看内网 IP
ifconfig | grep "inet "
ip addr show
```

### 方法二：查看请求日志

启动服务后，上传一个文件，查看日志中的 IP：

```bash
# 查看服务日志
tail -f /var/log/dxf_service.log

# 输出示例
2026-05-27 10:40:00 [INFO] 上传请求来自 IP: 192.168.10.100
```

### 方法三：测试接口

创建一个测试接口查看当前 IP：

```python
@router.get("/debug/my-ip")
async def get_my_ip(request: Request):
    return {
        "ip": request.client.host if request.client else "unknown",
        "headers": dict(request.headers)
    }
```

访问：`http://localhost:8080/template/debug/my-ip`

---

## 验证配置

### 1. 启动服务

```bash
# 设置白名单
export OFFICIAL_IP_WHITELIST="192.168.10.100,192.168.10.0/24"

# 启动服务
NETWORK_MODE=external bash run_qgis_mac.sh
```

### 2. 测试上传

```bash
# 从白名单 IP 上传
curl -F "file=@test.dxf" http://192.168.10.100:8080/template/upload
```

### 3. 检查响应

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "...",
    "is_official": true  // ✅ 应该是 true
  }
}
```

---

## 部署配置示例

### Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12

# 设置环境变量
ENV OFFICIAL_IP_WHITELIST="192.168.10.0/24,10.0.0.0/8"

# ... 其他配置
```

或使用 `docker-compose.yml`：

```yaml
version: '3.8'
services:
  dxf-service:
    image: dxf-template-service
    environment:
      - OFFICIAL_IP_WHITELIST=192.168.10.0/24,10.0.0.0/8
      - NETWORK_MODE=external
    ports:
      - "8080:8080"
```

### Systemd 服务

```ini
# /etc/systemd/system/dxf-service.service
[Unit]
Description=DXF Template Service

[Service]
Type=simple
User=dxf
WorkingDirectory=/opt/dxf-service
Environment="OFFICIAL_IP_WHITELIST=192.168.10.0/24"
Environment="NETWORK_MODE=external"
ExecStart=/usr/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8080

[Install]
WantedBy=multi-user.target
```

### Nginx 反向代理

如果通过 Nginx 代理，需要传递真实 IP：

```nginx
location /template/ {
    proxy_pass http://localhost:8080;
    
    # 传递真实 IP
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

修改代码获取真实 IP：

```python
def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP"""
    # 优先从 X-Forwarded-For 获取
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # 其次从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # 最后使用直连 IP
    return request.client.host if request.client else ""
```

---

## 安全建议

### 1. 最小权限原则

```bash
# ❌ 不推荐：过于宽泛
export OFFICIAL_IP_WHITELIST="0.0.0.0/0"

# ✅ 推荐：仅公司内网
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
```

### 2. 定期审查

```bash
# 每月检查白名单配置
cat /etc/environment | grep OFFICIAL_IP_WHITELIST

# 查看最近的官方上传记录
grep "is_official=True" /var/log/dxf_service.log | tail -20
```

### 3. 监控异常

```python
# 记录所有官方上传的 IP
if is_official:
    LOG.info(f"官方上传: IP={client_ip}, file={filename}")
```

### 4. 组合使用

```bash
# IP 白名单 + API Key 双重保护
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
export OFFICIAL_API_KEY="your_secure_key"
```

---

## 故障排查

### 问题1：配置了白名单，但仍显示 `is_official=false`

**可能原因**：
1. IP 格式错误
2. 通过代理访问，IP 被替换
3. 配置未生效（需重启服务）

**解决方法**：
```bash
# 1. 检查当前 IP
curl http://localhost:8080/template/debug/my-ip

# 2. 检查配置
echo $OFFICIAL_IP_WHITELIST

# 3. 重启服务
systemctl restart dxf-service
```

### 问题2：CIDR 网段不生效

**当前仅支持 /24 网段**，如需其他网段，需修改代码：

```python
# auth_middleware.py
def is_ip_in_whitelist(client_ip: str) -> bool:
    # 添加更多 CIDR 支持
    import ipaddress
    
    for allowed in OFFICIAL_IP_WHITELIST:
        if "/" in allowed:
            network = ipaddress.ip_network(allowed, strict=False)
            if ipaddress.ip_address(client_ip) in network:
                return True
    return False
```

### 问题3：IPv6 不生效

确保配置了 IPv6 地址：

```bash
export OFFICIAL_IP_WHITELIST="::1,fe80::1,2001:db8::/32"
```

---

## 完整示例

### 生产环境配置

```bash
#!/bin/bash
# /opt/dxf-service/start.sh

# 公司内网 IP 段
export OFFICIAL_IP_WHITELIST="192.168.10.0/24,10.0.0.0/8"

# 其他配置
export NETWORK_MODE="external"
export OFFICIAL_API_KEY="backup_key_for_external_access"

# 启动服务
cd /opt/dxf-service
bash run_qgis_mac.sh
```

### 测试脚本

```bash
#!/bin/bash
# test_ip_whitelist.sh

# 测试 IP
TEST_IP="192.168.10.100"

# 上传测试文件
curl -X POST "http://${TEST_IP}:8080/template/upload" \
  -F "file=@test.dxf" \
  -F "name=测试模板" \
  | jq '.data.is_official'

# 预期输出：true
```

---

## 总结

| 配置项 | 说明 | 示例 |
|--------|------|------|
| 单个 IP | 精确匹配 | `192.168.10.100` |
| 多个 IP | 逗号分隔 | `192.168.10.100,192.168.10.101` |
| CIDR /24 | C 段网络 | `192.168.10.0/24` |
| 本地回环 | 开发测试 | `127.0.0.1,::1` |

**优点**：
- ✅ 无需传递任何凭证
- ✅ 自动识别
- ✅ 配置简单

**限制**：
- ❌ 仅适用于固定 IP 环境
- ❌ 需要内网部署或 VPN 访问
