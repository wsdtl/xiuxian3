"""碎星切玉小游戏结算。

碎星切玉是 90 秒飞鹤修仙题材切玉局。前端负责手感、连击、星潮和
画面表现；服务端只认可单局凭证、服务端经过时间、合理切玉密度和
漏切惩罚支撑的成绩，避免把爽感项目变成静态页刷资源入口。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .service import medicine_embryo_reward

SUIXING_QIEYU_KEY = "suixing-qieyu"
SUIXING_QIEYU_TITLE = "碎星切玉"
SUIXING_DURATION_SECONDS = 90
SUIXING_TIDE_SECONDS = 30
SUIXING_SCORE_CAP = 3600
SUIXING_CUBE_CAP = 240
SUIXING_STRONG_CAP = 80
SUIXING_SLOWMO_CAP = 36
SUIXING_COMBO_CAP = 140
SUIXING_MISS_CAP = 120
SUIXING_END_REASONS = {"manual", "timeout"}


@dataclass(frozen=True)
class SuixingQieyuResult:
    """碎星切玉服务端认可的结算摘要。"""

    score: int
    cubes_sliced: int
    strong_cubes: int
    slowmo_cubes: int
    max_combo: int
    misses: int
    elapsed_seconds: int
    end_reason: str


def suixing_qieyu_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取碎星切玉启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        SUIXING_QIEYU_KEY,
        SUIXING_QIEYU_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": SUIXING_DURATION_SECONDS,
            "tide_seconds": SUIXING_TIDE_SECONDS,
            "score_cap": SUIXING_SCORE_CAP,
            "cube_cap": SUIXING_CUBE_CAP,
            "combo_cap": SUIXING_COMBO_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_suixing_qieyu(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给碎星切玉签发一次单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("碎星开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(SUIXING_QIEYU_KEY, game_token)
    round_info.update(
        {
            "game_duration": SUIXING_DURATION_SECONDS,
            "tide_seconds": SUIXING_TIDE_SECONDS,
            "score_cap": SUIXING_SCORE_CAP,
            "cube_cap": SUIXING_CUBE_CAP,
            "combo_cap": SUIXING_COMBO_CAP,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        }
    )
    return round_info


def finish_suixing_qieyu(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验碎星切玉成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("碎星结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        SUIXING_QIEYU_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_suixing_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _suixing_rewards(result)
    issued = service.issue_code_for_round(
        SUIXING_QIEYU_KEY,
        SUIXING_QIEYU_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "cubes_sliced": result.cubes_sliced,
            "strong_cubes": result.strong_cubes,
            "slowmo_cubes": result.slowmo_cubes,
            "max_combo": result.max_combo,
            "misses": result.misses,
            "elapsed_seconds": result.elapsed_seconds,
            "end_reason": result.end_reason,
        },
    )
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    display_cubes = max(0, _safe_int(issued_meta.get("cubes_sliced"))) if issued_meta else result.cubes_sliced
    display_combo = max(0, _safe_int(issued_meta.get("max_combo"))) if issued_meta else result.max_combo
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["cubes_sliced"] = display_cubes
    issued["max_combo"] = display_combo
    issued["misses"] = max(0, _safe_int(issued_meta.get("misses"))) if issued_meta else result.misses
    issued["elapsed_seconds"] = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    issued["message"] = (
        f"碎星归匣：认可玉尘 {display_score}，切玉 {display_cubes} 枚，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _suixing_rewards(result: SuixingQieyuResult) -> list[dict[str, Any]]:
    """把碎星切玉认可成绩转成洞天基础奖励快照。"""

    score = max(0, min(SUIXING_SCORE_CAP, result.score))
    cubes = max(0, min(SUIXING_CUBE_CAP, result.cubes_sliced))
    combo = max(0, min(SUIXING_COMBO_CAP, result.max_combo))
    strong = max(0, min(SUIXING_STRONG_CAP, result.strong_cubes))
    slowmo = max(0, min(SUIXING_SLOWMO_CAP, result.slowmo_cubes))
    rewards: list[dict[str, Any]] = []

    currency = min(720, 18 + int(score * 0.13) + cubes * 2 + combo * 2 + strong * 3 + slowmo * 5)
    exp = min(54, 4 + score // 120 + cubes // 10 + combo // 14 + strong // 9)
    rewards.append({"type": "currency", "quantity": max(16, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if score >= 120 or cubes >= 8:
        rewards.append(medicine_embryo_reward("xueqidan" if cubes % 2 == 0 else "yinmingcao"))
    if score >= 760 or combo >= 22:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if score >= 1800 and _chance_per_10000(min(620, 80 + combo * 4 + strong * 4)):
        rewards.append(medicine_embryo_reward("shenggudan" if combo % 2 else "yanghundan"))
    if score >= 1500 and combo >= 30 and _chance_per_10000(min(820, 120 + combo * 6 + slowmo * 10)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 3000 and combo >= 70 and _chance_per_10000(min(85, 12 + combo // 2)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_suixing_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> SuixingQieyuResult:
    """清洗碎星切玉前端成绩，并按服务端时间密度重新裁定。"""

    reported_score = max(0, _safe_int(payload.get("score")))
    cubes = max(0, _safe_int(payload.get("cubesSliced") or payload.get("cubes_sliced")))
    strong = max(0, _safe_int(payload.get("strongCubes") or payload.get("strong_cubes")))
    slowmo = max(0, _safe_int(payload.get("slowmoCubes") or payload.get("slowmo_cubes")))
    misses = max(0, _safe_int(payload.get("misses")))
    combo = max(0, _safe_int(payload.get("maxCombo") or payload.get("max_combo")))
    elapsed_seconds = min(
        SUIXING_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), SUIXING_DURATION_SECONDS)

    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    # 星潮阶段会明显加速刷玉，所以密度上限前 60 秒偏稳，最后 30 秒给
    # 更高余量；这里只拦截伪造级别的成绩，不压正常高手的爽感。
    tide_elapsed = max(0, effective_seconds - (SUIXING_DURATION_SECONDS - SUIXING_TIDE_SECONDS))
    cube_time_cap = min(SUIXING_CUBE_CAP, int(effective_seconds * 1.95 + tide_elapsed * 2.15) + 14)
    cubes = min(cubes, cube_time_cap, SUIXING_CUBE_CAP)
    strong = min(strong, SUIXING_STRONG_CAP, cubes)
    slowmo = min(slowmo, SUIXING_SLOWMO_CAP, cubes)
    misses = min(misses, SUIXING_MISS_CAP)
    combo = min(combo, SUIXING_COMBO_CAP, cubes + strong)

    server_score = (
        cubes * 15
        + strong * 22
        + slowmo * 30
        + combo * 12
        - misses * 16
    )
    score_time_cap = int(effective_seconds * 38 + tide_elapsed * 42) + 180
    accepted_score = min(reported_score if reported_score > 0 else server_score, server_score, score_time_cap, SUIXING_SCORE_CAP)
    end_reason = str(payload.get("endReason") or payload.get("end_reason") or "manual").strip().lower()
    if end_reason not in SUIXING_END_REASONS:
        end_reason = "manual"
    return SuixingQieyuResult(
        score=max(0, accepted_score),
        cubes_sliced=max(0, cubes),
        strong_cubes=max(0, strong),
        slowmo_cubes=max(0, slowmo),
        max_combo=max(0, combo),
        misses=max(0, misses),
        elapsed_seconds=max(0, elapsed_seconds),
        end_reason=end_reason,
    )


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(SUIXING_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
