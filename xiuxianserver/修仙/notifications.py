"""玩家回复头下方的轻量通知。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypeVar

from .common import business_day, dt, dump_json, load_json, money, row_value
from .constants import (
    BANK_LEVELS,
    ENCOUNTER_SECONDS,
    EXPLORE_MINUTES,
    REST_FAST_SECONDS,
    REST_FULL_MINUTES,
    SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES,
    SEASONAL_BOSS_MAX_CHALLENGES,
    TRADE_ACTIVE_WINDOW_DAYS,
)
from .markdown_utils import inline_command_link
from .rules import trade_daily_reward_thresholds, trade_global_soft_line, trade_player_soft_line
from .sect_war import sect_war_in_battle_window, sect_war_in_reward_claim_window, sect_war_is_member_locked

SYSTEM_NOTICE_PREFIX = "🔴 系统："
NOTICE_PREFIX = "🔴 通知："
DEFAULT_NOTICE_LIMIT = 3
DEFAULT_SYSTEM_NOTICE_LIMIT = 3


@dataclass(frozen=True)
class Notification:
    """一条适合常驻展示的用户待办。"""

    key: str
    text: str
    priority: int
    command: str = ""
    label: str = ""


@dataclass(frozen=True)
class SystemMessage:
    """一条从世界事实派生出来的全服消息。"""

    key: str
    text: str
    priority: int
    command: str = ""
    label: str = ""


NoticeItem = Notification | SystemMessage
NoticeT = TypeVar("NoticeT", bound=NoticeItem)


def system_message_line(database: Any, limit: int = DEFAULT_SYSTEM_NOTICE_LIMIT, client_id: str | None = None) -> str:
    """生成系统消息队列文本；查询失败时静默，避免回复出口被通知拖垮。"""

    try:
        messages = collect_system_messages(database, client_id=client_id)
    except Exception:
        # 回复出口不能被系统消息拖死；坏掉时少一行提示，比整条回复失败更可控。
        return ""
    return _queue_line(SYSTEM_NOTICE_PREFIX, messages, limit)


def collect_system_messages(
    database: Any,
    *,
    current_time: datetime | None = None,
    client_id: str | None = None,
) -> list[SystemMessage]:
    """收集全服系统消息；只展示正在发生、会过期或需要被看见的世界事实。"""

    current = current_time or _now()
    result: list[SystemMessage] = []
    result.extend(_sect_war_system_messages(database, current))
    result.extend(_wormhole_system_messages(database, current))
    result.extend(_seasonal_boss_system_messages(database, current, client_id))
    result.extend(_treasure_map_system_messages(database, current))
    return _dedupe_system_messages(result)


def notification_line(client_id: str, database: Any, limit: int = DEFAULT_NOTICE_LIMIT) -> str:
    """生成通知栏文本；查询失败时静默，避免回复出口被通知拖垮。"""

    try:
        notifications = collect_notifications(client_id, database)
    except Exception:
        # 个人通知是锦上添花，主命令回复才是刚需；异常时静默降级。
        return ""
    return _queue_line(NOTICE_PREFIX, notifications, limit)


def collect_notifications(
    client_id: str,
    database: Any,
    *,
    current_time: datetime | None = None,
) -> list[Notification]:
    """收集强通知：只提示已经成熟、错过会亏、需要用户处理的事项。"""

    current = current_time or _now()
    result: list[Notification] = []
    result.extend(_player_state_notifications(client_id, database, current))
    result.extend(_exploration_notifications(client_id, database, current))
    result.extend(_reward_notifications(client_id, database, current))
    result.extend(_duel_request_notifications(client_id, database, current))
    result.extend(_world_material_notifications(client_id, database, current))
    result.extend(_second_hand_notifications(client_id, database, current))
    result.extend(_bank_notifications(client_id, database, current))
    result.extend(_newbie_gift_notifications(client_id, database))
    result.extend(_daily_sign_notifications(client_id, database, current))
    return _dedupe_notifications(result)


def _player_state_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    row = database.fetch_one(
        """
        SELECT status, hp, max_hp, mp, max_mp, rest_full_at, rest_window_elapsed_seconds
        FROM players
        WHERE client_id = ?
        """,
        (client_id,),
    )
    if not row:
        return []

    result: list[Notification] = []
    status = str(row_value(row, "status", "") or "")
    hp = int(row_value(row, "hp", 0) or 0)
    mp = int(row_value(row, "mp", 0) or 0)
    if status != "休息中" and (hp <= 0 or mp <= 0):
        result.append(Notification("critical_state", "重伤待休息", 10, "休息", "重伤休息"))

    if status == "休息中":
        if _rest_ready(row, current):
            result.append(Notification("rest_ready", "休息可结束", 20, "结束休息", "结束休息"))
    return result


def _exploration_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    row = database.fetch_one(
        """
        SELECT started_at, ready_at, result
        FROM exploration_records
        WHERE client_id = ? AND claimed = 0
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (client_id,),
    )
    if not row:
        return []
    ready_at = _effective_exploration_ready_at(row)
    if ready_at and current >= ready_at:
        return [Notification("exploration_ready", "探险可结束", 30, "结束探险", "结束探险")]
    return []


