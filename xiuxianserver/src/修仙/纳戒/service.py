"""纳戒组件服务。"""

from __future__ import annotations

from ..common import CoreService, format_effect, hint
from ..item_effects import service as item_effects
from ..sql import db


class RingService(CoreService):
    """装备库库存。纳戒物品不占负重。"""

    def list_items(self, client_id: str) -> str:
        """查看纳戒。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.ring_rows(client_id)
        if not rows:
            return hint("纳戒为空。", "发送：新手礼包 领取初始恢复物，或发送：探险 获取恢复物、宝石和技能书。")
        lines = ["☆纳戒☆"]
        for row in rows:
            level = f" {row['level']}级" if row.get("level") else ""
            lines.append(f"{row['name']}{level} x{row['quantity']}，{row['category']}")
        return "\n".join(lines)

    def info(self, client_id: str, item_name: str) -> str:
        """查看装备库物品。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.equipment_item_def_by_name(item_name.strip())
        if not item:
            return hint(f"没有找到装备库物品：{item_name.strip()}。", "发送：查看纳戒 查看已拥有的装备库物品。")
        return (
            f"☆{item['name']}☆\n"
            f"分类:{item['category']} 品级:{item['quality']}\n"
            f"目标:{item['target_type']} 使用:{'可' if item['usable'] else '不可'}\n"
            f"效果:{format_effect(item['effect'])}\n"
            f"说明:{item['desc']}"
        )

    def use_item(self, client_id: str, item_name: str) -> str:
        """使用纳戒中的恢复类物品。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.equipment_item_def_by_name(item_name.strip())
        if not item:
            return hint(f"没有找到装备库物品：{item_name.strip()}。", "发送：查看纳戒 查看已拥有的装备库物品。")
        if item["category"] != "恢复类":
            return hint(f"{item['name']} 不能直接使用。", self._use_hint(item))

        with self.db.transaction() as conn:
            if not self.remove_ring_conn(conn, client_id, item["equipment_item_id"], 1):
                return hint(f"纳戒里没有 {item['name']}。", "发送：查看纳戒 确认库存，或继续探险获取。")
            return item_effects.apply_conn(conn, client_id, item, "纳戒")

    def wash(self, client_id: str) -> str:
        """消耗洗髓液洗髓体质。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.equipment_item_def_by_name("洗髓液")
        if not item:
            return hint("洗髓液配置不存在。", "请先检查装备库配置。")
        with self.db.transaction() as conn:
            if not self.remove_ring_conn(conn, client_id, item["equipment_item_id"], 1):
                return hint("纳戒里没有洗髓液。", "洗髓液只通过活动 Boss 掉落，获得后发送：洗髓")
            return item_effects.apply_conn(conn, client_id, item, "洗髓")

    @staticmethod
    def _use_hint(item: dict) -> str:
        """按物品类型给出正确消耗入口。"""

        if item["name"] == "洗髓液":
            return "洗髓液请发送：洗髓。"
        if item["category"] == "宝石":
            return "宝石请发送：镶嵌 装备位 孔位号 宝石名称；同名多等级时加等级，例如：护心玉 2级。"
        if item["category"] == "技能书":
            return "技能书请发送：附魔武器 武器ID 技能书名。"
        if item["name"] == "开孔器":
            return "开孔器请发送：开孔 装备位。"
        return "只有恢复类物品可以直接发送：使用 物品名。"


service = RingService(db)

__all__ = ["RingService", "service"]
