# 官方上传安全认证方案

## 三重认证机制

支持以下三种认证方式，**满足任一即可**标记为官方上传：

### 1. IP 白名单（最简单）
### 2. API Key（适中）
### 3. 时间戳签名（最安全）

---

## 方案一：IP 白名单

### 适用场景
- 公司内网固定 IP
- 部署在同一内网环境

### 配置

```bash
# 设置白名单（支持单个 IP 和 CIDR）
export OFFICIAL_IP_WHITELIST="192.168.10.100,192.168.10.0/24,10.0.0.0/24"
```

### 工作原理

```
1. 请求到达服务器
2. 检查客户端 IP
3. 如果在白名单内 → is_official = true
4. 否则 → is_official = false
```

### 优点
- ✅ 无需传递任何凭证
- ✅ 自动识别
- ✅ 配置简单

### 缺点
- ❌ 仅适用于固定 IP 环境
- ❌ 无法用于公网部署

---

## 方案二：API Key

### 适用场景
- 通过公司后端服务调用
- 需要跨网络访问

### 配置

```bash
export OFFICIAL_API_KEY="your_secure_random_key_here"
```

### 使用示例

```bash
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-API-Key: your_secure_random_key_here" \
  -F "file=@official.dxf"
```

### 后端集成（Node.js）

```javascript
const response = await fetch('http://dxf-service:8080/template/upload', {
  method: 'POST',
  headers: {
    'X-API-Key': process.env.OFFICIAL_API_KEY  // 从环境变量读取
  },
  body: formData
});
```

### 优点
- ✅ 简单易用
- ✅ 适用于任何网络环境
- ✅ 可随时更换 Key

### 缺点
- ❌ 如果 Key 泄露，需要更换
- ❌ 无法防止重放攻击

---

## 方案三：时间戳签名（推荐）

### 适用场景
- 高安全要求
- 需要防止重放攻击
- 公网环境

### 配置

```bash
export SIGNATURE_SECRET="your_signature_secret_key"
export SIGNATURE_EXPIRY="300"  # 签名有效期（秒）
```

### 签名算法

```
signature = HMAC-SHA256(secret, timestamp + file_hash)
```

### 使用示例

#### 1. 生成签名（Python）

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
timestamp, signature = generate_signature("your_signature_secret_key")
```

#### 2. 发送请求

```bash
curl -X POST "http://localhost:8080/template/upload" \
  -H "X-Timestamp: 1716782400" \
  -H "X-Signature: a1b2c3d4e5f6..." \
  -F "file=@official.dxf"
```

#### 3. 后端集成（Node.js）

```javascript
const crypto = require('crypto');

function generateSignature(secret, fileHash = '') {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const message = timestamp + fileHash;
  const signature = crypto
    .createHmac('sha256', secret)
    .update(message)
    .digest('hex');
  return { timestamp, signature };
}

// 使用
const { timestamp, signature } = generateSignature(process.env.SIGNATURE_SECRET);

const response = await fetch('http://dxf-service:8080/template/upload', {
  method: 'POST',
  headers: {
    'X-Timestamp': timestamp,
    'X-Signature': signature
  },
  body: formData
});
```

### 防重放攻击（可选）

添加文件哈希到签名中：

```javascript
const crypto = require('crypto');
const fs = require('fs');

// 计算文件哈希
const fileBuffer = fs.readFileSync('official.dxf');
const fileHash = crypto.createHash('sha256').update(fileBuffer).digest('hex');

// 生成签名（包含文件哈希）
const { timestamp, signature } = generateSignature(process.env.SIGNATURE_SECRET, fileHash);

