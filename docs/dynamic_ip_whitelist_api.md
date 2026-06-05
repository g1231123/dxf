# 动态 IP 白名单管理 API

## 概述

提供动态管理 IP 白名单的接口，数据存储在**内存**中，服务重启后自动恢复为配置文件默认值。

**基础路径**: `/admin/ip-whitelist`

**权限要求**: 所有接口需要在请求头中提供 `X-Admin-Key`（与官方上传的 API Key 相同）

---

## 接口列表

### 1. 查询白名单

**GET** `/admin/ip-whitelist/list`

#### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

#### 示例

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  http://localhost:8080/admin/ip-whitelist/list
```

#### 响应

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

### 2. 添加单个 IP

**POST** `/admin/ip-whitelist/add`

#### 请求头

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| X-Admin-Key | string | ✅ | 管理员密钥 |

#### 请求体

```json
{
  "ip": "192.168.10.200"
}
```

#### 示例

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/add \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

#### 响应

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

### 3. 批量添加 IP

**POST** `/admin/ip-whitelist/add-batch`

#### 请求体

```json
{
  "ips": [
    "192.168.10.201",
    "192.168.10.202",
    "192.168.20.0/24"
  ]
}
```

#### 示例

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/add-batch \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{
    "ips": ["192.168.10.201", "192.168.10.202", "192.168.20.0/24"]
  }'
```

#### 响应

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

### 4. 移除 IP

**DELETE** `/admin/ip-whitelist/remove`

#### 请求体

```json
{
  "ip": "192.168.10.200"
}
```

#### 示例

```bash
curl -X DELETE http://localhost:8080/admin/ip-whitelist/remove \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.200"}'
```

#### 响应

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

### 5. 检查 IP

**GET** `/admin/ip-whitelist/check?ip=192.168.10.100`

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ip | string | ✅ | 要检查的 IP |

#### 示例

```bash
curl -H "X-Admin-Key: yuxinda_official_2024" \
  "http://localhost:8080/admin/ip-whitelist/check?ip=192.168.10.100"
```

#### 响应

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

### 6. 重置为默认值

**POST** `/admin/ip-whitelist/reset`

清空所有动态添加的 IP，恢复为配置文件中的默认值。

#### 示例

```bash
curl -X POST http://localhost:8080/admin/ip-whitelist/reset \
  -H "X-Admin-Key: yuxinda_official_2024"
```

#### 响应

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

## 使用场景

### 场景一：临时添加测试 IP

```bash
# 添加测试人员的 IP
curl -X POST http://localhost:8080/admin/ip-whitelist/add \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.250"}'

# 测试完成后移除
curl -X DELETE http://localhost:8080/admin/ip-whitelist/remove \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.250"}'
```

### 场景二：新办公室上线

```bash
# 批量添加新办公室的 IP 段
curl -X POST http://localhost:8080/admin/ip-whitelist/add-batch \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{
    "ips": [
      "192.168.30.0/24",
      "192.168.31.0/24"
    ]
  }'
```

### 场景三：检查某个 IP 是否有权限

```bash
# 检查客户端 IP
curl -H "X-Admin-Key: yuxinda_official_2024" \
  "http://localhost:8080/admin/ip-whitelist/check?ip=192.168.10.100"
```

### 场景四：服务重启后自动恢复

```bash
# 1. 添加临时 IP
curl -X POST http://localhost:8080/admin/ip-whitelist/add \
  -H "X-Admin-Key: yuxinda_official_2024" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.10.250"}'

# 2. 重启服务
systemctl restart dxf-service

# 3. 查询白名单（临时 IP 已消失，恢复为默认值）
curl -H "X-Admin-Key: yuxinda_official_2024" \
  http://localhost:8080/admin/ip-whitelist/list
```

---

## 前端管理界面示例

### React 示例

