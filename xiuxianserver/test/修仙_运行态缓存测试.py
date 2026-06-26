"""修仙运行态缓存测试。

缓存只允许保存定义资料和短期身份解析：
- 定义表返回值必须是拷贝，调用方临时改字段不能污染缓存。
- 建库、世界皮肤切换、用户组绑定后必须能主动清理缓存。
- 玩家库存、货币、探险记录等实时数据不在本测试缓存范围内。
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.definition_cache import item_def_by_id, trade_location_by_point
from 修仙.identity import bind_client_to_player, ensure_player_identity, resolve_player_id
from 修仙.runtime_cache import clear_runtime_caches
from 修仙.sql import XiuxianDB


def test_definition_cache_returns_copies() -> None:
    """定义缓存不能被调用方修改污染。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "cache_copy.db")
        try:
            db.init()
            first = item_def_by_id(db, "loot_yao_1")
            assert first is not None
            original_name = first["name"]
            first["name"] = "被调用方临时改名"

            second = item_def_by_id(db, "loot_yao_1")
            assert second is not None
            assert second["name"] == original_name
        finally:
            db.close()


def test_runtime_cache_clear_refreshes_definition_rows() -> None:
    """清理运行态缓存后，定义表读取应反映数据库最新值。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "cache_clear.db")
        try:
            db.init()
            before = trade_location_by_point(db, 0, 0)
            assert before is not None
            assert before["name"]

            db.execute("UPDATE trade_locations SET name = ? WHERE location_id = ?", ("缓存测试城", "city_tianshu"))
            still_cached = trade_location_by_point(db, 0, 0)
            assert still_cached is not None
            assert still_cached["name"] == before["name"]

            clear_runtime_caches(reason="test_definition_refresh")
            refreshed = trade_location_by_point(db, 0, 0)
            assert refreshed is not None
            assert refreshed["name"] == "缓存测试城"
        finally:
            db.close()


def test_identity_cache_clears_after_binding() -> None:
    """绑定新入口后，身份解析缓存必须立即失效。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "identity_cache.db")
        try:
            db.init()
            db.execute(
                """
                INSERT INTO players
                (client_id, display_name, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                ("main_player", "缓存道友"),
            )
            assert resolve_player_id("extra_client", db) == "extra_client"

            ensure_player_identity("main_player", db)
            bind_client_to_player("extra_client", "main_player", db)
            assert resolve_player_id("extra_client", db) == "main_player"
        finally:
            db.close()


def main() -> None:
    test_definition_cache_returns_copies()
    test_runtime_cache_clear_refreshes_definition_rows()
    test_identity_cache_clears_after_binding()
    print("修仙运行态缓存测试通过")


if __name__ == "__main__":
    main()
