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
        finally:
            db.close()

    print("修仙跑商推荐测试通过")


if __name__ == "__main__":
    main()