def _reward_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    _close_expired_seasonal_boss_events(database, current)
    checks: tuple[tuple[str, str, int, str, str, str, tuple[Any, ...]], ...] = (
        (
            "boss_reward",
            "首领奖励待领",
            40,
            "首领奖励",
            "首领奖励",
            """
            SELECT 1
            FROM seasonal_boss_events AS e
            JOIN seasonal_boss_participants AS p ON p.event_id = e.event_id
            WHERE p.client_id = ?
              AND p.reward_claimed = 0
              AND e.status IN ('已击破', '已退去')
            LIMIT 1
            """,
            (client_id,),
        ),
        (
            "wormhole_reward",
            "虫洞奖励待领",
            50,
            "虫洞奖励",
            "虫洞奖励",
            """
            SELECT 1
            FROM wormholes AS w
            JOIN wormhole_participants AS p ON p.wormhole_id = w.wormhole_id
            WHERE p.client_id = ?
              AND p.reward_claimed = 0
              AND w.status IN ('已击杀', '已退去')
            LIMIT 1
            """,
            (client_id,),
        ),
    )
    result = [
        Notification(key, text, priority, command, label)
        for key, text, priority, command, label, sql, params in checks
        if database.fetch_one(sql, params)
    ]

    pending_sect_reward = database.fetch_one(
        """
        SELECT 1
        FROM sect_war_rewards
        WHERE client_id = ? AND claimed = 0
        LIMIT 1
        """,
        (client_id,),
    )
    if pending_sect_reward:
        result.append(Notification("sect_war_reward", "宗门大会奖励待领", 60, "领取宗门大会奖励", "宗门大会奖励"))
    if _trade_reward_ready(client_id, database, current):
        result.append(Notification("trade_reward", "跑商奖励待领", 65, "跑商奖励", "跑商奖励"))
    return result


