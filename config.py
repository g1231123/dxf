"""
配置文件 - MinIO 和 MySQL 连接配置
支持内网/外网切换，通过环境变量 NETWORK_MODE 控制：
  - internal: 内网模式（默认）
  - external: 外网模式
"""
import os

# 网络模式: internal(内网) / external(外网)
NETWORK_MODE = os.environ.get("NETWORK_MODE", "internal")

# MinIO 内外网配置
MINIO_INTERNAL = {
    "endpoint": "192.168.10.4:9000",
    "secure": False,  # 内网 HTTP
}
MINIO_EXTERNAL = {
    "endpoint": "database.yuxindazhineng.com",
    "secure": True,  # 外网 HTTPS
}

# MySQL 内外网配置
MYSQL_INTERNAL = {
    "host": "192.168.10.4",
    "port": 3306,
}
MYSQL_EXTERNAL = {
    "host": "www.yuxindazhineng.com",
    "port": 3306,
}

# 根据网络模式选择配置
_minio_net = MINIO_EXTERNAL if NETWORK_MODE == "external" else MINIO_INTERNAL
_mysql_net = MYSQL_EXTERNAL if NETWORK_MODE == "external" else MYSQL_INTERNAL

# MinIO 配置
MINIO_CONFIG = {
    "endpoint": os.environ.get("MINIO_ENDPOINT", _minio_net["endpoint"]),
    "access_key": os.environ.get("MINIO_ACCESS_KEY", "yuxinda_admin"),
    "secret_key": os.environ.get("MINIO_SECRET_KEY", "yuxinda_admin01"),
    "bucket_name": os.environ.get("MINIO_BUCKET", "team-bucket"),
    "secure": _minio_net["secure"],
    # 文件访问URL（外网访问地址）
    "public_url": os.environ.get("MINIO_PUBLIC_URL", "http://database.yuxindazhineng.com"),
}

# MySQL 配置
MYSQL_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", _mysql_net["host"]),
    "port": int(os.environ.get("MYSQL_PORT", str(_mysql_net["port"]))),
    "database": os.environ.get("MYSQL_DATABASE", "draw_design"),
    "user": os.environ.get("MYSQL_USER", "yxdzn"),
    "password": os.environ.get("MYSQL_PASSWORD", "Zn@2024#Safe"),
    "charset": "utf8mb4",
}

# 官方 API Key（用于标识官方上传）
OFFICIAL_API_KEY = os.environ.get("OFFICIAL_API_KEY", "yuxinda_official_2024")

# 官方 IP 白名单（用于自动识别官方上传）
# 支持格式：单个IP、CIDR网段，用逗号分隔
# 示例：127.0.0.1,192.168.10.100,192.168.10.0/24,10.0.0.0/8
OFFICIAL_IP_WHITELIST = os.environ.get(
    "OFFICIAL_IP_WHITELIST",
    "127.0.0.1,::1"  # 默认仅本地，生产环境需配置公司内网IP
)

# 获取 MySQL 连接 URL
def get_mysql_url() -> str:
    cfg = MYSQL_CONFIG
    return f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset={cfg['charset']}"


def get_file_public_url(object_name: str) -> str:
    """获取文件的公网访问URL"""
    public_url = MINIO_CONFIG["public_url"].rstrip("/")
    bucket = MINIO_CONFIG["bucket_name"]
    return f"{public_url}/{bucket}/{object_name}"
