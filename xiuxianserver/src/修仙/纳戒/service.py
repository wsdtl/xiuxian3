"""纳戒组件服务。"""

from __future__ import annotations

from ..format_text import T

from ..common import CoreService, equipment_item_use_hint, parse_name_quantity_optional
from ..item_effects import service as item_effects
from ..sql import db


class RingService(CoreService):
    """纳戒库存。纳戒物品不占负重。"""

    def list_items(self, client_id: str) -> str:
        """查看纳戒。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.ring_rows(client_id)
        if not rows:
            return T.hint("纳戒为空。", "发送：新手礼包 领取初始恢复物，或发送：探险 获取恢复物、宝石和技能书。<探险>")
        panel = T.panel()
        panel.section("纳戒")
        for row in rows:
            level = f" {row['level']}级" if row.get("level") else ""
            panel.line(f"{row['name']}{level} x{row['quantity']}｜{row['category']}")
        return panel.render()

    def use_item(self, client_id: str, item_message: str) -> str:
        """使用纳戒中的恢复类物品。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item_name, quantity = parse_name_quantity_optional(item_message)
        if quantity <= 0:
            return T.hint("使用数量必须大于 0。", "发送：使用 物品名 数量，例如：使用 福袋 5")
        item = self.equipment_item_def_by_name(item_name)
        if not item:
            return T.hint(f"没有找到纳戒物品：{item_name}。", "发送：纳戒 查看已拥有的物品。<纳戒>")
        if item["category"] != "恢复类":
            return T.hint(f"{item['name']} 不能直接使用。", equipment_item_use_hint(item))

        with self.db.transaction() as conn:
            if not self.remove_ring_conn(conn, client_id, item["equipment_item_id"], quantity):
                return T.hint(f"纳戒里没有足够的 {item['name']} x{quantity}。", "发送：纳戒 确认库存，或继续探险获取。<纳戒><探险>")
            return item_effects.apply_many_conn(conn, client_id, item, "纳戒", quantity)

    def wash(self, client_id: str) -> str:
        """消耗洗髓液洗髓体质。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.equipment_item_def_by_name("洗髓液")
        if not item:
            return T.hint("洗髓液配置不存在。", "请先检查纳戒物品配置。")
        with self.db.transaction() as conn:
            if not self.remove_ring_conn(conn, client_id, item["equipment_item_id"], 1):
                return T.hint("纳戒里没有洗髓液。", "洗髓液可从岁时情劫首领或异界虫洞奖励中获得，获得后发送：洗髓<洗髓>")
            return item_effects.apply_conn(conn, client_id, item, "洗髓")


service = RingService(db)

__all__ = ["RingService", "service"]