def _trade_reward_ready(client_id: str, database: Any, current: datetime) -> bool:
    """判断今日普通跑商奖励是否已达到领取条件。"""

    day = business_day(current)
    claimed = database.fetch_one(
        """
        SELECT 1
        FROM trade_daily_rewards
        WHERE client_id = ? AND business_day = ?
        LIMIT 1
        """,
        (client_id, day),
    )
    if claimed:
        return False
    stat = database.fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN action = 'sell' THEN quantity ELSE 0 END), 0) AS quantity,
            COALESCE(SUM(
                CASE
                    WHEN action = 'sell' THEN total_price - fee
                    WHEN action = 'buy' THEN -(total_price + fee)
                    ELSE 0
                END
            ), 0) AS net_profit
        FROM trade_records
        WHERE client_id = ?
          AND business_day = ?
          AND action IN ('buy', 'sell')
        """,
        (client_id, day),
    )
    quantity = int(row_value(stat, "quantity", 0) or 0) if stat else 0
    net_profit = int(row_value(stat, "net_profit", 0) or 0) if stat else 0
    if quantity <= 0 or net_profit <= 0:
        return False
    active_count = _active_trade_player_count(database, current)
    global_soft = trade_global_soft_line(active_count)
    player_soft = trade_player_soft_line(active_count, global_soft)
    min_quantity, min_net = trade_daily_reward_thresholds(player_soft)
    return quantity >= min_quantity or net_profit >= min_net


def _active_trade_player_count(database: Any, current: datetime) -> int:
    """读取近期活跃人数，用来和跑商实际奖励门槛保持一致。"""

    cutoff = _ts(current - timedelta(days=TRADE_ACTIVE_WINDOW_DAYS))
    row = database.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM players p
        WHERE p.created_at >= ?
           OR EXISTS (SELECT 1 FROM game_logs g WHERE g.client_id = p.client_id AND g.created_at >= ?)
           OR EXISTS (SELECT 1 FROM trade_records t WHERE t.client_id = p.client_id AND t.created_at >= ?)
           OR EXISTS (SELECT 1 FROM exploration_records e WHERE e.client_id = p.client_id AND e.started_at >= ?)
           OR EXISTS (SELECT 1 FROM wormhole_participants wp WHERE wp.client_id = p.client_id AND wp.updated_at >= ?)
           OR EXISTS (SELECT 1 FROM seasonal_boss_participants sp WHERE sp.client_id = p.client_id AND sp.updated_at >= ?)
           OR EXISTS (SELECT 1 FROM duel_records d WHERE (d.from_client_id = p.client_id OR d.to_client_id = p.client_id) AND d.created_at >= ?)
           OR EXISTS (SELECT 1 FROM combat_logs c WHERE c.client_id = p.client_id AND c.created_at >= ?)
        """,
        (cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff),
    )
    return max(1, int(row_value(row, "count", 0) or 0))


def _duel_request_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    row = database.fetch_one(
        """
        SELECT 1
        FROM duel_requests
        WHERE to_client_id = ?
          AND status = '等待'
          AND datetime(expires_at) > datetime(?)
        LIMIT 1
        """,
        (client_id, _ts(current)),
    )
    if row:
        return [Notification("duel_request", "对战请求待处理", 70, "决斗记录", "对战请求")]
    return []


def _world_material_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    """世界物资相关强通知，只放需要行动的事项。"""

    result: list[Notification] = []
    sect_map = database.fetch_one(
        """
        SELECT 1
        FROM treasure_maps
        WHERE owner_client_id = ? AND status IN ('宗主待领', '已成交')
        LIMIT 1
        """,
        (client_id,),
    )
    if sect_map:
        result.append(Notification("treasure_map_claim", "藏宝图待领", 55, "领取藏宝图", "领取藏宝图"))

    auction = database.fetch_one(
        """
        SELECT expires_at
        FROM treasure_maps
        WHERE status = '拍卖中'
          AND highest_bidder = ?
        ORDER BY expires_at ASC
        LIMIT 1
        """,
        (client_id,),
    )
    if auction:
        expires_at = dt(str(row_value(auction, "expires_at", "") or ""))
        if expires_at and expires_at - current <= timedelta(hours=2):
            result.append(Notification("treasure_map_auction", "藏宝图竞拍将结", 75, "藏宝图", "藏宝图竞拍"))

    return result


def _second_hand_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    """提醒卖家最近成交到账；低优先级，排在待处理事项后面。"""

    cutoff = _ts(current - timedelta(hours=6))
    row = database.fetch_one(
        """
        SELECT r.total_price, r.fee, p.display_name AS buyer_name
        FROM second_hand_records AS r
        LEFT JOIN players AS p ON p.client_id = r.buyer_id
        WHERE r.seller_id = ?
          AND datetime(replace(r.created_at, 'T', ' ')) >= datetime(replace(?, 'T', ' '))
        ORDER BY r.created_at DESC
        LIMIT 1
        """,
        (client_id, cutoff),
    )
    if not row:
        return []
    gain = max(0, int(row_value(row, "total_price", 0) or 0) - int(row_value(row, "fee", 0) or 0))
    buyer = str(row_value(row, "buyer_name", "某位道友") or "某位道友")
    return [Notification("second_hand_sale", f"二手成交到账：{buyer}付来{money(gain)}", 90, "二手市场", f"二手到账+{money(gain)}")]


