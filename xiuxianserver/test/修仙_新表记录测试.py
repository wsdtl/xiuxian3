"""修仙长期记录表测试。

运行方式：

    python test/修仙_新表记录测试.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.common import ts
from 修仙.sql import XiuxianDB
from 修仙.玩家.service import PlayerService
from 修仙.武器.service import WeaponService
from 修仙.源库.service import SourceVaultService


def main() -> None:
    """验证新表不只是建表，也会沉淀真实数据。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "xiuxian_records_test.db")
        player = PlayerService(db)
        weapon = WeaponService(db)
        vault = SourceVaultService(db)

        assert "创建成功" in player.create("record_player", "青衫客")
        assert "签到成功" in player.sign("record_player")
        assert "新手礼包领取成功" in player.newbie_gift("record_player")
        assert "已存入源石" in vault.deposit("record_player", 1000)
        weapon.ensure_starter_weapon("record_player")
        weapon_id = db.fetch_one("SELECT weapon_id FROM player_weapons WHERE owner_id = ?", ("record_player",))
        assert weapon_id is not None
        assert "升级成功" in weapon.upgrade("record_player", str(weapon_id["weapon_id"]))

        with db.transaction() as conn:
            conn.execute(
                "UPDATE players SET level = 9, exp = 12345, source_stones = source_stones + 500000 WHERE client_id = ?",
                ("record_player",),
            )
            conn.execute(
                "UPDATE source_vaults SET balance = 120000 WHERE client_id = ?",
                ("record_player",),
            )
            for index in range(5):
                conn.execute(
                    """
                    INSERT INTO exploration_records
                    (client_id, location_name, status, started_at, ready_at, finished_at, result, claimed)
                    VALUES (?, ?, '已领取', ?, ?, ?, '{}', 1)
                    """,
                    ("record_player", "青岚坊", ts(), ts(), ts()),
                )
            for index in range(20):
                conn.execute(
                    """
                    INSERT INTO trade_records
                    (client_id, action, item_id, quantity, total_price, fee, location_name, business_day, created_at)
                    VALUES (?, 'sell', ?, 1, 10000, 100, '天枢城', '2099-01-01', ?)
                    """,
                    ("record_player", f"test_trade_{index}", ts()),
                )

        profile_text = player.profile("record_player")
        assert "经验" in profile_text
        assert "源石" in profile_text
        assert "武器" in profile_text
        assert "修仙日记" in player.diary("record_player")

        journal_count = db.fetch_one(
            "SELECT COUNT(*) AS count FROM player_journals WHERE client_id = ?",
            ("record_player",),
        )
        assert int(journal_count["count"]) >= 8
        level_journal = db.fetch_one(
            """
            SELECT text FROM player_journals
            WHERE client_id = ? AND milestone_key = 'level'
            """,
            ("record_player",),
        )
        assert level_journal and "累计经验 12345" in level_journal["text"]

        title_count = db.fetch_one(
            "SELECT COUNT(*) AS count FROM player_titles WHERE client_id = ?",
            ("record_player",),
        )
        active_title = db.fetch_one(
            "SELECT title FROM player_titles WHERE client_id = ? AND active = 1",
            ("record_player",),
        )
        assert int(title_count["count"]) >= 5
        assert active_title is not None

        log_actions = {
            row["action"]
            for row in db.fetch_all(
                "SELECT action FROM game_logs WHERE client_id = ?",
                ("record_player",),
            )
        }
        assert {"创建用户", "签到", "新手礼包", "存入源石", "升级武器"}.issubset(log_actions)
        db.close()

    print("修仙长期记录表测试通过")


if __name__ == "__main__":
    main()
