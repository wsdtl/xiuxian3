"""战斗组件。

当前没有单独 WS 命令，只保留战斗服务入口。
探险和对战复用根目录 `combat_core`，不直接引用本组件。
"""

from .service import service as service

__all__ = ["service"]
