"""修仙 markdown 按钮协议测试。"""

from __future__ import annotations

from datetime import timedelta
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.format_text import T
from 修仙.markdown_utils import MarkdownKeyboard, button, inline_command_link, markdown_link, markdown_message_from_text
from 修仙.common import business_day, dump_json, now, ts
from 修仙.notifications import notification_line, system_message_line
from 修仙.sql import XiuxianDB
from 修仙.修仙帮助.service import service as help_service
from 修仙.reply import _with_player_name


def _link(label: str, command: str) -> str:
    return inline_command_link(label, command)


def test_inline_command_link_is_auto_send() -> None:
    """无框命令链接用于通知栏，点击后自动发送命令。"""

    assert _link("状态", "状态") == (
        "[状态](mqqapi://aio/inlinecmd?command=%E7%8A%B6%E6%80%81&enter=true&reply=false)"
    )
    assert _link("领取宗门大会奖励", "领取宗门大会奖励") == (
        "[领取宗门大会奖励]"
        "(mqqapi://aio/inlinecmd?command=%E9%A2%86%E5%8F%96%E5%AE%97%E9%97%A8%E5%A4%A7%E4%BC%9A%E5%A5%96%E5%8A%B1&enter=true&reply=false)"
    )


def test_markdown_link_hides_raw_web_url() -> None:
    """网页入口统一显示改名链接，不在正文裸露真实 URL。"""

    assert markdown_link("用户组后台", "https://example.com/xiuxian/user-groups") == (
        "[用户组后台](https://example.com/xiuxian/user-groups)"
    )


def test_panel_section_uses_light_semantic_icons() -> None:
    """正文卡栏目自动补语义图标，业务文本不用到处手写装饰。"""

    panel = T.panel()
    panel.section("状态")
    panel.section("武器详情")
    panel.section("青岚剑")
    panel.section("🌱 已带图标")

    assert panel.render().splitlines() == [
        "> **🌱 状态**",
        "> **⚔️ 武器详情**",
        "> **青岚剑**",
        "> **🌱 已带图标**",
    ]


class FakeDB:
    """只给回复包装读取玩家头。"""

    def fetch_one(self, sql: str, *_args, **_kwargs) -> dict | None:
        if "FROM players AS p" in sql:
            return {"display_name": "青衫客", "title": "试剑人", "level": 19}
        if "SELECT last_sign_date" in sql:
            return {"last_sign_date": business_day()}
        if "SELECT newbie_claimed" in sql:
            return {"newbie_claimed": 1}
        if "FROM bank_accounts" in sql:
            return None
        if "FROM players" in sql:
            return {
                "status": "空闲",
                "hp": 100,
                "max_hp": 100,
                "mp": 60,
                "max_mp": 60,
                "rest_full_at": None,
                "rest_window_elapsed_seconds": 0,
            }
        return None


class BrokenNoticeDB(FakeDB):
    """玩家头正常，但通知查询异常时不能影响回复。"""

    def fetch_one(self, sql: str, *args, **kwargs) -> dict | None:
        if "FROM players AS p" in sql:
            return {"display_name": "青衫客", "title": "试剑人", "level": 19}
        raise RuntimeError("notice query failed")


class NoticeDB(FakeDB):
    """模拟多条通知，验证第二行和数量上限。"""

    def fetch_one(self, sql: str, params=(), *_args, **_kwargs) -> dict | None:
        if "FROM players AS p" in sql:
            return {"display_name": "青衫客", "title": "试剑人", "level": 19}
        if "SELECT last_sign_date" in sql:
            return {"last_sign_date": None}
        if "SELECT newbie_claimed" in sql:
            return {"newbie_claimed": 0}
        if "FROM bank_accounts" in sql:
            return {
                "star_level": 1,
                "balance": 100_000,
                "last_settle_at": ts(now() - timedelta(hours=24)),
                "last_interest_day": None,
                "daily_interest_claimed": 0,
            }
        if "FROM players" in sql:
            return {
                "status": "休息中",
                "hp": 0,
                "max_hp": 100,
                "mp": 0,
                "max_mp": 60,
                "rest_full_at": ts(now() + timedelta(minutes=29)),
                "rest_window_elapsed_seconds": 0,
            }
        if "FROM exploration_records" in sql:
            return {
                "started_at": ts(now() - timedelta(minutes=40)),
                "ready_at": ts(now() - timedelta(minutes=10)),
                "result": dump_json({"duration_seconds": 1800}),
            }
        if "seasonal_boss_participants" in sql:
            return {"ok": 1}
        if "wormhole_participants" in sql:
            return {"ok": 1}
        if "FROM sect_war_rewards" in sql and params:
            return {"ok": 1}
        if "duel_requests" in sql:
            return {"ok": 1}
        return None


