"""
动态 IP 白名单管理
数据存储在内存中，服务重启后重置为配置文件中的默认值
"""
import logging
from typing import List, Set
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from config import OFFICIAL_IP_WHITELIST, OFFICIAL_API_KEY

LOG = logging.getLogger("ip_whitelist_manager")

# 创建路由
router = APIRouter(prefix="/admin/ip-whitelist", tags=["IP Whitelist Management"])

# 内存中的动态白名单（初始化为配置文件中的值）
_dynamic_whitelist: Set[str] = set(
    ip.strip() for ip in OFFICIAL_IP_WHITELIST.split(",") if ip.strip()
)


class IPWhitelistRequest(BaseModel):
    """IP 白名单请求模型"""
    ip: str


class IPWhitelistBatchRequest(BaseModel):
    """批量 IP 白名单请求模型"""
    ips: List[str]


def get_dynamic_whitelist() -> Set[str]:
    """获取当前动态白名单"""
    return _dynamic_whitelist.copy()


def verify_admin_key(x_admin_key: str = None) -> bool:
    """验证管理员权限"""
    if not x_admin_key or x_admin_key != OFFICIAL_API_KEY:
        raise HTTPException(403, "无权限操作，需要提供正确的 X-Admin-Key")
    return True


@router.get("/list")
async def list_whitelist(x_admin_key: str = Header(None)):
    """
    查询当前 IP 白名单
    
    需要管理员权限（X-Admin-Key）
    """
    verify_admin_key(x_admin_key)
    
    return {
        "code": 0,
        "message": "查询成功",
        "data": {
            "total": len(_dynamic_whitelist),
            "ips": sorted(list(_dynamic_whitelist)),
            "note": "内存存储，服务重启后恢复为配置文件默认值"
        }
    }


@router.post("/add")
async def add_ip(request: IPWhitelistRequest, x_admin_key: str = Header(None)):
    """
    添加 IP 到白名单
    
    支持格式：
    - 单个 IP: 192.168.10.100
    - CIDR 网段: 192.168.10.0/24
    """
    verify_admin_key(x_admin_key)
    
    ip = request.ip.strip()
    if not ip:
        raise HTTPException(400, "IP 不能为空")
    
    if ip in _dynamic_whitelist:
        return {
            "code": 0,
            "message": "IP 已存在",
            "data": {"ip": ip}
        }
    
    _dynamic_whitelist.add(ip)
    LOG.info(f"添加 IP 到白名单: {ip}")
    
    return {
        "code": 0,
        "message": "添加成功",
        "data": {
            "ip": ip,
            "total": len(_dynamic_whitelist)
        }
    }


@router.post("/add-batch")
async def add_batch_ips(request: IPWhitelistBatchRequest, x_admin_key: str = Header(None)):
    """
    批量添加 IP 到白名单
    """
    verify_admin_key(x_admin_key)
    
    added = []
    existed = []
    
    for ip in request.ips:
        ip = ip.strip()
        if not ip:
            continue
        
        if ip in _dynamic_whitelist:
            existed.append(ip)
        else:
            _dynamic_whitelist.add(ip)
            added.append(ip)
            LOG.info(f"批量添加 IP: {ip}")
    
    return {
        "code": 0,
        "message": "批量添加完成",
        "data": {
            "added": added,
            "existed": existed,
            "total": len(_dynamic_whitelist)
        }
    }


@router.delete("/remove")
async def remove_ip(request: IPWhitelistRequest, x_admin_key: str = Header(None)):
    """
    从白名单中移除 IP
    """
    verify_admin_key(x_admin_key)
    
    ip = request.ip.strip()
    if not ip:
        raise HTTPException(400, "IP 不能为空")
    
    if ip not in _dynamic_whitelist:
        raise HTTPException(404, f"IP 不在白名单中: {ip}")
    
    _dynamic_whitelist.remove(ip)
    LOG.info(f"从白名单移除 IP: {ip}")
    
    return {
        "code": 0,
        "message": "移除成功",
        "data": {
            "ip": ip,
            "total": len(_dynamic_whitelist)
        }
    }


@router.post("/clear")
async def clear_whitelist(x_admin_key: str = Header(None)):
    """
    清空白名单（保留配置文件中的默认值）
    """
    verify_admin_key(x_admin_key)
    
    # 重置为配置文件默认值
    global _dynamic_whitelist
    old_count = len(_dynamic_whitelist)
    _dynamic_whitelist = set(
        ip.strip() for ip in OFFICIAL_IP_WHITELIST.split(",") if ip.strip()
    )
    
    LOG.warning(f"白名单已重置为默认值，原有 {old_count} 个，现有 {len(_dynamic_whitelist)} 个")
    
    return {
        "code": 0,
        "message": "已重置为配置文件默认值",
        "data": {
            "old_count": old_count,
            "current_count": len(_dynamic_whitelist),
            "default_ips": sorted(list(_dynamic_whitelist))
        }
    }


@router.post("/reset")
async def reset_to_default(x_admin_key: str = Header(None)):
    """
    重置为配置文件默认值（同 clear）
    """
    return await clear_whitelist(x_admin_key)


@router.get("/check")
async def check_ip(ip: str, x_admin_key: str = Header(None)):
    """
    检查某个 IP 是否在白名单中
    """
    verify_admin_key(x_admin_key)
    
    from auth_middleware import is_ip_in_whitelist
    
    in_whitelist = is_ip_in_whitelist(ip)
    
    return {
        "code": 0,
        "message": "检查完成",
        "data": {
            "ip": ip,
            "in_whitelist": in_whitelist,
            "matched_rule": _find_matched_rule(ip) if in_whitelist else None
        }
    }


def _find_matched_rule(ip: str) -> str:
    """查找匹配的规则"""
    # 精确匹配
    if ip in _dynamic_whitelist:
        return ip
    
    # CIDR 匹配
    for rule in _dynamic_whitelist:
        if "/" in rule:
            network, prefix = rule.rsplit("/", 1)
            if prefix == "24":
                if ".".join(ip.split(".")[:3]) == ".".join(network.split(".")[:3]):
                    return rule
    
    return "unknown"
