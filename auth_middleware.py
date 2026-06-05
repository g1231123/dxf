"""
官方上传认证中间件
支持多种认证方式：IP 白名单、签名验证、API Key
"""
import hashlib
import hmac
import time
from typing import Optional
from fastapi import Request, HTTPException
from config import OFFICIAL_API_KEY
import os


# 动态 IP 白名单将从 ip_whitelist_manager 获取
# 这里仅作为初始化参考
from config import OFFICIAL_IP_WHITELIST as IP_WHITELIST_STR

# 签名密钥（用于时间戳签名）
SIGNATURE_SECRET = os.environ.get("SIGNATURE_SECRET", "yuxinda_secret_2024")

# 签名有效期（秒）
SIGNATURE_EXPIRY = int(os.environ.get("SIGNATURE_EXPIRY", "300"))  # 5分钟


def is_ip_in_whitelist(client_ip: str) -> bool:
    """
    检查 IP 是否在白名单中（使用动态白名单）
    支持单个 IP 和 CIDR 格式
    """
    if not client_ip:
        return False
    
    # 从动态白名单管理器获取当前白名单
    try:
        from ip_whitelist_manager import get_dynamic_whitelist
        whitelist = get_dynamic_whitelist()
    except ImportError:
        # 如果管理器未加载，使用配置文件默认值
        whitelist = set(ip.strip() for ip in IP_WHITELIST_STR.split(",") if ip.strip())
    
    for allowed in whitelist:
        allowed = allowed.strip()
        
        # 精确匹配
        if client_ip == allowed:
            return True
        
        # CIDR 匹配（简化版，仅支持 /24）
        if "/" in allowed:
            network, prefix = allowed.rsplit("/", 1)
            if prefix == "24":
                # 匹配前三段
                if ".".join(client_ip.split(".")[:3]) == ".".join(network.split(".")[:3]):
                    return True
    
    return False


def verify_signature(timestamp: str, signature: str, file_hash: str = "") -> bool:
    """
    验证时间戳签名
    
    签名算法：HMAC-SHA256(secret, timestamp + file_hash)
    """
    if not timestamp or not signature:
        return False
    
    try:
        # 检查时间戳是否过期
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > SIGNATURE_EXPIRY:
            return False
        
        # 计算签名
        message = f"{timestamp}{file_hash}"
        expected_signature = hmac.new(
            SIGNATURE_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 防止时序攻击
        return hmac.compare_digest(signature, expected_signature)
    except (ValueError, TypeError):
        return False


def check_official_auth(request: Request, x_api_key: Optional[str] = None) -> bool:
    """
    综合认证检查
    
    认证方式（满足任一即可）：
    1. IP 白名单
    2. API Key
    3. 时间戳签名
    
    返回：是否为官方上传
    """
    # 方式1：IP 白名单
    client_ip = request.client.host if request.client else None
    if client_ip and is_ip_in_whitelist(client_ip):
        return True
    
    # 方式2：API Key
    if x_api_key and x_api_key == OFFICIAL_API_KEY:
        return True
    
    # 方式3：时间戳签名
    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")
    if timestamp and signature:
        # 可选：文件哈希（用于防止重放攻击）
        file_hash = request.headers.get("X-File-Hash", "")
        if verify_signature(timestamp, signature, file_hash):
            return True
    
    return False


def generate_signature(timestamp: Optional[int] = None, file_hash: str = "") -> tuple:
    """
    生成签名（供客户端使用）
    
    返回：(timestamp, signature)
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    message = f"{timestamp}{file_hash}"
    signature = hmac.new(
        SIGNATURE_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return str(timestamp), signature