class SystemQueueDB(FakeDB):
    """模拟全服系统消息队列，验证队首展示和后续补位。"""

    def __init__(self, *, include_wormhole: bool = True) -> None:
        self.include_wormhole = include_wormhole

    def fetch_one(self, sql: str, params=(), *_args, **_kwargs) -> dict | None:
        if "FROM players AS p" in sql or "FROM players" in sql:
            return super().fetch_one(sql, params)
        if "FROM sects" in sql or "FROM sect_war_rewards" in sql:
            return None
        if "FROM wormholes" in sql:
            if not self.include_wormhole:
                return None
            return {
                "boss_name": "裂天游魂",
                "location_name": "破军营",
                "result": dump_json({"event_type": "war_prep", "force": "破军营"}),
            }
        if "FROM seasonal_boss_events" in sql:
            return {"boss_name": "折梅人", "title": "旧约", "weight_type": "普通"}
        if "FROM treasure_maps" in sql and "拍卖中" in sql:
            return {"city_name": "天枢城", "expires_at": ts(now() + timedelta(hours=1))}
        if "FROM treasure_maps" in sql and "可拾取" in sql:
            return {
                "city_name": "青岚坊",
                "x": 3,
                "y": -2,
                "expires_at": ts(now() + timedelta(hours=5)),
            }
        return None


class NormalWormholeDB(SystemQueueDB):
    """普通虫洞系统消息展示地点，Boss 名留给详情页。"""

    def fetch_one(self, sql: str, params=(), *_args, **_kwargs) -> dict | None:
        if "FROM wormholes" in sql:
            return {
                "boss_name": "陨炉泰坦",
                "location_name": "玄铁岭",
                "result": "{}",
            }
        return super().fetch_one(sql, params)


def _real_notice_db() -> XiuxianDB:
    temp_dir = TemporaryDirectory()
    db = XiuxianDB(Path(temp_dir.name) / "notice_test.db")
    db._notice_temp_dir = temp_dir  # type: ignore[attr-defined]
    return db


def _close_real_notice_db(db: XiuxianDB) -> None:
    temp_dir = getattr(db, "_notice_temp_dir", None)
    db.close()
    if temp_dir is not None:
        temp_dir.cleanup()


def _seed_notice_player(db: XiuxianDB, client_id: str = "notice_ws") -> None:
    db.execute(
        """
        INSERT INTO players
        (client_id, display_name, level, exp, hp, max_hp, mp, max_mp, physique_id,
         physique_value, base_attack, defense, raw_stones, status, location_name,
         x, y, backpack_limit, weight_limit, last_sign_date, created_at)
        VALUES (?, '听雪客', 12, 0, 0, 100, 0, 60, 'fanti',
                0, 5, 0, 0, '空闲', '天枢城',
                0, 0, 80, 500, ?, ?)
        """,
        (client_id, business_day(), ts()),
    )


def _payload_content(payload: dict) -> str:
    return str(payload["message"]["content"])


def _payload_lines(payload: dict) -> list[str]:
    return _payload_content(payload).splitlines()


FakeExploreService = type("FakeExploreService", (), {"__module__": "修仙.探险.service"})
FakeBossService = type("FakeBossService", (), {"__module__": "修仙.首领.service"})


def test_button_default() -> None:
    """button("修仙信息") 默认 button_type 为 1。"""

    item = button("修仙信息")
    assert item["render_data"]["label"] == "修仙信息"
    assert item["action"]["type"] == 1
    assert item["action"]["data"] == "修仙信息"
    assert "enter" not in item["action"]


