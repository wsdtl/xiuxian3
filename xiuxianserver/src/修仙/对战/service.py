"""玩家对战组件服务。"""

from __future__ import annotations

from ..combat_core import service as combat_service
from ..common import CoreService, hint, money, parse_player_ref, split_words, to_int, ts
from ..sql import db


class DuelService(CoreService):
    """切磋和赌约决斗。"""

    def spar(self, client_id: str, message: str) -> str:
        """发起切磋。"""

        return self._create_request(client_id, message, "spar", 0)

    def accept_spar(self, client_id: str, message: str) -> str:
        """接受切磋。"""

        return self._accept(client_id, message, "spar")

    def reject_spar(self, client_id: str, message: str) -> str:
        """拒绝切磋。"""

        return self._reject(client_id, message, "spar")

    def bet(self, client_id: str, message: str) -> str:
        """发起赌约。"""

        parts = split_words(message)
        if len(parts) < 2:
            return hint("赌约格式不正确。", "发送：赌约 对方ID 源石数量，也可以用 CQ/at 指定对方。")
        target_id = parse_player_ref(parts[0])
        stake = to_int(parts[1])
        if stake <= 0:
            return hint("赌约源石必须大于 0。", "重新发送：赌约 对方ID 源石数量")
        return self._create_request(client_id, target_id, "bet", stake)

    def accept_bet(self, client_id: str, message: str) -> str:
        """接受赌约。"""

        return self._accept(client_id, message, "bet")

    def reject_bet(self, client_id: str, message: str) -> str:
        """拒绝赌约。"""

        return self._reject(client_id, message, "bet")

    def records(self, client_id: str) -> str:
        """查看决斗记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all(
            """
            SELECT * FROM duel_records
            WHERE from_client_id = ? OR to_client_id = ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (client_id, client_id),
        )
        if not rows:
            return hint("暂无决斗记录。", "发送：切磋 对方ID，或发送：赌约 对方ID 源石数量。")
        return "\n".join(row["summary"] for row in rows)

    def _create_request(self, client_id: str, message: str, mode: str, stake: int) -> str:
        """创建对战请求。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        target_id = parse_player_ref(message)
        if not target_id:
            return hint("缺少对方 ID。", "发送：切磋 对方ID，或使用 CQ/at 指定对方。")
        target, error = self.require_player(target_id)
        if error:
            return hint("对方还没有创建用户。", "请对方先发送：创建用户 名称")
        if target_id == client_id:
            return hint("不能挑战自己。", "请输入其他玩家 ID，或使用 CQ/at 指定对方。")
        if player["status"] != "空闲" or target["status"] != "空闲":
            return hint("双方都需要处于空闲状态。", "双方可先发送：修仙信息 查看状态，处理探险或休息后再挑战。")
        with self.db.transaction() as conn:
            self._expire_requests_conn(conn, client_id, target_id)
            exists = conn.execute(
                """
                SELECT duel_id FROM duel_requests
                WHERE status = '等待'
                  AND (from_client_id = ? OR to_client_id = ? OR from_client_id = ? OR to_client_id = ?)
                LIMIT 1
                """,
                (client_id, client_id, target_id, target_id),
            ).fetchone()
            if exists:
                return hint("你或对方已有未处理的对战请求。", "先接受/拒绝当前请求，或等待请求超时后再发起。")
            if mode == "bet" and not self.spend_stones_conn(conn, client_id, stake):
                return hint(f"源石不足，赌约需要冻结 {money(stake)}。", "发送：源库 查看存量，或先取出源石、签到、探险、出售物品。")
            conn.execute(
                """
                INSERT INTO duel_requests
                (mode, from_client_id, to_client_id, stake, status, expires_at, created_at)
                VALUES (?, ?, ?, ?, '等待', datetime('now', 'localtime', '+10 minutes'), ?)
                """,
                (mode, client_id, target_id, stake, ts()),
            )
        mode_text = "切磋" if mode == "spar" else f"赌约 {money(stake)} 源石"
        return f"已向 {self.format_player_name(target_id)} 发起{mode_text}，等待对方接受。"

    def _accept(self, client_id: str, message: str, mode: str) -> str:
        """接受对战请求并结算。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        from_id = parse_player_ref(message)
        if not from_id:
            return hint("缺少发起人 ID。", "发送：接受切磋 发起人ID，或使用 CQ/at 指定发起人。")
        with self.db.transaction() as conn:
            self._expire_requests_conn(conn, client_id, from_id)
            request_row = conn.execute(
                """
                SELECT * FROM duel_requests
                WHERE mode = ? AND from_client_id = ? AND to_client_id = ? AND status = '等待'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (mode, from_id, client_id),
            ).fetchone()
            request = dict(request_row) if request_row else None
        if not request:
            return hint("没有找到待接受的请求。", "确认对方 ID 是否正确，或让对方重新发起切磋/赌约。")
        result = combat_service.duel(from_id, client_id, write_log=False)

        with self.db.transaction() as conn:
            self._expire_requests_conn(conn, client_id, from_id)
            request_row = conn.execute(
                """
                SELECT * FROM duel_requests
                WHERE duel_id = ? AND status = '等待'
                """,
                (request["duel_id"],),
            ).fetchone()
            if not request_row:
                return hint("没有找到待接受的请求。", "可能已超时或被处理，请让对方重新发起。")
            request = dict(request_row)
            if mode == "bet" and not self.spend_stones_conn(conn, client_id, request["stake"]):
                conn.execute(
                    "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                    (request["stake"], from_id),
                )
                conn.execute(
                    "UPDATE duel_requests SET status = '已拒绝' WHERE duel_id = ? AND status = '等待'",
                    (request["duel_id"],),
                )
                return hint("你的源石不足，赌约已取消，发起人的冻结源石已退回。", "补足源石后让对方重新发起赌约。")

            cursor = conn.execute(
                "UPDATE duel_requests SET status = '已接受' WHERE duel_id = ? AND status = '等待'",
                (request["duel_id"],),
            )
            if cursor.rowcount <= 0:
                return hint("没有找到待接受的请求。", "可能已超时或被处理，请让对方重新发起。")

            fee = 0
            if mode == "bet" and result["winner_id"]:
                pool = request["stake"] * 2
                fee = int(pool * 0.03)
                conn.execute(
                    "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                    (pool - fee, result["winner_id"]),
                )
            conn.execute(
                """
                INSERT INTO duel_records
                (duel_id, mode, from_client_id, to_client_id, winner_id, loser_id, stake, fee, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request["duel_id"],
                    "切磋" if mode == "spar" else "赌约",
                    from_id,
                    client_id,
                    result["winner_id"],
                    result["loser_id"],
                    request["stake"],
                    fee,
                    result["summary"],
                    ts(),
                ),
            )
            conn.execute(
                "INSERT INTO combat_logs (client_id, target, summary, created_at) VALUES (?, ?, ?, ?)",
                (from_id, client_id, result["summary"], ts()),
            )
        return result["summary"] + (f"\n赌约结算：胜者获得 {money(request['stake'] * 2 - fee)}，手续费 {money(fee)}。" if mode == "bet" else "")

    def _reject(self, client_id: str, message: str, mode: str) -> str:
        """拒绝对战请求。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        from_id = parse_player_ref(message)
        if not from_id:
            return hint("缺少发起人 ID。", "发送：拒绝切磋 发起人ID，或使用 CQ/at 指定发起人。")
        with self.db.transaction() as conn:
            self._expire_requests_conn(conn, client_id, from_id)
            request = conn.execute(
                """
                SELECT * FROM duel_requests
                WHERE mode = ? AND from_client_id = ? AND to_client_id = ? AND status = '等待'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (mode, from_id, client_id),
            ).fetchone()
            if not request:
                return hint("没有找到待拒绝的请求。", "确认对方 ID 是否正确，或忽略已超时的请求。")
            cursor = conn.execute(
                "UPDATE duel_requests SET status = '已拒绝' WHERE duel_id = ? AND status = '等待'",
                (request["duel_id"],),
            )
            if cursor.rowcount <= 0:
                return hint("没有找到待拒绝的请求。", "可能已超时或被处理，无需重复拒绝。")
            if mode == "bet":
                conn.execute(
                    "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                    (request["stake"], from_id),
                )
        return "已拒绝。"

    def _expire_requests_conn(self, conn, *client_ids: str) -> None:
        """把已超时的等待请求标记为超时，并退回赌约冻结源石。"""

        ids = [client_id for client_id in dict.fromkeys(client_ids) if client_id]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT * FROM duel_requests
                WHERE status = '等待'
                  AND expires_at <= datetime('now', 'localtime')
                  AND (
                    from_client_id IN ({placeholders})
                    OR to_client_id IN ({placeholders})
                  )
                """,
                (*ids, *ids),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM duel_requests
                WHERE status = '等待'
                  AND expires_at <= datetime('now', 'localtime')
                """
            ).fetchall()

        for row in rows:
            cursor = conn.execute(
                "UPDATE duel_requests SET status = '已超时' WHERE duel_id = ? AND status = '等待'",
                (row["duel_id"],),
            )
            if cursor.rowcount <= 0:
                continue
            if row["mode"] == "bet" and row["stake"] > 0:
                conn.execute(
                    "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                    (row["stake"], row["from_client_id"]),
                )
            conn.execute(
                """
                INSERT INTO game_logs (client_id, action, detail, created_at)
                VALUES (?, '对战超时', ?, datetime('now', 'localtime'))
                """,
                (row["from_client_id"], f"duel_id={row['duel_id']}, stake={row['stake']}"),
            )


service = DuelService(db)

__all__ = ["DuelService", "service"]
