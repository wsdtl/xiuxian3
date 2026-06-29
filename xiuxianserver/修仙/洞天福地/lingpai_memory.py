"""灵牌记忆小游戏结算。

灵牌记忆是 90 秒的翻牌配对短局。牌面顺序由单局凭证派生，
每次开局都会重洗；前端只提交配对数、翻牌数、
经过时间和是否完成，服务端再按时间密度、翻牌密度和统一上限裁定。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .random_seed import round_rng
from .service import medicine_embryo_reward

LINGPAI_MEMORY_KEY = "lingpai-memory"
LINGPAI_MEMORY_TITLE = "灵牌记忆"
LINGPAI_DURATION_SECONDS = 90
LINGPAI_PAIR_COUNT = 8
LINGPAI_CARD_COUNT = LINGPAI_PAIR_COUNT * 2
LINGPAI_FLIP_CAP = 120
LINGPAI_SCORE_CAP = 1000
LINGPAI_SYMBOLS = (
    "青莲",
    "赤羽",
    "玄龟",
    "白虎",
    "星砂",
    "月魄",
    "雷纹",
    "云篆",
)


@dataclass(frozen=True)
class LingpaiMemoryResult:
    """灵牌记忆服务端认可的结算摘要。"""

    score: int
    matched_pairs: int
    flip_count: int
    elapsed_seconds: int
    completed: bool


def lingpai_memory_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取灵牌记忆启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        LINGPAI_MEMORY_KEY,
        LINGPAI_MEMORY_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": LINGPAI_DURATION_SECONDS,
            "pair_count": LINGPAI_PAIR_COUNT,
            "card_count": LINGPAI_CARD_COUNT,
            "flip_cap": LINGPAI_FLIP_CAP,
            "score_cap": LINGPAI_SCORE_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_lingpai_memory(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，签发单局凭证和本局牌序。"""

    if not isinstance(payload, dict):
        raise ValueError("灵牌记忆开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(LINGPAI_MEMORY_KEY, game_token)
    session_id = str(round_info.get("session_id") or "")
    round_token = str(round_info.get("round_token") or "")
    round_info.update(
        {
            "game_duration": LINGPAI_DURATION_SECONDS,
            "pair_count": LINGPAI_PAIR_COUNT,
            "card_count": LINGPAI_CARD_COUNT,
            "flip_cap": LINGPAI_FLIP_CAP,
            "cards": _deck_for_round(game_token, session_id, round_token),
        }
    )
    return round_info


def finish_lingpai_memory(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验灵牌记忆成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("灵牌记忆结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        LINGPAI_MEMORY_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_lingpai_memory_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _lingpai_memory_rewards(result)
    issued = service.issue_code_for_round(
        LINGPAI_MEMORY_KEY,
        LINGPAI_MEMORY_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "matched_pairs": result.matched_pairs,
            "flip_count": result.flip_count,
            "elapsed_seconds": result.elapsed_seconds,
            "completed": result.completed,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_pairs = max(0, _safe_int(issued_meta.get("matched_pairs"))) if issued_meta else result.matched_pairs
    display_flips = max(0, _safe_int(issued_meta.get("flip_count"))) if issued_meta else result.flip_count
    display_elapsed = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    display_completed = bool(issued_meta.get("completed")) if issued_meta else result.completed
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["matched_pairs"] = display_pairs
    issued["flip_count"] = display_flips
    issued["elapsed_seconds"] = display_elapsed
    issued["completed"] = display_completed
    issued["message"] = (
        f"灵牌归位：{display_score} 分，配成 {display_pairs}/{LINGPAI_PAIR_COUNT} 对，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _deck_for_round(game_token: str, session_id: str, round_token: str) -> list[dict[str, Any]]:
    """用单局凭证派生牌序，每次开局重洗，同一局可复算。"""

    cards: list[dict[str, Any]] = []
    for pair_id, label in enumerate(LINGPAI_SYMBOLS, start=1):
        cards.append({"pair_id": pair_id, "label": label})
        cards.append({"pair_id": pair_id, "label": label})
    rng = round_rng(LINGPAI_MEMORY_KEY, game_token, session_id, round_token, "deck")
    rng.shuffle(cards)
    return [
        {
            "id": index + 1,
            "pair_id": card["pair_id"],
            "label": card["label"],
        }
        for index, card in enumerate(cards)
    ]


def _lingpai_memory_rewards(result: LingpaiMemoryResult) -> list[dict[str, Any]]:
    """把灵牌记忆认可分转成洞天基础奖励快照。"""

    score = max(0, min(LINGPAI_SCORE_CAP, result.score))
    rewards: list[dict[str, Any]] = []

    currency = min(
        620,
        22 + int(score * 0.25) + result.matched_pairs * 8 + (40 if result.completed else 0),
    )
    exp = min(46, 4 + score // 95 + result.matched_pairs * 2 + (4 if result.completed else 0))
    rewards.append({"type": "currency", "quantity": max(18, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if result.matched_pairs >= 2 or score >= 160:
        rewards.append(medicine_embryo_reward("xueqidan" if score % 2 == 0 else "yinmingcao"))
    if result.completed or score >= 700:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if result.completed and result.flip_count <= 36:
        chance = min(220, 20 + score // 12 + max(0, 40 - result.flip_count) * 4)
        if _chance_per_10000(chance):
            rewards.append({"type": "wish_token", "quantity": 1})
    return rewards


def _sanitize_lingpai_memory_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> LingpaiMemoryResult:
    """清洗灵牌记忆前端成绩，并按时间和翻牌密度重裁。"""

    matched_pairs = min(LINGPAI_PAIR_COUNT, max(0, _safe_int(payload.get("matchedPairs") or payload.get("matched_pairs"))))
    flip_count = min(LINGPAI_FLIP_CAP, max(0, _safe_int(payload.get("flipCount") or payload.get("flip_count"))))
    elapsed_seconds = min(
        LINGPAI_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), LINGPAI_DURATION_SECONDS)

    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    matched_pairs = min(matched_pairs, flip_count // 2)
    matched_pairs = min(matched_pairs, int(effective_seconds / 3.0) + 1)
    matched_pairs = max(0, matched_pairs)
    completed = bool(payload.get("completed")) and matched_pairs >= LINGPAI_PAIR_COUNT

    minimal_flips = max(1, matched_pairs * 2)
    extra_flips = max(0, flip_count - minimal_flips)
    pair_score = matched_pairs * 78
    complete_bonus = 180 if completed else 0
    efficiency_bonus = max(0, 120 - extra_flips * 4)
    time_bonus = max(0, int((LINGPAI_DURATION_SECONDS - elapsed_seconds) * 0.9)) if completed else 0
    score = min(LINGPAI_SCORE_CAP, max(0, pair_score + complete_bonus + efficiency_bonus + time_bonus))
    return LingpaiMemoryResult(
        score=score,
        matched_pairs=matched_pairs,
        flip_count=flip_count,
        elapsed_seconds=elapsed_seconds,
        completed=completed,
    )


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(LINGPAI_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