def test_keyboard_limit() -> None:
    """键盘最多 25 个按钮、每行最多 3 个。"""

    commands = [f"命令{i}" for i in range(1, 31)]
    keyboard = MarkdownKeyboard.from_commands(commands).to_content()
    rows = keyboard["content"]["rows"]
    assert len(rows) == 9
    assert all(len(row["buttons"]) <= 3 for row in rows)
    assert rows[-1]["buttons"][-1]["action"]["data"] == "命令25"


def test_plain_suggestion_uses_default_markdown_buttons() -> None:
    """没有 `<命令>` 时，也会因为默认按钮转成 markdown。"""

    message = markdown_message_from_text("普通提示。\n发送：修仙信息 查看状态")
    assert message is None

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "普通提示。\n发送：修仙信息 查看状态"},
        FakeDB(),
    )
    assert payload["type"] == "markdown"
    assert payload["message"]["content"].endswith("发送：修仙信息 查看状态")
    rows = payload["message"]["keyboard"]["content"]["rows"]
    assert [item["action"]["data"] for item in rows[0]["buttons"]] == ["指南", "状态", "修仙信息"]


def test_button_tags_to_markdown() -> None:
    """回复里的 `<命令>` 会转成按钮，正文不再显示尖括号标记。"""

    message = markdown_message_from_text("血气不足。\n可以先<休息>，也可以<修仙信息>")
    assert message is not None
    assert message["content"] == "血气不足。\n可以先，也可以"
    rows = message["keyboard"]["content"]["rows"]
    assert [item["action"]["data"] for item in rows[0]["buttons"]] == ["休息", "修仙信息"]


def test_button_tags_keep_command_text() -> None:
    """参数模板按钮保留命令模板，但点击后只填入输入框。"""

    message = markdown_message_from_text("原石不足。\n请先<存入货币 数量>")
    assert message is not None
    rows = message["keyboard"]["content"]["rows"]
    action = rows[0]["buttons"][0]["action"]
    assert action["data"] == "存入货币 数量"
    assert action["type"] == 2
    assert action["enter"] is False


def test_parameter_button_templates_use_type_2() -> None:
    """建立宗门这类缺参数入口使用 type=2，避免点击后直接发送半截命令。"""

    keyboard = MarkdownKeyboard.from_commands(["建立宗门", "创建用户 名称", "切磋 玩家名", "洞天兑换"]).to_content()
    buttons = [item for row in keyboard["content"]["rows"] for item in row["buttons"]]
    create_action = buttons[0]["action"]
    new_player_action = buttons[1]["action"]
    spar_action = buttons[2]["action"]
    dongtian_action = buttons[3]["action"]
    assert buttons[0]["render_data"]["label"] == "建立宗门"
    assert create_action["data"] == "建立宗门 x y 宗门名"
    assert create_action["type"] == 2
    assert create_action["enter"] is False
    assert buttons[1]["render_data"]["label"] == "创建用户"
    assert new_player_action["data"] == "创建用户 名称"
    assert new_player_action["type"] == 2
    assert new_player_action["enter"] is False
    assert buttons[2]["render_data"]["label"] == "切磋"
    assert spar_action["data"] == "切磋 玩家名"
    assert spar_action["type"] == 2
    assert spar_action["enter"] is False
    assert buttons[3]["render_data"]["label"] == "兑换码"
    assert dongtian_action["data"] == "洞天兑换 兑换码"
    assert dongtian_action["type"] == 2
    assert dongtian_action["enter"] is False


def test_reply_text_with_button_tags_to_markdown() -> None:
    """统一回复出口遇到 `<命令>` 时自动升级为 markdown。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "现在可以<探险状态><结束探险>"},
        FakeDB(),
    )
    assert payload["type"] == "markdown"
    assert "【青衫客·试剑人 LV19】" in payload["message"]["content"]
    assert "<探险状态>" not in payload["message"]["content"]
    rows = payload["message"]["keyboard"]["content"]["rows"]
    commands = [item["action"]["data"] for row in rows for item in row["buttons"]]
    assert commands == ["探险状态", "结束探险"]


def test_reply_keeps_long_handwritten_business_buttons() -> None:
    """业务手写按钮是明确入口页，不能被自动按钮目标数误截到 6 个。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "请选择<cmd1><cmd2><cmd3><cmd4><cmd5><cmd6><cmd7><cmd8>"},
        FakeDB(),
    )
    commands = _payload_commands(payload)
    assert commands == [f"cmd{index}" for index in range(1, 9)]


