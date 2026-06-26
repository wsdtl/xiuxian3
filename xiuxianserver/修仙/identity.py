"""用户组身份解析。

普通玩法只关心修仙角色 ID。适配器传入的原始 client_id 会先在
user_identities 中查找归属用户组，再映射到 user_groups.primary_player_id。
创建用户、绑定用户组这类身份入口仍必须使用原始 client_id。
"""

from __future__ import annotations

import ast
import sqlite3
from typing import Any

from launch.adapter import Depends
from launch import config

from .sql import db


def current_player_id(client_id: str) -> str:
    """Depends 依赖：把驱动器 client_id 解析为修仙玩家 player_id。"""

    return resolve_player_id(client_id)


def current_is_master(player_id: str = Depends(current_player_id)) -> bool:
    """Depends 依赖：判断当前修仙玩家是否在主人名单内。"""

    return is_master_player(player_id)


def resolve_player_id(client_id: str, database: Any | None = None) -> str:
    """把驱动器原始 client_id 解析成修仙业务 player_id。

    用户组表未初始化或查询异常时直接回退原始 client_id，保证启动、建库
    和测试中的空库场景不会因为身份映射表缺失而阻断基础命令。
    """

    raw_id = str(client_id or "").strip()
    if not raw_id:
        return ""

    database = _database(database)
    try:
        row = database.fetch_one(
            """
            SELECT g.primary_player_id
            FROM user_identities AS i
            JOIN user_groups AS g ON g.group_id = i.group_id
            WHERE i.client_id = ?
            LIMIT 1
            """,
            (raw_id,),
        )
    except sqlite3.Error:
        return raw_id

    player_id = str(row.get("primary_player_id") or "").strip() if row else ""
    return player_id or raw_id


def player_id_dep() -> Depends:
    """创建当前玩家 ID 依赖，避免业务模块直接关心依赖函数。"""

    return Depends(current_player_id)


def master_dep() -> Depends:
    """创建主人权限依赖，供需要主人级操作的命令入口使用。"""

    return Depends(current_is_master)


def is_master_player(player_id: str, database: Any | None = None) -> bool:
    """按玩家显示名判断是否具备主人权限。"""

    normalized = str(player_id or "").strip()
    if not normalized:
        return False

    database = _database(database)
    try:
        row = database.fetch_one(
            "SELECT display_name FROM players WHERE client_id = ? LIMIT 1",
            (normalized,),
        )
    except sqlite3.Error:
        return False
    if not row:
        return False
    display_name = str(row.get("display_name") or "").strip()
    return bool(display_name and display_name in master_names())


def master_names() -> set[str]:
    """读取 .env 的 MASTER_NAME 主人显示名列表。"""

    raw = str(config.get("MASTER_NAME", "") or "").strip()
    if not raw:
        return set()
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        parsed = raw
    if isinstance(parsed, str):
        return {parsed.strip()} if parsed.strip() else set()
    if isinstance(parsed, (list, tuple, set)):
        return {str(item).strip() for item in parsed if str(item).strip()}
    return set()


def player_exists(player_id: str, database: Any | None = None) -> bool:
    """判断某个修仙业务 player_id 是否已经创建角色。"""

    database = _database(database)
    return bool(database.fetch_one("SELECT 1 FROM players WHERE client_id = ? LIMIT 1", (player_id,)))


def client_id_has_player(client_id: str, database: Any | None = None) -> bool:
    """判断原始入口 client_id 是否已经拥有独立角色。"""

    return player_exists(client_id, database)


def identity_tables_ready(database: Any | None = None) -> bool:
    """判断用户组身份表是否已经存在。"""

    database = _database(database)
    try:
        return bool(
            database.fetch_one(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'user_identities'
                LIMIT 1
                """
            )
        )
    except sqlite3.Error:
        return False


def ensure_player_identity(player_id: str, database: Any | None = None) -> int:
    """确保已有玩家拥有用户组和主身份，返回 group_id。"""

    normalized = str(player_id or "").strip()
    if not normalized:
        raise ValueError("player_id 不能为空")

    database = _database(database)
    with database.transaction() as conn:
        group_id = _group_id_for_player_conn(conn, normalized)
        if group_id is None:
            cursor = conn.execute(
                """
                INSERT INTO user_groups (primary_player_id, created_at)
                VALUES (?, datetime('now'))
                """,
                (normalized,),
            )
            group_id = int(cursor.lastrowid)

        conn.execute(
            """
            INSERT INTO user_identities (group_id, client_id, is_primary, created_at)
            VALUES (?, ?, 1, datetime('now'))
            ON CONFLICT(client_id) DO NOTHING
            """,
            (group_id, normalized),
        )
        return group_id


def bind_client_to_player(client_id: str, player_id: str, database: Any | None = None) -> None:
    """把一个驱动器 client_id 绑定到已有修仙玩家 player_id。"""

    normalized_client = str(client_id or "").strip()
    normalized_player = str(player_id or "").strip()
    if not normalized_client or not normalized_player:
        raise ValueError("client_id 和 player_id 不能为空")

    database = _database(database)
    with database.transaction() as conn:
        group_id = _group_id_for_player_conn(conn, normalized_player)
        if group_id is None:
            cursor = conn.execute(
                """
                INSERT INTO user_groups (primary_player_id, created_at)
                VALUES (?, datetime('now'))
                """,
                (normalized_player,),
            )
            group_id = int(cursor.lastrowid)

        conn.execute(
            """
            INSERT INTO user_identities (group_id, client_id, is_primary, created_at)
            VALUES (?, ?, 0, datetime('now'))
            """,
            (group_id, normalized_client),
        )


def identities_for_player(player_id: str, database: Any | None = None) -> list[dict[str, Any]]:
    """列出某个主角色下的所有入口身份。"""

    normalized = str(player_id or "").strip()
    if not normalized:
        return []

    database = _database(database)
    try:
        return database.fetch_all(
            """
            SELECT i.identity_id, i.client_id, i.is_primary, i.created_at
            FROM user_identities AS i
            JOIN user_groups AS g ON g.group_id = i.group_id
            WHERE g.primary_player_id = ?
            ORDER BY i.is_primary DESC, i.identity_id
            """,
            (normalized,),
        )
    except sqlite3.Error:
        return []


def _database(database: Any | None) -> Any:
    """返回显式注入的数据库，否则使用全局玩法库。"""

    return database if database is not None else db


def _group_id_for_player_conn(conn: sqlite3.Connection, player_id: str) -> int | None:
    """在既有事务连接内查找玩家主身份对应用户组。"""

    row = conn.execute(
        "SELECT group_id FROM user_groups WHERE primary_player_id = ? LIMIT 1",
        (player_id,),
    ).fetchone()
    return int(row["group_id"]) if row else None