const response = await fetch('http://dxf-service:8080/template/upload', {
  method: 'POST',
  headers: {
    'X-Timestamp': timestamp,
    'X-Signature': signature,
    'X-File-Hash': fileHash  // 可选，用于防重放
  },
  body: formData
});
```

### 优点
- ✅ 最高安全性
- ✅ 防止重放攻击
- ✅ 签名自动过期
- ✅ 无需存储 API Key

### 缺点
- ❌ 实现稍复杂
- ❌ 需要时间同步

---

## 组合使用（推荐）

三种方式可以同时启用，**满足任一即可**：

```bash
# 环境变量配置
export OFFICIAL_IP_WHITELIST="192.168.10.0/24"
export OFFICIAL_API_KEY="api_key_for_backup"
export SIGNATURE_SECRET="signature_secret_for_high_security"
export SIGNATURE_EXPIRY="300"
```

### 认证流程

```
1. 检查 IP 白名单 → 通过 ✅
   ↓ 不通过
2. 检查 API Key → 通过 ✅
   ↓ 不通过
3. 检查时间戳签名 → 通过 ✅
   ↓ 不通过
4. is_official = false（用户上传）
```

---

## 安全建议

### 1. 密钥管理
```bash
# 生成强随机密钥
openssl rand -hex 32

# 使用环境变量，不要硬编码
export OFFICIAL_API_KEY="$(openssl rand -hex 32)"
export SIGNATURE_SECRET="$(openssl rand -hex 32)"
```

### 2. 定期轮换
- API Key：每月更换
- Signature Secret：每季度更换

### 3. 监控审计
```python
# 记录所有官方上传
LOG.info("官方上传: id=%s, ip=%s, method=%s", 
         template_id, client_ip, auth_method)
```

### 4. 限流保护
```python
# 限制上传频率
from fastapi_limiter import RateLimiter

@router.post("/upload")
@RateLimiter(times=10, seconds=60)  # 每分钟最多10次
async def upload_dxf_template(...):
    ...
```

---

## 完整示例

### Python 客户端

```python
import requests
import hmac
import hashlib
import time

class OfficialUploader:
    def __init__(self, base_url, secret):
        self.base_url = base_url
        self.secret = secret
    
    def upload(self, file_path, name=None):
        # 生成签名
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode(),
            timestamp.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 上传
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'name': name} if name else {}
            headers = {
                'X-Timestamp': timestamp,
                'X-Signature': signature
            }
            
            response = requests.post(
                f'{self.base_url}/template/upload',
                files=files,
                data=data,
                headers=headers
            )
            return response.json()

# 使用
uploader = OfficialUploader(
    'http://localhost:8080',
    'your_signature_secret_key'
)
result = uploader.upload('official_template.dxf', '官方标准模板')
print(result)
```

### Node.js 客户端

```javascript
const crypto = require('crypto');
const FormData = require('form-data');
const fs = require('fs');
const fetch = require('node-fetch');

class OfficialUploader {
  constructor(baseUrl, secret) {
    this.baseUrl = baseUrl;
    this.secret = secret;
  }

  generateSignature() {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const signature = crypto
      .createHmac('sha256', this.secret)
      .update(timestamp)
      .digest('hex');
    return { timestamp, signature };
  }

  async upload(filePath, name) {
    const { timestamp, signature } = this.generateSignature();
    
    const formData = new FormData();
    formData.append('file', fs.createReadStream(filePath));
    if (name) formData.append('name', name);

    const response = await fetch(`${this.baseUrl}/template/upload`, {
      method: 'POST',
      headers: {
        'X-Timestamp': timestamp,
        'X-Signature': signature,
        ...formData.getHeaders()
      },
      body: formData
    });

    return await response.json();
  }
}

// 使用
const uploader = new OfficialUploader(
  'http://localhost:8080',
  process.env.SIGNATURE_SECRET
);

uploader.upload('official_template.dxf', '官方标准模板')
  .then(result => console.log(result));
```

---

## 总结对比

| 方案 | 安全性 | 复杂度 | 适用场景 |
|------|--------|--------|----------|
| IP 白名单 | ⭐⭐⭐ | ⭐ | 内网固定 IP |
| API Key | ⭐⭐⭐⭐ | ⭐⭐ | 后端服务调用 |
| 时间戳签名 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 高安全要求 |

**推荐组合**：IP 白名单（内网自动） + 时间戳签名（外网高安全）
