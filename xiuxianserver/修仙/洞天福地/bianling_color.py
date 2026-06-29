"""辨灵试色小游戏结算。

辨灵试色是 60 秒的找异色短局。色阶序列由单局凭证派生，
每次开局都会重抽；前端只提交通关层数、误触、
经过时间和最高难层，服务端按时间密度和统一上限重新裁定。
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .random_seed import round_rng
from .service import medicine_embryo_reward

BIANLING_COLOR_KEY = "bianling-color"
BIANLING_COLOR_TITLE = "辨灵试色"
BIANLING_DURATION_SECONDS = 60
BIANLING_LEVEL_CAP = 45
BIANLING_MISTAKE_CAP = 20
BIANLING_SCORE_CAP = 1200


@dataclass(frozen=True)
class BianlingColorResult:
    """辨灵试色服务端认可的结算摘要。"""

    score: int
    levels_passed: int
    mistakes: int
    elapsed_seconds: int
    highest_layer: int


def bianling_color_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取辨灵试色启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        BIANLING_COLOR_KEY,
        BIANLING_COLOR_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": BIANLING_DURATION_SECONDS,
            "level_cap": BIANLING_LEVEL_CAP,
            "mistake_cap": BIANLING_MISTAKE_CAP,
            "score_cap": BIANLING_SCORE_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_bianling_color(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，签发单局凭证和本局色阶。"""

    if not isinstance(payload, dict):
        raise ValueError("辨灵试色开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(BIANLING_COLOR_KEY, game_token)
    session_id = str(round_info.get("session_id") or "")
    round_token = str(round_info.get("round_token") or "")
    round_info.update(
        {
            "game_duration": BIANLING_DURATION_SECONDS,
            "level_cap": BIANLING_LEVEL_CAP,
            "mistake_cap": BIANLING_MISTAKE_CAP,
            "score_cap": BIANLING_SCORE_CAP,
            "stages": _stages_for_round(game_token, session_id, round_token),
        }
    )
    return round_info


def finish_bianling_color(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验辨灵试色成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("辨灵试色结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        BIANLING_COLOR_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_bianling_color_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _bianling_color_rewards(result)
    issued = service.issue_code_for_round(
        BIANLING_COLOR_KEY,
        BIANLING_COLOR_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "levels_passed": result.levels_passed,
            "mistakes": result.mistakes,
            "elapsed_seconds": result.elapsed_seconds,
            "highest_layer": result.highest_layer,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_levels = max(0, _safe_int(issued_meta.get("levels_passed"))) if issued_meta else result.levels_passed
    display_mistakes = max(0, _safe_int(issued_meta.get("mistakes"))) if issued_meta else result.mistakes
    display_elapsed = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    display_layer = max(0, _safe_int(issued_meta.get("highest_layer"))) if issued_meta else result.highest_layer
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["levels_passed"] = display_levels
    issued["mistakes"] = display_mistakes
    issued["elapsed_seconds"] = display_elapsed
    issued["highest_layer"] = display_layer
    issued["message"] = (
        f"灵色辨明：{display_score} 分，过 {display_levels} 层，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _stages_for_round(game_token: str, session_id: str, round_token: str) -> list[dict[str, Any]]:
    """用单局凭证派生色阶，每次开局重抽，同一局可复算。"""

    rng = round_rng(BIANLING_COLOR_KEY, game_token, session_id, round_token, "stages")
    stages: list[dict[str, Any]] = []
    for level in range(1, BIANLING_LEVEL_CAP + 1):
        size = min(9, 2 + level // 5)
        layer = _layer_for_level(level)
        diff = max(7, 44 - level - rng.randint(0, min(8, layer + 2)))
        base = [rng.randint(66, 214), rng.randint(66, 214), rng.randint(66, 214)]
        target = list(base)
        channel = rng.randrange(3)
        direction = -1 if base[channel] + diff > 245 else 1
        target[channel] = max(22, min(245, target[channel] + direction * diff))
        # 给后段一点微弱串色，让它更像灵气偏移，不只是单通道亮暗。
        if level >= 16:
            side_channel = (channel + 1 + rng.randrange(2)) % 3
            target[side_channel] = max(22, min(245, target[side_channel] - direction * max(3, diff // 4)))
        if level >= 28:
            other_channel = rng.choice([item for item in (0, 1, 2) if item != channel])
            target[other_channel] = max(22, min(245, target[other_channel] + rng.choice((-1, 1)) * max(2, diff // 6)))
        stages.append(
            {
                "level": level,
                "size": size,
                "base": _rgb_hex(base),
                "target": _rgb_hex(target),
                "target_index": _spread_target_index(rng, size, level),
                "layer": layer,
            }
        )
    return stages


def _spread_target_index(rng: random.Random, size: int, level: int) -> int:
    """给目标格位置加一点分布约束，避免连续几层看起来总在同一块区域。"""

    total = max(1, int(size) * int(size))
    if level <= 1:
        return rng.randrange(total)
    previous_rolls = max(1, min(3, level // 6 + 1))
    blocked = {rng.randrange(total) for _ in range(previous_rolls)}
    choices = [index for index in range(total) if index not in blocked]
    return rng.choice(choices or list(range(total)))


def _bianling_color_rewards(result: BianlingColorResult) -> list[dict[str, Any]]:
    """把辨灵试色认可分转成洞天基础奖励快照。"""

    score = max(0, min(BIANLING_SCORE_CAP, result.score))
    levels = max(0, min(BIANLING_LEVEL_CAP, result.levels_passed))
    rewards: list[dict[str, Any]] = []

    currency = min(640, 20 + int(score * 0.22) + levels * 4 + result.highest_layer * 8)
    exp = min(46, 4 + score // 105 + levels // 2 + result.highest_layer)
    rewards.append({"type": "currency", "quantity": max(18, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if levels >= 6 or score >= 160:
        rewards.append(medicine_embryo_reward("yinmingcao" if score % 2 else "xueqidan"))
    if levels >= 24 or score >= 720:
        rewards.append(medicine_embryo_reward("ningshenlu" if score % 2 else "huichunlu"))
    if levels >= 32 and result.mistakes <= 4:
        chance = min(240, 22 + score // 11 + max(0, 6 - result.mistakes) * 12)
        if _chance_per_10000(chance):
            rewards.append({"type": "wish_token", "quantity": 1})
    return rewards


def _sanitize_bianling_color_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> BianlingColorResult:
    """清洗辨灵试色前端成绩，并按时间密度重裁。"""

    levels = min(BIANLING_LEVEL_CAP, max(0, _safe_int(payload.get("levelsPassed") or payload.get("levels_passed"))))
    mistakes = min(BIANLING_MISTAKE_CAP, max(0, _safe_int(payload.get("mistakes"))))
    elapsed_seconds = min(
        BIANLING_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), BIANLING_DURATION_SECONDS)

    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    level_time_cap = min(BIANLING_LEVEL_CAP, int(effective_seconds / 1.35) + 3)
    levels = min(levels, level_time_cap)
    derived_layer = _layer_for_level(levels) if levels > 0 else 0
    reported_layer = max(0, _safe_int(payload.get("highestLayer") or payload.get("highest_layer")))
    highest_layer = min(derived_layer, reported_layer or derived_layer)

    speed_bonus = max(0, int((BIANLING_DURATION_SECONDS - elapsed_seconds) * 0.55))
    raw_score = levels * 24 + highest_layer * 26 + speed_bonus - mistakes * 26
    score = min(BIANLING_SCORE_CAP, max(0, raw_score))
    return BianlingColorResult(
        score=score,
        levels_passed=levels,
        mistakes=mistakes,
        elapsed_seconds=elapsed_seconds,
        highest_layer=highest_layer,
    )


def _layer_for_level(level: int) -> int:
    """把关卡换成粗粒度难层，给前端和结算摘要展示。"""

    value = max(0, int(level))
    if value <= 0:
        return 0
    return min(6, 1 + (value - 1) // 8)


def _rgb_hex(channels: list[int]) -> str:
    """把 RGB 通道转成 CSS 十六进制颜色。"""

    return "#" + "".join(f"{max(0, min(255, int(item))):02x}" for item in channels[:3])


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(BIANLING_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
