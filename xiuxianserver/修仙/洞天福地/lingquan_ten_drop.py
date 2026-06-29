"""灵泉十滴小游戏结算。

这个小游戏的原型是经典十滴水，天然适合长线闯关。洞天福地版本把
一局收束在五分钟内：玩家可以主动结算本局，也可以到时自动结算。
服务端只认可压过上限后的综合成绩，避免把益智小游戏变成刷资源入口。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .service import medicine_embryo_reward

LINGQUAN_TEN_DROP_KEY = "lingquan-ten-drop"
LINGQUAN_TEN_DROP_TITLE = "灵泉十滴"
LINGQUAN_DURATION_SECONDS = 300
LINGQUAN_LEVEL_CAP = 30
LINGQUAN_BURST_CAP = 900
LINGQUAN_CHAIN_CAP = 180
LINGQUAN_SCORE_CAP = 5000
LINGQUAN_END_REASONS = {"manual", "timeout", "failed"}


@dataclass(frozen=True)
class LingquanTenDropResult:
    """灵泉十滴服务端认可的结算摘要。"""

    score: int
    levels_cleared: int
    total_bursts: int
    max_chain: int
    drops_left: int
    elapsed_seconds: int
    end_reason: str


def lingquan_ten_drop_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取灵泉十滴启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        LINGQUAN_TEN_DROP_KEY,
        LINGQUAN_TEN_DROP_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": LINGQUAN_DURATION_SECONDS,
            "score_cap": LINGQUAN_SCORE_CAP,
            "level_cap": LINGQUAN_LEVEL_CAP,
            "burst_cap": LINGQUAN_BURST_CAP,
            "chain_cap": LINGQUAN_CHAIN_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_lingquan_ten_drop(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给灵泉十滴签发一次单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("灵泉开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    return service.start_round(LINGQUAN_TEN_DROP_KEY, game_token)


def finish_lingquan_ten_drop(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验灵泉十滴成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("灵泉结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        LINGQUAN_TEN_DROP_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_lingquan_ten_drop_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _lingquan_ten_drop_rewards(result)
    issued = service.issue_code_for_round(
        LINGQUAN_TEN_DROP_KEY,
        LINGQUAN_TEN_DROP_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "levels_cleared": result.levels_cleared,
            "total_bursts": result.total_bursts,
            "max_chain": result.max_chain,
            "drops_left": result.drops_left,
            "elapsed_seconds": result.elapsed_seconds,
            "end_reason": result.end_reason,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_levels = max(0, _safe_int(issued_meta.get("levels_cleared"))) if issued_meta else result.levels_cleared
    display_bursts = max(0, _safe_int(issued_meta.get("total_bursts"))) if issued_meta else result.total_bursts
    display_chain = max(0, _safe_int(issued_meta.get("max_chain"))) if issued_meta else result.max_chain
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["levels_cleared"] = display_levels
    issued["total_bursts"] = display_bursts
    issued["max_chain"] = display_chain
    issued["message"] = (
        f"灵泉收束：{display_score} 分，清过 {display_levels} 关，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _lingquan_ten_drop_rewards(result: LingquanTenDropResult) -> list[dict[str, Any]]:
    """把灵泉十滴综合分转成洞天基础奖励快照。"""

    score = max(0, min(LINGQUAN_SCORE_CAP, result.score))
    levels = max(0, min(LINGQUAN_LEVEL_CAP, result.levels_cleared))
    chain = max(0, min(LINGQUAN_CHAIN_CAP, result.max_chain))
    rewards: list[dict[str, Any]] = []

    currency = min(720, 22 + int(score * 0.13) + levels * 8 + min(chain, 80))
    exp = min(58, 4 + score // 110 + levels + chain // 18)
    rewards.append({"type": "currency", "quantity": max(18, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if score >= 160 or levels >= 1:
        rewards.append(medicine_embryo_reward("yinmingcao" if score % 2 else "xueqidan"))
    if score >= 900 or levels >= 4:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if (score >= 1800 or levels >= 8) and _chance_per_10000(min(520, 120 + levels * 28 + chain)):
        rewards.append(medicine_embryo_reward("shenggudan" if score % 2 else "yanghundan"))
    if score >= 1500 and _chance_per_10000(min(850, 120 + levels * 35 + chain * 2)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 3600 and _chance_per_10000(min(110, 28 + levels * 2 + chain // 6)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_lingquan_ten_drop_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> LingquanTenDropResult:
    """清洗灵泉十滴前端成绩，并重新计算服务端认可分数。"""

    levels_cleared = min(LINGQUAN_LEVEL_CAP, max(0, _safe_int(payload.get("levelsCleared") or payload.get("levels_cleared"))))
    total_bursts = min(LINGQUAN_BURST_CAP, max(0, _safe_int(payload.get("totalBursts") or payload.get("total_bursts"))))
    max_chain = min(LINGQUAN_CHAIN_CAP, max(0, _safe_int(payload.get("maxChain") or payload.get("max_chain"))))
    drops_left = min(60, max(0, _safe_int(payload.get("dropsLeft") or payload.get("drops_left"))))
    elapsed_seconds = min(LINGQUAN_DURATION_SECONDS, max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))))
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), LINGQUAN_DURATION_SECONDS)
    end_reason = str(payload.get("endReason") or payload.get("end_reason") or "manual").strip().lower()
    if end_reason not in LINGQUAN_END_REASONS:
        end_reason = "manual"

    # 只接受能被五分钟局时支撑的成绩密度。这里不是严苛反作弊，
    # 而是防止明显伪造的高关卡/高连锁把兑换码抬到不合理上限。
    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    level_time_cap = min(LINGQUAN_LEVEL_CAP, max(0, effective_seconds // 10 + 2))
    burst_time_cap = min(LINGQUAN_BURST_CAP, effective_seconds * 4)
    chain_cap = min(LINGQUAN_CHAIN_CAP, max(8, total_bursts, effective_seconds * 2))

    levels_cleared = min(levels_cleared, level_time_cap)
    total_bursts = min(total_bursts, burst_time_cap)
    max_chain = min(max_chain, chain_cap, total_bursts)

    reported_score = max(0, _safe_int(payload.get("score")))
    server_score = (
        levels_cleared * 170
        + total_bursts * 5
        + max_chain * 16
        + drops_left * 6
        + _efficiency_bonus(levels_cleared, elapsed_seconds)
    )
    accepted_score = min(reported_score if reported_score > 0 else server_score, server_score, LINGQUAN_SCORE_CAP)
    return LingquanTenDropResult(
        score=max(0, accepted_score),
        levels_cleared=levels_cleared,
        total_bursts=total_bursts,
        max_chain=max_chain,
        drops_left=drops_left,
        elapsed_seconds=elapsed_seconds,
        end_reason=end_reason,
    )


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数，前端上报不能突破这个边界。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(LINGQUAN_DURATION_SECONDS, elapsed)


def _efficiency_bonus(levels_cleared: int, elapsed_seconds: int) -> int:
    """给快节奏通关一点奖励，但不鼓励拖满五分钟。"""

    if levels_cleared <= 0 or elapsed_seconds <= 0:
        return 0
    target_seconds = levels_cleared * 24
    if elapsed_seconds >= target_seconds:
        return 0
    return min(420, (target_seconds - elapsed_seconds) * 3)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
