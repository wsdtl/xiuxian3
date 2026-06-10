"""战斗日志展示格式。

这里只负责把已经结算好的战斗结果排版成玩家可读文本，不参与任何数值结算。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable


def wants_detail(player: dict[str, Any] | None) -> bool:
    """玩家是否开启旧版详细逐次出手日志。"""

    if not player:
        return False
    return bool(int(player.get("battle_log_detail") or 0))


def mode_text(player: dict[str, Any] | None) -> str:
    """战斗日志开关展示文本。"""

    return "详细" if wants_detail(player) else "简要"


def markdown_reply(content: str) -> dict[str, Any]:
    """生成 markdown 回复。"""

    return {
        "code": 202,
        "type": "markdown",
        "message": {
            "content": content.strip(),
        },
    }


def exploration_brief(
    *,
    record: dict[str, Any],
    player: dict[str, Any],
    events: list[dict[str, Any]],
    exp_total: int,
    old_level: int,
    new_level: int,
    drops_text: str,
    ring_drops_text: str,
    weapon_drops_text: str,
    medicine_text: str,
    stop_reason: str,
    event_drop_text: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """探险结算的简要战斗日志。"""

    wins = sum(1 for event in events if event.get("win"))
    losses = max(0, len(events) - wins)
    hp_left = int(player.get("hp", 1))
    mp_left = int(player.get("mp", 0))
    level_text = f"{old_level} -> {new_level}" if new_level > old_level else f"{new_level}，未升级"

    lines = [
        "> **探险结束**",
        f"> 记录 **#{record['record_id']}**｜地点：{record['location_name']}",
        f"> 战斗 **{len(events)}** 场｜胜 **{wins}**｜败 **{losses}**｜经验 **+{exp_total}**",
        f"> 等级：{level_text}｜最终血气 **{hp_left}/{player['max_hp']}**｜精神 **{mp_left}/{player['max_mp']}**",
        f"> 停止原因：{stop_reason}",
        ">",
        "> **战斗摘要**",
    ]

    if not events:
        lines.append("> 本次没有战斗事件。")
    for index, event in enumerate(events, start=1):
        lines.extend(_exploration_event_lines(index, event, player, event_drop_text))

    lines.extend(
        [
            ">",
            "> **最终收获**",
            f"> 背包：{drops_text}",
            f"> 纳戒：{ring_drops_text}",
            f"> 武器：{weapon_drops_text}",
            f"> 自动用药：{medicine_text or '无'}",
            "> 当前状态：空闲",
        ]
    )
    return markdown_reply("\n".join(lines))


def boss_brief(
    *,
    title: str,
    subtitle: str = "",
    boss_name: str,
    boss_label: str,
    player: dict[str, Any],
    result: dict[str, Any],
    damage: int,
    left_hp: int,
    max_hp: int,
    killed: bool,
    killed_text: str,
    alive_text: str,
    hurt_text: str,
) -> dict[str, Any]:
    """虫洞和首领挑战的简要战斗日志。"""

    actions = result.get("actions")
    action_list = actions if isinstance(actions, list) else []
    player_skills = _skill_count(action_list, "skill_used", "skill_name")
    boss_skills = _skill_count(action_list, "boss_skill_used", "boss_skill_name")
    state_text = killed_text if killed else alive_text
    if int(result.get("hp_left", 0)) <= 0:
        state_text = f"{hurt_text}；{state_text}"

    lines = [
        f"> **{title}**",
    ]
    if subtitle.strip():
        lines.append(f"> {subtitle.strip()}")
    lines.extend(
        [
            f"> {boss_label}：{boss_name}｜剩余 **{left_hp}/{max_hp}**",
            f"> 本次伤害 **{damage}**｜行动 **{len(action_list)}** 次",
            f"> 我方：血气 **{result['hp_left']}/{player['max_hp']}**｜精神 **{result['mp_left']}/{player['max_mp']}**",
            f"> 我方技能：{_skill_text(player_skills)}｜{boss_label}技能：{_skill_text(boss_skills)}",
            f"> {state_text}",
        ]
    )
    return markdown_reply("\n".join(lines))


def duel_brief(
    *,
    title: str,
    result: dict[str, Any],
    settlement: str,
    format_player_name: Callable[[str], str],
) -> dict[str, Any]:
    """切磋和决斗的简要战斗日志。"""

    actions = result.get("actions")
    action_list = actions if isinstance(actions, list) else []
    skill_counter: Counter[str] = Counter()
    for action in action_list:
        for side in ("left", "right"):
            attack = action.get(side)
            if not isinstance(attack, dict) or not attack.get("skill_used"):
                continue
            actor = format_player_name(str(attack.get("actor_id", "")))
            skill = str(attack.get("skill_name") or "技能")
            skill_counter[f"{actor}：{skill}"] += 1

    left_id = str(result.get("left_id", ""))
    right_id = str(result.get("right_id", ""))
    lines = [
        f"> **{title}**",
        f"> {result.get('summary', '')}",
        f"> 胜者：{format_player_name(str(result.get('winner_id', '')))}｜败者：{format_player_name(str(result.get('loser_id', '')))}",
        (
            f"> {format_player_name(left_id)}：血气 **{result.get('left_hp_left', 0)}/{result.get('left_max_hp', 0)}**｜"
            f"精神 **{result.get('left_mp_left', 0)}/{result.get('left_max_mp', 0)}**"
        ),
        (
            f"> {format_player_name(right_id)}：血气 **{result.get('right_hp_left', 0)}/{result.get('right_max_hp', 0)}**｜"
            f"精神 **{result.get('right_mp_left', 0)}/{result.get('right_max_mp', 0)}**"
        ),
        f"> 技能：{_skill_text(skill_counter)}｜行动 **{len(action_list)}** 次",
    ]
    if settlement:
        lines.append(f"> {settlement}")
    return markdown_reply("\n".join(lines))


def _exploration_event_lines(
    index: int,
    event: dict[str, Any],
    player: dict[str, Any],
    event_drop_text: Callable[[dict[str, Any]], str],
) -> list[str]:
    """单场探险战斗摘要。"""

    actions = event.get("actions")
    action_list = actions if isinstance(actions, list) else []
    player_skills = _skill_count(action_list, "skill_used", "skill_name")
    enemy_skills = _skill_count(action_list, "monster_skill_used", "monster_skill_name")
    result_text = "胜利" if event.get("win") else "失败"
    hp_left = max(0, int(event.get("hp_left", 0)))
    mp_left = max(0, int(event.get("mp_left", 0)))
    monster = str(event.get("monster") or "怪物")
    return [
        f"> **第 {index} 战**｜{monster}｜{result_text}",
        (
            f"> 行动 **{len(action_list)}** 次｜我方技能：{_skill_text(player_skills)}｜"
            f"敌方技能：{_skill_text(enemy_skills)}｜经验 **+{int(event.get('exp', 0))}**"
        ),
        f"> 战后：血气 **{hp_left}/{player['max_hp']}**｜精神 **{mp_left}/{player['max_mp']}**｜掉落：{event_drop_text(event)}",
    ]


def _skill_count(actions: list[dict[str, Any]], used_key: str, name_key: str) -> Counter[str]:
    """统计技能触发次数。"""

    counter: Counter[str] = Counter()
    for action in actions:
        if action.get(used_key):
            counter[str(action.get(name_key) or "技能")] += 1
    return counter


def _skill_text(counter: Counter[str]) -> str:
    """技能统计展示。"""

    if not counter:
        return "无"
    return "、".join(f"{name} x{count}" for name, count in counter.items())