def test_reply_header_notice_line_is_second_line() -> None:
    """通知显示在玩家头下一行，并限制最多三条。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "正文"},
        NoticeDB(),
    )
    lines = _payload_lines(payload)
    assert lines[0] == "【青衫客·试剑人 LV19】"
    assert lines[1] == "🔴 通知：" + "｜".join(
        [
            _link("结束休息", "结束休息"),
            _link("结束探险", "结束探险"),
            _link("首领奖励", "首领奖励"),
        ]
    )
    assert lines[2] == "正文"
    assert "虫洞奖励待领" not in lines[1]
    assert "对战请求待处理" not in lines[1]


def test_reply_header_system_line_before_personal_notice() -> None:
    """系统消息排在个人通知前，二者都不挤占正文。"""

    db = _real_notice_db()
    try:
        _seed_notice_player(db)
        db.execute("UPDATE players SET newbie_claimed = 1 WHERE client_id = ?", ("notice_ws",))
        db.execute(
            """
            INSERT INTO wormholes (
                boss_name, boss_kind, location_name, x, y,
                level, max_hp, hp, attack, defense, difficulty,
                opened_by, source, status, opened_at, closes_at, result
            )
            VALUES (
                '裂天游魂', '魂', '青岚坊', 1, 1,
                12, 1000, 1000, 50, 20, 1.0,
                'notice_ws', 'war_prep', '开启', ?, ?, ?
            )
            """,
            (
                ts(now() - timedelta(minutes=5)),
                ts(now() + timedelta(minutes=55)),
                dump_json({"event_type": "war_prep", "force": "破军营"}),
            ),
        )
        payload = _with_player_name(
            "notice_ws",
            {"code": 202, "type": "text", "message": "查看状态"},
            db,
        )
        lines = _payload_lines(payload)
        assert lines[0] == "【听雪客·无 LV12】"
        assert lines[1] == "🔴 系统：" + _link("战备虫洞·青岚坊", "虫洞状态")
        assert lines[2] == "🔴 通知：" + _link("重伤休息", "休息")
        assert lines[3] == "查看状态"
    finally:
        _close_real_notice_db(db)


def test_system_message_queue_limit_and_backfill() -> None:
    """系统消息按优先级排队，只展示队首三条；队首消失后后续补上。"""

    line = system_message_line(SystemQueueDB(), limit=3)
    assert line == "🔴 系统：" + "｜".join(
        [
            _link("战备虫洞·破军营", "虫洞状态"),
            _link("岁时情劫·折梅人", "挑战首领"),
            _link("天枢城·藏宝图将结", "藏宝图"),
        ]
    )
    assert "青岚坊藏宝图散落" not in line

    backfilled = system_message_line(SystemQueueDB(include_wormhole=False), limit=3)
    assert backfilled == "🔴 系统：" + "｜".join(
        [
            _link("岁时情劫·折梅人", "挑战首领"),
            _link("天枢城·藏宝图将结", "藏宝图"),
            _link("青岚坊·藏宝图(3,-2)", "导航 3 -2"),
        ]
    )


def test_normal_wormhole_system_label_uses_location() -> None:
    """普通虫洞系统消息展示地点，不在消息头铺 Boss 名。"""

    line = system_message_line(NormalWormholeDB(), limit=1)
    assert line == "🔴 系统：" + _link("异界虫洞·玄铁岭", "虫洞状态")
    assert "陨炉泰坦" not in line


def test_boss_system_message_hidden_until_client_cooldown_ready() -> None:
    """首领系统消息对当前玩家要等 CD 结束后再出现。"""

    db = _real_notice_db()
    try:
        _seed_notice_player(db)
        db.execute("UPDATE players SET hp = max_hp, mp = max_mp, newbie_claimed = 1 WHERE client_id = ?", ("notice_ws",))
        cursor = db.execute(
            """
            INSERT INTO seasonal_boss_events (
                business_day, boss_key, event_type, weight_type, boss_name, title,
                scene, story, farewell, feather_text, location_name, atmosphere,
                level, max_hp, hp, attack, defense, difficulty,
                status, opened_at, closes_at, killed_at, result
            )
            VALUES (
                ?, 'test_active', '每日旧愿', '每日旧愿', '沙洲望潮客',
                '在退潮后等船的人', '一段用于测试的旧愿。', '它还在潮声里。',
                '旧愿退去。', '一枚测试铭刻之羽。', '天枢城', '[]',
                10, 10000, 7500, 50, 10, 1.0,
                '开启', ?, ?, NULL, '{}'
            )
            """,
            (business_day(), ts(now() - timedelta(minutes=5)), ts(now() + timedelta(hours=1))),
        )
        event_id = int(cursor.lastrowid)
        db.execute(
            """
            INSERT INTO seasonal_boss_participants
            (event_id, client_id, damage, challenge_count, last_challenge_at, reward_claimed, created_at, updated_at)
            VALUES (?, 'notice_ws', 2500, 1, ?, 0, ?, ?)
            """,
            (
                event_id,
                ts(now() - timedelta(minutes=3)),
                ts(now() - timedelta(minutes=3)),
                ts(now() - timedelta(minutes=3)),
            ),
        )

        cooldown_payload = _with_player_name(
            "notice_ws",
            {"code": 202, "type": "text", "message": "正文"},
            db,
        )
        assert "岁时情劫：在退潮后等船的人·沙洲望潮客" not in _payload_content(cooldown_payload)

        db.execute(
            """
            UPDATE seasonal_boss_participants
            SET last_challenge_at = ?
            WHERE event_id = ? AND client_id = ?
            """,
            (ts(now() - timedelta(minutes=31)), event_id, "notice_ws"),
        )
        ready_payload = _with_player_name(
            "notice_ws",
            {"code": 202, "type": "text", "message": "正文"},
            db,
        )
        assert _link("岁时情劫·沙洲望潮客", "挑战首领") in _payload_content(ready_payload)
    finally:
        _close_real_notice_db(db)


def test_reply_header_notice_keeps_handwritten_buttons() -> None:
    """通知不使用尖括号，不破坏业务手写按钮优先级。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "现在可以<探险状态><结束探险>"},
        NoticeDB(),
    )
    content = _payload_content(payload)
    assert "🔴 通知：" in content
    assert "<探险状态>" not in content
    commands = _payload_commands(payload)
    assert commands == ["探险状态", "结束探险"]


