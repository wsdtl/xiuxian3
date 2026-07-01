"""银行组件服务。"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from ..common import CoreService, business_day, currency_amount, currency_name, dt, money, now, ts
from ..constants import BANK_LEVELS, BANK_MAX_LEVEL
from ..format_text import T
from ..sql import db


class BankService(CoreService):
    """货币存储和活期收益系统。"""

    def currency(self, client_id: str) -> str:
        """查看随身和银行货币总览。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        account = self._account(client_id)
        raw_stones = int(player["raw_stones"] or 0)
        balance = int(account["balance"] or 0)
        panel = T.panel()
        panel.section("货币")
        panel.line(f"随身{currency_name()}：**{money(raw_stones)}**")
        panel.line(f"银行{currency_name()}：**{money(balance)}**")
        panel.line(f"合计：**{currency_amount(raw_stones + balance)}**")
        buttons = ["银行"]
        star_level = int(account["star_level"] or 1)
        capacity_left = max(0, int(BANK_LEVELS[star_level]["limit"]) - balance)
        if raw_stones > 0 and capacity_left > 0:
            buttons.append(f"存入货币 {min(raw_stones, capacity_left)}")
        if balance > 0:
            buttons.append(f"取出货币 {balance}")
        return T.attach(panel.render(), T.buttons(*buttons))

    def info(self, client_id: str) -> str:
        """查看银行。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        account = self._account(client_id)
        star_level = int(account["star_level"])
        level_conf = BANK_LEVELS[star_level]
        balance = int(account["balance"] or 0)
        limit = int(level_conf["limit"])
        capacity_left = max(0, limit - balance)
        raw_stones = int(player["raw_stones"] or 0)
        preview = self._interest_preview(account)
        panel = T.panel()
        panel.section("银行")
        panel.line(f"星级：{level_conf['name']}")
        panel.line(f"随身{currency_name()}：**{money(raw_stones)}**")
        panel.line(f"银行{currency_name()}：**{money(balance)}/{money(limit)}**｜余量 {money(capacity_left)}")
        daily_interest_claimed = self._display_daily_interest_claimed(account)
        panel.line(f"今日利息：**{currency_amount(daily_interest_claimed)}/{money(level_conf['daily_interest_limit'])}**")
        panel.line(
            f"待结息：**{currency_amount(preview['reward'])}**｜"
            f"已计 {preview['hours']:.2f} 小时"
        )
        panel.line(f"计息：每小时 {float(level_conf['hour_rate']) * 100:.3f}%｜单次最多 24 小时。")
        if star_level < BANK_MAX_LEVEL:
            next_conf = BANK_LEVELS[star_level + 1]
            panel.line(
                f"下级：{next_conf['name']}｜容量 {money(next_conf['limit'])}｜"
                f"日上限 {money(next_conf['daily_interest_limit'])}｜升级费 {currency_amount(next_conf['cost'])}"
            )
        else:
            panel.line("下级：已满级。")
        buttons = ["银行结息"]
        if star_level < BANK_MAX_LEVEL:
            buttons.append("升级银行")
        if raw_stones > 0 and capacity_left > 0:
            buttons.append(f"存入货币 {min(raw_stones, capacity_left)}")
        if balance > 0:
            buttons.append(f"取出货币 {balance}")
        return T.attach(panel.render(), T.buttons(*buttons))

    def settle(self, client_id: str) -> str:
        """手动结息。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        with self.db.transaction() as conn:
            reward, hours = self._settle_conn(conn, client_id)
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '银行结息', ?, ?)",
                (client_id, f"reward={reward}, hours={hours:.2f}", ts()),
            )
        return T.success(f"银行结息完成，本次计算 {hours:.2f} 小时，获得{currency_amount(reward)}。")

    def upgrade(self, client_id: str) -> str:
        """升级银行。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        with self.db.transaction() as conn:
            self._settle_conn(conn, client_id)
            account = self._account_conn(conn, client_id)
            if account["star_level"] >= BANK_MAX_LEVEL:
                return T.hint("银行已经满级。", f"可以继续存入{currency_name()}结息，或把{currency_name()}用于装备、武器升级。")
            next_star_level = account["star_level"] + 1
            cost = BANK_LEVELS[next_star_level]["cost"]
            if not self.spend_stones_conn(conn, client_id, cost):
                return T.hint(f"{currency_name()}不足，升级需要 {money(cost)}。", f"先签到、探险、出售物品，或从银行取出{currency_name()}。")
            conn.execute("UPDATE bank_accounts SET star_level = ? WHERE client_id = ?", (next_star_level, client_id))
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '升级银行', ?, ?)",
                (client_id, f"star_level={next_star_level}, cost={cost}", ts()),
            )
        return T.success(f"银行升级成功，当前为 {BANK_LEVELS[next_star_level]['name']}。")

    def deposit(self, client_id: str, amount: int) -> str:
        """存入货币。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        if amount <= 0:
            return T.hint("存入数量必须大于 0。", "发送：存入货币 数量，例如：存入货币 1000<银行><银行结息>")
        with self.db.transaction() as conn:
            account = self._account_conn(conn, client_id)
            limit = BANK_LEVELS[account["star_level"]]["limit"]
            can_deposit = min(amount, limit - account["balance"])
            if can_deposit <= 0:
                return T.hint("银行已经存满。", "可以发送：升级银行 提高容量，或发送：取出货币 数量。<升级银行><银行><银行结息>")
            if not self.spend_stones_conn(conn, client_id, can_deposit):
                return T.hint(f"随身{currency_name()}不足。", f"发送：修仙信息 查看随身{currency_name()}，或先签到、探险、出售物品。<签到><探险><银行><银行结息>")
            new_balance = int(account["balance"]) + can_deposit
            last_settle_at = self._rebased_settle_at_after_deposit(account, new_balance)
            conn.execute(
                "UPDATE bank_accounts SET balance = ?, last_settle_at = ? WHERE client_id = ?",
                (new_balance, last_settle_at, client_id),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '存入货币', ?, ?)",
                (client_id, f"amount={can_deposit}", ts()),
            )
        return T.attach(f"已存入：{currency_amount(can_deposit)}。", "<银行><银行结息>")

    def withdraw(self, client_id: str, amount: int) -> str:
        """取出货币。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        if amount <= 0:
            return T.hint("取出数量必须大于 0。", "发送：取出货币 数量，例如：取出货币 1000<银行><银行结息>")
        with self.db.transaction() as conn:
            self._settle_conn(conn, client_id)
            account = self._account_conn(conn, client_id)
            amount = min(amount, account["balance"])
            if amount <= 0:
                return T.hint(f"银行里没有可取出的{currency_name()}。", "发送：存入货币 数量 后才会有可取余额。<银行><银行结息>")
            conn.execute(
                """
                UPDATE bank_accounts SET balance = balance - ? WHERE client_id = ?
                """,
                (amount, client_id),
            )
            conn.execute(
                "UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?",
                (amount, client_id),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '取出货币', ?, ?)",
                (client_id, f"amount={amount}", ts()),
            )
        return T.attach(f"已取出：{currency_amount(amount)}。", "<银行><银行结息>")

    def _account(self, client_id: str) -> dict:
        """读取或创建银行账户。"""

        account = self.db.fetch_one("SELECT * FROM bank_accounts WHERE client_id = ?", (client_id,))
        if account:
            return account
        self.db.execute(
            "INSERT INTO bank_accounts (client_id, star_level, balance, last_settle_at) VALUES (?, 1, 0, ?)",
            (client_id, ts()),
        )
        return self.db.fetch_one("SELECT * FROM bank_accounts WHERE client_id = ?", (client_id,)) or {}

    def _account_conn(self, conn: sqlite3.Connection, client_id: str) -> dict:
        """在当前事务里读取或创建银行账户。"""

        account = conn.execute("SELECT * FROM bank_accounts WHERE client_id = ?", (client_id,)).fetchone()
        if account:
            return dict(account)
        conn.execute(
            "INSERT INTO bank_accounts (client_id, star_level, balance, last_settle_at) VALUES (?, 1, 0, ?)",
            (client_id, ts()),
        )
        account = conn.execute("SELECT * FROM bank_accounts WHERE client_id = ?", (client_id,)).fetchone()
        return dict(account) if account else {}

    def _settle_conn(self, conn: sqlite3.Connection, client_id: str) -> tuple[int, float]:
        """在当前事务里结息，避免结息和发放货币分离。"""

        account = self._account_conn(conn, client_id)
        day = business_day()
        daily_interest_claimed = account["daily_interest_claimed"] if account["last_interest_day"] == day else 0
        last = dt(account["last_settle_at"]) or now()
        hours = max(0.0, min(24.0, (now() - last).total_seconds() / 3600))
        conf = BANK_LEVELS[account["star_level"]]
        raw_reward = int(account["balance"] * conf["hour_rate"] * hours)
        reward = max(0, min(raw_reward, conf["daily_interest_limit"] - daily_interest_claimed))
        conn.execute(
            """
            UPDATE bank_accounts
            SET last_settle_at = ?, last_interest_day = ?, daily_interest_claimed = ?
            WHERE client_id = ?
            """,
            (ts(), day, daily_interest_claimed + reward, client_id),
        )
        if reward:
            conn.execute(
                "UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?",
                (reward, client_id),
            )
        return reward, hours

    @staticmethod
    def _display_daily_interest_claimed(vault: dict) -> int:
        """面板展示用今日利息；跨业务日后先按 0 展示。"""

        if vault.get("last_interest_day") != business_day():
            return 0
        return max(0, int(vault.get("daily_interest_claimed", 0) or 0))

    @staticmethod
    def _interest_preview(account: dict) -> dict:
        """预览本次可结息数值，不修改账本。"""

        current = now()
        day = business_day(current)
        star_level = int(account.get("star_level", 1) or 1)
        conf = BANK_LEVELS.get(star_level, BANK_LEVELS[1])
        claimed = int(account.get("daily_interest_claimed", 0) or 0) if account.get("last_interest_day") == day else 0
        daily_left = max(0, int(conf["daily_interest_limit"]) - claimed)
        last = dt(account.get("last_settle_at")) or current
        hours = max(0.0, min(24.0, (current - last).total_seconds() / 3600))
        balance = max(0, int(account.get("balance", 0) or 0))
        raw_reward = int(balance * float(conf["hour_rate"]) * hours)
        reward = max(0, min(raw_reward, daily_left))
        return {"reward": reward, "hours": hours, "daily_left": daily_left, "raw_reward": raw_reward}

    @staticmethod
    def _rebased_settle_at_after_deposit(vault: dict, new_balance: int) -> str:
        """存入时折算计息起点，保留旧余额已经累计的结息进度。"""

        old_balance = max(0, int(vault.get("balance", 0)))
        current = now()
        if old_balance <= 0 or new_balance <= 0:
            return ts(current)

        last = dt(vault.get("last_settle_at")) or current
        hours = max(0.0, min(24.0, (current - last).total_seconds() / 3600))
        if hours <= 0:
            return ts(current)

        rebased_hours = min(24.0, hours * old_balance / new_balance)
        return ts(current - timedelta(hours=rebased_hours))


service = BankService(db)

__all__ = ["BankService", "service"]
