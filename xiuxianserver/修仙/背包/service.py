"""背包组件服务。"""

from __future__ import annotations

from ..format_text import T

from ..common import CoreService, equipment_item_use_hint, parse_name_quantity_optional
from ..item_effects import service as item_effects
from ..sql import db


class BackpackService(CoreService):
    """背包库存。背包物品占负重。"""

    def list_items(self, client_id: str) -> str:
        """查看背包。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        rows = self.backpack_rows(client_id)
        weight = self.backpack_weight(client_id)
        if not rows:
            return T.hint(f"背包为空。负重 {weight}/{player['weight_limit']}。", "<商场自动出售><特殊自动出售><商场推荐>")
        panel = T.panel()
        panel.section("背包")
        panel.line(f"负重：**{weight}/{player['weight_limit']}**")
        panel.hr()
        panel.section("物品")
        for row in rows:
            panel.line(f"{row['name']} x{row['quantity']}｜单重 {row['weight']}｜{row['category']}")
        return panel.render() + "<商场自动出售><特殊自动出售><商场推荐>"

    def use_item(self, client_id: str, item_message: str) -> str:
        """使用恢复类物品。

        这个入口只允许消耗恢复类；宝石、技能书、洗髓液等都必须走自己的命令。
        """

        player, error = self.require_player(client_id)
        if error:
            return error
        item_name, quantity = parse_name_quantity_optional(item_message)
        if quantity <= 0:
            return T.hint("使用数量必须大于 0。", "发送：使用 物品名 数量，例如：使用 福袋 5")
        item = self.item_def_by_name(item_name)
        if not item:
            ring_item = self.equipment_item_def_by_name(item_name)
            if not ring_item:
                return T.hint(f"没有找到物品：{item_name}。", "发送：背包 或 纳戒，复制准确物品名。<背包><纳戒>")
            if ring_item["category"] != "恢复类":
                return T.hint(f"{ring_item['name']} 不能直接使用。", equipment_item_use_hint(ring_item))
            with self.db.transaction() as conn:
                if not self.remove_ring_conn(conn, client_id, ring_item["equipment_item_id"], quantity):
                    return T.hint(f"纳戒里没有足够的 {ring_item['name']} x{quantity}。", "发送：纳戒 确认库存，或继续探险获取。<纳戒>")
                return item_effects.apply_many_conn(conn, client_id, ring_item, "纳戒", quantity)
        if item["category"] != "恢复类":
            return T.hint(f"{item['name']} 不能直接使用。", "跑商物品可发送：商场出售 商品名 数量；特殊战利品可发送：特殊出售 物品名 数量。<商场自动出售><特殊自动出售>")

        with self.db.transaction() as conn:
            if not self.remove_backpack_conn(conn, client_id, item["item_id"], quantity):
                return T.hint(f"背包里没有足够的 {item['name']} x{quantity}。", "发送：背包 确认库存，或继续探险/跑商获取。<背包><商场推荐>")
            return item_effects.apply_many_conn(conn, client_id, item, "背包", quantity)


service = BackpackService(db)

__all__ = ["BackpackService", "service"]