def test_reply_header_notice_not_used_for_predictive_buttons() -> None:
    """通知文字只展示，不参与正文预测按钮。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "普通提示。"},
        NoticeDB(),
    )
    commands = _payload_commands(payload)
    assert commands == ["指南", "状态", "修仙信息"]


def test_daily_sign_notice_is_low_priority() -> None:
    """低优先级日常会进个人通知，但不能挤掉更急的三条队首。"""

    full_line = notification_line("player_ws", NoticeDB(), limit=10)
    assert _link("银行结息", "银行结息") in full_line
    assert _link("新手礼包", "新手礼包") in full_line
    assert _link("今日签到", "签到") in full_line

    limited_payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "正文"},
        NoticeDB(),
    )
    lines = _payload_lines(limited_payload)
    assert lines[1] == "🔴 通知：" + "｜".join(
        [
            _link("结束休息", "结束休息"),
            _link("结束探险", "结束探险"),
            _link("首领奖励", "首领奖励"),
        ]
    )
    assert "今日签到" not in lines[1]


def test_expired_boss_reward_notice_closes_lazily_from_header() -> None:
    """首领过了次日 04:00 后，任意回复头都应推进退去并提示领奖。"""

    db = _real_notice_db()
    try:
        _seed_notice_player(db)
        db.execute("UPDATE players SET hp = max_hp, mp = max_mp, newbie_claimed = 1 WHERE client_id = ?", ("notice_ws",))
        cursor = db.execute(
            """
            INSERT INTO seasonal_boss_events (
                business_day, boss_key, event_type, weight_type, boss_name, title,
                scene, story, farewell, feather_text, location_name, atmosphere,
                level, max_hp, hp, attack, defense, difficulty,
                status, opened_at, closes_at, killed_at, result
            )
            VALUES (
                ?, 'test_timeout', '每日旧愿', '每日旧愿', '退去旧愿',
                '迟归旧愿', '一段用于测试的旧愿。', '它只剩半口气，却没有被击破。',
                '旧愿退去。', '一枚测试铭刻之羽。', '天枢城', '[]',
                10, 10000, 7500, 50, 10, 1.0,
                '开启', ?, ?, NULL, '{}'
            )
            """,
            (
                business_day(now() - timedelta(days=1)),
                ts(now() - timedelta(days=1)),
                ts(now() - timedelta(minutes=1)),
            ),
        )
        event_id = int(cursor.lastrowid)
        db.execute(
            """
            INSERT INTO seasonal_boss_participants
            (event_id, client_id, damage, challenge_count, last_challenge_at, reward_claimed, created_at, updated_at)
            VALUES (?, 'notice_ws', 2500, 1, ?, 0, ?, ?)
            """,
            (
                event_id,
                ts(now() - timedelta(hours=2)),
                ts(now() - timedelta(hours=2)),
                ts(now() - timedelta(hours=2)),
            ),
        )

        line = notification_line("notice_ws", db, limit=10)
        assert _link("首领奖励", "首领奖励") in line
        event = db.fetch_one("SELECT status, result FROM seasonal_boss_events WHERE event_id = ?", (event_id,))
        assert event is not None
        assert event["status"] == "已退去"
        assert '"reason": "timeout"' in event["result"]
    finally:
        _close_real_notice_db(db)


def test_low_priority_daily_notices_from_real_tables() -> None:
    """低优先级提醒按真实表状态判断。"""

    db = _real_notice_db()
    try:
        _seed_notice_player(db)
        line = notification_line("notice_ws", db, limit=10)
        assert "今日签到" not in line
        assert _link("新手礼包", "新手礼包") in line
        assert "银行结息" not in line

        db.execute(
            """
            INSERT INTO bank_accounts
            (client_id, star_level, balance, last_settle_at, last_interest_day, daily_interest_claimed)
            VALUES (?, 1, 100000, ?, NULL, 0)
            """,
            ("notice_ws", ts(now() - timedelta(hours=2))),
        )
        assert "银行结息" not in notification_line("notice_ws", db, limit=10)

        db.execute(
            "UPDATE bank_accounts SET last_settle_at = ? WHERE client_id = ?",
            (ts(now() - timedelta(hours=24)), "notice_ws"),
        )
        assert _link("银行结息", "银行结息") in notification_line("notice_ws", db, limit=10)

        db.execute("UPDATE players SET newbie_claimed = 1 WHERE client_id = ?", ("notice_ws",))
        assert "新手礼包" not in notification_line("notice_ws", db, limit=10)

        db.execute("UPDATE players SET last_sign_date = ? WHERE client_id = ?", ("2000-01-01", "notice_ws"))
        assert _link("今日签到", "签到") in notification_line("notice_ws", db, limit=10)
    finally:
        _close_real_notice_db(db)


def test_reply_header_notice_failure_is_silent() -> None:
    """通知查询失败不影响正常回复。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "普通提示。"},
        BrokenNoticeDB(),
    )
    content = _payload_content(payload)
    assert "【青衫客·试剑人 LV19】" in content
    assert "🔴 通知：" not in content
    assert content.endswith("普通提示。")


