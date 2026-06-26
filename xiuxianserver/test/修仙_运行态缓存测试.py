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

from 修仙.common import CoreService
from 修仙.definition_cache import item_def_by_id, trade_location_by_point
from 修仙.identity import bind_client_to_player, ensure_player_identity, resolve_player_id
from 修仙.runtime_cache import clear_runtime_caches
from 修仙.sql import XiuxianDB
from 修仙.world_skin import apply_world_skin_package, load_skin_package, validate_skin_package
from 修仙.修仙百科.service import EncyclopediaService


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


def test_player_reference_uses_group_primary_id() -> None:
    """@ 到对方副入口时，决斗同款目标解析必须落到对方主角色。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "identity_ref.db")
        try:
            db.init()
            db.execute(
                """
                INSERT INTO players
                (client_id, display_name, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                ("target_main", "主号道友"),
            )
            ensure_player_identity("target_main", db)
            bind_client_to_player("target_extra", "target_main", db)

            service = CoreService(db)
            assert service.player_id_by_ref("target_extra") == "target_main"
            assert service.player_id_from_last_arg("决斗 100 target_extra") == "target_main"
            assert service.player_id_by_ref("主号道友") == "target_main"
            assert service.format_player_name("target_extra") == "主号道友"
        finally:
            db.close()


def test_encyclopedia_cache_clears_after_world_skin_switch() -> None:
    """百科预加载后再换皮，也必须用新皮肤名回答具体物品。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "encyclopedia_skin.db")
        try:
            db.init()
            encyclopedia = EncyclopediaService(db)
            encyclopedia.load()

            package = load_skin_package("perfect_world")
            errors = validate_skin_package(package, db)
            assert not errors, errors[:3]
            with db.transaction() as conn:
                apply_world_skin_package(conn, package, switched_by="test")

            row = db.fetch_one("SELECT name FROM ring_item_defs WHERE ring_item_id = ?", ("kaikongqi",))
            assert row is not None
            skin_item_name = str(row["name"])
            answer = encyclopedia.ask("visitor", f"{skin_item_name}怎么用")
            assert skin_item_name in answer
            assert "不走“使用”" in answer
            assert "开孔 装备位" in answer
            assert "血藤籽" not in answer
        finally:
            db.close()


def main() -> None:
    test_definition_cache_returns_copies()
    test_runtime_cache_clear_refreshes_definition_rows()
    test_identity_cache_clears_after_binding()
    test_player_reference_uses_group_primary_id()
    test_encyclopedia_cache_clears_after_world_skin_switch()
    print("修仙运行态缓存测试通过")


if __name__ == "__main__":
    main()