```jsx
import React, { useState, useEffect } from 'react';

function IPWhitelistManager() {
  const [ips, setIps] = useState([]);
  const [newIp, setNewIp] = useState('');
  const adminKey = process.env.REACT_APP_ADMIN_KEY;

  // 加载白名单
  useEffect(() => {
    fetch('/admin/ip-whitelist/list', {
      headers: { 'X-Admin-Key': adminKey }
    })
      .then(res => res.json())
      .then(data => setIps(data.data.ips));
  }, []);

  // 添加 IP
  const handleAdd = async () => {
    const response = await fetch('/admin/ip-whitelist/add', {
      method: 'POST',
      headers: {
        'X-Admin-Key': adminKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ip: newIp })
    });
    
    if (response.ok) {
      setIps([...ips, newIp]);
      setNewIp('');
    }
  };

  // 移除 IP
  const handleRemove = async (ip) => {
    await fetch('/admin/ip-whitelist/remove', {
      method: 'DELETE',
      headers: {
        'X-Admin-Key': adminKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ip })
    });
    
    setIps(ips.filter(i => i !== ip));
  };

  return (
    <div>
      <h2>IP 白名单管理</h2>
      
      <div>
        <input 
          value={newIp} 
          onChange={e => setNewIp(e.target.value)}
          placeholder="输入 IP 或 CIDR"
        />
        <button onClick={handleAdd}>添加</button>
      </div>

      <ul>
        {ips.map(ip => (
          <li key={ip}>
            {ip}
            <button onClick={() => handleRemove(ip)}>移除</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## Python 管理脚本

```python
#!/usr/bin/env python3
"""IP 白名单管理脚本"""
import requests
import sys

class IPWhitelistManager:
    def __init__(self, base_url, admin_key):
        self.base_url = base_url
        self.headers = {'X-Admin-Key': admin_key}
    
    def list(self):
        """查询白名单"""
        r = requests.get(f'{self.base_url}/admin/ip-whitelist/list', 
                        headers=self.headers)
        return r.json()
    
    def add(self, ip):
        """添加 IP"""
        r = requests.post(f'{self.base_url}/admin/ip-whitelist/add',
                         headers=self.headers,
                         json={'ip': ip})
        return r.json()
    
    def remove(self, ip):
        """移除 IP"""
        r = requests.delete(f'{self.base_url}/admin/ip-whitelist/remove',
                           headers=self.headers,
                           json={'ip': ip})
        return r.json()
    
    def check(self, ip):
        """检查 IP"""
        r = requests.get(f'{self.base_url}/admin/ip-whitelist/check',
                        headers=self.headers,
                        params={'ip': ip})
        return r.json()

# 使用示例
if __name__ == '__main__':
    manager = IPWhitelistManager(
        'http://localhost:8080',
        'yuxinda_official_2024'
    )
    
    if len(sys.argv) < 2:
        print("用法: python manage_ip.py [list|add|remove|check] [ip]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'list':
        result = manager.list()
        print(f"当前白名单 ({result['data']['total']} 个):")
        for ip in result['data']['ips']:
            print(f"  - {ip}")
    
    elif cmd == 'add' and len(sys.argv) > 2:
        ip = sys.argv[2]
        result = manager.add(ip)
        print(f"添加成功: {ip}")
    
    elif cmd == 'remove' and len(sys.argv) > 2:
        ip = sys.argv[2]
        result = manager.remove(ip)
        print(f"移除成功: {ip}")
    
    elif cmd == 'check' and len(sys.argv) > 2:
        ip = sys.argv[2]
        result = manager.check(ip)
        print(f"IP: {ip}")
        print(f"在白名单中: {result['data']['in_whitelist']}")
        if result['data']['matched_rule']:
            print(f"匹配规则: {result['data']['matched_rule']}")
```

使用：
```bash
# 查询
python manage_ip.py list

# 添加
python manage_ip.py add 192.168.10.250

# 移除
python manage_ip.py remove 192.168.10.250

# 检查
python manage_ip.py check 192.168.10.100
```

---

## 安全建议

1. **保护管理接口**
   - 仅在内网开放
   - 或通过 Nginx 限制访问

2. **定期审计**
   ```bash
   # 每天检查白名单
   curl -H "X-Admin-Key: xxx" http://localhost:8080/admin/ip-whitelist/list
   ```

3. **重要 IP 写入配置文件**
   ```bash
   # 临时 IP 用动态接口
   # 长期 IP 写入 config.py
   export OFFICIAL_IP_WHITELIST="192.168.10.0/24,192.168.20.0/24"
   ```

---

## 总结

| 特性 | 说明 |
|------|------|
| 存储方式 | 内存（不持久化） |
| 初始值 | 配置文件默认值 |
| 重启后 | 自动恢复默认值 |
| 权限 | 需要 X-Admin-Key |
| 适用场景 | 临时授权、测试环境 |
