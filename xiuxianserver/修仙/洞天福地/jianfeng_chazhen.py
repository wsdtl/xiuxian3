"""剑锋插阵小游戏结算。

剑锋插阵是 90 秒点击插剑局。前端负责转盘、插剑手感、天隙窗口和最后
三十息的万剑归宗表现；服务端只认可单局凭证、服务端经过时间和经过清洗的
成绩材料，避免把小游戏页面变成直接刷资源入口。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .service import medicine_embryo_reward

JIANFENG_CHAZHEN_KEY = "jianfeng-chazhen"
JIANFENG_CHAZHEN_TITLE = "剑锋插阵"
JIANFENG_DURATION_SECONDS = 90
JIANFENG_BURST_SECONDS = 30
JIANFENG_SCORE_CAP = 3000
JIANFENG_SWORD_CAP = 150
JIANFENG_FORMATION_CAP = 36
JIANFENG_GAP_HIT_CAP = 48
JIANFENG_COMBO_CAP = 90
JIANFENG_BURST_SWORD_CAP = 80
JIANFENG_MISS_CAP = 4
JIANFENG_END_REASONS = {"manual", "timeout", "mistake_limit"}


@dataclass(frozen=True)
class JianfengChazhenResult:
    """剑锋插阵服务端认可的结算摘要。"""

    score: int
    swords_inserted: int
    formations_broken: int
    gap_hits: int
    max_combo: int
    burst_swords: int
    misses: int
    elapsed_seconds: int
    end_reason: str


def jianfeng_chazhen_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取剑锋插阵启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        JIANFENG_CHAZHEN_KEY,
        JIANFENG_CHAZHEN_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": JIANFENG_DURATION_SECONDS,
            "burst_seconds": JIANFENG_BURST_SECONDS,
            "score_cap": JIANFENG_SCORE_CAP,
            "sword_cap": JIANFENG_SWORD_CAP,
            "formation_cap": JIANFENG_FORMATION_CAP,
            "combo_cap": JIANFENG_COMBO_CAP,
            "miss_limit": JIANFENG_MISS_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_jianfeng_chazhen(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给剑锋插阵签发一次性单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("剑阵开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(JIANFENG_CHAZHEN_KEY, game_token)
    round_info.update(
        {
            "game_duration": JIANFENG_DURATION_SECONDS,
            "burst_seconds": JIANFENG_BURST_SECONDS,
            "score_cap": JIANFENG_SCORE_CAP,
            "sword_cap": JIANFENG_SWORD_CAP,
            "formation_cap": JIANFENG_FORMATION_CAP,
            "combo_cap": JIANFENG_COMBO_CAP,
            "miss_limit": JIANFENG_MISS_CAP,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        }
    )
    return round_info


def finish_jianfeng_chazhen(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验剑锋插阵成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("剑阵结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        JIANFENG_CHAZHEN_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_jianfeng_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _jianfeng_rewards(result)
    issued = service.issue_code_for_round(
        JIANFENG_CHAZHEN_KEY,
        JIANFENG_CHAZHEN_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "swords_inserted": result.swords_inserted,
            "formations_broken": result.formations_broken,
            "gap_hits": result.gap_hits,
            "max_combo": result.max_combo,
            "burst_swords": result.burst_swords,
            "misses": result.misses,
            "elapsed_seconds": result.elapsed_seconds,
            "end_reason": result.end_reason,
        },
    )
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    display_swords = max(0, _safe_int(issued_meta.get("swords_inserted"))) if issued_meta else result.swords_inserted
    display_formations = max(0, _safe_int(issued_meta.get("formations_broken"))) if issued_meta else result.formations_broken
    display_gap_hits = max(0, _safe_int(issued_meta.get("gap_hits"))) if issued_meta else result.gap_hits
    display_combo = max(0, _safe_int(issued_meta.get("max_combo"))) if issued_meta else result.max_combo
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["swords_inserted"] = display_swords
    issued["formations_broken"] = display_formations
    issued["gap_hits"] = display_gap_hits
    issued["max_combo"] = display_combo
    issued["misses"] = max(0, _safe_int(issued_meta.get("misses"))) if issued_meta else result.misses
    issued["elapsed_seconds"] = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    issued["message"] = (
        f"剑阵归鞘：认可剑意 {display_score}，破阵 {display_formations} 重，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _jianfeng_rewards(result: JianfengChazhenResult) -> list[dict[str, Any]]:
    """把剑锋插阵认可成绩转成洞天基础奖励快照。"""

    score = max(0, min(JIANFENG_SCORE_CAP, result.score))
    swords = max(0, min(JIANFENG_SWORD_CAP, result.swords_inserted))
    formations = max(0, min(JIANFENG_FORMATION_CAP, result.formations_broken))
    gap_hits = max(0, min(JIANFENG_GAP_HIT_CAP, result.gap_hits))
    combo = max(0, min(JIANFENG_COMBO_CAP, result.max_combo))
    burst_swords = max(0, min(JIANFENG_BURST_SWORD_CAP, result.burst_swords))
    rewards: list[dict[str, Any]] = []

    currency = min(650, 16 + int(score * 0.15) + formations * 5 + gap_hits * 4 + combo * 2)
    exp = min(50, 4 + score // 110 + formations // 4 + combo // 12 + gap_hits // 10)
    rewards.append({"type": "currency", "quantity": max(16, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if score >= 100 or swords >= 8:
        rewards.append(medicine_embryo_reward("xueqidan" if swords % 2 == 0 else "yinmingcao"))
    if score >= 650 or formations >= 8 or gap_hits >= 5:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if score >= 1700 and _chance_per_10000(min(560, 80 + combo * 4 + gap_hits * 8 + burst_swords * 2)):
        rewards.append(medicine_embryo_reward("shenggudan" if combo % 2 else "yanghundan"))
    if score >= 1300 and combo >= 18 and gap_hits >= 8 and _chance_per_10000(min(720, 90 + combo * 5 + gap_hits * 10)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 2600 and combo >= 55 and gap_hits >= 18 and _chance_per_10000(min(70, 12 + combo // 2 + gap_hits)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_jianfeng_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> JianfengChazhenResult:
    """清洗剑锋插阵前端成绩，并按服务端时间密度重新裁定。"""

    reported_score = max(0, _safe_int(payload.get("score")))
    swords = max(0, _safe_int(payload.get("swordsInserted") or payload.get("swords_inserted")))
    formations = max(0, _safe_int(payload.get("formationsBroken") or payload.get("formations_broken")))
    gap_hits = max(0, _safe_int(payload.get("gapHits") or payload.get("gap_hits")))
    combo = max(0, _safe_int(payload.get("maxCombo") or payload.get("max_combo")))
    burst_swords = max(0, _safe_int(payload.get("burstSwords") or payload.get("burst_swords")))
    misses = max(0, _safe_int(payload.get("misses")))
    elapsed_seconds = min(
        JIANFENG_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), JIANFENG_DURATION_SECONDS)

    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    burst_elapsed = max(0, effective_seconds - (JIANFENG_DURATION_SECONDS - JIANFENG_BURST_SECONDS))
    sword_time_cap = min(JIANFENG_SWORD_CAP, int(effective_seconds * 1.15 + burst_elapsed * 1.0) + 8)
    formation_time_cap = min(JIANFENG_FORMATION_CAP, int(effective_seconds / 2.7) + 2)
    gap_time_cap = min(JIANFENG_GAP_HIT_CAP, int(effective_seconds * 0.36 + burst_elapsed * 0.35) + 3)
    burst_time_cap = min(JIANFENG_BURST_SWORD_CAP, int(burst_elapsed * 2.0) + 3)

    swords = min(swords, sword_time_cap, JIANFENG_SWORD_CAP)
    formations = min(formations, formation_time_cap, max(0, swords // 3 + 1), JIANFENG_FORMATION_CAP)
    gap_hits = min(gap_hits, gap_time_cap, swords, JIANFENG_GAP_HIT_CAP)
    burst_swords = min(burst_swords, burst_time_cap, swords, JIANFENG_BURST_SWORD_CAP)
    combo = min(combo, JIANFENG_COMBO_CAP, swords + gap_hits)
    misses = min(misses, JIANFENG_MISS_CAP)

    server_score = (
        swords * 8
        + formations * 36
        + gap_hits * 18
        + combo * 12
        + burst_swords * 5
        - misses * 120
    )
    score_time_cap = min(JIANFENG_SCORE_CAP, int(effective_seconds * 26 + burst_elapsed * 22) + 160)
    accepted_score = min(
        reported_score if reported_score > 0 else server_score,
        server_score,
        score_time_cap,
        JIANFENG_SCORE_CAP,
    )
    end_reason = str(payload.get("endReason") or payload.get("end_reason") or "manual").strip().lower()
    if end_reason not in JIANFENG_END_REASONS:
        end_reason = "manual"
    return JianfengChazhenResult(
        score=max(0, accepted_score),
        swords_inserted=max(0, swords),
        formations_broken=max(0, formations),
        gap_hits=max(0, gap_hits),
        max_combo=max(0, combo),
        burst_swords=max(0, burst_swords),
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
    return min(JIANFENG_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
