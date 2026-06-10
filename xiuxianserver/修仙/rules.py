"""修仙模块通用公式。"""

from __future__ import annotations

from math import floor, sqrt

from .constants import (
    BOOK_RECYCLE_MIN_RATE,
    BOOK_RECYCLE_SINGLE_CAP_BASE,
    BOOK_RECYCLE_SINGLE_CAP_LEVEL_BONUS,
    BOOK_RECYCLE_SOFT_BASE,
    BOOK_RECYCLE_SOFT_LEVEL_BONUS,
    GEM_RECYCLE_MIN_RATE,
    GEM_RECYCLE_SINGLE_CAP_BASE,
    GEM_RECYCLE_SINGLE_CAP_LEVEL_BONUS,
    GEM_RECYCLE_SOFT_BASE,
    GEM_RECYCLE_SOFT_LEVEL_BONUS,
    MAX_LEVEL,
    PLAYER_BASE_ATTACK,
    SPECIAL_SELL_MIN_RATE,
    SPECIAL_SELL_SOFT_BASE,
    SPECIAL_SELL_SOFT_LEVEL_BONUS,
    WEAPON_RECYCLE_MIN_RATE,
    WEAPON_RECYCLE_SINGLE_CAP_BASE,
    WEAPON_RECYCLE_SINGLE_CAP_LEVEL_BONUS,
    WEAPON_RECYCLE_SOFT_BASE,
    WEAPON_RECYCLE_SOFT_LEVEL_BONUS,
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

    # 40 级后进入长期曲线：
    # - 40-60 级只轻微加压，避免中期突然卡死。
    # - 60-80 级开始拉开差距。
    # - 80 级后明显变重，专门压住每日十几次探险的高频玩家。
    progress = (level - 40) / 59
    difficulty = 1 + 8 * (progress**1.35) + 12 * (progress**2.4) + 18 * (progress**4.0)
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


def weapon_recycle_single_cap(level: int) -> int:
    """计算单把武器回收价上限。"""

    return WEAPON_RECYCLE_SINGLE_CAP_BASE + max(1, int(level)) * WEAPON_RECYCLE_SINGLE_CAP_LEVEL_BONUS


def weapon_recycle_soft_line(level: int) -> int:
    """计算武器回收开始明显降价的日收入参考线。"""

    return WEAPON_RECYCLE_SOFT_BASE + max(1, int(level)) * WEAPON_RECYCLE_SOFT_LEVEL_BONUS


def weapon_recycle_price_rate(level: int, today_income: int) -> float:
    """按今日武器回收收入计算当前回收倍率。"""

    soft_line = max(1, weapon_recycle_soft_line(level))
    pressure = max(0, int(today_income)) / soft_line
    rate = 1.0 / (1.0 + pressure * 0.75)
    return max(WEAPON_RECYCLE_MIN_RATE, min(1.0, rate))


def gem_recycle_single_cap(level: int) -> int:
    """计算单颗宝石回收价上限。"""

    return GEM_RECYCLE_SINGLE_CAP_BASE + max(1, int(level)) * GEM_RECYCLE_SINGLE_CAP_LEVEL_BONUS


def gem_recycle_soft_line(level: int) -> int:
    """计算宝石回收开始明显降价的日收入参考线。"""

    return GEM_RECYCLE_SOFT_BASE + max(1, int(level)) * GEM_RECYCLE_SOFT_LEVEL_BONUS


def gem_recycle_price_rate(level: int, today_income: int) -> float:
    """按今日宝石回收收入计算当前回收倍率。"""

    soft_line = max(1, gem_recycle_soft_line(level))
    pressure = max(0, int(today_income)) / soft_line
    rate = 1.0 / (1.0 + pressure * 0.65)
    return max(GEM_RECYCLE_MIN_RATE, min(1.0, rate))


def book_recycle_single_cap(level: int) -> int:
    """计算单本技能书回收价上限。"""

    return BOOK_RECYCLE_SINGLE_CAP_BASE + max(1, int(level)) * BOOK_RECYCLE_SINGLE_CAP_LEVEL_BONUS


def book_recycle_soft_line(level: int) -> int:
    """计算技能书回收开始明显降价的日收入参考线。"""

    return BOOK_RECYCLE_SOFT_BASE + max(1, int(level)) * BOOK_RECYCLE_SOFT_LEVEL_BONUS


def book_recycle_price_rate(level: int, today_income: int) -> float:
    """按今日技能书回收收入计算当前回收倍率。"""

    soft_line = max(1, book_recycle_soft_line(level))
    pressure = max(0, int(today_income)) / soft_line
    rate = 1.0 / (1.0 + pressure * 0.65)
    return max(BOOK_RECYCLE_MIN_RATE, min(1.0, rate))


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
    for need in (10, 25, 40, 60, 80, 95, 100):
        if int(max_level) >= need and int(level) >= need:
            slots += 1
    return slots


def weapon_upgrade_cost(next_level: int, quality_factor: float) -> int:
    """计算武器升级源石。"""

    factor = max(1.0, float(quality_factor))
    quality_cost = max(0.65, (factor**1.55) * 0.78)
    return floor(1500 * (int(next_level) ** 1.6) * quality_cost)


def equipment_upgrade_cost(next_level: int, slot_factor: float) -> int:
    """计算装备升级源石。"""

    return floor(800 * (int(next_level) ** 1.55) * float(slot_factor))


def gem_upgrade_cost(next_level: int) -> int:
    """计算已镶嵌宝石升级源石。

    1-5 级保持平滑铺底，6 级后用立方段拉开长期消耗。
    """

    level = max(1, int(next_level))
    late_level = max(0, level - 5)
    return 5000 * (level**2) + 70000 * (late_level**3)


def page_count(total: int, page_size: int) -> int:
    """计算页数。"""

    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size


__all__ = [
    "base_attack",
    "book_recycle_price_rate",
    "book_recycle_single_cap",
    "book_recycle_soft_line",
    "damage_after_defense",
    "defense",
    "equipment_upgrade_cost",
    "exp_need",
    "gem_upgrade_cost",
    "gem_recycle_price_rate",
    "gem_recycle_single_cap",
    "gem_recycle_soft_line",
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
    "weapon_recycle_price_rate",
    "weapon_recycle_single_cap",
    "weapon_recycle_soft_line",
    "weapon_upgrade_cost",
]
