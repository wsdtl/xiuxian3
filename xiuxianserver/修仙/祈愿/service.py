"""祈愿组件服务。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..common import CoreService, currency_amount, load_json, random, ring_item_display_name, ts
from ..constants import WISH_TOKEN_ITEM_ID
from ..format_text import T
from ..public_url import public_url
from ..sql import WISH_DEFAULT_POOL_ID, WISH_VOUCHERS, db

VOUCHER_NAMES = {key: name for key, name in WISH_VOUCHERS}
REWARD_TYPE_LABELS = {
    "currency": "货币",
    "exp": "经验",
    "backpack_item": "背包物资",
    "ring_item": "纳戒物品",
    "voucher": "凭证",
}
WISH_ANIMATION_DIR = Path(__file__).resolve().parents[2] / "static" / "wish"
WISH_ANIMATION_PUBLIC_PATH = "/static/wish"
WISH_ANIMATION_VERSION = "20260627-small"
WISH_ANIMATION_FILES = {
    "single_blue": "单抽出蓝.gif",
    "single_purple": "单抽出紫.gif",
    "single_gold": "单抽出金.gif",
    "ten_purple": "十连出紫.gif",
    "ten_gold": "十连出金.gif",
}
RARITY_SCORE = {"blue": 0, "purple": 1, "gold": 2}
GOLD_PRIZE_IDS = {
    "currency_5000",
    "exp_1500",
    "voucher_liuguang",
    "voucher_xuanqi",
    "voucher_xingming",
    "voucher_guixu",
    "voucher_tianqi",
}
PURPLE_PRIZE_IDS = {
    "currency_1500",
    "exp_600",
    "ring_huichunlu_1",
    "ring_ningshenlu_1",
    "ring_shenggudan_1",
    "ring_yanghundan_1",
    "world_build_jichu_2",
    "world_relic_weiyun_1",
}


@dataclass(frozen=True)
class WishDrawResult:
    """祈愿抽取后的发送结果。"""

    message: str
    animation_key: str = ""
    success: bool = False

    @property
    def animation_path(self) -> Path | None:
        """读取当前结果对应的演出 GIF；缺文件时安静降级为只发文本。"""

        filename = WISH_ANIMATION_FILES.get(self.animation_key)
        if not filename:
            return None
        path = WISH_ANIMATION_DIR / filename
        return path if path.exists() else None

    @property
    def animation_markdown(self) -> str:
        """生成 QQ Markdown 可直接展示的公网 GIF；没有演出文件时返回空字符串。"""

        path = self.animation_path
        if path is None:
            return ""
        url = f"{public_url(f'{WISH_ANIMATION_PUBLIC_PATH}/{quote(path.name)}')}?v={WISH_ANIMATION_VERSION}"
        return f"![祈愿演出 #360px #203px]({url})"

    def message_with_animation(self) -> str:
        """把祈愿演出嵌到结算正文前，同一条富文本里一起发出。"""

        animation = self.animation_markdown if self.success else ""
        if not animation:
            return self.message
        return f"{animation}\n\n{self.message}"


class WishService(CoreService):
    """消耗流光签进行祈愿，并把奖励发到现有库存体系。"""

    def draw(self, client_id: str, count: int = 1) -> str:
        """进行指定次数的祈愿；当前只开放单抽和十连。"""

        return self.draw_result(client_id, count).message_with_animation()

    def draw_result(self, client_id: str, count: int = 1) -> WishDrawResult:
        """进行祈愿并返回正文与演出信息。"""

        _, error = self.require_player(client_id)
        if error:
            return WishDrawResult(error)
        draw_count = 10 if int(count) >= 10 else 1

        with self.db.transaction() as conn:
            pool = self._active_pool_conn(conn)
            if not pool:
                return WishDrawResult(T.hint("当前没有开启的祈愿奖池。", "稍后再发送：祈愿奖池 查看配置。<祈愿奖池>"))

            prizes = self._pool_prizes_conn(conn, str(pool["pool_id"]))
            if not prizes:
                return WishDrawResult(T.hint("当前祈愿奖池没有可抽奖品。", "请先检查 wish_prizes 配置。"))

            cost_token_id = str(pool["cost_token_id"] or WISH_TOKEN_ITEM_ID)
            cost_each = max(1, int(pool["cost_token_quantity"] or 1))
            draws_per_token = self._wish_draws_per_token_conn(conn, cost_token_id)
            # `cost_token_quantity` 表示每抽基础消耗多少“凭证单位”，
            # `wish_draws` 表示一枚凭证能提供多少次祈愿额度。当前流光签为 1，
            # 行为不变；以后若增加高阶凭证，也不用再改祈愿结算公式。
            total_cost = max(1, ceil(cost_each * draw_count / draws_per_token))
            token_name = self._ring_item_name_conn(conn, cost_token_id)
            owned = self._ring_quantity_conn(conn, client_id, cost_token_id)
            if owned < total_cost:
                return WishDrawResult(
                    T.hint(
                        f"纳戒里的 {token_name} 不足，需要 {total_cost} 枚，当前 {owned} 枚。",
                        "流光签可在探险中低概率获得，获得后发送：祈愿 或 十连祈愿。<探险><纳戒><祈愿奖池>",
                    )
                )

            rolled = self._roll_prizes(prizes, draw_count)
            backpack_rewards = self._aggregate_rewards(rolled, "backpack_item")
            can_add, reason = self._can_add_backpack_rewards_conn(conn, client_id, backpack_rewards)
            if not can_add:
                return WishDrawResult(reason)

            if not self.remove_ring_conn(conn, client_id, cost_token_id, total_cost):
                return WishDrawResult(T.hint(f"纳戒里的 {token_name} 不足。", "发送：纳戒 确认库存。<纳戒>"))

            summary: dict[tuple[str, str, str], int] = {}
            now_text = ts()
            for prize in rolled:
                reward = self._grant_prize_conn(conn, client_id, prize, now_text)
                summary_key = (reward["reward_type"], reward["reward_key"], reward["display_name"])
                summary[summary_key] = summary.get(summary_key, 0) + int(reward["quantity"])
                conn.execute(
                    """
                    INSERT INTO wish_draw_records
                    (
                        player_id, pool_id, prize_id, reward_type, reward_key,
                        display_name, quantity, cost_token_id, cost_token_quantity, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        pool["pool_id"],
                        prize["prize_id"],
                        reward["reward_type"],
                        reward["reward_key"],
                        reward["display_name"],
                        int(reward["quantity"]),
                        cost_token_id,
                        cost_each,
                        now_text,
                    ),
                )

        panel = T.panel()
        panel.section("祈愿结果")
        panel.line(f"奖池：{pool['name']}｜消耗：{token_name} x{total_cost}")
        for reward_type, reward_key, display_name, quantity in self._summary_lines(summary):
            panel.line("获得：" + self._format_reward_amount(reward_type, reward_key, display_name, quantity))
        return WishDrawResult(
            T.attach(panel.render(), "<祈愿><十连祈愿><我的凭证><祈愿记录>"),
            self._animation_key(draw_count, rolled),
            True,
        )

    def pool_info(self, client_id: str) -> str:
        """查看当前祈愿奖池、消耗和奖品结构。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        with self.db.transaction() as conn:
            pool = self._active_pool_conn(conn)
            if not pool:
                return T.hint("当前没有开启的祈愿奖池。", "稍后再试。")
            prizes = self._pool_prizes_conn(conn, str(pool["pool_id"]))
            total_weight = sum(max(0, int(row["weight"] or 0)) for row in prizes)
            token_name = self._ring_item_name_conn(conn, str(pool["cost_token_id"]))
            type_weights: dict[str, int] = {}
            for row in prizes:
                reward_type = str(row["reward_type"])
                type_weights[reward_type] = type_weights.get(reward_type, 0) + max(0, int(row["weight"] or 0))

            panel = T.panel()
            panel.section(str(pool["name"]))
            panel.line(f"消耗：{token_name} x{int(pool['cost_token_quantity'] or 1)} / 次")
            panel.line("流光签来自探险低概率掉落；显示名会随当前世界皮肤变化。")
            panel.hr()
            panel.section("奖品结构")
            if total_weight <= 0:
                panel.line("暂无可抽权重。")
            else:
                for reward_type, weight in sorted(type_weights.items(), key=lambda item: item[1], reverse=True):
                    panel.line(f"{REWARD_TYPE_LABELS.get(reward_type, reward_type)}：{weight / total_weight * 100:.1f}%")
            panel.hr()
            panel.section("主要奖品")
            for row in prizes[:8]:
                panel.line(
                    f"{self._format_prize_conn(conn, row)}｜{int(row['weight'] or 0) / total_weight * 100:.1f}%"
                    if total_weight > 0
                    else self._format_prize_conn(conn, row)
                )
            voucher_prizes = {
                str(row["reward_key"]): row
                for row in prizes
                if str(row["reward_type"]) == "voucher"
            }
            if voucher_prizes:
                panel.hr()
                panel.section("凭证池")
                panel.line("固定池，无周期轮换。")
                for voucher_key, voucher_name in WISH_VOUCHERS:
                    row = voucher_prizes.get(voucher_key)
                    if not row:
                        continue
                    if total_weight > 0:
                        panel.line(f"{voucher_name} x{int(row['quantity'] or 1)}｜{int(row['weight'] or 0) / total_weight * 100:.1f}%")
                    else:
                        panel.line(f"{voucher_name} x{int(row['quantity'] or 1)}")
        return T.attach(panel.render(), "<祈愿><十连祈愿><我的凭证>")

    def my_vouchers(self, client_id: str) -> str:
        """查看玩家祈愿凭证。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all(
            """
            SELECT voucher_key, display_name, quantity
            FROM wish_user_vouchers
            WHERE player_id = ? AND quantity > 0
            ORDER BY voucher_key
            """,
            (client_id,),
        )
        if not rows:
            return T.hint("你还没有祈愿凭证。", "发送：祈愿 消耗流光签获取；凭证第一版只记账，暂不开放兑换。<祈愿><祈愿奖池>")
        panel = T.panel()
        panel.section("我的凭证")
        for row in rows:
            panel.line(f"{row['display_name']} x{row['quantity']}")
        panel.hr()
        panel.line("凭证第一版只作为抽取结果记账，兑换入口后续再开放。")
        return T.attach(panel.render(), "<祈愿><祈愿记录>")

    def records(self, client_id: str) -> str:
        """查看最近十条祈愿记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all(
            """
            SELECT r.*, COALESCE(p.name, r.pool_id) AS pool_name
            FROM wish_draw_records AS r
            LEFT JOIN wish_pools AS p ON p.pool_id = r.pool_id
            WHERE r.player_id = ?
            ORDER BY r.record_id DESC
            LIMIT 10
            """,
            (client_id,),
        )
        if not rows:
            return T.hint("暂无祈愿记录。", "发送：祈愿 消耗流光签进行第一次祈愿。<祈愿><祈愿奖池>")
        panel = T.panel()
        panel.section("祈愿记录")
        for row in rows:
            reward = self._format_reward_amount(
                str(row["reward_type"]),
                str(row["reward_key"]),
                str(row["display_name"]),
                int(row["quantity"] or 0),
            )
            panel.line(f"{row['created_at']}｜{row['pool_name']}｜{reward}")
        return T.attach(panel.render(), "<祈愿><十连祈愿><我的凭证>")

    @staticmethod
    def _summary_lines(summary: dict[tuple[str, str, str], int]) -> list[tuple[str, str, str, int]]:
        """按奖励类型整理十连结果，方便消息里合并重复项。"""

        order = {"currency": 0, "exp": 1, "ring_item": 2, "backpack_item": 3, "voucher": 4}
        rows = [
            (reward_type, reward_key, display_name, quantity)
            for (reward_type, reward_key, display_name), quantity in summary.items()
        ]
        return sorted(rows, key=lambda row: (order.get(row[0], 99), row[2]))

    @staticmethod
    def _aggregate_rewards(prizes: list[dict[str, Any]], reward_type: str) -> dict[str, int]:
        """把同类奖品数量先合并，用于背包容量预检查。"""

        result: dict[str, int] = {}
        for prize in prizes:
            if str(prize["reward_type"]) != reward_type:
                continue
            reward_key = str(prize["reward_key"])
            result[reward_key] = result.get(reward_key, 0) + int(prize["quantity"] or 0)
        return result

    @staticmethod
    def _animation_key(draw_count: int, prizes: list[dict[str, Any]]) -> str:
        """按五个固定视频文件选择演出档位。"""

        best = "blue"
        for prize in prizes:
            rarity = WishService._prize_rarity(prize)
            if RARITY_SCORE[rarity] > RARITY_SCORE[best]:
                best = rarity
        if draw_count >= 10:
            return "ten_gold" if best == "gold" else "ten_purple"
        return f"single_{best}"

    @staticmethod
    def _prize_rarity(prize: dict[str, Any]) -> str:
        """把奖品映射到蓝、紫、金三档；只影响演出，不影响实际掉率。"""

        prize_id = str(prize.get("prize_id") or "")
        reward_type = str(prize.get("reward_type") or "")
        if prize_id in GOLD_PRIZE_IDS or reward_type == "voucher":
            return "gold"
        if prize_id in PURPLE_PRIZE_IDS:
            return "purple"
        return "blue"

    def _active_pool_conn(self, conn: sqlite3.Connection) -> sqlite3.Row | None:
        """读取当前默认开启奖池。"""

        return conn.execute(
            """
            SELECT *
            FROM wish_pools
            WHERE pool_id = ? AND enabled = 1
            LIMIT 1
            """,
            (WISH_DEFAULT_POOL_ID,),
        ).fetchone()

    @staticmethod
    def _pool_prizes_conn(conn: sqlite3.Connection, pool_id: str) -> list[dict[str, Any]]:
        """读取奖池启用奖品，权重大的排前面。"""

        rows = conn.execute(
            """
            SELECT *
            FROM wish_prizes
            WHERE pool_id = ? AND enabled = 1 AND weight > 0 AND quantity > 0
            ORDER BY weight DESC, prize_id
            """,
            (pool_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _roll_prizes(prizes: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
        """按权重抽取奖品。"""

        total_weight = sum(max(0, int(row["weight"] or 0)) for row in prizes)
        if total_weight <= 0:
            return []
        rolled: list[dict[str, Any]] = []
        for _ in range(count):
            cursor = random.uniform(0, total_weight)
            passed = 0.0
            for row in prizes:
                passed += max(0, int(row["weight"] or 0))
                if cursor <= passed:
                    rolled.append(row)
                    break
            else:
                rolled.append(prizes[-1])
        return rolled

    def _grant_prize_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        prize: dict[str, Any],
        now_text: str,
    ) -> dict[str, Any]:
        """发放单个奖品，并返回记录用的稳定结果。"""

        reward_type = str(prize["reward_type"])
        reward_key = str(prize["reward_key"])
        quantity = max(1, int(prize["quantity"] or 1))
        display_name = str(prize["display_name"])
        if reward_type == "currency":
            conn.execute(
                "UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?",
                (quantity, client_id),
            )
            display_name = "原石"
        elif reward_type == "exp":
            self.add_exp_conn(conn, client_id, quantity)
            display_name = "经验"
        elif reward_type == "backpack_item":
            self.add_backpack_conn(conn, client_id, reward_key, quantity)
            display_name = self._backpack_item_name_conn(conn, reward_key)
        elif reward_type == "ring_item":
            self.add_ring_conn(conn, client_id, reward_key, quantity)
            display_name = self._ring_item_name_conn(conn, reward_key)
        elif reward_type == "voucher":
            display_name = VOUCHER_NAMES.get(reward_key, display_name)
            conn.execute(
                """
                INSERT INTO wish_user_vouchers
                (player_id, voucher_key, display_name, quantity, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(player_id, voucher_key)
                DO UPDATE SET
                    display_name = excluded.display_name,
                    quantity = quantity + excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (client_id, reward_key, display_name, quantity, now_text),
            )
        return {
            "reward_type": reward_type,
            "reward_key": reward_key,
            "display_name": display_name,
            "quantity": quantity,
        }

    def _format_prize_conn(self, conn: sqlite3.Connection, prize: dict[str, Any]) -> str:
        """按当前定义表展示奖品名，避免皮肤切换后仍显示旧名。"""

        reward_type = str(prize["reward_type"])
        reward_key = str(prize["reward_key"])
        quantity = int(prize["quantity"] or 0)
        display_name = str(prize["display_name"])
        if reward_type == "backpack_item":
            display_name = self._backpack_item_name_conn(conn, reward_key)
        elif reward_type == "ring_item":
            display_name = self._ring_item_name_conn(conn, reward_key)
        elif reward_type == "voucher":
            display_name = VOUCHER_NAMES.get(reward_key, display_name)
        return self._format_reward_amount(reward_type, reward_key, display_name, quantity)

    @staticmethod
    def _format_reward_amount(reward_type: str, reward_key: str, display_name: str, quantity: int) -> str:
        """把奖励稳定类型转成玩家可读的一行。"""

        if reward_type == "currency":
            return currency_amount(quantity, reward_key)
        if reward_type == "exp":
            return f"经验 +{quantity}"
        return f"{display_name} x{quantity}"

    @staticmethod
    def _ring_quantity_conn(conn: sqlite3.Connection, client_id: str, ring_item_id: str) -> int:
        """读取普通纳戒物品数量。"""

        row = conn.execute(
            "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
            (client_id, ring_item_id),
        ).fetchone()
        return int(row["quantity"]) if row else 0

    @staticmethod
    def _ring_item_name_conn(conn: sqlite3.Connection, ring_item_id: str) -> str:
        """读取纳戒物品当前展示名。"""

        row = conn.execute(
            "SELECT * FROM ring_item_defs WHERE ring_item_id = ?",
            (ring_item_id,),
        ).fetchone()
        return ring_item_display_name(dict(row) if row else None, ring_item_id)

    @staticmethod
    def _wish_draws_per_token_conn(conn: sqlite3.Connection, ring_item_id: str) -> int:
        """读取一枚祈愿凭证可抵扣的祈愿次数。

        这个值来自 `ring_item_defs.effect.wish_draws`，属于道具定义能力；
        缺失或写错时按 1 处理，避免奖池配置异常导致免费抽或除零。
        """

        row = conn.execute(
            "SELECT effect FROM ring_item_defs WHERE ring_item_id = ?",
            (ring_item_id,),
        ).fetchone()
        effect = load_json(row["effect"], {}) if row else {}
        return max(1, int(effect.get("wish_draws") or 1))

    @staticmethod
    def _backpack_item_name_conn(conn: sqlite3.Connection, item_id: str) -> str:
        """读取背包物品当前展示名。"""

        row = conn.execute("SELECT name FROM item_defs WHERE item_id = ?", (item_id,)).fetchone()
        return str(row["name"]) if row else item_id

    @staticmethod
    def _can_add_backpack_rewards_conn(
        conn: sqlite3.Connection,
        client_id: str,
        rewards: dict[str, int],
    ) -> tuple[bool, str]:
        """一次性模拟多个背包奖品，避免十连时逐项检查漏掉总负重和新格子数。"""

        if not rewards:
            return True, ""
        player = conn.execute(
            "SELECT backpack_limit, weight_limit FROM players WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if not player:
            return False, T.hint("玩家不存在。", "请先发送：创建用户 名称。")

        current_rows = conn.execute(
            "SELECT item_id, quantity FROM backpack_items WHERE client_id = ? AND quantity > 0",
            (client_id,),
        ).fetchall()
        current_quantities = {str(row["item_id"]): int(row["quantity"] or 0) for row in current_rows}
        current_kind_count = len(current_quantities)
        weight_row = conn.execute(
            """
            SELECT COALESCE(SUM(b.quantity * i.weight), 0) AS total
            FROM backpack_items AS b
            JOIN item_defs AS i ON i.item_id = b.item_id
            WHERE b.client_id = ?
            """,
            (client_id,),
        ).fetchone()
        weight_after = int(weight_row["total"] or 0)
        new_kind_count = 0

        for item_id, quantity in rewards.items():
            if quantity <= 0:
                continue
            item = conn.execute(
                "SELECT name, weight, stack_limit FROM item_defs WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if not item:
                return False, T.hint(f"祈愿奖品不存在：{item_id}。", "请检查 wish_prizes 配置。")
            current_quantity = current_quantities.get(item_id, 0)
            if current_quantity + quantity > int(item["stack_limit"]):
                return False, T.hint(
                    f"{item['name']} 堆叠上限不足，最多 {item['stack_limit']}。",
                    "先出售或使用一部分同名物品，再重新祈愿。<背包>",
                )
            if current_quantity <= 0:
                new_kind_count += 1
            weight_after += int(item["weight"]) * quantity

        if current_kind_count + new_kind_count > int(player["backpack_limit"]):
            return False, T.hint(
                f"背包格子不足，最多 {player['backpack_limit']} 种物品。",
                "先清理背包，再重新祈愿。<背包><自动出售>",
            )
        if weight_after > int(player["weight_limit"]):
            return False, T.hint(
                f"背包负重不足，放入后会变成 {weight_after}/{player['weight_limit']}。",
                "先清理背包，再重新祈愿。<背包><自动出售>",
            )
        return True, ""


service = WishService(db)
