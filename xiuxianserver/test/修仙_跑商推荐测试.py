"""跑商推荐测试。

运行方式：

    python test/修仙_跑商推荐测试.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.sql import XiuxianDB
from 修仙.玩家.service import PlayerService
from 修仙.贸易服务.service import TradeService
from 修仙.common import business_day, ts
from 修仙.rules import trade_fatigue_profit_rate


def main() -> None:
    """推荐页前三条路线应综合市场状态，而不是全指向同一个终点。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "trade_recommend_test.db")
        try:
            player = PlayerService(db)
            trade = TradeService(db)
            player.create("trade_tester", "行商客")
            player.add_stones("trade_tester", 500_000)
            db.execute(
                """
                UPDATE players
                SET location_name = '天枢城', x = 0, y = 0
                WHERE client_id = ?
                """,
                ("trade_tester",),
            )

            row = trade.player("trade_tester")
            assert row is not None
            options = trade._trade_options("trade_tester", row)
            recommended = trade._recommended_trade_options("trade_tester", row)
            assert options
            assert recommended
            assert all(option.get("market_label") for option in recommended[:3])

            available_targets = {str(option["target"]) for option in options}
            shown_targets = {str(option["target"]) for option in recommended[:3]}
            assert len(shown_targets) >= min(3, len(available_targets)), recommended[:3]

            same_market = trade._daily_market("city_xingyun", "trade_contract")
            assert same_market == trade._daily_market("city_xingyun", "trade_contract")
            assert 0.88 <= float(same_market["factor"]) <= 1.15

            text = trade.recommend("trade_tester")
            assert text.count("导航 星陨墟") < 3, text
            assert "行情：" in text, text

            with db.transaction() as conn:
                market_state = trade._trade_market_state_conn(conn, "trade_tester")
                fatigue_seed = max(1, market_state["player_soft_line"] // 2)
                conn.execute(
                    """
                    INSERT INTO trade_records
                    (client_id, action, item_id, quantity, effective_quantity, fatigue_quantity,
                     total_price, fee, effective_profit, fatigue_profit, location_name, business_day, created_at)
                    VALUES (?, 'sell', ?, ?, ?, ?, 1, 0, 1, 0, ?, ?, ?)
                    """,
                    (
                        "trade_tester",
                        options[0]["item_id"],
                        market_state["player_soft_line"] + fatigue_seed,
                        market_state["player_soft_line"],
                        fatigue_seed,
                        str(options[0]["target"]),
                        business_day(),
                        ts(),
                    ),
                )
            fatigue_text = trade.recommend("trade_tester")
            assert "商场购买" in fatigue_text, fatigue_text
            assert "散商" in fatigue_text, fatigue_text
            with db.transaction() as conn:
                fatigue_state = trade._trade_market_state_conn(conn, "trade_tester")
            fresh_fatigue_rate = trade_fatigue_profit_rate(0, fatigue_state["player_soft_line"])
            current_fatigue_rate = trade_fatigue_profit_rate(
                fatigue_state["player_fatigue_used"],
                fatigue_state["player_soft_line"],
            )
            heavy_fatigue_rate = trade_fatigue_profit_rate(
                fatigue_state["player_soft_line"] * 20,
                fatigue_state["player_soft_line"],
            )
            assert 0.149 <= fresh_fatigue_rate <= 0.151
            assert current_fatigue_rate < fresh_fatigue_rate
            assert 0.079 <= heavy_fatigue_rate <= 0.081

            with db.transaction() as conn:
                hot_state = trade._trade_market_state_conn(conn, "trade_tester")
                conn.execute(
                    """
                    INSERT INTO trade_records
                    (client_id, action, item_id, quantity, effective_quantity, fatigue_quantity,
                     total_price, fee, effective_profit, fatigue_profit, location_name, business_day, created_at)
                    VALUES ('other_runner', 'sell', ?, ?, ?, 0, 1, 0, 1, 0, ?, ?, ?)
                    """,
                    (
                        options[0]["item_id"],
                        hot_state["global_soft_line"] * 2,
                        hot_state["global_soft_line"] * 2,
                        str(options[0]["target"]),
                        business_day(),
                        ts(),
                    ),
                )
                locations = conn.execute("SELECT location_id, name FROM trade_locations").fetchall()
                goods = conn.execute("SELECT item_id FROM trade_goods").fetchall()
                for location in locations:
                    for good in goods:
                        trade._add_heat_conn(
                            conn,
                            str(location["name"]),
                            str(good["item_id"]),
                            buy_count=500,
                            sell_count=500,
                            location_id=str(location["location_id"]),
                        )
            hot_text = trade.recommend("trade_tester")
            assert "商场购买" in hot_text, hot_text
            assert "散商" in hot_text, hot_text
            hot_options = trade._recommended_trade_options("trade_tester", trade.player("trade_tester"))
            assert hot_options, hot_text
            assert min(int(option["quantity"]) for option in hot_options) >= 3

            original_trade_options_for_location = trade._trade_options_for_location

            def no_current_location_options(client_id: str, player_row: dict, source: str, current: str) -> list[dict]:
                if source == current:
                    return []
                return original_trade_options_for_location(client_id, player_row, source, current)

            trade._trade_options_for_location = no_current_location_options  # type: ignore[method-assign]
            global_text = trade.recommend("trade_tester")
            assert "全图跑商推荐" in global_text, global_text
            assert "当前城池暂无正收益路线" in global_text, global_text
            assert "导航 " in global_text and "商场购买" in global_text, global_text
        finally:
            db.close()

    print("修仙跑商推荐测试通过")


if __name__ == "__main__":
    main()
