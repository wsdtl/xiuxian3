"""修仙模块通用能力。

根目录只放基础函数和公共服务，不反向导入各个玩法包。
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable

from .constants import (
    DAY_RESET_HOUR,
    DEFAULT_BACKPACK_LIMIT,
    DEFAULT_LOCATION,
    DEFAULT_WEIGHT_LIMIT,
    EQUIPMENT_SLOTS,
    FIXED_EQUIPMENT_SLOT_FACTORS,
    MAX_LEVEL,
    RENAME_COOLDOWN_HOURS,
)
from .rules import base_attack, defense, exp_need, level_from_exp, max_hp, max_mp, money


AT_RE = re.compile(r"\[CQ:at,qq=(?P<id>[^\],]+)")


def now() -> datetime:
    """返回当前时间。"""

    return datetime.now()


def ts(value: datetime | None = None) -> str:
    """把时间转成数据库保存的字符串。"""

    return (value or now()).isoformat(timespec="seconds")


def dt(value: str | None) -> datetime | None:
    """把数据库时间字符串转成时间对象。"""

    if not value:
        return None
    return datetime.fromisoformat(value)


def business_day(value: datetime | None = None) -> str:
    """按每日 04:00 计算业务日。"""

    return ((value or now()) - timedelta(hours=DAY_RESET_HOUR)).date().isoformat()


def to_int(value: object, default: int = 0) -> int:
    """把输入转成整数。"""

    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def load_json(text: object, default: Any = None) -> Any:
    """安全读取 JSON 字段。"""

    if default is None:
        default = {}
    if not text:
        return default
    try:
        return json.loads(str(text))
    except json.JSONDecodeError:
        return default


def dump_json(data: Any) -> str:
    """把对象保存成 JSON 文本。"""

    return json.dumps(data, ensure_ascii=False)


def validate_name(name: str) -> tuple[bool, str]:
    """校验展示名称。"""

    clean = name.strip()
    if len(clean) < 2 or len(clean) > 12:
        return False, "名称需要 2 到 12 个字符。"
    if any(ch.isspace() for ch in clean):
        return False, "名称中不能包含空白字符。"
    return True, clean


def hint(reason: str, suggestion: str) -> str:
    """把失败原因和下一步建议拼成统一回复。"""

    return f"{reason}\n建议：{suggestion}"


def parse_player_ref(text: str) -> str:
    """把纯 id 或 CQ/at 转成 client_id。"""

    value = text.strip()
    match = AT_RE.search(value)
    if match:
        return match.group("id").strip()
    return value.split()[0].strip() if value else ""


def split_words(message: str) -> list[str]:
    """按空白拆参数。"""

    return [part for part in message.strip().split() if part]


def parse_name_level(text: str) -> tuple[str, int | None]:
    """解析“名称 2级 / 名称 Lv2”，没有等级时返回 None。"""

    parts = split_words(text)
    if not parts:
        return "", None

    token = parts[-1].strip().lower()
    level_text = ""
    if token.endswith("级"):
        level_text = token[:-1]
    elif token.startswith("lv"):
        level_text = token[2:]

    if level_text.isdigit() and len(parts) > 1:
        return " ".join(parts[:-1]), max(1, to_int(level_text, 1))
    return text.strip(), None


def quality_factor(quality: str) -> float:
    """返回品质系数。"""

    return {"凡品": 1.0, "良品": 1.4, "珍品": 2.0, "稀品": 3.0}.get(quality, 1.0)


def random_quality() -> str:
    """随机品质。"""

    return random.choices(("凡品", "良品", "珍品", "稀品"), weights=(60, 28, 10, 2), k=1)[0]


class CoreService:
    """所有玩法服务共享的基础能力。"""

    def __init__(self, database: Any) -> None:
        self.db = database

    def player(self, client_id: str) -> dict[str, Any] | None:
        """读取玩家。"""

        return self.db.fetch_one("SELECT * FROM players WHERE client_id = ?", (client_id,))

    def require_player(self, client_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """要求玩家已创建。"""

        player = self.player(client_id)
        if not player:
            return None, hint("你还没有创建用户。", "发送：创建用户 名称，例如：创建用户 青衫客")
        return player, None

    def create_player(self, client_id: str, display_name: str) -> str:
        """创建玩家。"""

        if self.player(client_id):
            return hint("你已经创建过用户了。", "发送：修仙信息 查看角色，或发送：改名 新名称")
        ok, result = validate_name(display_name)
        if not ok:
            return hint(result, "请换一个 2 到 12 个字符、且不含空白的名称。")

        hp = max_hp(1, 0)
        mp = max_mp(1)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO players (
                    client_id, display_name, level, exp, hp, max_hp, mp, max_mp,
                    physique_id, physique, base_attack, defense, source_stones, status,
                    location_name, x, y, backpack_limit, weight_limit, created_at
                )
                VALUES (?, ?, 1, 0, ?, ?, ?, ?, 'fanti', 0, ?, ?, 0, '空闲',
                        ?, 0, 0, ?, ?, ?)
                """,
                (
                    client_id,
                    result,
                    hp,
                    hp,
                    mp,
                    mp,
                    base_attack(1),
                    defense(1, 0),
                    DEFAULT_LOCATION,
                    DEFAULT_BACKPACK_LIMIT,
                    DEFAULT_WEIGHT_LIMIT,
                    ts(),
                ),
            )
            if cursor.rowcount <= 0:
                return hint("你已经创建过用户了。", "发送：修仙信息 查看角色，或发送：改名 新名称")
            conn.execute(
                """
                INSERT INTO source_vaults (client_id, level, balance, last_settle_at)
                VALUES (?, 1, 0, ?)
                """,
                (client_id, ts()),
            )
            conn.executemany(
                "INSERT INTO fixed_equipment (client_id, slot, level) VALUES (?, ?, 0)",
                [(client_id, slot) for slot in EQUIPMENT_SLOTS],
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '创建用户', ?, ?)",
                (client_id, result, ts()),
            )
        return f"创建成功，道友 {result}，你的 id 是 {client_id}。"

    def rename_player(self, client_id: str, display_name: str) -> str:
        """修改展示名称。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        ok, result = validate_name(display_name)
        if not ok:
            return hint(result, "请换一个 2 到 12 个字符、且不含空白的名称。")

        last = dt(player.get("last_rename_at"))
        if last and now() - last < timedelta(hours=RENAME_COOLDOWN_HOURS):
            left = timedelta(hours=RENAME_COOLDOWN_HOURS) - (now() - last)
            hours = max(1, int(left.total_seconds() // 3600) + 1)
            return hint(f"改名太频繁，请约 {hours} 小时后再试。", "冷却结束后发送：改名 新名称")

        self.db.execute(
            "UPDATE players SET display_name = ?, last_rename_at = ? WHERE client_id = ?",
            (result, ts(), client_id),
        )
        self.log(client_id, "改名", result)
        return f"改名成功，现在叫 {result}。"

    def log(self, client_id: str, action: str, detail: str = "") -> None:
        """写行为日志。"""

        self.db.execute(
            "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (client_id, action, detail, ts()),
        )

    def equipment_bonuses(self, client_id: str) -> dict[str, float]:
        """汇总固定装备和宝石加成。

        固定装备只给生存属性，宝石和体质按自身效果叠加。
        这里放在公共服务里，所有组件都能读取，不需要二级包互相引用。
        """

        self.db.ensure_fixed_equipment(client_id)
        with self.db.transaction() as conn:
            return self.equipment_bonuses_conn(conn, client_id)

    def equipment_bonuses_conn(self, conn: sqlite3.Connection, client_id: str) -> dict[str, float]:
        """在事务里汇总固定装备、宝石和体质加成。

        事务内不能调用 ensure_fixed_equipment()，否则会提前 commit 外层事务。
        创建玩家时已经写入固定装备位，普通查询入口也会兜底补齐。
        """

        bonuses: dict[str, float] = {
            "max_hp_bonus": 0,
            "max_mp_bonus": 0,
            "defense_bonus": 0,
            "dodge_bonus": 0,
            "recover_bonus": 0,
            "explore_bonus": 0,
            "trade_bonus": 0,
            "crit_resist_bonus": 0,
        }

        rows = conn.execute(
            "SELECT slot, level FROM fixed_equipment WHERE client_id = ?",
            (client_id,),
        ).fetchall()
        for row in rows:
            level = int(row["level"])
            factor = FIXED_EQUIPMENT_SLOT_FACTORS.get(row["slot"], 1.0)
            bonuses["max_hp_bonus"] += int(level * 8 * factor)
            bonuses["max_mp_bonus"] += int(level * 3 * factor)
            bonuses["defense_bonus"] += int(level * 2 * factor)

        inlays = conn.execute(
            """
            SELECT i.level, e.effect
            FROM fixed_equipment_inlays i
            JOIN equipment_item_defs e ON e.equipment_item_id = i.gem_id
            WHERE i.client_id = ?
            """,
            (client_id,),
        ).fetchall()
        for row in inlays:
            level = max(1, int(row["level"]))
            effect = load_json(row["effect"], {})
            for key, value in effect.items():
                if not isinstance(value, int | float):
                    continue
                bonus_key = "max_mp_bonus" if key == "mp_bonus" else key
                bonuses[bonus_key] = bonuses.get(bonus_key, 0) + float(value) * level
        physique = conn.execute(
            """
            SELECT d.effect
            FROM players p
            JOIN physique_defs d ON d.physique_id = p.physique_id
            WHERE p.client_id = ?
            """,
            (client_id,),
        ).fetchone()
        if physique:
            for key, value in load_json(physique["effect"], {}).items():
                if isinstance(value, int | float):
                    bonus_key = "max_mp_bonus" if key == "mp_bonus" else key
                    bonuses[bonus_key] = bonuses.get(bonus_key, 0) + float(value)
        return bonuses

    def recalc_player(self, client_id: str) -> dict[str, Any]:
        """按经验重算等级和基础数值。"""

        with self.db.transaction() as conn:
            return self.recalc_player_conn(conn, client_id)

    def recalc_player_conn(self, conn: sqlite3.Connection, client_id: str) -> dict[str, Any]:
        """在事务里按经验重算等级和基础数值。"""

        player = conn.execute("SELECT * FROM players WHERE client_id = ?", (client_id,)).fetchone()
        if not player:
            raise ValueError("玩家不存在")
        level = level_from_exp(player["exp"])
        physique_value = int(player["physique"])
        physique_def = conn.execute(
            "SELECT physique_value FROM physique_defs WHERE physique_id = ?",
            (player["physique_id"],),
        ).fetchone()
        if physique_def:
            physique_value = int(physique_def["physique_value"])
        bonuses = self.equipment_bonuses_conn(conn, client_id)
        hp_max = max_hp(level, physique_value, int(bonuses["max_hp_bonus"]))
        mp_max = max_mp(level, int(bonuses["max_mp_bonus"]))
        attack_value = base_attack(level)
        defense_value = defense(level, physique_value, int(bonuses["defense_bonus"]))
        conn.execute(
            """
            UPDATE players
            SET level = ?, max_hp = ?, max_mp = ?, hp = min(hp, ?), mp = min(mp, ?),
                physique = ?, base_attack = ?, defense = ?
            WHERE client_id = ?
            """,
            (level, hp_max, mp_max, hp_max, mp_max, physique_value, attack_value, defense_value, client_id),
        )
        row = conn.execute("SELECT * FROM players WHERE client_id = ?", (client_id,)).fetchone()
        return dict(row) if row else dict(player)

    def add_exp(self, client_id: str, amount: int) -> tuple[int, int]:
        """增加经验，返回旧等级和新等级。"""

        with self.db.transaction() as conn:
            return self.add_exp_conn(conn, client_id, amount)

    def add_exp_conn(self, conn: sqlite3.Connection, client_id: str, amount: int) -> tuple[int, int]:
        """在事务里增加经验，返回旧等级和新等级。"""

        player = conn.execute("SELECT * FROM players WHERE client_id = ?", (client_id,)).fetchone()
        if not player:
            return 1, 1
        old_level = player["level"]
        conn.execute(
            "UPDATE players SET exp = exp + ? WHERE client_id = ?",
            (max(0, amount), client_id),
        )
        player = self.recalc_player_conn(conn, client_id)
        return old_level, player["level"]

    def add_stones(self, client_id: str, amount: int) -> None:
        """增加随身源石。"""

        if amount <= 0:
            return
        self.db.execute(
            "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
            (amount, client_id),
        )

    def spend_stones_conn(self, conn: sqlite3.Connection, client_id: str, amount: int) -> bool:
        """在事务里扣源石。"""

        if amount < 0:
            return False
        row = conn.execute("SELECT source_stones FROM players WHERE client_id = ?", (client_id,)).fetchone()
        if not row or row["source_stones"] < amount:
            return False
        conn.execute(
            "UPDATE players SET source_stones = source_stones - ? WHERE client_id = ?",
            (amount, client_id),
        )
        return True

    def item_def_by_name(self, name: str) -> dict[str, Any] | None:
        """按名称读取物品库定义。"""

        return self.db.fetch_one("SELECT * FROM item_defs WHERE name = ?", (name.strip(),))

    def item_def(self, item_id: str) -> dict[str, Any] | None:
        """按 id 读取物品库定义。"""

        return self.db.fetch_one("SELECT * FROM item_defs WHERE item_id = ?", (item_id,))

    def equipment_item_def_by_name(self, name: str) -> dict[str, Any] | None:
        """按名称读取装备库定义。"""

        return self.db.fetch_one("SELECT * FROM equipment_item_defs WHERE name = ?", (name.strip(),))

    def equipment_item_def(self, equipment_item_id: str) -> dict[str, Any] | None:
        """按 id 读取装备库定义。"""

        return self.db.fetch_one(
            "SELECT * FROM equipment_item_defs WHERE equipment_item_id = ?",
            (equipment_item_id,),
        )

    def add_backpack_conn(self, conn: sqlite3.Connection, client_id: str, item_id: str, quantity: int) -> None:
        """在事务里增加背包物品。"""

        if quantity <= 0:
            return
        conn.execute(
            """
            INSERT INTO backpack_items (client_id, item_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(client_id, item_id)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (client_id, item_id, quantity),
        )

    def can_add_backpack_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        item_id: str,
        quantity: int,
    ) -> tuple[bool, str]:
        """检查背包是否还能放入指定物品。"""

        if quantity <= 0:
            return True, ""

        player = conn.execute(
            "SELECT backpack_limit, weight_limit FROM players WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        item = conn.execute(
            "SELECT name, weight, stack_limit FROM item_defs WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if not player or not item:
            return False, hint("玩家或物品不存在。", "确认已创建用户，并检查物品名称是否正确。")

        weight_row = conn.execute(
            """
            SELECT COALESCE(SUM(b.quantity * i.weight), 0) AS total
            FROM backpack_items b
            JOIN item_defs i ON i.item_id = b.item_id
            WHERE b.client_id = ?
            """,
            (client_id,),
        ).fetchone()
        weight_after = int(weight_row["total"]) + int(item["weight"]) * quantity
        if weight_after > int(player["weight_limit"]):
            return False, hint(
                f"背包负重不足，放入后会变成 {weight_after}/{player['weight_limit']}。",
                "先发送：商场出售 商品名 数量，或发送：商场自动出售 清理跑商货物。",
            )

        current = conn.execute(
            "SELECT quantity FROM backpack_items WHERE client_id = ? AND item_id = ?",
            (client_id, item_id),
        ).fetchone()
        current_quantity = int(current["quantity"]) if current else 0
        if current_quantity + quantity > int(item["stack_limit"]):
            return False, hint(
                f"{item['name']} 堆叠上限不足，最多 {item['stack_limit']}。",
                "先出售或使用一部分同名物品，再重新领取或购买。",
            )

        if not current:
            kind_row = conn.execute(
                "SELECT COUNT(*) AS total FROM backpack_items WHERE client_id = ? AND quantity > 0",
                (client_id,),
            ).fetchone()
            if int(kind_row["total"]) + 1 > int(player["backpack_limit"]):
                return False, hint(
                    f"背包格子不足，最多 {player['backpack_limit']} 种物品。",
                    "先出售不需要的背包物品，再重新领取或购买。",
                )

        return True, ""

    def remove_backpack_conn(self, conn: sqlite3.Connection, client_id: str, item_id: str, quantity: int) -> bool:
        """在事务里扣除背包物品。"""

        row = conn.execute(
            "SELECT quantity FROM backpack_items WHERE client_id = ? AND item_id = ?",
            (client_id, item_id),
        ).fetchone()
        if not row or row["quantity"] < quantity:
            return False
        left = row["quantity"] - quantity
        if left:
            conn.execute(
                "UPDATE backpack_items SET quantity = ? WHERE client_id = ? AND item_id = ?",
                (left, client_id, item_id),
            )
        else:
            conn.execute(
                "DELETE FROM backpack_items WHERE client_id = ? AND item_id = ?",
                (client_id, item_id),
            )
        return True

    def add_ring_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        equipment_item_id: str,
        quantity: int,
    ) -> None:
        """在事务里增加纳戒物品。"""

        if quantity <= 0:
            return
        if self._is_gem_conn(conn, equipment_item_id):
            self.add_gem_conn(conn, client_id, equipment_item_id, 1, quantity)
            return
        conn.execute(
            """
            INSERT INTO ring_items (client_id, equipment_item_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(client_id, equipment_item_id)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (client_id, equipment_item_id, quantity),
        )

    def remove_ring_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        equipment_item_id: str,
        quantity: int,
    ) -> bool:
        """在事务里扣除纳戒物品。"""

        if self._is_gem_conn(conn, equipment_item_id):
            return self.remove_gem_conn(conn, client_id, equipment_item_id, 1, quantity)

        row = conn.execute(
            "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
            (client_id, equipment_item_id),
        ).fetchone()
        if not row or row["quantity"] < quantity:
            return False
        left = row["quantity"] - quantity
        if left:
            conn.execute(
                "UPDATE ring_items SET quantity = ? WHERE client_id = ? AND equipment_item_id = ?",
                (left, client_id, equipment_item_id),
            )
        else:
            conn.execute(
                "DELETE FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
                (client_id, equipment_item_id),
            )
        return True

    def add_gem_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        gem_id: str,
        level: int,
        quantity: int,
    ) -> None:
        """在事务里增加指定等级的宝石库存。"""

        if quantity <= 0:
            return
        conn.execute(
            """
            INSERT INTO gem_items (client_id, gem_id, level, quantity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id, gem_id, level)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (client_id, gem_id, max(1, int(level)), quantity),
        )

    def remove_gem_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        gem_id: str,
        level: int,
        quantity: int,
    ) -> bool:
        """在事务里扣除指定等级的宝石库存。"""

        row = conn.execute(
            """
            SELECT quantity FROM gem_items
            WHERE client_id = ? AND gem_id = ? AND level = ?
            """,
            (client_id, gem_id, max(1, int(level))),
        ).fetchone()
        if not row or row["quantity"] < quantity:
            return False
        left = row["quantity"] - quantity
        if left:
            conn.execute(
                """
                UPDATE gem_items
                SET quantity = ?
                WHERE client_id = ? AND gem_id = ? AND level = ?
                """,
                (left, client_id, gem_id, max(1, int(level))),
            )
        else:
            conn.execute(
                """
                DELETE FROM gem_items
                WHERE client_id = ? AND gem_id = ? AND level = ?
                """,
                (client_id, gem_id, max(1, int(level))),
            )
        return True

    @staticmethod
    def _is_gem_conn(conn: sqlite3.Connection, equipment_item_id: str) -> bool:
        """判断装备库物品是否是宝石。"""

        row = conn.execute(
            "SELECT category FROM equipment_item_defs WHERE equipment_item_id = ?",
            (equipment_item_id,),
        ).fetchone()
        return bool(row and row["category"] == "宝石")

    def backpack_weight(self, client_id: str) -> int:
        """计算背包负重。"""

        rows = self.db.fetch_all(
            """
            SELECT b.quantity, i.weight
            FROM backpack_items b
            JOIN item_defs i ON i.item_id = b.item_id
            WHERE b.client_id = ?
            """,
            (client_id,),
        )
        return sum(row["quantity"] * row["weight"] for row in rows)

    def backpack_rows(self, client_id: str) -> list[dict[str, Any]]:
        """读取背包明细。"""

        return self.db.fetch_all(
            """
            SELECT b.item_id, b.quantity, i.name, i.weight, i.category, i.usable, i.base_price, i.effect
            FROM backpack_items b
            JOIN item_defs i ON i.item_id = b.item_id
            WHERE b.client_id = ? AND b.quantity > 0
            ORDER BY i.category, i.name
            """,
            (client_id,),
        )

    def ring_rows(self, client_id: str) -> list[dict[str, Any]]:
        """读取纳戒明细。"""

        rows = self.db.fetch_all(
            """
            SELECT r.equipment_item_id, r.quantity, e.name, e.category, e.usable, e.effect, NULL AS level
            FROM ring_items r
            JOIN equipment_item_defs e ON e.equipment_item_id = r.equipment_item_id
            WHERE r.client_id = ? AND r.quantity > 0
              AND e.category != '宝石'
            ORDER BY e.category, e.name
            """,
            (client_id,),
        )
        rows.extend(self.gem_rows(client_id))
        return sorted(rows, key=lambda row: (row["category"], row["name"], row.get("level") or 0))

    def gem_rows(self, client_id: str) -> list[dict[str, Any]]:
        """读取纳戒里按等级分组的宝石库存。"""

        return self.db.fetch_all(
            """
            SELECT g.gem_id AS equipment_item_id, g.quantity, g.level,
                   e.name, e.category, e.usable, e.effect
            FROM gem_items g
            JOIN equipment_item_defs e ON e.equipment_item_id = g.gem_id
            WHERE g.client_id = ? AND g.quantity > 0
            ORDER BY e.name, g.level
            """,
            (client_id,),
        )

    def format_player_name(self, client_id: str) -> str:
        """返回展示名和 id。"""

        player = self.player(client_id)
        if not player:
            return client_id
        return f"{player['display_name']}({client_id})"

    def next_level_text(self, player: dict[str, Any]) -> str:
        """返回升级进度文本。"""

        if player["level"] >= MAX_LEVEL:
            return "已满级"
        need_total = sum(exp_need(level) for level in range(1, player["level"] + 1))
        current = player["exp"] - sum(exp_need(level) for level in range(1, player["level"]))
        need = exp_need(player["level"])
        return f"{current}/{need}"


