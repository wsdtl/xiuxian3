"""战斗组件服务。"""

from __future__ import annotations

from ..combat_core import CombatCore
from ..sql import db


class CombatService(CombatCore):
    """保留战斗组件入口，具体结算在根目录 combat_core。"""


service = CombatService(db)

__all__ = ["CombatService", "service"]