def _bank_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    """银行计息达到单次 24 小时上限后再提醒结息。"""

    row = database.fetch_one(
        """
        SELECT star_level, balance, last_settle_at, last_interest_day, daily_interest_claimed
        FROM bank_accounts
        WHERE client_id = ?
        """,
        (client_id,),
    )
    if not row:
        return []
    balance = max(0, int(row_value(row, "balance", 0) or 0))
    if balance <= 0:
        return []
    star_level = int(row_value(row, "star_level", 1) or 1)
    conf = BANK_LEVELS.get(star_level, BANK_LEVELS[1])
    day = business_day(current)
    claimed = int(row_value(row, "daily_interest_claimed", 0) or 0) if row_value(row, "last_interest_day", "") == day else 0
    left_limit = int(conf["daily_interest_limit"]) - claimed
    if left_limit <= 0:
        return []
    last = dt(str(row_value(row, "last_settle_at", "") or "")) or current
    elapsed_hours = max(0.0, (current - last).total_seconds() / 3600)
    if elapsed_hours < 24.0:
        return []
    hours = min(24.0, elapsed_hours)
    reward = max(0, min(int(balance * float(conf["hour_rate"]) * hours), left_limit))
    if reward <= 0:
        return []
    return [Notification("bank_interest", "银行结息", 85, "银行结息", "银行结息")]


def _newbie_gift_notifications(client_id: str, database: Any) -> list[Notification]:
    """提醒还没领一次性新手礼包；低优先级，不挤占成熟待办。"""

    row = database.fetch_one(
        """
        SELECT newbie_claimed
        FROM players
        WHERE client_id = ?
        """,
        (client_id,),
    )
    if not row or int(row_value(row, "newbie_claimed", 0) or 0):
        return []
    return [Notification("newbie_gift", "新手礼包待领", 95, "新手礼包", "新手礼包")]


def _daily_sign_notifications(client_id: str, database: Any, current: datetime) -> list[Notification]:
    """提醒今日还没签到；这是低优先级日常，不挤占急事队首。"""

    row = database.fetch_one(
        """
        SELECT last_sign_date
        FROM players
        WHERE client_id = ?
        """,
        (client_id,),
    )
    if not row:
        return []
    if str(row_value(row, "last_sign_date", "") or "") == business_day(current):
        return []
    return [Notification("daily_sign", "今日签到待领", 100, "签到", "今日签到")]


def _sect_war_system_messages(database: Any, current: datetime) -> list[SystemMessage]:
    if not _has_sect_war_activity(database):
        return []
    result: list[SystemMessage] = []
    if sect_war_in_reward_claim_window(current):
        result.append(SystemMessage("sect_war_reward_day", "宗门大会领取日", 20, "领取宗门大会奖励", "宗门大会领取日"))
    elif current.weekday() == 5 and sect_war_in_battle_window(current):
        result.append(SystemMessage("sect_war_final_day", "宗门大会收官日", 30, "宗门大会", "宗门大会收官日"))
    if sect_war_is_member_locked(current):
        result.append(SystemMessage("sect_war_member_lock", "宗门变动锁定", 90, "宗门", "宗门变动锁定"))
    return result


def _has_sect_war_activity(database: Any) -> bool:
    row = database.fetch_one(
        """
        SELECT 1
        FROM sects
        LIMIT 1
        """
    )
    if row:
        return True
    row = database.fetch_one(
        """
        SELECT 1
        FROM sect_war_rewards
        LIMIT 1
        """
    )
    return bool(row)


