"""商场跑商组件服务。"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from math import hypot

from ..common import CoreService, business_day, dt, hint, load_json, money, now, split_words, to_int, ts
from ..constants import (
    TRADE_BUY_FEE_RATE,
    TRADE_MAX_PROFIT_RATE,
    TRADE_RESALE_LOCK_HOURS,
    TRADE_SELL_FEE_RATE,
)
from ..rules import special_sell_price_rate, special_sell_soft_line
from ..sql import TRADE_LOCATION_DEMANDS, db


class TradeService(CoreService):
    """地点跑商、价格查询和特殊收购。"""

    def current(self, client_id: str) -> str:
        """查看当前位置商场。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        rows = self._location_goods(player["location_name"])
        if not rows:
            return hint(f"{player['location_name']} 暂无商场商品。", "发送：商场列表 查看跑商地点，再发送：导航 地点名")
        lines = [f"☆{player['location_name']}商场☆"]
        for row in rows[:12]:
            buy, sell = self.price(player["location_name"], row["item_id"])
            lines.append(f"{row['name']} 买{money(buy)} 卖{money(sell)} 重{row['weight']}")
        return "\n".join(lines)

    def locations(self, client_id: str) -> str:
        """查看地点列表。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        trade_rows = self.db.fetch_all("SELECT * FROM trade_locations ORDER BY name")
        buyer_rows = self.db.fetch_all("SELECT * FROM special_buyers ORDER BY buyer_name")
        recycle_rows = self.db.fetch_all("SELECT * FROM weapon_recycle_locations ORDER BY name")
        lines = ["☆跑商地点☆"]
        lines.extend(f"{row['name']} ({row['x']},{row['y']})" for row in trade_rows)
        lines.append("☆特殊收购地点☆")
        lines.extend(f"{row['buyer_name']} ({row['x']},{row['y']})" for row in buyer_rows)
        lines.append("☆武器回收地点☆")
        lines.extend(f"{row['name']} ({row['x']},{row['y']})" for row in recycle_rows)
        return "\n".join(lines)

    def detail(self, client_id: str, location_name: str) -> str:
        """查看地点详情。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        name = location_name.strip()
        location = self._location(name)
        if not location:
            buyer = self._special_buyer(name)
            if buyer:
                return self._format_special_buyer(buyer)
            recycle_location = self._weapon_recycle_location(name)
            if recycle_location:
                return self._format_weapon_recycle_location(recycle_location)
            return hint(f"没有找到地点：{name}。", "发送：商场列表 查看可导航地点。")

        demand = TRADE_LOCATION_DEMANDS.get(location["name"], {})
        goods = self._location_goods(location["name"])
        lines = [f"☆{location['name']}详情☆", f"坐标：({location['x']},{location['y']})"]
        lines.append("偏好：" + ("、".join(f"{key}x{value}" for key, value in demand.items()) if demand else "无明显偏好"))
        lines.append("特产：")
        for row in goods:
            buy, sell = self.price(location["name"], row["item_id"])
            lines.append(f"{row['name']} {row['category']} 重{row['weight']} 买{money(buy)} 卖{money(sell)}")
        return "\n".join(lines)

    def market_price(self, client_id: str, item_name: str) -> str:
        """查看全图市价。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        item = self.item_def_by_name(item_name.strip())
        if not item:
            return hint(f"没有找到商品：{item_name.strip()}。", "发送：商场 查看当前位置商品，或发送：商场详情 地点名")
        if not item["tradeable"]:
            return hint(f"{item['name']} 不是跑商商品。", "跑商只能查询特产商品；其他物品可发送：查看背包 或 查看纳戒")
        rows = self.db.fetch_all("SELECT name FROM trade_locations ORDER BY name")
        lines = [f"☆{item['name']}市价☆"]
        for row in rows:
            buy, sell = self.price(row["name"], item["item_id"])
            lines.append(f"{row['name']} 买{money(buy)} 卖{money(sell)}")
        return "\n".join(lines)

    def buy(self, client_id: str, message: str) -> str:
        """商场购买。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        item_name, quantity = self._parse_name_quantity(message)
        if quantity <= 0:
            return hint("购买格式不正确。", "发送：商场购买 商品名 数量，例如：商场购买 青木符纸 3")
        item = self.item_def_by_name(item_name)
        if not item or not item["tradeable"]:
            return hint(f"{item_name} 不是可购买的跑商商品。", "发送：商场 查看当前位置可买商品。")
        location = self._location(player["location_name"])
        if not location:
            return hint("当前位置不是商场地点，无法购买跑商商品。", "发送：商场列表 查看地点，再发送：导航 地点名")
        home = self.db.fetch_one("SELECT home_location FROM trade_goods WHERE item_id = ?", (item["item_id"],))
        if not home or home["home_location"] != player["location_name"]:
            return hint(f"{player['location_name']} 不出售 {item['name']}。", "发送：商场市价 商品名 查看各地价格，再导航到产地购买。")
        buy_price, _sell_price = self.price(player["location_name"], item["item_id"], save=True)
        total = buy_price * quantity
        fee = int(total * self._trade_fee_rate(client_id, TRADE_BUY_FEE_RATE))
        with self.db.transaction() as conn:
            ok, reason = self.can_add_backpack_conn(conn, client_id, item["item_id"], quantity)
            if not ok:
                return reason
            if not self.spend_stones_conn(conn, client_id, total + fee):
                return hint(f"源石不足，需要 {money(total + fee)}。", "发送：源库 或 取出源石 数量，或先签到、探险、出售物品。")
            self.add_backpack_conn(conn, client_id, item["item_id"], quantity)
            conn.execute(
                """
                INSERT INTO trade_records
                (client_id, action, item_id, quantity, total_price, fee, location_name, business_day, created_at)
                VALUES (?, 'buy', ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_id, item["item_id"], quantity, total, fee, player["location_name"], business_day(), ts()),
            )
            self._add_heat_conn(conn, player["location_name"], item["item_id"], buy_count=quantity)
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_limits
                (client_id, item_id, location_name, last_buy_at, last_buy_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (client_id, item["item_id"], player["location_name"], ts(), buy_price),
            )
        return f"购买成功：{item['name']} x{quantity}，花费 {money(total)}，手续费 {money(fee)}。"

    def sell(self, client_id: str, message: str) -> str:
        """商场出售。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        if not self._location(player["location_name"]):
            return hint("当前位置不是商场地点。", "跑商货物请先导航到商场地点；特殊战利品请使用：特殊出售 物品名 数量")
        item_name, quantity = self._parse_name_quantity(message)
        if quantity <= 0:
            return hint("出售格式不正确。", "发送：商场出售 商品名 数量，例如：商场出售 青木符纸 3")
        item = self.item_def_by_name(item_name)
        if not item or not item["tradeable"]:
            return hint(f"{item_name} 不是可出售的跑商商品。", "发送：查看背包 查看可出售的跑商货物。")
        return self._sell_item(client_id, player["location_name"], item, quantity)

    def auto_sell(self, client_id: str) -> str:
        """自动出售所有可跑商物品。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        if not self._location(player["location_name"]):
            return hint("当前位置不是商场地点，无法自动出售跑商商品。", "发送：商场列表 查看跑商地点，再发送：导航 地点名")
        rows = [row for row in self.backpack_rows(client_id) if row["base_price"] and self.item_def(row["item_id"])["tradeable"]]
        if not rows:
            return hint("背包里没有可出售的跑商商品。", "发送：商场购买 商品名 数量，或先去探险获取特产。")
        total_gain = 0
        texts: list[str] = []
        for row in rows:
            item = self.item_def(row["item_id"])
            if not item:
                continue
            text = self._sell_item(client_id, player["location_name"], item, row["quantity"])
            texts.append(text)
            total_gain += 1
        return "自动出售完成：\n" + "\n".join(texts) if total_gain else hint("没有成功出售的商品。", "发送：查看背包 确认货物数量和类型。")

    def recommend(self, client_id: str) -> str:
        """按单位负重收益推荐当前能买的跑商路线。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        current = player["location_name"]
        if not self._location(current):
            return hint("当前位置不是商场地点。", "发送：商场列表 查看跑商地点，再发送：导航 地点名")
        options: list[tuple[float, int, str, str, int, int]] = []
        buy_fee_rate = self._trade_fee_rate(client_id, TRADE_BUY_FEE_RATE)
        sell_fee_rate = self._trade_fee_rate(client_id, TRADE_SELL_FEE_RATE)
        for item in self._location_goods(current):
            if not self._can_buy_one(client_id, player, item, buy_fee_rate):
                continue
            buy, _ = self.price(current, item["item_id"])
            for loc in self.db.fetch_all("SELECT name FROM trade_locations"):
                _, sell = self.price(loc["name"], item["item_id"])
                capped_sell = min(sell, int(buy * (1 + TRADE_MAX_PROFIT_RATE)))
                profit = int(capped_sell * (1 - sell_fee_rate)) - int(buy * (1 + buy_fee_rate))
                if loc["name"] != current and profit > 0:
                    profit_per_weight = profit / max(1, int(item["weight"]))
                    options.append((profit_per_weight, profit, item["name"], loc["name"], buy, capped_sell))
        options.sort(reverse=True, key=lambda row: row[0])
        if not options:
            return hint("当前没有能购买且有利润的跑商路线。", "确认随身源石和背包空间足够，或换一个商场地点再试。")
        lines = [f"☆{current}跑商推荐☆"]
        for profit_per_weight, profit, item_name, target, buy, sell in options[:5]:
            lines.append(
                f"{item_name} -> {target}，买{money(buy)} 卖{money(sell)}，"
                f"单件利润{money(profit)}，每负重{profit_per_weight:.1f}"
            )
        return "\n".join(lines)

    def records(self, client_id: str) -> str:
        """查看交易记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all(
            """
            SELECT r.*, i.name
            FROM trade_records r
            JOIN item_defs i ON i.item_id = r.item_id
            WHERE r.client_id = ?
            ORDER BY r.created_at DESC
            LIMIT 10
            """,
            (client_id,),
        )
        if not rows:
            return hint("暂无跑商记录。", "发送：商场推荐 查看路线，再发送：商场购买 商品名 数量")
        return "\n".join(
            f"{self._action_text(row['action'])} {row['name']} x{row['quantity']} {money(row['total_price'])} @ {row['location_name']}"
            for row in rows
        )

    def limits(self, client_id: str) -> str:
        """查看交易限制。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        return (
            f"限制：同地点买入后 {TRADE_RESALE_LOCK_HOURS} 小时内不能原地出售；"
            f"跑商单件利润率最高约 {int(TRADE_MAX_PROFIT_RATE * 100)}%；"
            f"今日特殊收购价 {self._special_sell_rate_text(client_id, player['level'])}。"
        )

    def special_buyers(self, client_id: str) -> str:
        """查看特殊收购。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        rows = self.db.fetch_all("SELECT * FROM special_buyers ORDER BY buyer_name")
        lines = [f"☆特殊收购☆ 今日收购价 {self._special_sell_rate_text(client_id, player['level'])}"]
        lines.append("自动出售：特殊自动出售")
        for row in rows:
            names = self._buyer_item_names(row)
            lines.append(
                f"{row['buyer_name']} ({row['x']},{row['y']})："
                f"{'、'.join(names)}，倍率 {row['price_factor']}"
            )
        return "\n".join(lines)

    def special_sell(self, client_id: str, message: str) -> str:
        """在特殊收购地点出售怪物战利品。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        buyer = self._special_buyer(player["location_name"])
        if not buyer:
            return hint("当前位置不是特殊收购地点。", "发送：特殊收购 查看收购地点，再发送：导航 地点名")

        item_name, quantity = self._parse_name_quantity(message)
        if quantity <= 0:
            return hint("特殊出售格式不正确。", "发送：特殊出售 物品名 数量，例如：特殊出售 妖核 2")
        item = self.item_def_by_name(item_name)
        if not item:
            return hint(f"没有找到物品：{item_name}。", "发送：查看背包 确认物品名称。")
        allowed = set(str(buyer["item_ids"]).split(","))
        if item["item_id"] not in allowed:
            return hint(f"{buyer['buyer_name']} 不收 {item['name']}。", "发送：特殊收购 查看各地点收购物，再导航到对应地点。")

        raw_total = int(item["base_price"] * float(buyer["price_factor"]) * quantity)
        with self.db.transaction() as conn:
            used = self._special_sell_used_conn(conn, client_id)
            rate = special_sell_price_rate(player["level"], used + raw_total // 2)
            total = max(1, int(raw_total * rate))
            if not self.remove_backpack_conn(conn, client_id, item["item_id"], quantity):
                return hint(f"背包中 {item['name']} 数量不足。", "发送：查看背包 确认数量，或继续探险获取。")
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (total, client_id),
            )
            conn.execute(
                """
                INSERT INTO trade_records
                (client_id, action, item_id, quantity, total_price, fee, location_name, business_day, created_at)
                VALUES (?, 'special_sell', ?, ?, ?, 0, ?, ?, ?)
                """,
                (client_id, item["item_id"], quantity, total, buyer["buyer_name"], business_day(), ts()),
            )
        return (
            f"特殊出售成功：{item['name']} x{quantity}，"
            f"原价 {money(raw_total)}，当前倍率 {int(rate * 100)}%，收入 {money(total)}。"
        )

    def special_auto_sell(self, client_id: str) -> str:
        """自动导航并出售背包里的所有特殊收购物。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        buyers = self._special_buyers_ordered()
        sell_plan = self._special_auto_sell_plan(client_id, buyers)
        if not sell_plan:
            return hint("背包里没有可特殊出售的物品。", "发送：特殊收购 查看收购物，或继续探险获取怪物战利品。")

        total_gain = 0
        last_buyer: dict | None = None
        lines = ["☆特殊自动出售☆"]
        with self.db.transaction() as conn:
            used = self._special_sell_used_conn(conn, client_id)
            for buyer, items in sell_plan:
                sold_lines: list[str] = []
                for item in items:
                    quantity = int(item["quantity"])
                    raw_total = int(item["base_price"] * float(buyer["price_factor"]) * quantity)
                    rate = special_sell_price_rate(player["level"], used + raw_total // 2)
                    total = max(1, int(raw_total * rate))
                    if not self.remove_backpack_conn(conn, client_id, item["item_id"], quantity):
                        sold_lines.append(f"{item['name']} x{quantity} 库存不足，已跳过")
                        continue

                    conn.execute(
                        "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                        (total, client_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO trade_records
                        (client_id, action, item_id, quantity, total_price, fee, location_name, business_day, created_at)
                        VALUES (?, 'special_auto_sell', ?, ?, ?, 0, ?, ?, ?)
                        """,
                        (client_id, item["item_id"], quantity, total, buyer["buyer_name"], business_day(), ts()),
                    )
                    used += total
                    total_gain += total
                    sold_lines.append(
                        f"{item['name']} x{quantity}，原价 {money(raw_total)}，"
                        f"倍率 {int(rate * 100)}%，收入 {money(total)}"
                    )

                if not sold_lines:
                    continue
                last_buyer = buyer
                lines.append(f"自动导航：{buyer['buyer_name']} ({buyer['x']},{buyer['y']})")
                lines.extend(sold_lines)

            if not last_buyer:
                return hint("没有成功出售的特殊物品。", "发送：查看背包 确认可出售物品数量。")
            conn.execute(
                "UPDATE players SET location_name = ?, x = ?, y = ? WHERE client_id = ?",
                (last_buyer["buyer_name"], last_buyer["x"], last_buyer["y"], client_id),
            )

        lines.append(f"合计收入：{money(total_gain)}")
        lines.append(f"当前位置：{last_buyer['buyer_name']} ({last_buyer['x']},{last_buyer['y']})")
        return "\n".join(lines)

    def navigate(self, client_id: str, message: str) -> str:
        """导航到最近地点。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        parts = split_words(message)
        if len(parts) == 1:
            location = self._location(parts[0]) or self._special_buyer(parts[0]) or self._weapon_recycle_location(parts[0])
        elif len(parts) >= 2:
            x = to_int(parts[0])
            y = to_int(parts[1])
            location = self._nearest_location(x, y)
        else:
            return hint("导航格式不正确。", "发送：导航 地点名，或发送：导航 x y")
        if not location:
            return hint("没有找到可导航地点。", "发送：商场列表 或 地点列表 查看地点名称。")
        name = location.get("name") or location.get("buyer_name")
        self.db.execute(
            "UPDATE players SET location_name = ?, x = ?, y = ? WHERE client_id = ?",
            (name, location["x"], location["y"], client_id),
        )
        return f"已到达 {name} ({location['x']},{location['y']})。"

    def price(self, location_name: str, item_id: str, save: bool = False) -> tuple[int, int]:
        """获取当天价格。

        跑商价格分三层：
        1. 物品自身基础价：写在 item_defs.base_price。
        2. 供需位置：产地便宜，离产地越远越贵。
        3. 地点需求：不同地点偏好不同类型货物。

        每日波动和买卖热度只做轻微扰动，不再决定货物的核心价值。
        """

        day = business_day()
        item = self.item_def(item_id)
        if not item:
            return 0, 0
        item_effect = load_json(item.get("effect"), {})
        trade_type = str(item_effect.get("trade_type") or "")
        home = self.db.fetch_one("SELECT home_location FROM trade_goods WHERE item_id = ?", (item_id,))
        home_name = home["home_location"] if home else location_name
        loc = self._location(location_name)
        home_loc = self._location(home_name)
        distance = hypot((loc["x"] - home_loc["x"]), (loc["y"] - home_loc["y"])) if loc and home_loc else 0
        seed = int(hashlib.md5(f"{day}:{location_name}:{item_id}".encode()).hexdigest()[:8], 16)
        daily_wave = 0.95 + (seed % 13) / 100
        supply_factor = self._supply_factor(distance, location_name == home_name)
        demand_factor = self._demand_factor(location_name, trade_type)
        heat = self.db.fetch_one(
            """
            SELECT buy_count, sell_count FROM trade_heat
            WHERE location_name = ? AND item_id = ? AND business_day = ?
            """,
            (location_name, item_id, day),
        ) or {"buy_count": 0, "sell_count": 0}
        market_price = item["base_price"] * supply_factor * demand_factor * daily_wave
        buy_price = max(1, int(market_price * min(1.5, 1.04 + heat["buy_count"] * 0.01)))
        sell_price = max(
            1,
            int(
                market_price
                * 0.82
                * max(0.65, 1.0 - heat["sell_count"] * 0.008)
            ),
        )
        if save:
            self.db.execute(
                """
                INSERT OR REPLACE INTO trade_prices
                (location_name, item_id, buy_price, sell_price, business_day)
                VALUES (?, ?, ?, ?, ?)
                """,
                (location_name, item_id, buy_price, sell_price, day),
            )
        return buy_price, sell_price

    @staticmethod
    def _supply_factor(distance: float, is_home: bool) -> float:
        """产地供给充足，所以便宜；离产地越远，运输价越高。"""

        if is_home:
            return 0.82
        return 0.96 + min(0.36, distance / 2600)

    @staticmethod
    def _demand_factor(location_name: str, trade_type: str) -> float:
        """读取地点对某类货物的需求倍率。"""

        if not trade_type:
            return 0.98
        return TRADE_LOCATION_DEMANDS.get(location_name, {}).get(trade_type, 0.98)

    def _sell_item(self, client_id: str, location_name: str, item: dict, quantity: int) -> str:
        """出售一类背包物品。"""

        _buy, sell_price = self.price(location_name, item["item_id"], save=True)
        locked_text = self._resale_lock_text(client_id, item["item_id"], location_name)
        if locked_text:
            return locked_text
        sell_price = self._profit_capped_sell_price(client_id, item["item_id"], sell_price)
        total = sell_price * quantity
        fee = int(total * self._trade_fee_rate(client_id, TRADE_SELL_FEE_RATE))
        with self.db.transaction() as conn:
            if not self.remove_backpack_conn(conn, client_id, item["item_id"], quantity):
                return hint(f"背包中 {item['name']} 数量不足。", "发送：查看背包 确认数量，或继续探险/购买获取。")
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (total - fee, client_id),
            )
            conn.execute(
                """
                INSERT INTO trade_records
                (client_id, action, item_id, quantity, total_price, fee, location_name, business_day, created_at)
                VALUES (?, 'sell', ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_id, item["item_id"], quantity, total, fee, location_name, business_day(), ts()),
            )
            self._add_heat_conn(conn, location_name, item["item_id"], sell_count=quantity)
        return f"出售成功：{item['name']} x{quantity}，收入 {money(total - fee)}，手续费 {money(fee)}。"

    def _resale_lock_text(self, client_id: str, item_id: str, location_name: str) -> str:
        """同地点刚买入的货物不能立刻原地卖出。"""

        row = self.db.fetch_one(
            """
            SELECT last_buy_at FROM trade_limits
            WHERE client_id = ? AND item_id = ? AND location_name = ?
            """,
            (client_id, item_id, location_name),
        )
        if not row:
            return ""
        last_buy_at = dt(row["last_buy_at"])
        if not last_buy_at:
            return ""
        passed = now() - last_buy_at
        lock_time = timedelta(hours=TRADE_RESALE_LOCK_HOURS)
        if passed >= lock_time:
            return ""
        left_minutes = max(1, int((lock_time - passed).total_seconds() // 60) + 1)
        return hint(f"这批货刚在本地买入，{left_minutes} 分钟后才能原地出售。", "先导航到其他商场出售，或等待冷却结束。")

    def _profit_capped_sell_price(self, client_id: str, item_id: str, sell_price: int) -> int:
        """按最近买入价限制最高利润，避免单次价格波动被刷爆。"""

        row = self.db.fetch_one(
            """
            SELECT last_buy_price FROM trade_limits
            WHERE client_id = ? AND item_id = ?
            ORDER BY last_buy_at DESC
            LIMIT 1
            """,
            (client_id, item_id),
        )
        if not row or not row["last_buy_price"]:
            return sell_price
        max_sell = int(row["last_buy_price"] * (1 + TRADE_MAX_PROFIT_RATE))
        return min(sell_price, max(1, max_sell))

    def _trade_fee_rate(self, client_id: str, base_rate: float) -> float:
        """按聚财类宝石小幅降低跑商手续费。"""

        trade_bonus = min(base_rate * 0.8, self.equipment_bonuses(client_id).get("trade_bonus", 0))
        return max(0.0, base_rate - trade_bonus)

    @staticmethod
    def _add_heat_conn(conn, location_name: str, item_id: str, buy_count: int = 0, sell_count: int = 0) -> None:
        """记录商场买卖热度。"""

        conn.execute(
            """
            INSERT INTO trade_heat (location_name, item_id, business_day, buy_count, sell_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(location_name, item_id, business_day)
            DO UPDATE SET
                buy_count = buy_count + excluded.buy_count,
                sell_count = sell_count + excluded.sell_count
            """,
            (location_name, item_id, business_day(), buy_count, sell_count),
        )

    def _parse_name_quantity(self, message: str) -> tuple[str, int]:
        """从命令参数里解析名称和数量。"""

        parts = split_words(message)
        if len(parts) < 2:
            return message.strip(), 0
        return " ".join(parts[:-1]), to_int(parts[-1])

    def _location(self, name: str) -> dict | None:
        """读取地点。"""

        return self.db.fetch_one("SELECT * FROM trade_locations WHERE name = ?", (name.strip(),))

    def _special_buyer(self, name: str) -> dict | None:
        """读取特殊收购地点。"""

        return self.db.fetch_one("SELECT * FROM special_buyers WHERE buyer_name = ?", (name.strip(),))

    def _weapon_recycle_location(self, name: str) -> dict | None:
        """读取武器回收地点。"""

        return self.db.fetch_one("SELECT * FROM weapon_recycle_locations WHERE name = ?", (name.strip(),))

    def _nearest_location(self, x: int, y: int) -> dict | None:
        """按坐标找最近地点。"""

        trade_rows = self.db.fetch_all("SELECT name, x, y FROM trade_locations")
        buyer_rows = self.db.fetch_all("SELECT buyer_name, x, y FROM special_buyers")
        recycle_rows = self.db.fetch_all("SELECT name, x, y FROM weapon_recycle_locations")
        rows = trade_rows + buyer_rows + recycle_rows
        if not rows:
            return None
        return min(rows, key=lambda row: hypot(row["x"] - x, row["y"] - y))

    def _buyer_item_names(self, buyer: dict) -> list[str]:
        """把特殊收购配置里的物品 id 转成名称。"""

        names = []
        for item_id in str(buyer["item_ids"]).split(","):
            item = self.item_def(item_id)
            names.append(item["name"] if item else item_id)
        return names

    def _format_special_buyer(self, buyer: dict) -> str:
        """格式化特殊收购地点详情。"""

        names = self._buyer_item_names(buyer)
        return (
            f"☆{buyer['buyer_name']}详情☆\n"
            f"坐标：({buyer['x']},{buyer['y']})\n"
            f"收购：{'、'.join(names)}\n"
            f"倍率：{buyer['price_factor']}"
        )

    @staticmethod
    def _format_weapon_recycle_location(location: dict) -> str:
        """格式化武器回收地点详情。"""

        return (
            f"☆{location['name']}详情☆\n"
            f"坐标：({location['x']},{location['y']})\n"
            f"倍率：{location['price_factor']}\n"
            f"{location['desc']}"
        )

    def _special_sell_rate_text(self, client_id: str, level: int) -> str:
        """读取今日特殊收购价格倍率展示。"""

        with self.db.transaction() as conn:
            used = self._special_sell_used_conn(conn, client_id)
        rate = special_sell_price_rate(level, used)
        soft_line = special_sell_soft_line(level)
        return f"{int(rate * 100)}%，今日已收入 {money(used)}，参考线 {money(soft_line)}"

    @staticmethod
    def _special_sell_used_conn(conn, client_id: str) -> int:
        """统计今日特殊收购已变现金额。"""

        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_price), 0) AS total
            FROM trade_records
            WHERE client_id = ?
              AND action IN ('special_sell', 'special_auto_sell')
              AND business_day = ?
            """,
            (client_id, business_day()),
        ).fetchone()
        return int(row["total"] if row else 0)

    def _location_goods(self, location_name: str) -> list[dict]:
        """读取地点可购买商品。"""

        return self.db.fetch_all(
            """
            SELECT i.*
            FROM trade_goods g
            JOIN item_defs i ON i.item_id = g.item_id
            WHERE g.home_location = ?
              AND i.tradeable = 1
            ORDER BY i.base_price, i.name
            """,
            (location_name,),
        )

    def _can_buy_one(self, client_id: str, player: dict, item: dict, buy_fee_rate: float) -> bool:
        """推荐前确认当前玩家至少能买 1 个该商品。"""

        if not item.get("tradeable"):
            return False
        buy_price, _sell_price = self.price(player["location_name"], item["item_id"])
        fee = int(buy_price * buy_fee_rate)
        if int(player["source_stones"]) < buy_price + fee:
            return False
        with self.db.transaction() as conn:
            ok, _reason = self.can_add_backpack_conn(conn, client_id, item["item_id"], 1)
        return ok

    def _special_buyers_ordered(self) -> list[dict]:
        """按初始化顺序读取特殊收购地点。"""

        return self.db.fetch_all("SELECT rowid, * FROM special_buyers ORDER BY rowid")

    def _special_auto_sell_plan(self, client_id: str, buyers: list[dict]) -> list[tuple[dict, list[dict]]]:
        """按收购地点整理可自动出售的背包物品。"""

        backpack = {
            row["item_id"]: row
            for row in self.backpack_rows(client_id)
            if int(row["quantity"]) > 0
        }
        plan: list[tuple[dict, list[dict]]] = []
        for buyer in buyers:
            items = []
            for item_id in str(buyer["item_ids"]).split(","):
                item = backpack.get(item_id)
                if item:
                    items.append(item)
            if items:
                plan.append((buyer, items))
        return plan

    @staticmethod
    def _action_text(action: str) -> str:
        """把交易动作转成玩家能看懂的文字。"""

        return {
            "buy": "购买",
            "sell": "出售",
            "special_sell": "特殊出售",
            "special_auto_sell": "特殊自动出售",
        }.get(action, action)


service = TradeService(db)

__all__ = ["TradeService", "service"]