def test_reply_header_notice_from_real_tables() -> None:
    """用真实临时库覆盖重伤、探险和对战待处理。"""

    db = _real_notice_db()
    try:
        _seed_notice_player(db)
        db.execute(
            """
            INSERT INTO exploration_records
            (client_id, location_name, status, started_at, ready_at, result)
            VALUES (?, '青岚坊', '探险中', ?, ?, ?)
            """,
            (
                "notice_ws",
                ts(now() - timedelta(minutes=40)),
                ts(now() + timedelta(minutes=90)),
                dump_json({"duration_seconds": 60}),
            ),
        )
        db.execute(
            """
            INSERT INTO duel_requests
            (mode, from_client_id, to_client_id, stake, status, expires_at, created_at)
            VALUES ('spar', 'other_ws', 'notice_ws', 0, '等待', ?, ?)
            """,
            ((now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), ts()),
        )
        payload = _with_player_name(
            "notice_ws",
            {"code": 202, "type": "text", "message": "查看状态"},
            db,
        )
        lines = _payload_lines(payload)
        assert lines[0] == "【听雪客·无 LV12】"
        assert lines[1] == "🔴 通知：" + "｜".join(
            [
                _link("重伤休息", "休息"),
                _link("结束探险", "结束探险"),
                _link("对战请求", "决斗记录"),
            ]
        )
        assert lines[2] == "查看状态"
    finally:
        _close_real_notice_db(db)


