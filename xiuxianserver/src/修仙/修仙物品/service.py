"""修仙物品详情服务。"""

from __future__ import annotations

from ..common import CoreService, format_effect, hint, load_json
from ..sql import db


class TreasureService(CoreService):
    """查询修仙物品定义。

    玩家真正的存储只有两个：
    - 背包：存放占负重的普通物品。
    - 纳戒：存放不占负重的恢复类、宝石和技能书。

    这里查的是“定义资料”，不是玩家库存：
    背包物品、纳戒物品、武器模板、武器自带技能、附魔效果、体质资料都能查。
    """

    def info(self, client_id: str, item_name: str) -> str:
        """查看任意修仙物品说明。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        name = item_name.strip()
        if not name:
            return hint("缺少物品名称。", "发送：查看修仙物品 福袋")

        item = self.item_def_by_name(name)
        if item:
            return self._backpack_item_text(item)

        item = self.equipment_item_def_by_name(name)
        if item:
            return self._ring_item_text(item)

        weapon = self._weapon_def_by_name(name)
        if weapon:
            return self._weapon_text(weapon)

        skill = self._weapon_skill_by_name(name)
        if skill:
            return self._weapon_skill_text(skill)

        enchant = self._weapon_enchant_by_name(name)
        if enchant:
            return self._weapon_enchant_text(enchant)

        physique = self._physique_by_name(name)
        if physique:
            return self._physique_text(physique)

        return hint(
            f"没有找到修仙物品：{name}。",
            "发送：背包、纳戒、武器，复制准确名称后再查；武器实例请发送：查看武器 武器ID。",
        )

    @staticmethod
    def _backpack_item_text(item: dict) -> str:
        """格式化背包物品定义。"""

        return (
            f"☆{item['name']}☆\n"
            f"存放:背包 分类:{item['category']} 品级:{item['quality']} 重量:{item['weight']}\n"
            f"跑商:{'可' if item['tradeable'] else '不可'} 使用:{'可' if item['usable'] else '不可'}\n"
            f"基准价:{item['base_price']}\n"
            f"效果:{format_effect(item['effect'])}\n"
            f"说明:{item['desc']}"
        )

    def _ring_item_text(self, item: dict) -> str:
        """格式化纳戒物品定义。"""

        lines = [
            f"☆{item['name']}☆\n"
            f"存放:纳戒 分类:{item['category']} 品级:{item['quality']}\n"
            f"目标:{item['target_type']} 使用:{'可' if item['usable'] else '不可'}\n"
            f"效果:{format_effect(item['effect'])}\n"
            f"说明:{item['desc']}"
        ]
        enchant_id = load_json(item["effect"], {}).get("enchant_id")
        enchant = self._weapon_enchant_by_id(enchant_id) if enchant_id else None
        if enchant:
            lines.append(f"附魔效果:{format_effect(enchant['effect'])}，精神消耗变化:{enchant['mp_delta']:+d}")
        return "\n".join(lines)

    def _weapon_text(self, weapon: dict) -> str:
        """格式化武器模板定义。"""

        skill = self._weapon_skill_by_id(weapon["skill_id"])
        skill_text = "无"
        if skill:
            skill_text = (
                f"{skill['name']} | 威力{skill['power']}倍 | "
                f"消耗精神{skill['cost_mp']} | 每{skill['interval']}次攻击触发 | {skill['effect_desc']}"
            )
        return (
            f"☆{weapon['name']}☆\n"
            f"类型:武器模板 武器类型:{weapon['weapon_type']} 掉落:{weapon['drop_location']}\n"
            f"模板基础攻击:{weapon['base_attack']}\n"
            f"自带技能:{skill_text}\n"
            f"实例详情:发送 查看武器 武器ID"
        )

    @staticmethod
    def _weapon_skill_text(skill: dict) -> str:
        """格式化武器自带技能定义。"""

        return (
            f"☆{skill['name']}☆\n"
            f"类型:武器自带技能\n"
            f"威力:{skill['power']}倍 消耗精神:{skill['cost_mp']} 触发间隔:每{skill['interval']}次攻击\n"
            f"说明:{skill['effect_desc']}"
        )

    @staticmethod
    def _weapon_enchant_text(enchant: dict) -> str:
        """格式化武器附魔定义。"""

        return (
            f"☆{enchant['name']}☆\n"
            f"类型:武器附魔/技能书效果\n"
            f"效果:{format_effect(enchant['effect'])}\n"
            f"精神消耗变化:{enchant['mp_delta']:+d}"
        )

    @staticmethod
    def _physique_text(physique: dict) -> str:
        """格式化体质定义。"""

        return (
            f"☆{physique['name']}☆\n"
            f"类型:体质资料 阶位:{physique['grade']} 路线:{physique['kind']}\n"
            f"体质值:{physique['physique_value']} 稀有等级:{physique['level']}\n"
            f"效果:{format_effect(physique['effect'])}\n"
            f"说明:{physique['desc']}"
        )

    def _weapon_def_by_name(self, name: str) -> dict | None:
        """按名称读取武器模板。"""

        return self.db.fetch_one("SELECT * FROM weapon_defs WHERE name = ?", (name.strip(),))

    def _weapon_skill_by_name(self, name: str) -> dict | None:
        """按名称读取武器自带技能。"""

        return self.db.fetch_one("SELECT * FROM weapon_skill_defs WHERE name = ?", (name.strip(),))

    def _weapon_skill_by_id(self, skill_id: str) -> dict | None:
        """按 id 读取武器自带技能。"""

        return self.db.fetch_one("SELECT * FROM weapon_skill_defs WHERE skill_id = ?", (skill_id,))

    def _weapon_enchant_by_name(self, name: str) -> dict | None:
        """按名称读取附魔效果。"""

        return self.db.fetch_one("SELECT * FROM weapon_enchants WHERE name = ?", (name.strip(),))

    def _weapon_enchant_by_id(self, enchant_id: str) -> dict | None:
        """按 id 读取附魔效果。"""

        return self.db.fetch_one("SELECT * FROM weapon_enchants WHERE enchant_id = ?", (enchant_id,))

    def _physique_by_name(self, name: str) -> dict | None:
        """按名称读取体质资料。"""

        return self.db.fetch_one("SELECT * FROM physique_defs WHERE name = ?", (name.strip(),))


service = TreasureService(db)

__all__ = ["TreasureService", "service"]
