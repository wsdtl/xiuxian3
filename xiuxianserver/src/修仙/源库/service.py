"""源库组件服务。"""

from __future__ import annotations

import sqlite3

from ..common import CoreService, business_day, dt, hint, money, now, ts
from ..constants import BANK_LEVELS, BANK_MAX_LEVEL
from ..sql import db


class SourceVaultService(CoreService):
    """源石仓库和低息系统。"""

    def info(self, client_id: str) -> str:
        """查看源库。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        vault = self._vault(client_id)
        level_conf = BANK_LEVELS[vault["level"]]
        return (
            "☆源库☆\n"
            f"星级:{level_conf['name']}\n"
            f"随身源石:{money(player['source_stones'])}\n"
            f"源库存量:{money(vault['balance'])}/{money(level_conf['limit'])}\n"
            f"今日利息:{money(vault['daily_interest'])}/{money(level_conf['daily_interest_limit'])}"
        )

    def settle(self, client_id: str) -> str:
        """手动结息。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        with self.db.transaction() as conn:
            reward, hours = self._settle_conn(conn, client_id)
        return f"源库结息完成，本次计算 {hours:.2f} 小时，获得源石 {money(reward)}。"

    def upgrade(self, client_id: str) -> str:
        """升级源库。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        with self.db.transaction() as conn:
            self._settle_conn(conn, client_id)
            vault = self._vault_conn(conn, client_id)
            if vault["level"] >= BANK_MAX_LEVEL:
                return hint("源库已经满级。", "可以继续存入源石结息，或把源石用于装备、武器升级。")
            next_level = vault["level"] + 1
            cost = BANK_LEVELS[next_level]["cost"]
            if not self.spend_stones_conn(conn, client_id, cost):
                return hint(f"源石不足，升级需要 {money(cost)}。", "先签到、探险、出售物品，或从源库取出源石。")
            conn.execute("UPDATE source_vaults SET level = ? WHERE client_id = ?", (next_level, client_id))
        return f"源库升级成功，当前为 {BANK_LEVELS[next_level]['name']}。"

    def deposit(self, client_id: str, amount: int) -> str:
        """存入源石。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        if amount <= 0:
            return hint("存入数量必须大于 0。", "发送：存入源石 数量，例如：存入源石 1000")
        with self.db.transaction() as conn:
            self._settle_conn(conn, client_id)
            vault = self._vault_conn(conn, client_id)
            limit = BANK_LEVELS[vault["level"]]["limit"]
            can_deposit = min(amount, limit - vault["balance"])
            if can_deposit <= 0:
                return hint("源库已经存满。", "可以发送：升级源库 提高容量，或发送：取出源石 数量。")
            if not self.spend_stones_conn(conn, client_id, can_deposit):
                return hint("随身源石不足。", "发送：修仙信息 查看随身源石，或先签到、探险、出售物品。")
            conn.execute(
                "UPDATE source_vaults SET balance = balance + ? WHERE client_id = ?",
                (can_deposit, client_id),
            )
        return f"已存入源石 {money(can_deposit)}。"

    def withdraw(self, client_id: str, amount: int) -> str:
        """取出源石。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        if amount <= 0:
            return hint("取出数量必须大于 0。", "发送：取出源石 数量，例如：取出源石 1000")
        with self.db.transaction() as conn:
            self._settle_conn(conn, client_id)
            vault = self._vault_conn(conn, client_id)
            amount = min(amount, vault["balance"])
            if amount <= 0:
                return hint("源库里没有可取出的源石。", "发送：存入源石 数量 后才会有可取余额。")
            conn.execute(
                """
                UPDATE source_vaults SET balance = balance - ? WHERE client_id = ?
                """,
                (amount, client_id),
            )
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (amount, client_id),
            )
        return f"已取出源石 {money(amount)}。"

    def _vault(self, client_id: str) -> dict:
        """读取或创建源库。"""

        vault = self.db.fetch_one("SELECT * FROM source_vaults WHERE client_id = ?", (client_id,))
        if vault:
            return vault
        self.db.execute(
            "INSERT INTO source_vaults (client_id, level, balance, last_settle_at) VALUES (?, 1, 0, ?)",
            (client_id, ts()),
        )
        return self.db.fetch_one("SELECT * FROM source_vaults WHERE client_id = ?", (client_id,)) or {}

    def _settle(self, client_id: str) -> tuple[int, float]:
        """内部结息。"""

        with self.db.transaction() as conn:
            return self._settle_conn(conn, client_id)

    def _vault_conn(self, conn: sqlite3.Connection, client_id: str) -> dict:
        """在当前事务里读取或创建源库。"""

        vault = conn.execute("SELECT * FROM source_vaults WHERE client_id = ?", (client_id,)).fetchone()
        if vault:
            return dict(vault)
        conn.execute(
            "INSERT INTO source_vaults (client_id, level, balance, last_settle_at) VALUES (?, 1, 0, ?)",
            (client_id, ts()),
        )
        vault = conn.execute("SELECT * FROM source_vaults WHERE client_id = ?", (client_id,)).fetchone()
        return dict(vault) if vault else {}

    def _settle_conn(self, conn: sqlite3.Connection, client_id: str) -> tuple[int, float]:
        """在当前事务里结息，避免结息和发放源石分离。"""

        vault = self._vault_conn(conn, client_id)
        day = business_day()
        daily_interest = vault["daily_interest"] if vault["last_interest_day"] == day else 0
        last = dt(vault["last_settle_at"]) or now()
        hours = max(0.0, min(24.0, (now() - last).total_seconds() / 3600))
        conf = BANK_LEVELS[vault["level"]]
        raw_reward = int(vault["balance"] * conf["hour_rate"] * hours)
        reward = max(0, min(raw_reward, conf["daily_interest_limit"] - daily_interest))
        conn.execute(
            """
            UPDATE source_vaults
            SET last_settle_at = ?, last_interest_day = ?, daily_interest = ?,
                balance = balance
            WHERE client_id = ?
            """,
            (ts(), day, daily_interest + reward, client_id),
        )
        if reward:
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (reward, client_id),
            )
        return reward, hours


service = SourceVaultService(db)

__all__ = ["SourceVaultService", "service"]
