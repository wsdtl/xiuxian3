"""修仙模块基础数值。

这里只放全局常量。玩法逻辑写在各组件 service.py，避免根目录反向依赖子组件。
"""

from __future__ import annotations


SCHEMA_VERSION = 2026052212
DAY_RESET_HOUR = 4
MAX_LEVEL = 100
REST_MINUTES = 1


# ----------------------------
# 玩家
# ----------------------------


DEFAULT_LOCATION = "天枢城"
DEFAULT_BACKPACK_LIMIT = 80
DEFAULT_WEIGHT_LIMIT = 500
RENAME_COOLDOWN_HOURS = 24
NEWBIE_GIFT_STONES = 10_000


# ----------------------------
# 源库
# ----------------------------


BANK_LEVELS = {
    1: {"name": "一星", "limit": 100_000, "cost": 0, "daily_interest_limit": 120, "hour_rate": 0.00003},
    2: {"name": "二星", "limit": 300_000, "cost": 50_000, "daily_interest_limit": 360, "hour_rate": 0.00004},
    3: {"name": "三星", "limit": 800_000, "cost": 180_000, "daily_interest_limit": 960, "hour_rate": 0.00005},
    4: {"name": "四星", "limit": 2_000_000, "cost": 600_000, "daily_interest_limit": 2_400, "hour_rate": 0.00006},
    5: {"name": "五星", "limit": 5_000_000, "cost": 1_800_000, "daily_interest_limit": 6_000, "hour_rate": 0.00007},
    6: {"name": "六星", "limit": 12_000_000, "cost": 5_000_000, "daily_interest_limit": 14_400, "hour_rate": 0.00008},
    7: {"name": "七星", "limit": 30_000_000, "cost": 15_000_000, "daily_interest_limit": 36_000, "hour_rate": 0.00009},
}
BANK_MAX_LEVEL = 7


# ----------------------------
# 商场 / 市场
# ----------------------------


MARKET_FEE_RATE = 0.05
TRADE_BUY_FEE_RATE = 0.01
TRADE_SELL_FEE_RATE = 0.02
TRADE_RESALE_LOCK_HOURS = 4
TRADE_MAX_PROFIT_RATE = 0.45
SPECIAL_SELL_SOFT_BASE = 50_000
SPECIAL_SELL_SOFT_LEVEL_BONUS = 15_000
SPECIAL_SELL_MIN_RATE = 0.35

FIXED_EQUIPMENT_SLOT_FACTORS = {
    "头部": 1.0,
    "左手": 0.9,
    "右手": 0.9,
    "左脚": 0.8,
    "右脚": 0.8,
    "饰品": 1.2,
    "护甲": 1.5,
}


# ----------------------------
# 探险 / 战斗
# ----------------------------


EXPLORE_MINUTES = 30
ENCOUNTER_SECONDS = 90
MAX_COMBAT_ROUNDS = 40
PLAYER_BASE_ATTACK = 5


EQUIPMENT_SLOTS = ("头部", "左手", "右手", "左脚", "右脚", "饰品", "护甲")


__all__ = [
    "BANK_LEVELS",
    "BANK_MAX_LEVEL",
    "DAY_RESET_HOUR",
    "DEFAULT_BACKPACK_LIMIT",
    "DEFAULT_LOCATION",
    "DEFAULT_WEIGHT_LIMIT",
    "ENCOUNTER_SECONDS",
    "EQUIPMENT_SLOTS",
    "EXPLORE_MINUTES",
    "FIXED_EQUIPMENT_SLOT_FACTORS",
    "MARKET_FEE_RATE",
    "MAX_COMBAT_ROUNDS",
    "MAX_LEVEL",
    "NEWBIE_GIFT_STONES",
    "PLAYER_BASE_ATTACK",
    "RENAME_COOLDOWN_HOURS",
    "REST_MINUTES",
    "SCHEMA_VERSION",
    "SPECIAL_SELL_MIN_RATE",
    "SPECIAL_SELL_SOFT_BASE",
    "SPECIAL_SELL_SOFT_LEVEL_BONUS",
    "TRADE_BUY_FEE_RATE",
    "TRADE_MAX_PROFIT_RATE",
    "TRADE_RESALE_LOCK_HOURS",
    "TRADE_SELL_FEE_RATE",
]