def test_hint_without_button_tags_uses_default_markdown_buttons() -> None:
    """T.hint 只负责提示格式；回复层统一补默认 markdown 按钮。"""

    text = T.hint("普通提示。", "发送：修仙信息 查看状态")
    assert text == "*普通提示。*\n发送：修仙信息 查看状态"

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": text},
        FakeDB(),
    )
    assert payload["type"] == "markdown"
    assert payload["message"]["content"].endswith("发送：修仙信息 查看状态")
    rows = payload["message"]["keyboard"]["content"]["rows"]
    assert [item["action"]["data"] for item in rows[0]["buttons"]] == ["指南", "状态", "修仙信息"]


def test_predictive_buttons_from_content() -> None:
    """回复正文会预判下一步固定命令。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "血气不足，建议先休息一下。"},
        FakeDB(),
    )
    commands = _payload_commands(payload)
    assert commands == ["休息", "结束休息", "状态"]
    assert len(commands) <= 6


def test_predictive_buttons_before_context_buttons() -> None:
    """预测按钮排在当前组件按钮之前，并按实际命令去重。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "探险还没有到 30 分钟冷却，先查看预计算结果。"},
        FakeDB(),
        FakeExploreService(),
    )
    commands = _payload_commands(payload)
    assert commands == ["探险状态", "结束探险", "探险记录", "探险列表", "背包", "纳戒"]
    assert commands.count("探险状态") == 1
    assert len(commands) <= 6


def test_boss_cooldown_hint_uses_safe_buttons_only() -> None:
    """首领冷却中不预测首领入口，等 CD 结束后再展示可挑战按钮。"""

    payload = _with_player_name(
        "player_ws",
        {
            "code": 202,
            "type": "text",
            "message": T.hint("岁时旧念尚未重新凝形，还需 29分59秒。", "冷却结束后再来。<状态><纳戒>"),
        },
        FakeDB(),
        FakeBossService(),
    )
    commands = _payload_commands(payload)
    assert commands == ["状态", "纳戒"]
    assert "首领" not in commands
    assert "挑战首领" not in commands
    assert "首领奖励" not in commands