def format_effect(effect_text: str) -> str:
    """把物品效果 JSON 转成展示文本。"""

    effect = load_json(effect_text, {})
    parts: list[str] = []
    if effect.get("exp_delta"):
        parts.append(f"经验+{effect['exp_delta']}")
    if effect.get("random_exp_min") is not None:
        parts.append(f"经验+{effect['random_exp_min']}-{effect['random_exp_max']}")
    if effect.get("random_stones_min") is not None:
        parts.append(f"源石+{effect['random_stones_min']}-{effect['random_stones_max']}")
    if effect.get("random_stones_segments"):
        texts = []
        for segment in effect["random_stones_segments"]:
            if not isinstance(segment, dict):
                continue
            texts.append(
                f"{segment.get('min_level')}-{segment.get('max_level')}级:"
                f"{segment.get('min')}-{segment.get('max')}"
            )
        if texts:
            parts.append("源石按等级段随机(" + "；".join(texts) + ")")
    if effect.get("hp_delta"):
        parts.append(f"血气+{effect['hp_delta']}")
    if effect.get("mp_delta"):
        parts.append(f"精神+{effect['mp_delta']}")
    if effect.get("hp_ratio"):
        parts.append(f"血气+{int(effect['hp_ratio'] * 100)}%")
    if effect.get("mp_ratio"):
        parts.append(f"精神+{int(effect['mp_ratio'] * 100)}%")
    if effect.get("wash_physique"):
        parts.append("洗髓体质，大概率升阶，小概率回落")
    bonus_labels = {
        "max_hp_bonus": "血气上限",
        "max_mp_bonus": "精神上限",
        "mp_bonus": "精神上限",
        "defense_bonus": "防御",
    }
    for key, label in bonus_labels.items():
        value = effect.get(key)
        if isinstance(value, int | float) and value:
            parts.append(f"{label}{value:+g}")
    rate_labels = {
        "dodge_bonus": "闪避",
        "recover_bonus": "恢复",
        "explore_bonus": "探险",
        "crit_resist_bonus": "承伤减免",
    }
    for key, label in rate_labels.items():
        value = effect.get(key)
        if isinstance(value, int | float) and value:
            parts.append(f"{label}{value * 100:+.1f}%")
    trade_bonus = effect.get("trade_bonus")
    if isinstance(trade_bonus, int | float) and trade_bonus:
        if trade_bonus > 0:
            parts.append(f"跑商手续费-{trade_bonus * 100:.1f}%")
        else:
            parts.append(f"跑商手续费+{abs(trade_bonus) * 100:.1f}%")
    return "，".join(parts) if parts else "无主动效果"


def choose_one(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """随机选择一行。"""

    values = list(rows)
    if not values:
        return None
    return random.choice(values)


def mark_request_once(client_id: str, request_id: object, raw_message: object = "") -> bool:
    """记录 WS request_id，重复请求返回 False。"""

    request_text = str(request_id or "").strip()
    if not request_text:
        return True

    from .sql import db

    with db.transaction() as conn:
        exists = conn.execute(
            """
            SELECT 1 FROM request_idempotency
            WHERE client_id = ? AND request_id = ?
            """,
            (client_id, request_text),
        ).fetchone()
        if exists:
            return False
        conn.execute(
            """
            INSERT INTO request_idempotency (client_id, request_id, raw_message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (client_id, request_text, str(raw_message or ""), ts()),
        )
    return True


__all__ = [
    "Any",
    "CoreService",
    "business_day",
    "choose_one",
    "dt",
    "dump_json",
    "format_effect",
    "hint",
    "load_json",
    "money",
    "mark_request_once",
    "now",
    "parse_name_level",
    "parse_player_ref",
    "quality_factor",
    "random",
    "random_quality",
    "split_words",
    "sqlite3",
    "timedelta",
    "to_int",
    "ts",
    "validate_name",
]
