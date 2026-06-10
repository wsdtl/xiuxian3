"""修仙帮助组件服务。"""

from __future__ import annotations

from pathlib import Path

from launch import config

from ..common import CoreService
from ..sql import db

HELP_IMAGE = Path(__file__).with_name("help.png")


def _help_page_url() -> str:
    """按 .env 中配置的公开域名生成帮助页地址。"""

    port = str(config.server.port)
    domain = (config.project.domain or "127.0.0.1").strip().rstrip("/")
    base_url = _with_project_port(domain, port)
    return f"{base_url}/xiuxian/help"


def _with_project_port(domain: str, port: str) -> str:
    """生成项目访问基地址；80 端口不展示，其他端口自动展示。"""

    if domain.startswith(("http://", "https://")):
        scheme, rest = domain.split("://", 1)
    else:
        scheme, rest = "http", domain

    host, _, path = rest.partition("/")
    hostname = host
    explicit_port = ""
    if ":" in host and not host.startswith("["):
        hostname, explicit_port = host.rsplit(":", 1)

    final_port = explicit_port or port
    netloc = hostname if final_port == "80" else f"{hostname}:{final_port}"
    suffix = f"/{path.strip('/')}" if path else ""
    return f"{scheme}://{netloc}{suffix}".rstrip("/")


HELP_PAGE_URL = _help_page_url()


class HelpService(CoreService):
    """修仙帮助图片、网页入口和固定导航。"""

    def web_help(self) -> str:
        """返回当前阶段的帮助入口提示。"""

        return f"修仙帮助网页：{HELP_PAGE_URL}\n发送：修仙帮助 查看帮助图，或发送：指南 查看关键入口。"

    def command_guide(self) -> str:
        """返回关键组件跳转按钮。"""

        return "<地图><背包><纳戒><保险箱><商场推荐><探险状态><结束探险><武器><装备><宝石><源库><首领><修仙早报><修仙百科 武器>"


service = HelpService(db)
