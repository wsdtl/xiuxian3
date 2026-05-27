"""武器组件服务。"""

from __future__ import annotations

from ..format_text import T

from ..common import (
    business_day,
    dump_json,
    enchant_label_name,
    load_json,
    money,
    parse_weapon_ref,
    quality_factor,
    split_words,
    to_int,
    ts,
    weapon_label_name,
)
from ..rules import (
    book_recycle_price_rate,
    book_recycle_single_cap,
    weapon_enchant_slots,
    weapon_recycle_price_rate,
    weapon_recycle_single_cap,
    weapon_upgrade_cost,
)
from ..sql import db
from ..weapon_core import WeaponCore


class WeaponService(WeaponCore):
    """武器持有、切换、升级、附魔和掉落。"""

    def list_weapons(self, client_id: str) -> str:
        """查看武器简表。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.ensure_starter_weapon(client_id)
        rows = self.weapons(client_id)
        panel = T.panel()
        panel.section(f"武器 共{len(rows)}把")
        for row in rows:
            panel.line(self._weapon_summary_text(row))
        equipped = next((row for row in rows if int(row["equipped"])), None)
        if not equipped:
            return panel.render()
        return panel.render() + f"<升级武器 {equipped['weapon_id']}:武器升级>"

    def detail(self, client_id: str, message: str) -> str:
        """查看单把武器详情。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        player = self.recalc_player(client_id)
        self.ensure_starter_weapon(client_id)

        weapon_id = parse_weapon_ref(message)
        if weapon_id <= 0:
            return T.hint("查看武器格式不正确。", "发送：查看武器 武器ID，例如：查看武器 1")

        rows = self.weapons(client_id)
        weapon = next((row for row in rows if int(row["weapon_id"]) == weapon_id), None)
        if not weapon:
            return T.hint("没有找到这把武器。", "发送：武器 查看自己的武器 ID，再发送：查看武器 武器ID。")

        panel = T.panel()
        panel.section("武器详情")
        panel.lines(self._weapon_detail_lines(client_id, player, weapon, len(rows)))
        return panel.render()

    def legend(self, client_id: str, message: str) -> str:
        """查看一把武器的完整传奇记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.ensure_starter_weapon(client_id)
        weapon_id = parse_weapon_ref(message)
        if weapon_id <= 0:
            return T.hint("缺少武器 ID。", "发送：武器 查看编号，再发送：武器传奇 武器ID<武器>")
        weapon = self.weapon(client_id, weapon_id)
        if not weapon:
            return T.hint(f"没有找到武器 #{weapon_id}。", "发送：武器 查看自己的武器列表。<武器>")
        with self.db.transaction() as conn:
            self.record_weapon_created_conn(conn, client_id, weapon_id)
        legend = self.db.fetch_one("SELECT * FROM weapon_legends WHERE weapon_id = ?", (weapon_id,))
        weapon["legend"] = dict(legend) if legend else {}
        return self._weapon_legend_text(weapon)

    def switch(self, client_id: str, message: str) -> str:
        """切换武器。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        weapon_id = to_int(message)
        weapon = self.weapon(client_id, weapon_id)
        if not weapon:
            return T.hint("没有找到这把武器。", "发送：武器 查看自己的武器 ID。<武器>")
        with self.db.transaction() as conn:
            conn.execute("UPDATE player_weapons SET equipped = 0 WHERE owner_id = ?", (client_id,))
            conn.execute("UPDATE player_weapons SET equipped = 1 WHERE owner_id = ? AND weapon_id = ?", (client_id, weapon_id))
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '切换武器', ?, ?)",
                (client_id, f"weapon_id={weapon_id}, name={weapon_label_name(weapon)}", ts()),
            )
        return f"已切换武器：{weapon_label_name(weapon)}。"

    def upgrade(self, client_id: str, message: str) -> str:
        """升级武器。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        weapon_id = to_int(message)
        with self.db.transaction() as conn:
            weapon = conn.execute(
                """
                SELECT w.*, d.name
                FROM player_weapons w
                JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
                WHERE w.owner_id = ? AND w.weapon_id = ?
                """,
                (client_id, weapon_id),
            ).fetchone()
            if not weapon:
                return T.hint("没有找到这把武器。", "发送：武器 查看自己的武器 ID。<武器>")
            if weapon["level"] >= weapon["max_level"]:
                return T.hint("这把武器已经到达自身等级上限。", "可以切换或继续探险获取更高上限武器。")
            next_level = weapon["level"] + 1
            cost = weapon_upgrade_cost(next_level, quality_factor(weapon["quality"]))
            if not self.spend_stones_conn(conn, client_id, cost):
                return T.hint(f"源石不足，升级需要 {money(cost)}。", "发送：源库 查看存量，或通过签到、探险、出售物品获取源石。<签到><探险>")
            attack = weapon["attack"] + max(1, int(weapon["attack"] * 0.04))
            slots = weapon_enchant_slots(weapon["max_level"], next_level)
            conn.execute(
                """
                UPDATE player_weapons
                SET level = ?, attack = ?, enchant_slots = ?
                WHERE weapon_id = ? AND owner_id = ?
                """,
                (next_level, attack, slots, weapon_id, client_id),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '升级武器', ?, ?)",
                (
                    client_id,
                    f"weapon_id={weapon_id}, level={next_level}, attack={attack}, cost={cost}, slots={slots}",
                    ts(),
                ),
            )
        return (
            f"升级成功，{weapon_label_name(weapon)} 等级 {next_level}/{weapon['max_level']}，"
            f"攻击 {attack}，附魔栏 {slots}。"
        )

    def recycle(self, client_id: str, message: str) -> str:
        """在武器回收地点处理备用武器。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        location = self.recycle_location(player["location_name"], "weapon")
        if not location:
            return T.hint("当前位置不是武器回收地点。", "发送：商场列表 查看地点，再发送：导航 铸剑阁<导航 铸剑阁>")

        text = message.strip()
        if not text:
            return self._recycle_preview(client_id, location)

        with self.db.transaction() as conn:
            recycle_all = self._is_recycle_all(text)
            weapon_ids = self._recyclable_weapon_ids_conn(conn, client_id) if recycle_all else self._parse_recycle_weapon_ids(text)
            if not weapon_ids:
                if recycle_all:
                    return T.hint("当前没有可批量回收的备用武器。", "已装备武器和最后一把武器不能回收；发送：武器 查看列表。<武器>")
                return T.hint("武器回收格式不正确。", "发送：回收武器 武器ID，或一次发送：回收武器 12 13 14。")

            weapons = self._weapon_rows_for_recycle_conn(conn, client_id, weapon_ids)
            missing_ids = [weapon_id for weapon_id in weapon_ids if weapon_id not in weapons]
            if missing_ids:
                return T.hint(f"没有找到武器：{self._format_weapon_ids(missing_ids)}。", "发送：武器 查看自己的武器 ID。<武器>")

            equipped_ids = [weapon_id for weapon_id in weapon_ids if int(weapons[weapon_id]["equipped"])]
            if equipped_ids:
                return T.hint(f"已装备武器不能回收：{self._format_weapon_ids(equipped_ids)}。", "先切换到其他武器，再回收备用武器。<武器>")

            count = conn.execute(
                "SELECT COUNT(*) AS total FROM player_weapons WHERE owner_id = ?",
                (client_id,),
            ).fetchone()
            total_count = int(count["total"])
            if total_count - len(weapon_ids) < 1:
                return T.hint("不能回收最后一把武器。", "至少保留一把自用武器，避免无法探险战斗。")

            today_income = self._today_recycle_income_conn(conn, client_id)
            records = []
            total_value = 0
            for weapon_id in weapon_ids:
                record = self._recycle_weapon_conn(
                    conn,
                    client_id,
                    dict(weapons[weapon_id]),
                    location,
                    int(player["level"]),
                    today_income,
                )
                records.append(record)
                total_value += int(record["value"])
                today_income += int(record["value"])

            conn.execute("UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?", (total_value, client_id))

        return self._format_recycle_result(records)

    def recycle_book(self, client_id: str, message: str) -> str:
        """在回收地点处理纳戒里的未附魔技能书。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        location = self.recycle_location(player["location_name"], "book")
        if not location:
            return T.hint("当前位置不是技能书回收地点。", "发送：商场列表 查看地点，再发送：导航 藏经阁<导航 藏经阁>")

        text = message.strip()
        if not text:
            return self._book_recycle_preview(client_id, location)
        if self._is_book_recycle_all(text):
            return self._recycle_all_books(client_id, player, location)

        book_name, quantity = self._parse_book_recycle_message(text)
        if quantity <= 0:
            return T.hint("技能书回收格式不正确。", "发送：回收技能书 技能书名 数量，例如：回收技能书 风刃书 1")
        book = self.equipment_item_def_by_name(book_name)
        if not book or book["category"] != "技能书":
            return T.hint(f"没有找到技能书：{book_name}。", "发送：纳戒 查看已有技能书名称。<纳戒>")

        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT quantity FROM ring_items
                WHERE client_id = ? AND equipment_item_id = ?
                """,
                (client_id, book["equipment_item_id"]),
            ).fetchone()
            owned = int(row["quantity"]) if row else 0
            if owned < quantity:
                return T.hint(f"纳戒里 {book['name']} 只有 {owned} 本。", "发送：纳戒 查看库存后再回收。<纳戒>")

            today_income = self._today_book_recycle_income_conn(conn, client_id)
            quote = self._book_recycle_quote(
                book,
                quantity,
                float(location["price_factor"]),
                int(player["level"]),
                today_income,
            )
            if not self.remove_ring_conn(conn, client_id, book["equipment_item_id"], quantity):
                return T.hint("技能书库存已变化，回收失败。", "发送：纳戒 查看当前库存后再试。<纳戒>")
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (quote["value"], client_id),
            )
            conn.execute(
                """
                INSERT INTO book_recycle_records (
                    client_id, book_id, book_name, quality, quantity,
                    raw_value, capped_value, price_rate, total_price,
                    location_name, business_day, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    book["equipment_item_id"],
                    book["name"],
                    book["quality"],
                    quantity,
                    quote["raw_value"],
                    quote["capped_value"],
                    quote["rate"],
                    quote["value"],
                    location["name"],
                    business_day(),
                    ts(),
                ),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '技能书回收', ?, ?)",
                (client_id, f"book={book['equipment_item_id']}, quantity={quantity}, stones={quote['value']}", ts()),
            )
        return (
            f"回收成功：{book['name']} x{quantity}，"
            f"获得源石 {money(quote['value'])}，当前倍率 {int(quote['rate'] * 100)}%。"
        )

    def _recycle_all_books(self, client_id: str, player: dict, location: dict) -> str:
        """一键回收纳戒里的全部未附魔技能书。"""

        records: list[dict[str, object]] = []
        total_value = 0
        total_quantity = 0
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT r.equipment_item_id, r.quantity, e.name, e.quality
                FROM ring_items r
                JOIN equipment_item_defs e ON e.equipment_item_id = r.equipment_item_id
                WHERE r.client_id = ? AND r.quantity > 0 AND e.category = '技能书'
                ORDER BY e.quality, e.name
                """,
                (client_id,),
            ).fetchall()
            if not rows:
                return T.hint(f"{location['name']}可以回收纳戒里的未附魔技能书，但你当前没有技能书。", "继续探险、挑战虫洞或首领获取技能书。")

            today_income = self._today_book_recycle_income_conn(conn, client_id)
            for row in rows:
                quantity = int(row["quantity"])
                quote = self._book_recycle_quote(
                    row,
                    quantity,
                    float(location["price_factor"]),
                    int(player["level"]),
                    today_income,
                )
                if not self.remove_ring_conn(conn, client_id, row["equipment_item_id"], quantity):
                    continue
                conn.execute(
                    """
                    INSERT INTO book_recycle_records (
                        client_id, book_id, book_name, quality, quantity,
                        raw_value, capped_value, price_rate, total_price,
                        location_name, business_day, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        row["equipment_item_id"],
                        row["name"],
                        row["quality"],
                        quantity,
                        quote["raw_value"],
                        quote["capped_value"],
                        quote["rate"],
                        quote["value"],
                        location["name"],
                        business_day(),
                        ts(),
                    ),
                )
                today_income += int(quote["value"])
                total_value += int(quote["value"])
                total_quantity += quantity
                records.append(
                    {
                        "name": row["name"],
                        "quality": row["quality"],
                        "quantity": quantity,
                        "value": int(quote["value"]),
                        "rate": float(quote["rate"]),
                    }
                )

            if not records:
                return T.hint("技能书库存已变化，回收失败。", "发送：纳戒 查看当前库存后再试。<纳戒>")
            conn.execute("UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?", (total_value, client_id))
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '技能书批量回收', ?, ?)",
                (client_id, f"quantity={total_quantity}, stones={total_value}", ts()),
            )

        panel = T.panel()
        panel.section("技能书批量回收")
        panel.line(f"回收 **{total_quantity}** 本，获得源石 **{money(total_value)}**。")
        for record in records:
            panel.line(
                f"{record['name']}[{record['quality']}] x{record['quantity']}｜"
                f"收入 **{money(record['value'])}**｜倍率 {int(float(record['rate']) * 100)}%"
            )
        return panel.render()

    def enchant(self, client_id: str, message: str) -> str:
        """给武器附魔。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        parts = split_words(message)
        if len(parts) < 2:
            return T.hint("附魔格式不正确。", "发送：附魔武器 武器ID 技能书名，例如：附魔武器 1 破甲残卷")
        weapon_id = to_int(parts[0])
        book_name = " ".join(parts[1:])
        book = self.equipment_item_def_by_name(book_name)
        if not book or book["category"] != "技能书":
            return T.hint(f"没有找到技能书：{book_name}。", "发送：纳戒 查看已有技能书。<纳戒>")
        effect = load_json(book["effect"], {})
        enchant_id = effect.get("enchant_id")
        enchant = self.db.fetch_one("SELECT * FROM weapon_enchants WHERE enchant_id = ?", (enchant_id,))
        if not enchant:
            return T.hint("这本技能书暂时不能附魔。", "换一本技能书，或发送：查看修仙物品 技能书名 查看说明。")
        with self.db.transaction() as conn:
            weapon = conn.execute(
                """
                SELECT w.*, d.name
                FROM player_weapons w
                JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
                WHERE w.owner_id = ? AND w.weapon_id = ?
                """,
                (client_id, weapon_id),
            ).fetchone()
            if not weapon:
                return T.hint("没有找到这把武器。", "发送：武器 查看自己的武器 ID。<武器>")
            current = load_json(weapon["enchant_effects"], [])
            if len(current) >= weapon["enchant_slots"]:
                return T.hint("这把武器没有空余附魔栏。", "升级武器可能解锁附魔栏，或换一把更高上限武器。")
            if not self.remove_ring_conn(conn, client_id, book["equipment_item_id"], 1):
                return T.hint(f"纳戒里没有 {book['name']}。", "发送：纳戒 确认库存，或继续探险获取技能书。<纳戒>")
            current.append(enchant_id)
            conn.execute(
                "UPDATE player_weapons SET enchant_effects = ? WHERE weapon_id = ? AND owner_id = ?",
                (dump_json(current), weapon_id, client_id),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '附魔武器', ?, ?)",
                (client_id, f"weapon_id={weapon_id}, book={book['equipment_item_id']}, enchant={enchant_id}", ts()),
            )
        return f"附魔成功：{weapon_label_name(weapon)} 获得 {book['name']}。"

    def _recycle_preview(self, client_id: str, location: dict) -> str:
        """展示当前可回收武器和估价。"""

        self.ensure_starter_weapon(client_id)
        rows = self.weapons(client_id)
        spares = [row for row in rows if not int(row["equipped"])]
        if not spares:
            return T.hint(
                f"{location['name']}可以稳定回收备用武器，但你当前没有可回收武器。",
                "继续探险获取备用武器；已装备武器和最后一把武器不能回收。",
            )

        player = self.player(client_id) or {}
        today_income = self._today_recycle_income(client_id)
        rate = weapon_recycle_price_rate(int(player.get("level", 1)), today_income)
        panel = T.panel()
        panel.section(f"{location['name']}武器回收")
        panel.line(f"当前倍率：**{int(rate * 100)}%**")
        panel.line(f"今日已回收：**{money(today_income)}**。估价会随今日回收收入降低。")
        panel.line("已装备武器和最后一把武器不能回收。")
        for row in spares:
            quote = self._recycle_quote(
                row,
                float(location["price_factor"]),
                int(player.get("level", 1)),
                today_income,
            )
            enchants = len(load_json(row["enchant_effects"], []))
            panel.line(
                f"#{row['weapon_id']} {weapon_label_name(row)}[{row['quality']}] "
                f"等级:{row['level']}/{row['max_level']} 攻击:{row['attack']} "
                f"附魔:{enchants}/{row['enchant_slots']} 估价：**{money(quote['value'])}**"
            )
        panel.line("批量回收：回收武器 12 13 14；回收全部备用武器：回收武器 全部")
        return panel.render()

    @staticmethod
    def _is_recycle_all(message: str) -> bool:
        """是否回收全部备用武器。"""

        return message.strip() in {"全部", "全部备用", "全回收", "一键回收"}

    @staticmethod
    def _parse_recycle_weapon_ids(message: str) -> list[int]:
        """解析一个或多个武器 ID。"""

        normalized = message
        for separator in ("，", ",", "、", "；", ";"):
            normalized = normalized.replace(separator, " ")

        weapon_ids = []
        for token in split_words(normalized):
            if token in {"武器", "武器ID"}:
                continue
            weapon_id = parse_weapon_ref(token)
            if weapon_id <= 0:
                return []
            if weapon_id not in weapon_ids:
                weapon_ids.append(weapon_id)
        return weapon_ids

    @staticmethod
    def _format_weapon_ids(weapon_ids: list[int]) -> str:
        """把多个武器 ID 排成玩家可读文本。"""

        return "、".join(f"#{weapon_id}" for weapon_id in weapon_ids)

    @staticmethod
    def _recyclable_weapon_ids_conn(conn, client_id: str) -> list[int]:
        """读取全部备用武器 ID。"""

        rows = conn.execute(
            """
            SELECT weapon_id
            FROM player_weapons
            WHERE owner_id = ? AND equipped = 0
            ORDER BY weapon_id
            """,
            (client_id,),
        ).fetchall()
        return [int(row["weapon_id"]) for row in rows]

    @staticmethod
    def _weapon_rows_for_recycle_conn(conn, client_id: str, weapon_ids: list[int]) -> dict[int, dict]:
        """读取本次回收涉及的武器行。"""

        rows = {}
        for weapon_id in weapon_ids:
            row = conn.execute(
                """
                SELECT w.*, d.name
                FROM player_weapons w
                JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
                WHERE w.owner_id = ? AND w.weapon_id = ?
                """,
                (client_id, weapon_id),
            ).fetchone()
            if row:
                rows[weapon_id] = dict(row)
        return rows

    def _recycle_weapon_conn(
        self,
        conn,
        client_id: str,
        weapon: dict,
        location: dict,
        player_level: int,
        today_income: int,
    ) -> dict[str, object]:
        """在事务中回收一把武器并写入回收流水。"""

        weapon_id = int(weapon["weapon_id"])
        quote = self._recycle_quote(weapon, float(location["price_factor"]), player_level, today_income)
        value = int(quote["value"])
        conn.execute("DELETE FROM weapon_enchant_names WHERE weapon_id = ?", (weapon_id,))
        conn.execute("DELETE FROM player_weapons WHERE owner_id = ? AND weapon_id = ?", (client_id, weapon_id))
        conn.execute(
            """
            INSERT INTO weapon_recycle_records (
                client_id, weapon_id, weapon_name, quality, level, max_level,
                raw_value, capped_value, price_rate, total_price,
                location_name, business_day, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                weapon_id,
                weapon_label_name(weapon),
                weapon["quality"],
                int(weapon["level"]),
                int(weapon["max_level"]),
                quote["raw_value"],
                quote["capped_value"],
                quote["rate"],
                value,
                location["name"],
                business_day(),
                ts(),
            ),
        )
        conn.execute(
            "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '武器回收', ?, ?)",
            (client_id, f"weapon_id={weapon_id}, stones={value}, rate={quote['rate']:.2f}", ts()),
        )
        return {
            "weapon_id": weapon_id,
            "name": weapon_label_name(weapon),
            "quality": weapon["quality"],
            "value": value,
            "rate": float(quote["rate"]),
        }

    @staticmethod
    def _format_recycle_result(records: list[dict[str, object]]) -> str:
        """格式化单把或批量武器回收结果。"""

        if len(records) == 1:
            record = records[0]
            return (
                f"回收成功：#{record['weapon_id']} {record['name']}[{record['quality']}]，"
                f"获得源石 {money(int(record['value']))}，当前倍率 {int(float(record['rate']) * 100)}%。"
            )

        total_value = sum(int(record["value"]) for record in records)
        panel = T.panel()
        panel.section("武器批量回收")
        panel.line(f"回收成功：**{len(records)}** 把，获得源石 **{money(total_value)}**。")
        for record in records:
            panel.line(
                f"#{record['weapon_id']} {record['name']}[{record['quality']}] "
                f"-> {money(int(record['value']))}，倍率 {int(float(record['rate']) * 100)}%"
            )
        return panel.render()

    def _enchant_text(self, weapon_id: int, enchant_ids: object) -> str:
        """把武器已附魔技能书按槽位展示出来。"""

        if not isinstance(enchant_ids, list) or not enchant_ids:
            return ""
        custom_rows = self.db.fetch_all(
            "SELECT slot_no, custom_name FROM weapon_enchant_names WHERE weapon_id = ?",
            (weapon_id,),
        )
        custom_names = {int(row["slot_no"]): row["custom_name"] for row in custom_rows}
        labels = []
        for slot_no, enchant_id in enumerate(enchant_ids, start=1):
            row = self.db.fetch_one("SELECT name FROM weapon_enchants WHERE enchant_id = ?", (enchant_id,))
            base_name = row["name"] if row else str(enchant_id)
            labels.append(f"{slot_no}.{enchant_label_name(base_name, custom_names.get(slot_no, ''))}")
        return "（" + "、".join(labels) + "）"

    def _weapon_summary_text(self, weapon: dict) -> str:
        """格式化武器简表中的一行。"""

        mark = "已装备" if int(weapon["equipped"]) else "备用"
        skill = self.skill(weapon["skill_id"])
        skill_name = self.weapon_skill_label(int(weapon["weapon_id"]), skill)
        enchant_ids = load_json(weapon["enchant_effects"], [])
        if not isinstance(enchant_ids, list):
            enchant_ids = []
        return (
            f"({weapon['weapon_id']}) {weapon_label_name(weapon)}[{weapon['quality']}] {mark} "
            f"等级:{weapon['level']}/{weapon['max_level']} 攻击:{weapon['attack']} "
            f"技能:{skill_name} 附魔:{len(enchant_ids)}/{weapon['enchant_slots']}"
            f"{self._enchant_text(int(weapon['weapon_id']), enchant_ids)}"
        )

    def _weapon_detail_lines(self, client_id: str, player: dict, weapon: dict, total_count: int) -> list[str]:
        """格式化一把武器的完整展示。"""

        skill = self.skill(weapon["skill_id"])
        enchant_ids = load_json(weapon["enchant_effects"], [])
        if not isinstance(enchant_ids, list):
            enchant_ids = []
        effects = self._merge_effects(self.equipment_bonuses(client_id), self.weapon_effects_from_ids(enchant_ids))
        combat_info = self.combat_profile(int(player["level"]), weapon, skill, effects)
        used_slots = len(enchant_ids)
        unlocked_slots = int(weapon["enchant_slots"])
        potential_slots = weapon_enchant_slots(int(weapon["max_level"]), int(weapon["max_level"]))
        status = "已装备" if int(weapon["equipped"]) else "备用"
        next_cost = self._next_upgrade_text(weapon)
        recycle_text = self._recycle_state_text(weapon, total_count)
        legend_text = self._legend_text(int(weapon["weapon_id"]))
        return [
            f"#{weapon['weapon_id']} {weapon_label_name(weapon)}[{weapon['quality']}] {status}",
            (
                f"模板：{weapon['name']}｜类型：{weapon['weapon_type']}｜"
                f"掉落：{weapon['drop_location']}｜模板基础攻击：{weapon['base_attack']}"
            ),
            f"定位：{combat_info['weapon_style']}",
            f"速度：**{combat_info['speed']}**（{combat_info['speed_grade']}）",
            f"技能节奏：{combat_info['skill_tempo']}",
            f"蓄势基准：{combat_info['skill_interval']}（越小越快）",
            (
                f"成长：等级 {weapon['level']}/{weapon['max_level']}｜"
                f"当前攻击 {weapon['attack']}｜下级：{next_cost}"
            ),
            "自带技能：" + self._skill_text(skill, weapon, effects),
            (
                f"附魔栏：已用 {used_slots}/已解锁 {unlocked_slots}/潜力 {potential_slots}；"
                f"{self._next_slot_text(weapon, unlocked_slots, potential_slots)}"
            ),
            "附魔：" + self._enchant_detail_text(int(weapon["weapon_id"]), enchant_ids),
            f"传奇：{legend_text}",
            f"回收：{recycle_text}",
        ]

    def _legend_text(self, weapon_id: int) -> str:
        """展示武器轻量传奇记录。"""

        row = self.db.fetch_one("SELECT * FROM weapon_legends WHERE weapon_id = ?", (weapon_id,))
        if not row:
            return "暂无记录"
        return (
            f"斩怪{row['monster_kills']} Boss{row['boss_challenges']} "
            f"决斗胜{row['duel_wins']} 最高伤害{row['highest_damage']}"
        )

    def _weapon_legend_text(self, weapon: dict) -> str:
        """格式化完整武器传奇记录。"""

        legend = weapon.get("legend") or {}
        original = self.format_player_name(legend.get("original_owner_id", weapon["owner_id"]))
        current = self.format_player_name(legend.get("current_owner_id", weapon["owner_id"]))
        panel = T.panel()
        panel.section(f"武器传奇 #{weapon['weapon_id']} {weapon_label_name(weapon)}")
        panel.line(f"品质：{weapon['quality']}｜类型：{weapon['weapon_type']}｜等级：**{weapon['level']}/{weapon['max_level']}**")
        panel.line(f"初主：{original}｜现主：{current}")
        panel.line(
            f"斩怪：**{legend.get('monster_kills', 0)}** 次｜"
            f"Boss：**{legend.get('boss_challenges', 0)}** 战｜"
            f"决斗胜：**{legend.get('duel_wins', 0)}** 场"
        )
        panel.line(f"最高单次伤害：**{legend.get('highest_damage', 0)}**")
        return panel.render()

    @staticmethod
    def _next_upgrade_text(weapon: dict) -> str:
        """展示下一次升级花费。"""

        if int(weapon["level"]) >= int(weapon["max_level"]):
            return "已到上限"
        next_level = int(weapon["level"]) + 1
        cost = weapon_upgrade_cost(next_level, quality_factor(weapon["quality"]))
        return f"{next_level}级需源石{money(cost)}"

    @staticmethod
    def _recycle_state_text(weapon: dict, total_count: int) -> str:
        """展示当前武器是否能系统回收。"""

        if int(weapon["equipped"]):
            return "已装备，不能回收；先切换到其他武器"
        if total_count <= 1:
            return "最后一把武器，不能回收"
        return "可在铸剑阁回收"

    @staticmethod
    def _next_slot_text(weapon: dict, unlocked_slots: int, potential_slots: int) -> str:
        """展示下一格附魔栏的解锁条件。"""

        if potential_slots <= 0:
            return "这把武器等级上限不足，无法解锁附魔栏"
        if unlocked_slots >= potential_slots:
            return "附魔栏已按当前等级上限全部解锁"
        for level in (20, 40, 60, 80, 90, 100):
            if int(weapon["max_level"]) >= level and int(weapon["level"]) < level:
                return f"下个附魔栏在武器{level}级解锁"
        return "继续升级可解锁更多附魔栏"

    def _skill_text(self, skill: dict, weapon: dict, effects: dict[str, float]) -> str:
        """展示武器自带技能本身，不混入速度面板。"""

        cost = self._skill_cost(skill, effects)
        power = self._skill_power(skill, effects)
        name = self.weapon_skill_label(int(weapon["weapon_id"]), skill)
        desc = skill.get("effect_desc") or skill.get("desc", "")
        text = f"{name} | 威力{power:.2f}倍 | 消耗精神{cost}"
        return f"{text} | {desc}" if desc else text

    def _enchant_detail_text(self, weapon_id: int, enchant_ids: list[str]) -> str:
        """展示附魔名称和效果。"""

        if not enchant_ids:
            return "无"
        custom_rows = self.db.fetch_all(
            "SELECT slot_no, custom_name FROM weapon_enchant_names WHERE weapon_id = ?",
            (weapon_id,),
        )
        custom_names = {int(row["slot_no"]): row["custom_name"] for row in custom_rows}
        lines = []
        for slot_no, enchant_id in enumerate(enchant_ids, start=1):
            row = self.db.fetch_one("SELECT name, effect, mp_delta FROM weapon_enchants WHERE enchant_id = ?", (enchant_id,))
            if not row:
                lines.append(f"{slot_no}.{enchant_id}")
                continue
            name = enchant_label_name(row["name"], custom_names.get(slot_no, ""))
            effect_text = self._effect_text(load_json(row["effect"], {}), int(row["mp_delta"]))
            lines.append(f"{slot_no}.{name}({effect_text})")
        return "；".join(lines)

    @staticmethod
    def _effect_text(effect: dict, mp_delta: int) -> str:
        """把附魔效果翻译成玩家可读文本。"""

        labels = {
            "hit_bonus": "命中稳定",
            "pierce_bonus": "防御穿透",
            "life_steal": "吸血",
            "shield_bonus": "技能护盾",
            "mp_suppress": "精神压制",
            "defense_suppress": "压低防御",
            "combo_bonus": "连击概率",
            "damage_reduce": "最终减伤",
            "skill_power_bonus": "技能威力",
            "heavy_bonus": "重击威力",
            "combo_damage_bonus": "连击伤害",
            "single_hit_bonus": "单次爆发",
            "dodge_bonus": "闪避",
        }
        texts = []
        for key, label in labels.items():
            value = effect.get(key)
            if isinstance(value, int | float) and value:
                texts.append(f"{label}{value * 100:+.1f}%")
        interval_delta = effect.get("interval_delta")
        if isinstance(interval_delta, int | float) and interval_delta:
            if interval_delta > 0:
                texts.append(f"技能间隔+{int(interval_delta)}")
            else:
                texts.append(f"技能间隔{int(interval_delta)}")
        if mp_delta:
            texts.append(f"精神消耗{mp_delta:+d}")
        return "、".join(texts) if texts else "无数值效果"

    def _today_recycle_income(self, client_id: str) -> int:
        """读取玩家今日武器回收收入。"""

        with self.db.transaction() as conn:
            return self._today_recycle_income_conn(conn, client_id)

    @staticmethod
    def _today_recycle_income_conn(conn, client_id: str) -> int:
        """在事务里读取玩家今日武器回收收入。"""

        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_price), 0) AS total
            FROM weapon_recycle_records
            WHERE client_id = ? AND business_day = ?
            """,
            (client_id, business_day()),
        ).fetchone()
        return int(row["total"]) if row else 0

    @staticmethod
    def _recycle_quote(weapon: dict, price_factor: float, player_level: int, today_income: int) -> dict[str, float | int]:
        """计算武器回收报价。

        先按武器属性估价，再限制单把上限，最后按今日回收收入降价。
        """

        enchants = len(load_json(weapon.get("enchant_effects"), []))
        raw_value = int(
            (
                int(weapon["attack"]) * 60
                + int(weapon["max_level"]) * 100
                + int(weapon["level"]) * 250
                + enchants * 5_000
            )
            * quality_factor(weapon["quality"])
            * price_factor
        )
        single_cap = weapon_recycle_single_cap(player_level)
        capped_value = min(raw_value, single_cap)
        rate = weapon_recycle_price_rate(player_level, today_income + capped_value // 2)
        value = max(1, int(capped_value * rate))
        return {
            "raw_value": raw_value,
            "single_cap": single_cap,
            "capped_value": capped_value,
            "rate": rate,
            "value": value,
        }

    def _book_recycle_preview(self, client_id: str, location: dict) -> str:
        """展示当前可回收技能书和估价。"""

        rows = self.db.fetch_all(
            """
            SELECT r.equipment_item_id, r.quantity, e.name, e.quality
            FROM ring_items r
            JOIN equipment_item_defs e ON e.equipment_item_id = r.equipment_item_id
            WHERE r.client_id = ? AND r.quantity > 0 AND e.category = '技能书'
            ORDER BY e.quality, e.name
            """,
            (client_id,),
        )
        if not rows:
            return T.hint(f"{location['name']}可以回收纳戒里的未附魔技能书，但你当前没有技能书。", "继续探险、挑战虫洞或首领获取技能书。")

        player = self.player(client_id) or {}
        player_level = int(player.get("level", 1))
        today_income = self._today_book_recycle_income(client_id)
        rate = book_recycle_price_rate(player_level, today_income)
        panel = T.panel()
        panel.section(f"{location['name']}技能书回收")
        panel.line(f"当前倍率：**{int(rate * 100)}%**")
        panel.line(f"今日已回收：**{money(today_income)}**。估价会随今日回收收入降低。")
        panel.line("只回收纳戒里未附魔的技能书；已经附魔到武器上的技能书不能取下。")
        for row in rows:
            quote = self._book_recycle_quote(
                row,
                1,
                float(location["price_factor"]),
                player_level,
                today_income,
            )
            panel.line(f"{row['name']}[{row['quality']}] x{row['quantity']}｜单本估价：**{money(quote['value'])}**")
        return panel.render()

    def _today_book_recycle_income(self, client_id: str) -> int:
        """读取玩家今日技能书回收收入。"""

        with self.db.transaction() as conn:
            return self._today_book_recycle_income_conn(conn, client_id)

    @staticmethod
    def _today_book_recycle_income_conn(conn, client_id: str) -> int:
        """在事务里读取玩家今日技能书回收收入。"""

        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_price), 0) AS total
            FROM book_recycle_records
            WHERE client_id = ? AND business_day = ?
            """,
            (client_id, business_day()),
        ).fetchone()
        return int(row["total"]) if row else 0

    @staticmethod
    def _book_recycle_quote(
        book: dict,
        quantity: int,
        price_factor: float,
        player_level: int,
        today_income: int,
    ) -> dict[str, float | int]:
        """计算技能书回收报价。"""

        amount = max(1, int(quantity))
        raw_unit = int(4000 * quality_factor(book["quality"]) * price_factor)
        single_cap = book_recycle_single_cap(player_level)
        capped_unit = min(raw_unit, single_cap)
        raw_value = raw_unit * amount
        capped_value = capped_unit * amount
        rate = book_recycle_price_rate(player_level, today_income + capped_value // 2)
        value = max(1, int(capped_value * rate))
        return {
            "raw_value": raw_value,
            "single_cap": single_cap,
            "capped_value": capped_value,
            "rate": rate,
            "value": value,
        }

    @staticmethod
    def _parse_book_recycle_message(message: str) -> tuple[str, int]:
        """解析 回收技能书 技能书名 [数量]。"""

        parts = split_words(message)
        if not parts:
            return "", 0
        quantity = 1
        if len(parts) > 1 and parts[-1].isdigit():
            quantity = to_int(parts[-1], 1)
            parts = parts[:-1]
        return " ".join(parts), quantity

    @staticmethod
    def _is_book_recycle_all(message: str) -> bool:
        """是否一键回收全部技能书。"""

        return "".join(split_words(message)) in {"全部", "全部技能书", "全回收", "一键回收"}


service = WeaponService(db)

__all__ = ["WeaponService", "service"]
