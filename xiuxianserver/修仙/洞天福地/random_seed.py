"""洞天小游戏随机种子工具。

这里刻意把“每日随机”和“单局随机”拆成两个入口，避免把启动凭证
误当作所有玩法随机的默认种子。
"""

from __future__ import annotations

import hashlib
import random
from datetime import date


def daily_rng(game_key: str, purpose: str, day: str | date | None = None) -> random.Random:
    """返回每日随机源。

    只给真正设计成每日统一内容的小游戏使用，例如全局难度。`day`
    由调用方传入，结算时应使用单局开局日期，避免跨零点错难度。
    """

    if isinstance(day, date):
        day_text = day.isoformat()
    else:
        day_text = str(day or date.today().isoformat()).strip()[:10]
    seed = _seed("daily", game_key, purpose, day_text)
    return random.Random(seed)


def round_rng(game_key: str, game_token: str, session_id: str, round_token: str, purpose: str) -> random.Random:
    """返回单局随机源。

    用于每局应该变化、但结算阶段又必须可复算的玩法内容。这里仍纳入
    `game_token`，不是为了固定长期内容，而是把单局凭证绑定到入口身份。
    """

    seed = _seed("round", game_key, purpose, game_token, session_id, round_token)
    return random.Random(seed)


def _seed(scope: str, game_key: str, purpose: str, *parts: str) -> int:
    """把结构化种子材料压成 `random.Random` 可用的整数。"""

    text = "|".join(
        str(item or "").strip()
        for item in (scope, game_key, purpose, *parts)
    )
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:16], "big")
