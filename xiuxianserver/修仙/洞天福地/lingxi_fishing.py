"""灵溪垂钓小游戏结算。

洞天福地的每个小游戏独立维护自己的分数体系和奖励换算。公共服务只
负责签发兑换码、保存奖励快照和兑换发奖；这样后续新增游戏时，不会
把各自玩法规则混进 `service.py`。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Protocol

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .service import medicine_embryo_reward

LINGXI_FISHING_KEY = "lingxi-fishing"
LINGXI_FISHING_TITLE = "灵溪垂钓"
LINGXI_SCORE_CAP = 3600
LINGXI_FISH_COUNT_CAP = 120
LINGXI_GAME_DURATION_SECONDS = 90
LINGXI_FISH_BASE_SCORE = {
    "clownfish": 5,
    "blueCrucian": 10,
    "goldfish": 15,
    "pufferfish": 20,
    "swordfish": 40,
    "shark": 75,
    "goldenDragon": 130,
}
LINGXI_RARE_FISH = {"shark", "goldenDragon"}


class DongtianIssuer(Protocol):
    """小游戏结算只依赖洞天公共发码和凭证能力。"""

    def game_config(
        self,
        game_key: str,
        game_title: str,
        *,
        config: dict[str, Any] | None = None,
        reuse_token: str | None = None,
    ) -> dict[str, Any]:
        """签发静态小游戏启动配置。"""

    def start_round(self, game_key: str, game_token: str) -> dict[str, Any]:
        """签发一次单局凭证。"""

    def consume_round(
        self,
        game_key: str,
        game_token: str,
        session_id: str,
        round_token: str,
        *,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """消费一次单局凭证。"""

    def inspect_round(
        self,
        game_key: str,
        game_token: str,
        session_id: str,
        round_token: str,
        *,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """校验一次单局凭证，但不消费。"""

    def issue_code(
        self,
        game_key: str,
        game_title: str,
        rewards: list[dict[str, Any]],
        *,
        score: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """签发十分钟一次性兑换码。"""

    def issue_code_for_round(
        self,
        game_key: str,
        game_title: str,
        game_token: str,
        session_id: str,
        round_token: str,
        rewards: list[dict[str, Any]],
        *,
        score: int = 0,
        meta: dict[str, Any] | None = None,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """原子消费单局凭证并签发兑换码。"""

    def reward_preview(self, rewards: list[dict[str, Any]]) -> list[str]:
        """把奖励快照转成小游戏页面可展示的预览文本。"""


@dataclass(frozen=True)
class LingxiFishingResult:
    """灵溪垂钓服务端认可的结算摘要。"""

    score: int
    caught_count: int
    rare_count: int
    fish_score: int


def lingxi_fishing_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取灵溪垂钓启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        LINGXI_FISHING_KEY,
        LINGXI_FISHING_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": LINGXI_GAME_DURATION_SECONDS,
            "score_cap": LINGXI_SCORE_CAP,
            "fish_count_cap": LINGXI_FISH_COUNT_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_lingxi_fishing(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给灵溪垂钓签发一次单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("灵溪开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    return service.start_round(LINGXI_FISHING_KEY, game_token)


def finish_lingxi_fishing(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验灵溪垂钓成绩，签发低量洞天兑换码。

    静态小游戏没有玩家身份，不能在这里直接发奖；这里只签发短码。
    真正发放仍走 `洞天兑换`，从而复用玩家身份、今日收益曲线和日志。
    """

    if not isinstance(payload, dict):
        raise ValueError("灵溪结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        LINGXI_FISHING_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_lingxi_fishing_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _lingxi_fishing_rewards(result)
    issued = service.issue_code_for_round(
        LINGXI_FISHING_KEY,
        LINGXI_FISHING_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "caught_count": result.caught_count,
            "rare_count": result.rare_count,
            "fish_score": result.fish_score,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_caught_count = max(0, _safe_int(issued_meta.get("caught_count"))) if issued_meta else result.caught_count
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["caught_count"] = display_caught_count
    issued["message"] = (
        f"灵溪收竿：{display_score} 分，钓获 {display_caught_count} 尾。"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _lingxi_fishing_rewards(result: LingxiFishingResult) -> list[dict[str, Any]]:
    """把灵溪垂钓分数转成洞天基础奖励快照。

    这里刻意保守：高分只提高基础量和小概率额外物，不让小游戏收益
    盖过探险、跑商、首领、虫洞这些主线循环。
    """

    score = max(0, min(LINGXI_SCORE_CAP, result.score))
    caught_count = max(0, min(LINGXI_FISH_COUNT_CAP, result.caught_count))
    rare_count = max(0, result.rare_count)
    rewards: list[dict[str, Any]] = []

    currency = min(760, 24 + int(score * 0.16) + min(caught_count, 45) * 2 + rare_count * 5)
    exp = min(60, 4 + score // 95 + caught_count // 8 + rare_count)
    rewards.append({"type": "currency", "quantity": max(20, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if caught_count >= 3 or score >= 200:
        rewards.append(medicine_embryo_reward("xueqidan" if score % 2 == 0 else "yinmingcao"))
    if score >= 800 or (score >= 600 and rare_count >= 2):
        rewards.append(medicine_embryo_reward("yinmingcao" if score % 2 == 0 else "xueqidan"))
    if score >= 1600 and _chance_per_10000(min(1600, 350 + rare_count * 180)):
        rewards.append(medicine_embryo_reward("huichunlu" if score % 3 else "ningshenlu"))
    if score >= 2400 and _chance_per_10000(min(520, 120 + rare_count * 80)):
        rewards.append(medicine_embryo_reward("shenggudan" if score % 2 else "yanghundan"))
    if score >= 1800 and _chance_per_10000(min(900, 120 + score // 12 + rare_count * 80)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 3200 and _chance_per_10000(min(120, 35 + rare_count * 12)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_lingxi_fishing_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> LingxiFishingResult:
    """清洗灵溪垂钓前端成绩。

    前端成绩只作为结算材料。服务端不再接受前端自带鱼分，也不接受
    没有钓获明细的纯分数；最终分数必须被服务端时长、鱼种白名单和
    稀有鱼密度同时支撑。
    """

    if not isinstance(payload, dict):
        raise ValueError("灵溪结算数据异常，请重新开局。")

    reported_score = max(0, _safe_int(payload.get("score")))
    caught_fish = payload.get("caughtFish") or payload.get("caught_fish") or []
    if caught_fish is None:
        caught_fish = []
    if not isinstance(caught_fish, list):
        raise ValueError("灵溪钓获记录异常，请重新开局。")
    if len(caught_fish) > LINGXI_FISH_COUNT_CAP:
        raise ValueError("灵溪钓获数量异常，请重新开局。")

    elapsed_seconds = LINGXI_GAME_DURATION_SECONDS
    if server_elapsed_seconds is not None:
        elapsed_seconds = max(0, min(LINGXI_GAME_DURATION_SECONDS, int(server_elapsed_seconds)))
    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    fish_count_cap = min(LINGXI_FISH_COUNT_CAP, int(effective_seconds / 1.25) + 4)
    type_caps = {
        "goldenDragon": max(0, int(effective_seconds // 42)),
        "shark": max(1, int(effective_seconds // 28)),
        "swordfish": max(2, int(effective_seconds // 14)),
    }
    type_counts: dict[str, int] = {}
    fish_score = 0
    caught_count = 0
    rare_count = 0
    for item in caught_fish:
        if caught_count >= fish_count_cap:
            break
        if not isinstance(item, dict):
            continue
        fish_key = str(item.get("typeNameEn") or "").strip()
        if fish_key not in LINGXI_FISH_BASE_SCORE:
            continue
        if fish_key in type_caps and type_counts.get(fish_key, 0) >= type_caps[fish_key]:
            continue
        type_counts[fish_key] = type_counts.get(fish_key, 0) + 1
        caught_count += 1
        if fish_key in LINGXI_RARE_FISH:
            rare_count += 1
        fish_score += LINGXI_FISH_BASE_SCORE[fish_key]

    score_time_cap = int(effective_seconds * 42)
    source_score = fish_score if caught_count else 0
    accepted_score = min(reported_score if reported_score > 0 else source_score, source_score, score_time_cap, LINGXI_SCORE_CAP)
    return LingxiFishingResult(
        score=accepted_score,
        caught_count=caught_count,
        rare_count=rare_count,
        fish_score=fish_score,
    )


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数，前端上报不能突破这个边界。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(LINGXI_GAME_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
