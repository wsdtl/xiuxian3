"""玩家对战组件服务。"""

from __future__ import annotations

from ..combat_core import service as combat_service
from ..common import CoreService, hint, money, split_words, to_int, ts
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

        target_ref, stake = self._parse_bet_message(message)
        if not target_ref or stake <= 0:
            return hint("赌约格式不正确。", "发送：赌约 源石数量 对方名称，也可以把 CQ/at 放最后。")
        return self._create_request(client_id, target_ref, "bet", stake)

    def duel(self, client_id: str, message: str) -> str:
        """发起决斗；有金额走赌约，没有金额走无押注切磋。"""

        target_ref, stake = self._parse_bet_message(message)
        if target_ref and stake > 0:
            return self._create_request(client_id, target_ref, "bet", stake)
        return self._create_request(client_id, message, "spar", 0)

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
        self.cleanup_battle_records()
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
            return hint("暂无决斗记录。", "发送：切磋 对方名称，或发送：赌约 源石数量 对方名称。")
        return "\n".join(row["summary"] for row in rows)

    def _create_request(self, client_id: str, message: str, mode: str, stake: int) -> str:
        """创建对战请求。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        target_id = self.resolve_player_ref(message)
        if not target_id:
            return hint("没有找到对方。", "发送：切磋 对方名称，或使用 CQ/at 指定对方。")
        target, error = self.require_player(target_id)
        if error:
            return hint("对方还没有创建用户。", "请对方先发送：创建用户 名称")
        if target_id == client_id:
            return hint("不能挑战自己。", "请输入其他玩家名称，或使用 CQ/at 指定对方。")
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
        accept_cmd = "接受切磋" if mode == "spar" else "接受赌约"
        reject_cmd = "拒绝切磋" if mode == "spar" else "拒绝赌约"
        from_name = str(player["display_name"])
        return (
            f"已向 {self.format_player_name(target_id)} 发起{mode_text}，等待对方处理。\n"
            f"对方 10 分钟内发送：{accept_cmd} {from_name}\n"
            f"如果不接受，发送：{reject_cmd} {from_name}"
        )

    def _accept(self, client_id: str, message: str, mode: str) -> str:
        """接受对战请求并结算。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
        from_id = self.resolve_player_ref(message)
        if not from_id:
            return hint("没有找到发起人。", "发送：接受切磋 发起人名称，或使用 CQ/at 指定发起人。")
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
            return hint("没有找到待接受的请求。", "确认对方名称是否正确，或让对方重新发起切磋/赌约。")
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
        settlement = ""
        if mode == "bet":
            settlement = f"赌约结算：胜者获得 {money(request['stake'] * 2 - fee)}，手续费 {money(fee)}。"
        return self._duel_log_block(
            title="切磋结束" if mode == "spar" else "赌约决斗结束",
            result=result,
            settlement=settlement,
        )

    def _duel_log_block(self, *, title: str, result: dict, settlement: str = "") -> str:
        """把切磋/赌约整理成逐回合代码块。"""

        lines = [
            title,
            result["summary"],
            "",
            "一、战斗明细",
        ]
        actions = result.get("actions")
        if isinstance(actions, list) and actions:
            for action in actions:
                lines.extend(self._duel_round_lines(action))
        else:
            lines.append("无逐次出手记录。")

        left_id = result.get("left_id", "")
        right_id = result.get("right_id", "")
        lines.extend(
            [
                "",
                "二、最终结算",
                f"胜者：{self.format_player_name(result.get('winner_id', ''))}",
                f"败者：{self.format_player_name(result.get('loser_id', ''))}",
                (
                    f"{self.format_player_name(left_id)}：血气 {result.get('left_hp_left', 0)}/{result.get('left_max_hp', 0)}，"
                    f"精神 {result.get('left_mp_left', 0)}/{result.get('left_max_mp', 0)}"
                ),
                (
                    f"{self.format_player_name(right_id)}：血气 {result.get('right_hp_left', 0)}/{result.get('right_max_hp', 0)}，"
                    f"精神 {result.get('right_mp_left', 0)}/{result.get('right_max_mp', 0)}"
                ),
            ]
        )
        if settlement:
            lines.append(settlement)
        return "```javascript\r\n" + "\r\n".join(lines) + "\r\n```"

    def _parse_bet_message(self, message: str) -> tuple[str, int]:
        """解析赌约参数；金额和对方顺序可以互换。"""

        parts = split_words(message)
        if len(parts) < 2:
            return "", 0

        fallback: tuple[str, int] = ("", 0)
        for index, part in enumerate(parts):
            stake = to_int(part)
            if stake <= 0:
                continue

            target_ref = " ".join(parts[:index] + parts[index + 1 :]).strip()
            if not target_ref:
                continue

            if not fallback[0]:
                fallback = (target_ref, stake)
            if self.resolve_player_ref(target_ref):
                return target_ref, stake
        return fallback

    def _duel_round_lines(self, action: dict) -> list[str]:
        """整理一回合双方出手。"""

        lines = [f"第 {int(action.get('round', 0))} 回合"]
        for side in ("left", "right"):
            attack = action.get(side)
            if not isinstance(attack, dict):
                continue
            lines.append("  " + self._duel_attack_text(attack))
        return lines

    def _duel_attack_text(self, attack: dict) -> str:
        """整理一次玩家出手。"""

        actor = self.format_player_name(str(attack.get("actor_id", "")))
        target = self.format_player_name(str(attack.get("target_id", "")))
        if attack.get("skill_used"):
            move = f"技能「{attack.get('skill_name', '')}」"
            cost = f"，消耗精神 {int(attack.get('mp_cost', 0))}"
        else:
            move = "普通攻击"
            cost = ""
        if attack.get("dodged"):
            return (
                f"{actor} 出手：{move} 被 {target} 闪过{cost}；"
                f"{target} 血气 {attack.get('target_hp_left', 0)}，精神 {attack.get('target_mp_left', 0)}"
            )
        combo = int(attack.get("combo_damage", 0))
        combo_text = f"，连击追加 {combo}" if combo > 0 else ""
        steal = int(attack.get("life_steal", 0))
        steal_text = f"，吸血 +{steal}" if steal > 0 else ""
        return (
            f"{actor} 出手：{move}，对 {target} 造成 {int(attack.get('damage', 0))} 伤害"
            f"{combo_text}{steal_text}{cost}；"
            f"{target} 血气 {attack.get('target_hp_left', 0)}，精神 {attack.get('target_mp_left', 0)}"
        )

    def _reject(self, client_id: str, message: str, mode: str) -> str:
        """拒绝对战请求。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        from_id = self.resolve_player_ref(message)
        if not from_id:
            return hint("没有找到发起人。", "发送：拒绝切磋 发起人名称，或使用 CQ/at 指定发起人。")
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
                return hint("没有找到待拒绝的请求。", "确认对方名称是否正确，或忽略已超时的请求。")
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
