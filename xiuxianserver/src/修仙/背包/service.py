"""背包组件服务。"""

from __future__ import annotations

from ..common import CoreService, format_effect, hint
from ..item_effects import service as item_effects
from ..sql import db


class BackpackService(CoreService):
    """物品库库存。背包物品占负重。"""

    def list_items(self, client_id: str) -> str:
        """查看背包。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        rows = self.backpack_rows(client_id)
        weight = self.backpack_weight(client_id)
        if not rows:
            return hint(f"背包为空。负重 {weight}/{player['weight_limit']}。", "发送：探险 获取掉落，或发送：商场购买 商品名 数量。")
        lines = [f"☆背包☆ 负重 {weight}/{player['weight_limit']}"]
        for row in rows:
            lines.append(f"{row['name']} x{row['quantity']}，单重 {row['weight']}，{row['category']}")
        return "\n".join(lines)

    def use_item(self, client_id: str, item_name: str) -> str:
        """使用恢复类物品。

        这个入口只允许消耗恢复类；宝石、技能书、洗髓液等都必须走自己的命令。
        """

        player, error = self.require_player(client_id)
        if error:
            return error
        item = self.item_def_by_name(item_name.strip())
        if not item:
            ring_item = self.equipment_item_def_by_name(item_name.strip())
            if not ring_item:
                return hint(f"没有找到物品：{item_name.strip()}。", "发送：查看背包 或 查看纳戒，复制准确物品名。")
            if ring_item["category"] != "恢复类":
                return hint(f"{ring_item['name']} 不能直接使用。", self._use_hint(ring_item))
            with self.db.transaction() as conn:
                if not self.remove_ring_conn(conn, client_id, ring_item["equipment_item_id"], 1):
                    return hint(f"纳戒里没有 {ring_item['name']}。", "发送：查看纳戒 确认库存，或继续探险获取。")
                return item_effects.apply_conn(conn, client_id, ring_item, "纳戒")
        if item["category"] != "恢复类":
            return hint(f"{item['name']} 不能直接使用。", "跑商物品可发送：商场出售 商品名 数量；特殊战利品可发送：特殊出售 物品名 数量。")

        with self.db.transaction() as conn:
            if not self.remove_backpack_conn(conn, client_id, item["item_id"], 1):
                return hint(f"背包里没有 {item['name']}。", "发送：查看背包 确认库存，或继续探险/跑商获取。")
            return item_effects.apply_conn(conn, client_id, item, "背包")

    @staticmethod
    def _use_hint(item: dict) -> str:
        """按纳戒物品类型给出正确消耗入口。"""

        if item["name"] == "洗髓液":
            return "洗髓液请发送：洗髓。"
        if item["category"] == "宝石":
            return "宝石请发送：镶嵌 装备位 孔位号 宝石名称；同名多等级时加等级，例如：护心玉 2级。"
        if item["category"] == "技能书":
            return "技能书请发送：附魔武器 武器ID 技能书名。"
        if item["name"] == "开孔器":
            return "开孔器请发送：开孔 装备位。"
        return "只有恢复类物品可以直接发送：使用 物品名。"

    def info(self, client_id: str, item_name: str) -> str:
        """查看物品库物品。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.item_def_by_name(item_name.strip())
        if not item:
            return hint(f"没有找到物品：{item_name.strip()}。", "发送：查看背包 查看已拥有物品，或发送：商场 查看当地商品。")
        return (
            f"☆{item['name']}☆\n"
            f"分类:{item['category']} 品级:{item['quality']} 重量:{item['weight']}\n"
            f"跑商:{'可' if item['tradeable'] else '不可'} 使用:{'可' if item['usable'] else '不可'}\n"
            f"基准价:{item['base_price']}\n"
            f"效果:{format_effect(item['effect'])}\n"
            f"说明:{item['desc']}"
        )


service = BackpackService(db)

__all__ = ["BackpackService", "service"]
