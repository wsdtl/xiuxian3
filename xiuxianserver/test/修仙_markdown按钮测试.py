"""修仙 markdown 按钮协议测试。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.format_text import T
from 修仙.markdown_utils import MarkdownKeyboard, button, markdown_message_from_text
from 修仙.修仙帮助.service import service as help_service
from 修仙.reply import _with_player_name


class FakeDB:
    """只给回复包装读取玩家头。"""

    def fetch_one(self, *_args, **_kwargs) -> dict:
        return {"display_name": "青衫客", "title": "试剑人", "level": 19}


FakeExploreService = type("FakeExploreService", (), {"__module__": "修仙.探险.service"})


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
    """尖括号里的内容原样作为按钮命令，是否可用由业务自己决定。"""

    message = markdown_message_from_text("源石不足。\n请先<存入源石 数量>")
    assert message is not None
    rows = message["keyboard"]["content"]["rows"]
    assert rows[0]["buttons"][0]["action"]["data"] == "存入源石 数量"


def test_reply_text_with_button_tags_to_markdown() -> None:
    """统一回复出口遇到 `<命令>` 时自动升级为 markdown。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "现在可以<探险状态><结束探险>"},
        FakeDB(),
    )
    assert payload["type"] == "markdown"
    assert "【青衫客·试剑人 Lv.19】" in payload["message"]["content"]
    assert "<探险状态>" not in payload["message"]["content"]
    rows = payload["message"]["keyboard"]["content"]["rows"]
    commands = [item["action"]["data"] for row in rows for item in row["buttons"]]
    assert commands[:2] == ["探险状态", "结束探险"]
    assert commands[2:5] == ["指南", "状态", "修仙信息"]


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
    assert commands[:4] == ["休息", "结束休息", "状态", "纳戒"]
    assert commands[-2:] == ["指南", "修仙信息"]


def test_predictive_buttons_before_context_buttons() -> None:
    """预测按钮排在当前组件按钮之前，并按实际命令去重。"""

    payload = _with_player_name(
        "player_ws",
        {"code": 202, "type": "text", "message": "探险还没有到 30 分钟冷却，先查看预计算结果。"},
        FakeDB(),
        FakeExploreService(),
    )
    commands = _payload_commands(payload)
    assert commands[:3] == ["探险状态", "结束探险", "状态"]
    assert commands.count("探险状态") == 1
    assert "探险记录" in commands


def test_command_guide_buttons() -> None:
    """指南里的手写按钮都能转成 markdown。"""

    message = markdown_message_from_text(help_service.command_guide())
    assert message is not None
    rows = message["keyboard"]["content"]["rows"]
    commands = [item["action"]["data"] for row in rows for item in row["buttons"]]
    assert commands[:3] == ["地图", "背包", "纳戒"]
    assert "探险状态" in commands
    assert "结束探险" in commands
    assert "宝石" in commands
    assert "武器" in commands
    assert commands[-1] == "修仙百科 武器"


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
    test_reply_text_with_button_tags_to_markdown()
    test_hint_without_button_tags_uses_default_markdown_buttons()
    test_predictive_buttons_from_content()
    test_predictive_buttons_before_context_buttons()
    test_command_guide_buttons()
    print("修仙 markdown 按钮测试通过")


if __name__ == "__main__":
    main()