def _wormhole_system_messages(database: Any, current: datetime) -> list[SystemMessage]:
    row = database.fetch_one(
        """
        SELECT boss_name, location_name, result
        FROM wormholes
        WHERE status = '开启'
          AND datetime(closes_at) > datetime(?)
        ORDER BY opened_at DESC
        LIMIT 1
        """,
        (_ts(current),),
    )
    if not row:
        return []
    boss = str(row_value(row, "boss_name", "异界裂隙") or "异界裂隙")
    location = str(row_value(row, "location_name", "未知地点") or "未知地点")
    metadata = load_json(row_value(row, "result", "{}"), {})
    event_type = metadata.get("event_type") if isinstance(metadata, dict) else ""
    if event_type == "war_prep":
        force = str(metadata.get("force", "") or "") if isinstance(metadata, dict) else ""
        if force:
            return [SystemMessage("war_prep_wormhole", f"战备虫洞：{force}@{location}", 10, "虫洞状态", f"战备虫洞·{location}")]
        return [SystemMessage("war_prep_wormhole", f"战备虫洞：{boss}@{location}", 10, "虫洞状态", f"战备虫洞·{location}")]
    return [SystemMessage("normal_wormhole", f"异界虫洞：{boss}@{location}", 40, "虫洞状态", f"异界虫洞·{location}")]


def _seasonal_boss_system_messages(database: Any, current: datetime, client_id: str | None) -> list[SystemMessage]:
    _close_expired_seasonal_boss_events(database, current)
    row = database.fetch_one(
        """
        SELECT event_id, boss_name, title, weight_type
        FROM seasonal_boss_events
        WHERE status = '开启'
          AND datetime(closes_at) > datetime(?)
        ORDER BY opened_at DESC
        LIMIT 1
        """,
        (_ts(current),),
    )
    if not row:
        return []
    if client_id and _seasonal_boss_hidden_for_client(database, int(row_value(row, "event_id", 0) or 0), client_id, current):
        return []
    boss = str(row_value(row, "boss_name", "岁时情劫") or "岁时情劫")
    title = str(row_value(row, "title", "") or "")
    name = f"{title}·{boss}" if title else boss
    return [SystemMessage("seasonal_boss", f"岁时情劫：{name}", 50, "挑战首领", f"岁时情劫·{boss}")]


def _seasonal_boss_hidden_for_client(database: Any, event_id: int, client_id: str, current: datetime) -> bool:
    """玩家正在首领 CD 或已无挑战次数时，系统行不再催他看首领。"""

    if event_id <= 0:
        return False
    row = database.fetch_one(
        """
        SELECT challenge_count, last_challenge_at
        FROM seasonal_boss_participants
        WHERE event_id = ? AND client_id = ?
        """,
        (event_id, client_id),
    )
    if not row:
        return False
    if int(row_value(row, "challenge_count", 0) or 0) >= SEASONAL_BOSS_MAX_CHALLENGES:
        return True
    last = dt(str(row_value(row, "last_challenge_at", "") or ""))
    if not last:
        return False
    return current - last < timedelta(minutes=SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES)


def _close_expired_seasonal_boss_events(database: Any, current: datetime) -> None:
    """回复头也要推进首领日结，避免领奖通知等到玩家先查首领。"""

    execute = getattr(database, "execute", None)
    if not callable(execute):
        return
    try:
        execute(
            """
            UPDATE seasonal_boss_events
            SET status = '已退去', result = ?
            WHERE status = '开启'
              AND datetime(closes_at) <= datetime(?)
            """,
            (dump_json({"reason": "timeout"}), _ts(current)),
        )
    except Exception:
        # 首领状态推进只是回复头的顺手维护；真正结算入口仍会再次校验。
        return


def _treasure_map_system_messages(database: Any, current: datetime) -> list[SystemMessage]:
    result: list[SystemMessage] = []
    auction = database.fetch_one(
        """
        SELECT city_name, expires_at
        FROM treasure_maps
        WHERE status = '拍卖中'
        ORDER BY expires_at ASC
        LIMIT 1
        """
    )
    if auction:
        expires_at = dt(str(row_value(auction, "expires_at", "") or ""))
        if expires_at and expires_at > current and expires_at - current <= timedelta(hours=2):
            city = str(row_value(auction, "city_name", "某城") or "某城")
            result.append(SystemMessage("treasure_map_auction", f"{city}藏宝图将结", 60, "藏宝图", f"{city}·藏宝图将结"))

    pickup = database.fetch_one(
        """
        SELECT city_name, x, y, expires_at
        FROM treasure_maps
        WHERE status = '可拾取'
        ORDER BY expires_at ASC
        LIMIT 1
        """
    )
    if pickup:
        expires_at = dt(str(row_value(pickup, "expires_at", "") or ""))
        if not expires_at or expires_at > current:
            city = str(row_value(pickup, "city_name", "某城") or "某城")
            x = int(row_value(pickup, "x", 0) or 0)
            y = int(row_value(pickup, "y", 0) or 0)
            result.append(SystemMessage("treasure_map_pickup", f"{city}藏宝图散落({x},{y})", 70, f"导航 {x} {y}", f"{city}·藏宝图({x},{y})"))
    return result


