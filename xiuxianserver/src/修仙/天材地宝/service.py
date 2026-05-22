"""天材地宝组件服务。"""

from __future__ import annotations

from ..common import CoreService, format_effect, hint
from ..sql import db


class TreasureService(CoreService):
    """物品库查询。"""

    def info(self, client_id: str, item_name: str) -> str:
        """查看物品说明。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.item_def_by_name(item_name.strip())
        if not item:
            return hint(f"没有找到天材地宝：{item_name.strip()}。", "发送：查看背包 或 商场 查看已有物品名称。")
        return (
            f"☆{item['name']}☆\n"
            f"分类:{item['category']} 品级:{item['quality']} 重量:{item['weight']}\n"
            f"跑商:{'可' if item['tradeable'] else '不可'} 使用:{'可' if item['usable'] else '不可'}\n"
            f"基准价:{item['base_price']}\n"
            f"效果:{format_effect(item['effect'])}\n"
            f"说明:{item['desc']}"
        )


service = TreasureService(db)

__all__ = ["TreasureService", "service"]
