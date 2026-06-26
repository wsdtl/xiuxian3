"""修仙服务公开 URL 生成。"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from launch.config import DEFAULT_PUBLIC_HOST, config


def server_uses_https() -> bool:
    """后端 uvicorn 是否按 HTTPS 启动。"""

    return bool(config.server.ssl_certfile and config.server.ssl_keyfile)


def public_base_url() -> str:
    """按当前项目域名、端口和 SSL 配置生成公开访问基地址。"""

    return build_public_base_url(
        config.project.domain,
        config.server.port,
        https_enabled=server_uses_https(),
    )


def public_url(path: str = "") -> str:
    """生成项目公开完整地址。"""

    base = public_base_url()
    value = str(path or "").strip()
    if not value:
        return base
    if value.startswith(("http://", "https://")):
        return value
    return f"{base}/{value.lstrip('/')}"


def build_public_base_url(domain: str | None, port: int | str, *, https_enabled: bool = False) -> str:
    """按传入参数生成公开访问基地址，方便测试不同 .env 组合。"""

    # 公开链接规则：
    # 1. PROJECT_DOMAIN 写了 http:// 或 https:// 时，协议以 PROJECT_DOMAIN 为准。
    # 2. PROJECT_DOMAIN 没写协议时，根据后端 SSL 状态自动选择 http 或 https。
    # 3. PROJECT_DOMAIN 写了端口时，使用显式端口；没写端口时，使用服务运行端口。
    # 4. http:80 和 https:443 隐藏端口，其他端口都保留在链接里。
    default_scheme = "https" if https_enabled else "http"
    value = (domain or DEFAULT_PUBLIC_HOST).strip().rstrip("/")
    if not value:
        value = DEFAULT_PUBLIC_HOST
    if "://" not in value:
        value = f"{default_scheme}://{value}"

    parsed = urlsplit(value)
    scheme = parsed.scheme or default_scheme
    hostname = parsed.hostname or parsed.netloc or DEFAULT_PUBLIC_HOST
    explicit_port = parsed.port
    final_port = str(explicit_port if explicit_port is not None else port).strip()

    host = _format_hostname(hostname)
    netloc = host if _is_default_port(scheme, final_port) else f"{host}:{final_port}"
    path = f"/{parsed.path.strip('/')}" if parsed.path else ""
    return urlunsplit((scheme, netloc, path, "", "")).rstrip("/")


def _format_hostname(hostname: str) -> str:
    """IPv6 地址需要带方括号，普通域名原样返回。"""

    value = hostname.strip()
    if ":" in value and not value.startswith("["):
        return f"[{value}]"
    return value


def _is_default_port(scheme: str, port: str) -> bool:
    """默认端口不展示。"""

    return (scheme == "http" and port == "80") or (scheme == "https" and port == "443")