def test_command_guide_buttons() -> None:
    """指南主入口只展示方向，具体业务入口下沉到方向页。"""

    message = markdown_message_from_text(help_service.command_guide())
    assert message is not None
    rows = message["keyboard"]["content"]["rows"]
    commands = [item["action"]["data"] for row in rows for item in row["buttons"]]
    assert commands == [
        "指南 成长",
        "指南 账户",
        "指南 行囊",
        "指南 奖励",
        "指南 武器",
        "指南 装备",
        "指南 铭刻",
        "指南 探险",
        "指南 战斗",
        "指南 首领",
        "指南 交易",
        "指南 出售",
        "指南 宗门",
        "指南 世界",
        "指南 消息",
    ]

    explore_message = markdown_message_from_text(help_service.command_guide("探险"))
    assert explore_message is not None
    explore_commands = [
        item["action"]["data"]
        for row in explore_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert explore_commands[:4] == ["地图", "位置", "探险列表", "导航 地点名"]
    assert "探险 地点名" in explore_commands
    assert "结束探险" in explore_commands

    battle_message = markdown_message_from_text(help_service.command_guide("战斗"))
    assert battle_message is not None
    battle_commands = [
        item["action"]["data"]
        for row in battle_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert battle_commands[:4] == ["战斗日志", "切磋 玩家名", "接受切磋 玩家名", "拒绝切磋 玩家名"]
    assert "决斗 玩家名 数量" in battle_commands
    assert battle_commands[-1] == "指南"

    boss_message = markdown_message_from_text(help_service.command_guide("首领"))
    assert boss_message is not None
    boss_commands = [
        item["action"]["data"]
        for row in boss_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert boss_commands[:4] == ["首领", "首领状态", "挑战首领", "首领排行"]
    assert "虫洞奖励" in boss_commands

    trade_message = markdown_message_from_text(help_service.command_guide("交易"))
    assert trade_message is not None
    trade_commands = [
        item["action"]["data"]
        for row in trade_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert "商场推荐" in trade_commands
    assert "跑商奖励" in trade_commands
    assert "藏宝图出价 数量" in trade_commands

    sell_message = markdown_message_from_text(help_service.command_guide("出售"))
    assert sell_message is not None
    sell_commands = [
        item["action"]["data"]
        for row in sell_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert "自动出售" in sell_commands
    assert "出售全部 武器" in sell_commands
    assert "二手市场上架 物品名 数量 价格" in sell_commands

    flow_message = markdown_message_from_text(help_service.command_guide("消息"))
    assert flow_message is not None
    flow_commands = [
        item["action"]["data"]
        for row in flow_message["keyboard"]["content"]["rows"]
        for item in row["buttons"]
    ]
    assert flow_commands[0] == "消息流水"
    assert flow_commands[-1] == "指南"
    assert len(flow_commands) == 2


def test_daily_guide_uses_inline_command_links() -> None:
    """引导只使用无框命令链接，不生成底部按钮。"""

    text = help_service.daily_guide()
    assert "引导" in text
    assert "[签到](mqqapi://aio/inlinecmd?" in text
    assert "command=%E7%AD%BE%E5%88%B0" in text
    assert "[领奖](mqqapi://aio/inlinecmd?" in text
    assert "command=%E9%A2%86%E5%8F%96%E5%AE%97%E9%97%A8%E5%A4%A7%E4%BC%9A%E5%A5%96%E5%8A%B1" in text
    payload = markdown_message_from_text(text)
    assert payload is not None
    assert "keyboard" not in payload["message"]


def test_web_help_uses_hidden_web_links() -> None:
    """帮助入口隐藏帮助站和交互地图真实链接。"""

    text = help_service.web_help()
    assert "[修仙帮助网页](" in text
    assert "/xiuxian/help" in text
    assert "[修仙界地图](" in text
    assert "/xiuxian/map" in text
    assert "发送：修仙帮助 查看指令速查图，发送：引导 查看日常入口，发送：指南 查看关键入口。" in text
    assert "![修仙界地图" not in text


def _payload_commands(payload: dict) -> list[str]:
    """展开 markdown payload 里的按钮命令。"""

    rows = payload["message"]["keyboard"]["content"]["rows"]
    return [item["action"]["data"] for row in rows for item in row["buttons"]]


def main() -> None:
    test_button_default()
    test_keyboard_limit()
    test_plain_suggestion_uses_default_markdown_buttons()
    test_button_tags_to_markdown()
    test_button_tags_keep_command_text()
    test_parameter_button_templates_use_type_2()
    test_reply_text_with_button_tags_to_markdown()
    test_reply_keeps_long_handwritten_business_buttons()
    test_reply_header_notice_line_is_second_line()
    test_reply_header_system_line_before_personal_notice()
    test_system_message_queue_limit_and_backfill()
    test_boss_system_message_hidden_until_client_cooldown_ready()
    test_reply_header_notice_keeps_handwritten_buttons()
    test_reply_header_notice_not_used_for_predictive_buttons()
    test_daily_sign_notice_is_low_priority()
    test_expired_boss_reward_notice_closes_lazily_from_header()
    test_low_priority_daily_notices_from_real_tables()
    test_reply_header_notice_failure_is_silent()
    test_reply_header_notice_from_real_tables()
    test_hint_without_button_tags_uses_default_markdown_buttons()
    test_predictive_buttons_from_content()
    test_predictive_buttons_before_context_buttons()
    test_boss_cooldown_hint_uses_safe_buttons_only()
    test_command_guide_buttons()
    test_daily_guide_uses_inline_command_links()
    test_web_help_uses_hidden_web_links()
    print("修仙 markdown 按钮测试通过")


if __name__ == "__main__":
    main()