def _notice_text(item: Notification | SystemMessage) -> str:
    """通知正文统一使用无框命令链接；没有动作命令时退回纯文本。"""

    label = item.label or item.text
    if item.command:
        return inline_command_link(label, item.command)
    return label


def _queue_line(prefix: str, items: list[NoticeItem], limit: int) -> str:
    """把通知队列压成回复头的一行。

    队列里保留完整待办对象，展示时只取前几条；前面的事项处理掉以后，后面
    会自然补上，不需要额外公告命令，也不抢底部按钮位置。
    """

    if not items:
        return ""
    ordered = sorted(items, key=lambda item: item.priority)
    texts = [_notice_text(item) for item in ordered[: max(1, int(limit))]]
    return f"{prefix}{'｜'.join(texts)}"


def _effective_exploration_ready_at(row: Any) -> datetime | None:
    ready_at = dt(str(row_value(row, "ready_at", "") or ""))
    started_at = dt(str(row_value(row, "started_at", "") or ""))
    if not ready_at or not started_at:
        return ready_at
    result = load_json(row_value(row, "result", "{}"), {})
    duration_seconds = _exploration_duration_seconds(result)
    expected_ready_at = started_at if duration_seconds <= 0 else started_at + _seconds_offset(duration_seconds)
    if ready_at > expected_ready_at:
        return expected_ready_at
    return ready_at


def _exploration_duration_seconds(result: Any) -> int:
    if not isinstance(result, dict):
        return EXPLORE_MINUTES * 60
    for key in ("duration_seconds", "total_seconds"):
        value = result.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return max(ENCOUNTER_SECONDS, int(value))
    realm = result.get("secret_realm")
    if isinstance(realm, dict):
        value = realm.get("duration_seconds")
        if isinstance(value, (int, float)) and value > 0:
            return max(ENCOUNTER_SECONDS, int(value))
    return EXPLORE_MINUTES * 60


def _dedupe_notifications(notifications: list[Notification]) -> list[Notification]:
    return _dedupe_by_key(notifications)


def _dedupe_system_messages(messages: list[SystemMessage]) -> list[SystemMessage]:
    return _dedupe_by_key(messages)


def _dedupe_by_key(items: list[NoticeT]) -> list[NoticeT]:
    """按 key 保留优先级最高的同类通知。"""

    result: list[NoticeT] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda value: value.priority):
        if item.key in seen:
            continue
        seen.add(item.key)
        result.append(item)
    return result


def _rest_ready(player: Any, current: datetime) -> bool:
    rest_full_at = dt(str(row_value(player, "rest_full_at", "") or ""))
    if not rest_full_at:
        return False
    full_seconds = REST_FULL_MINUTES * 60
    elapsed = max(0, min(full_seconds, int(row_value(player, "rest_window_elapsed_seconds", 0) or 0)))
    remaining_seconds = max(0, full_seconds - elapsed)
    active_started_at = rest_full_at - timedelta(seconds=remaining_seconds)
    active_seconds = max(0, int((current - active_started_at).total_seconds()))
    return active_seconds >= REST_FAST_SECONDS


def _seconds_offset(seconds: int):
    return timedelta(seconds=max(0, int(seconds)))


def _now() -> datetime:
    from .common import now

    return now()


def _ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


__all__ = [
    "DEFAULT_NOTICE_LIMIT",
    "DEFAULT_SYSTEM_NOTICE_LIMIT",
    "NOTICE_PREFIX",
    "Notification",
    "SYSTEM_NOTICE_PREFIX",
    "SystemMessage",
    "collect_notifications",
    "collect_system_messages",
    "notification_line",
    "system_message_line",
]
