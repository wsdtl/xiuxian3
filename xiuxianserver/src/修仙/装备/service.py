"""固定装备组件服务。"""

from __future__ import annotations

from ..common import CoreService, hint, money, parse_name_level, split_words, to_int
from ..constants import EQUIPMENT_SLOTS, FIXED_EQUIPMENT_SLOT_FACTORS
from ..rules import equipment_upgrade_cost
from ..sql import db

DEFAULT_HOLES = 3
MAX_HOLES = 9
HOLE_ITEM_ID = "kaikongqi"


class EquipmentService(CoreService):
    """固定装备升级和镶嵌。"""

    def list_equipment(self, client_id: str) -> str:
        """查看固定装备。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.db.ensure_fixed_equipment(client_id)
        rows = self.db.fetch_all(
            "SELECT * FROM fixed_equipment WHERE client_id = ? ORDER BY slot",
            (client_id,),
        )
        bonuses = self.equipment_bonuses(client_id)
        lines = [f"{row['slot']}：{row['level']}级，孔位 {row['hole_count']}/{MAX_HOLES}" for row in rows]
        lines.append(
            f"当前总生存加成：血气+{int(bonuses['max_hp_bonus'])} "
            f"精神+{int(bonuses['max_mp_bonus'])} 防御+{int(bonuses['defense_bonus'])}"
        )
        return "\n".join(lines)

    def upgrade(self, client_id: str, slot: str) -> str:
        """升级固定装备。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        slot = slot.strip()
        if slot not in EQUIPMENT_SLOTS:
            return hint(f"装备位只能是：{'、'.join(EQUIPMENT_SLOTS)}", "发送：固定装备 查看已有装备位。")
        self.db.ensure_fixed_equipment(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM fixed_equipment WHERE client_id = ? AND slot = ?",
                (client_id, slot),
            ).fetchone()
            level = row["level"] if row else 0
            if level >= 100:
                return hint(f"{slot} 已满级。", "可以升级其他装备位，或继续镶嵌、升级宝石。")
            cost = equipment_upgrade_cost(level + 1, FIXED_EQUIPMENT_SLOT_FACTORS[slot])
            if not self.spend_stones_conn(conn, client_id, cost):
                return hint(f"源石不足，升级需要 {money(cost)}。", "发送：源库 查看存量，或通过签到、探险、出售物品获取源石。")
            conn.execute(
                "UPDATE fixed_equipment SET level = level + 1 WHERE client_id = ? AND slot = ?",
                (client_id, slot),
            )
        self.recalc_player(client_id)
        return f"{slot} 升级成功，当前 {level + 1} 级。"

    def holes(self, client_id: str, slot: str) -> str:
        """查看固定装备孔位。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        slot = slot.strip()
        if slot not in EQUIPMENT_SLOTS:
            return hint(f"装备位只能是：{'、'.join(EQUIPMENT_SLOTS)}", "发送：固定装备 查看已有装备位。")
        equipment = self._equipment_row(client_id, slot)
        hole_count = int(equipment["hole_count"]) if equipment else DEFAULT_HOLES
        rows = self.db.fetch_all(
            """
            SELECT i.hole_no, i.level, e.name
            FROM fixed_equipment_inlays i
            LEFT JOIN equipment_item_defs e ON e.equipment_item_id = i.gem_id
            WHERE i.client_id = ? AND i.slot = ?
            ORDER BY i.hole_no
            """,
            (client_id, slot),
        )
        used = {row["hole_no"]: f"{row['name']} {row['level']}级" for row in rows}
        lines = [f"☆{slot}孔位☆ {hole_count}/{MAX_HOLES}"]
        for index in range(1, MAX_HOLES + 1):
            if index > hole_count:
                lines.append(f"{index}：未开孔")
            else:
                lines.append(f"{index}：{used.get(index, '空')}")
        return "\n".join(lines)

    def open_hole(self, client_id: str, slot: str) -> str:
        """消耗开孔器，为固定装备增加 1 个孔位。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        slot = slot.strip()
        if slot not in EQUIPMENT_SLOTS:
            return hint(f"装备位只能是：{'、'.join(EQUIPMENT_SLOTS)}", "发送：固定装备 查看已有装备位。")
        self.db.ensure_fixed_equipment(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT hole_count FROM fixed_equipment WHERE client_id = ? AND slot = ?",
                (client_id, slot),
            ).fetchone()
            hole_count = int(row["hole_count"]) if row else DEFAULT_HOLES
            if hole_count >= MAX_HOLES:
                return hint(f"{slot} 已经达到 {MAX_HOLES} 孔上限。", "可以给其他固定装备开孔，或继续镶嵌、升级宝石。")
            if not self.remove_ring_conn(conn, client_id, HOLE_ITEM_ID, 1):
                return hint("纳戒里没有开孔器。", "开孔器只通过活动 Boss 掉落，获得后发送：开孔 装备位")
            conn.execute(
                """
                UPDATE fixed_equipment
                SET hole_count = hole_count + 1
                WHERE client_id = ? AND slot = ?
                """,
                (client_id, slot),
            )
        return f"开孔成功：{slot} 当前孔位 {hole_count + 1}/{MAX_HOLES}。"

    def inlay(self, client_id: str, message: str) -> str:
        """镶嵌固定装备。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        parts = split_words(message)
        if len(parts) < 3:
            return hint("镶嵌格式不正确。", "发送：镶嵌 装备位 孔位号 宝石名称，例如：镶嵌 护甲 1 护心玉")
        slot = parts[0]
        hole_no = to_int(parts[1])
        item_name, wanted_level = parse_name_level(" ".join(parts[2:]))
        if slot not in EQUIPMENT_SLOTS or hole_no < 1 or hole_no > MAX_HOLES:
            return hint("装备位或孔位号不正确。", f"装备位只能是：{'、'.join(EQUIPMENT_SLOTS)}；孔位号只能是 1 到 {MAX_HOLES}。")
        item = self.equipment_item_def_by_name(item_name)
        if not item or item["category"] != "宝石":
            return hint(f"没有找到宝石：{item_name}。", "发送：我的宝石 查看纳戒里的宝石名称。")
        with self.db.transaction() as conn:
            equipment = conn.execute(
                "SELECT hole_count FROM fixed_equipment WHERE client_id = ? AND slot = ?",
                (client_id, slot),
            ).fetchone()
            hole_count = int(equipment["hole_count"]) if equipment else DEFAULT_HOLES
            if hole_no > hole_count:
                return hint(f"{slot} 当前只开启到 {hole_count} 号孔。", "先发送：开孔 装备位，消耗开孔器后再镶嵌。")
            exists = conn.execute(
                """
                SELECT 1 FROM fixed_equipment_inlays
                WHERE client_id = ? AND slot = ? AND hole_no = ?
                """,
                (client_id, slot, hole_no),
            ).fetchone()
            if exists:
                return hint("该孔位已经有宝石。", "发送：拆卸 装备位 孔位号 后再重新镶嵌。")
            gem_level, level_error = self._resolve_gem_level_conn(
                conn,
                client_id,
                item["equipment_item_id"],
                item["name"],
                wanted_level,
            )
            if level_error:
                return level_error
            assert gem_level is not None
            if not self.remove_gem_conn(conn, client_id, item["equipment_item_id"], gem_level, 1):
                return hint(f"纳戒里没有 {item['name']} {gem_level}级。", "发送：我的宝石 查看已有宝石等级，或继续探险获取。")
            conn.execute(
                """
                INSERT INTO fixed_equipment_inlays (client_id, slot, hole_no, gem_id, level)
                VALUES (?, ?, ?, ?, ?)
                """,
                (client_id, slot, hole_no, item["equipment_item_id"], gem_level),
            )
        self.recalc_player(client_id)
        return f"镶嵌成功：{slot} {hole_no}号孔 -> {item['name']} {gem_level}级。"

    def remove_inlay(self, client_id: str, message: str) -> str:
        """拆卸宝石。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        parts = split_words(message)
        if len(parts) < 2:
            return hint("拆卸格式不正确。", "发送：拆卸 装备位 孔位号，例如：拆卸 护甲 1")
        slot = parts[0]
        hole_no = to_int(parts[1])
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT i.*, e.name
                FROM fixed_equipment_inlays i
                JOIN equipment_item_defs e ON e.equipment_item_id = i.gem_id
                WHERE i.client_id = ? AND i.slot = ? AND i.hole_no = ?
                """,
                (client_id, slot, hole_no),
            ).fetchone()
            if not row:
                return hint("该孔位没有宝石。", "发送：孔位 装备位 查看当前孔位。")
            self.add_gem_conn(conn, client_id, row["gem_id"], row["level"], 1)
            conn.execute(
                "DELETE FROM fixed_equipment_inlays WHERE client_id = ? AND slot = ? AND hole_no = ?",
                (client_id, slot, hole_no),
            )
        self.recalc_player(client_id)
        return f"拆卸成功：{row['name']} {row['level']}级已回到纳戒。"

    def my_inlays(self, client_id: str) -> str:
        """查看纳戒里尚未镶嵌的宝石库存。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.gem_rows(client_id)
        if not rows:
            return hint("纳戒中没有宝石。", "继续探险有概率获得宝石。")
        return "\n".join(f"{row['name']} {row['level']}级 x{row['quantity']}" for row in rows)

    def upgrade_inlay(self, client_id: str, message: str) -> str:
        """升级已镶嵌的宝石。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        text = message.strip()
        if not text:
            return hint("宝石升级格式不正确。", "发送：宝石升级 装备位 孔位号，例如：宝石升级 护甲 1")
        with self.db.transaction() as conn:
            row, error = self._upgrade_target_conn(conn, client_id, text)
            if error:
                return error
            assert row is not None
            if row["level"] >= 10:
                return hint(f"{row['name']} 已经 10 级。", "可以升级其他宝石，或镶嵌到其他装备孔位。")
            next_level = row["level"] + 1
            cost = 5000 * (next_level**2)
            if not self.spend_stones_conn(conn, client_id, cost):
                return hint(f"源石不足，升级需要 {money(cost)}。", "发送：源库 查看存量，或通过签到、探险、出售物品获取源石。")
            conn.execute(
                """
                UPDATE fixed_equipment_inlays
                SET level = ?
                WHERE client_id = ? AND slot = ? AND hole_no = ?
                """,
                (next_level, client_id, row["slot"], row["hole_no"]),
            )
        self.recalc_player(client_id)
        return f"{row['slot']} {row['hole_no']}号孔 {row['name']} 升级成功：{row['level']} -> {next_level}，消耗源石 {money(cost)}。"

    def _upgrade_target_conn(self, conn, client_id: str, text: str):
        """解析宝石升级目标；只按 装备位+孔位 精确定位。"""

        parts = split_words(text)
        if len(parts) >= 2 and parts[0] in EQUIPMENT_SLOTS:
            hole_no = to_int(parts[1])
            row = conn.execute(
                """
                SELECT i.*, e.name
                FROM fixed_equipment_inlays i
                JOIN equipment_item_defs e ON e.equipment_item_id = i.gem_id
                WHERE i.client_id = ? AND i.slot = ? AND i.hole_no = ?
                """,
                (client_id, parts[0], hole_no),
            ).fetchone()
            if not row:
                return None, hint("该孔位没有可升级宝石。", "发送：孔位 装备位 查看当前孔位。")
            return row, None

        item = self.equipment_item_def_by_name(text)
        if not item or item["category"] != "宝石":
            return None, hint("宝石升级格式不正确。", "发送：宝石升级 装备位 孔位号，例如：宝石升级 护甲 1")
        rows = conn.execute(
            """
            SELECT i.*, e.name
            FROM fixed_equipment_inlays i
            JOIN equipment_item_defs e ON e.equipment_item_id = i.gem_id
            WHERE i.client_id = ? AND i.gem_id = ?
            ORDER BY i.slot, i.hole_no
            """,
            (client_id, item["equipment_item_id"]),
        ).fetchall()
        if not rows:
            return None, hint(f"你还没有镶嵌 {item['name']}。", "先发送：镶嵌 装备位 孔位号 宝石名称。")
        options = "、".join(f"{row['slot']}{row['hole_no']}号孔({row['level']}级)" for row in rows)
        return None, hint(
            "宝石升级需要用装备位和孔位号定位。",
            f"发送：宝石升级 装备位 孔位号，例如：宝石升级 {rows[0]['slot']} {rows[0]['hole_no']}。可选：{options}",
        )

    @staticmethod
    def _resolve_gem_level_conn(conn, client_id: str, gem_id: str, gem_name: str, wanted_level: int | None):
        """确定要镶嵌的宝石等级；同名多等级时要求用户写清等级。"""

        if wanted_level is not None:
            return wanted_level, None

        rows = conn.execute(
            """
            SELECT level, quantity FROM gem_items
            WHERE client_id = ? AND gem_id = ? AND quantity > 0
            ORDER BY level
            """,
            (client_id, gem_id),
        ).fetchall()
        if not rows:
            return 1, None
        if len(rows) == 1:
            return int(rows[0]["level"]), None

        options = "、".join(f"{row['level']}级x{row['quantity']}" for row in rows)
        return None, hint(
            f"纳戒里有多种等级的 {gem_name}。",
            f"请写清等级，例如：镶嵌 护甲 1 {gem_name} {rows[-1]['level']}级。现有：{options}",
        )

    def _equipment_row(self, client_id: str, slot: str) -> dict | None:
        """读取某个固定装备位。"""

        self.db.ensure_fixed_equipment(client_id)
        return self.db.fetch_one(
            "SELECT * FROM fixed_equipment WHERE client_id = ? AND slot = ?",
            (client_id, slot),
        )


service = EquipmentService(db)

__all__ = ["EquipmentService", "service"]
