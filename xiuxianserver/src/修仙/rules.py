"""修仙模块通用公式。"""

from __future__ import annotations

from math import floor, sqrt

from .constants import (
    MAX_LEVEL,
    PLAYER_BASE_ATTACK,
    SPECIAL_SELL_MIN_RATE,
    SPECIAL_SELL_SOFT_BASE,
    SPECIAL_SELL_SOFT_LEVEL_BONUS,
)


def money(value: int) -> str:
    """把源石数量转成稳定文本。"""

    return f"{max(0, int(value)):,}".replace(",", "")


def exp_need(level: int) -> int:
    """计算当前等级升到下一级需要的经验。"""

    level = max(1, min(MAX_LEVEL, int(level)))
    if level >= MAX_LEVEL:
        return 0
    base_need = floor(120 * (level**1.85) + 600 * level)
    if level <= 40:
        return base_need

    # 40 级后平滑加难，压住高强度在线冲级，但不做突然断崖。
    progress = (level - 40) / 59
    difficulty = 1 + 0.4 * (progress**1.25)
    return floor(base_need * difficulty)


def level_from_exp(exp: int) -> int:
    """按累计经验计算等级。"""

    level = 1
    left = max(0, int(exp))
    while level < MAX_LEVEL:
        need = exp_need(level)
        if left < need:
            break
        left -= need
        level += 1
    return level


def max_hp(level: int, physique: int, equipment_bonus: int = 0) -> int:
    """计算血气上限。"""

    return 100 + int(level) * 12 + int(physique) * 8 + int(equipment_bonus)


def max_mp(level: int, equipment_bonus: int = 0) -> int:
    """计算精神上限。"""

    return 60 + int(level) * 6 + int(equipment_bonus)


def base_attack(level: int) -> int:
    """计算人物低基础攻击。"""

    return PLAYER_BASE_ATTACK + floor(int(level) / 10)


def defense(level: int, physique: int, equipment_bonus: int = 0) -> int:
    """计算防御。"""

    return int(level) + int(physique) * 2 + int(equipment_bonus)


def sign_reward(level: int) -> int:
    """计算每日签到源石。"""

    return min(500 + int(level) * 30, 5_000)


def special_sell_soft_line(level: int) -> int:
    """计算特殊收购开始明显降价的参考线。"""

    return SPECIAL_SELL_SOFT_BASE + max(1, int(level)) * SPECIAL_SELL_SOFT_LEVEL_BONUS


def special_sell_price_rate(level: int, today_income: int) -> float:
    """按今日特殊出售收入计算当前收购价倍率。

    不做硬限制，玩家一直可以卖；只是卖得越多，后续价格越低。
    """

    soft_line = max(1, special_sell_soft_line(level))
    pressure = max(0, int(today_income)) / soft_line
    rate = 1.0 / (1.0 + pressure * 0.45)
    return max(SPECIAL_SELL_MIN_RATE, min(1.0, rate))


def monster_exp(monster_level: int, kind_factor: float = 1.0, player_level: int | None = None) -> int:
    """计算怪物经验。"""

    base = 80 + int(monster_level) * 22
    return int(base * monster_exp_rate(monster_level, player_level) * kind_factor)


def monster_exp_rate(monster_level: int, player_level: int | None) -> float:
    """按玩家和怪物等级差计算经验倍率。

    平级是 1.0；越级打怪奖励更高；高等级刷低级怪会明显衰减。
    """

    if player_level is None:
        return 1.0

    diff = int(monster_level) - int(player_level)
    if diff == 0:
        return 1.0
    if diff > 0:
        return min(2.0, 1.0 + diff * 0.1)
    return max(0.15, 1.0 + diff * 0.08)


def damage_after_defense(raw_damage: int, defense_value: int, pierce_rate: float = 0.0) -> int:
    """按防御公式计算最终伤害。"""

    raw_damage = max(1, int(raw_damage))
    effective_defense = max(0.0, float(defense_value) * (1.0 - max(0.0, min(0.9, pierce_rate))))
    flat_reduce = min(effective_defense * 0.2, raw_damage * 0.5)
    middle_damage = raw_damage - flat_reduce
    reduction_rate = effective_defense / (effective_defense + 300 + 30 * sqrt(effective_defense))
    reduction_rate = min(0.6, reduction_rate)
    return max(1, int(middle_damage * (1 - reduction_rate)))


def weapon_enchant_slots(max_level: int, level: int) -> int:
    """按武器上限和当前等级计算已解锁附魔栏。"""

    slots = 0
    for need in (20, 40, 60, 80, 100):
        if int(max_level) >= need and int(level) >= need:
            slots += 1
    return slots


def weapon_upgrade_cost(next_level: int, quality_factor: float) -> int:
    """计算武器升级源石。"""

    return floor(1500 * (int(next_level) ** 1.6) * float(quality_factor))


def equipment_upgrade_cost(next_level: int, slot_factor: float) -> int:
    """计算固定装备升级源石。"""

    return floor(800 * (int(next_level) ** 1.55) * float(slot_factor))


def page_count(total: int, page_size: int) -> int:
    """计算页数。"""

    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size


__all__ = [
    "base_attack",
    "damage_after_defense",
    "defense",
    "equipment_upgrade_cost",
    "exp_need",
    "level_from_exp",
    "max_hp",
    "max_mp",
    "money",
    "monster_exp",
    "monster_exp_rate",
    "page_count",
    "sign_reward",
    "special_sell_price_rate",
    "special_sell_soft_line",
    "weapon_enchant_slots",
    "weapon_upgrade_cost",
]
