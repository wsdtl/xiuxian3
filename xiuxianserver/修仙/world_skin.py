"""世界皮肤公共只读能力。

二级组件不要互相导入；帮助、百科等组件需要皮肤展示名时，
统一从这个根目录公共模块读取。
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import (
    CURRENCY_DEFS,
    ENEMY_SKILL_NAMES_BY_KEY,
    PLAYER_LEVEL_DEFS,
    QUALITY_DEFS,
    SPECIAL_RING_ITEM_DEFAULT_NAMES,
    currency_name,
    player_level_label,
    quality_label,
    set_currency_label_overrides,
    set_enemy_skill_label_overrides,
    set_player_level_label_overrides,
    set_quality_label_overrides,
)
from .constants import SCHEMA_VERSION
from .sql import db


DEFAULT_SKIN_ID = "default"
PACKAGE_FORMAT = 4
PACKS_DIR = Path(__file__).resolve().parent / "世界皮肤" / "packs"
SKIN_HELP_MAP_DIR = "/static/map"
DEFAULT_HELP_MAP_PATH = f"{SKIN_HELP_MAP_DIR}/{DEFAULT_SKIN_ID}.png"
SKIN_HELP_MAP_EXTENSIONS = ("jpeg", "jpg", "png")
SERVER_ROOT = Path(__file__).resolve().parent.parent
SECRET_REALM_ENVIRONMENT_KEYS = {
    "secret_env_youming_wind",
    "secret_env_mirror_sky",
    "secret_env_dragon_bone_dust",
    "secret_env_star_fire_rain",
    "secret_env_returning_tide",
}


@dataclass(frozen=True)
class WorldSkinPackage:
    """已安全解析的世界皮肤包。"""

    skin_id: str
    display_name: str
    version: str
    author: str
    desc: str
    manifest: dict[str, Any]
    names: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class WorldSkinEntry:
    """当前皮肤下可检索的世界展示名。"""

    kind: str
    group: str
    stable_id: str
    title: str
    summary: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorldSkinDefinition:
    """当前皮肤名解析到的完整定义资料。"""

    kind: str
    group: str
    stable_id: str
    title: str
    row: dict[str, Any]


@dataclass(frozen=True)
class WorldSkinToken:
    """当前皮肤运行态缓存令牌。"""

    db_key: str
    skin_id: str
    snapshot_id: int
    switched_at: str


@dataclass(frozen=True)
class WorldSkinCatalog:
    """当前世界名录及常用检索索引。"""

    token: WorldSkinToken
    entries: tuple[WorldSkinEntry, ...]
    by_name: dict[str, WorldSkinEntry]
    by_stable_id: dict[str, WorldSkinEntry]
    by_kind_name: dict[tuple[str, str], WorldSkinEntry]
    by_kind_stable_id: dict[tuple[str, str], WorldSkinEntry]


WORLD_DEFINITION_TABLES: dict[str, tuple[str, str]] = {
    "世界物品": ("item_defs", "item_id"),
    "纳戒物品": ("ring_item_defs", "ring_item_id"),
    "武器": ("weapon_defs", "weapon_def_id"),
    "武器技能": ("weapon_skill_defs", "skill_id"),
    "技能书附魔": ("weapon_enchants", "enchant_id"),
    "怪物": ("monster_defs", "monster_id"),
    "体质": ("physique_defs", "physique_id"),
    "货币": ("currency_labels", "currency_key"),
    "等级显示": ("player_level_labels", "level"),
}
_PACKAGE_CACHE: dict[tuple[str, int, int], WorldSkinPackage] = {}
_CATALOG_CACHE: dict[WorldSkinToken, WorldSkinCatalog] = {}
_DEFINITION_CACHE: dict[tuple[WorldSkinToken, str, str], WorldSkinDefinition | None] = {}


def list_skin_packages() -> tuple[WorldSkinPackage, ...]:
    """列出所有可解析的世界皮肤包；坏包会被跳过，切换时仍会报详细错误。"""

    result: list[WorldSkinPackage] = []
    if not PACKS_DIR.exists():
        return ()
    for pack_dir in sorted(path for path in PACKS_DIR.iterdir() if path.is_dir()):
        try:
            result.append(load_skin_package(pack_dir.name))
        except Exception:
            continue
    return tuple(result)


def load_skin_package(skin_id: str) -> WorldSkinPackage:
    """按包名安全读取一个世界皮肤包。"""

    safe_id = _safe_skin_id(skin_id)
    pack_dir = PACKS_DIR / safe_id
    if safe_id != str(skin_id or "").strip() or not pack_dir.is_dir():
        raise ValueError(f"世界皮肤包不存在：{skin_id}")

    manifest_path = pack_dir / "manifest.py"
    names_path = pack_dir / "names.py"
    cache_key = _package_cache_key(safe_id, manifest_path, names_path)
    cached = _PACKAGE_CACHE.get(cache_key)
    if cached:
        return cached

    manifest = _read_literal_assignment(manifest_path, "PACKAGE")
    names = _read_literal_assignment(names_path, "NAMES")
    if not isinstance(manifest, dict) or not isinstance(names, dict):
        raise ValueError(f"世界皮肤包结构错误：{safe_id}")
    if str(manifest.get("skin_id") or "").strip() != safe_id:
        raise ValueError(f"manifest.py 的 skin_id 必须等于目录名：{safe_id}")
    if int(manifest.get("package_format") or 0) != PACKAGE_FORMAT:
        raise ValueError(f"{safe_id} 的 package_format 必须是 {PACKAGE_FORMAT}")
    if int(manifest.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"{safe_id} 的 schema_version 必须是 {SCHEMA_VERSION}")
    if list(manifest.get("files") or []) != ["names.py"]:
        raise ValueError(f"{safe_id} 的 files 必须只包含 names.py")
    package = WorldSkinPackage(
        skin_id=safe_id,
        display_name=str(manifest.get("display_name") or safe_id).strip(),
        version=str(manifest.get("version") or "").strip(),
        author=str(manifest.get("author") or "").strip(),
        desc=str(manifest.get("desc") or "").strip(),
        manifest=manifest,
        names=names,
        path=pack_dir,
    )
    _drop_package_cache_for_skin(safe_id)
    _PACKAGE_CACHE[cache_key] = package
    return package


def validate_skin_package(package: WorldSkinPackage, database: Any = db) -> list[str]:
    """校验皮肤包是否覆盖当前代码和数据库需要的稳定键。"""

    errors: list[str] = []
    names = package.names
    places = _dict_at(names, "places", errors)
    cities = _dict_at(places, "cities", errors)
    realm = _dict_at(places, "realm", errors)
    buyers = _dict_at(places, "buyers", errors)
    recycles = _dict_at(places, "recycles", errors)
    world_items = _dict_at(names, "world_items", errors)
    ring = _dict_at(names, "ring", errors)
    weapons = _dict_at(names, "weapons", errors)
    actors = _dict_at(names, "actors", errors)
    wormhole = _dict_at(names, "wormhole", errors)
    secret_realm = _dict_at(names, "secret_realm", errors)
    system = _dict_at(names, "system", errors)
    if errors:
        return errors

    _require_count(errors, "普通城池", cities, 11)
    _require_count(errors, "太虚秘境", realm, 1)
    _require_count(errors, "特殊收购点", buyers, 6)
    _require_count(errors, "回收点", recycles, 3)
    _require_keys(errors, "世界物资大类", world_items, {"medicine", "life", "build", "relic", "loot"})
    _require_keys(errors, "纳戒分组", ring, {"recovery", "gems", "special"})
    _require_keys(errors, "武器分组", weapons, {"skill_books", "types"})
    _require_keys(errors, "生物分组", actors, {"monsters", "physiques", "enemy_kinds", "enemy_skills"})
    _require_keys(errors, "虫洞分组", wormhole, {"bosses", "flows", "war_prep_bosses", "war_prep_affixes"})
    _require_keys(errors, "太虚秘境分组", secret_realm, {"environments"})
    _require_keys(errors, "系统分组", system, {"quality", "currency", "levels"})

    city_weapon_count = 0
    city_trade_count = 0
    for city_id, city in cities.items():
        if not isinstance(city, dict):
            errors.append(f"城池配置必须是字典：{city_id}")
            continue
        _require_text(errors, f"{city_id}.name", city.get("name"))
        _require_count(errors, f"{city_id}.trade_goods", city.get("trade_goods"), 3)
        weapons_map = city.get("weapons")
        if not isinstance(weapons_map, dict):
            errors.append(f"{city_id}.weapons 必须是字典")
            continue
        city_trade_count += len(city.get("trade_goods") or {})
        city_weapon_count += len(weapons_map)
        for weapon_id, weapon in weapons_map.items():
            if not isinstance(weapon, dict):
                errors.append(f"武器配置必须是字典：{weapon_id}")
                continue
            _require_text(errors, f"{weapon_id}.name", weapon.get("name"))
            innate = weapon.get("innate_skill")
            if not isinstance(innate, dict):
                errors.append(f"{weapon_id}.innate_skill 必须是字典")
                continue
            _require_text(errors, f"{weapon_id}.innate_skill.skill_id", innate.get("skill_id"))
            _require_text(errors, f"{weapon_id}.innate_skill.name", innate.get("name"))
    _require_exact(errors, "普通城池特产", city_trade_count, 33)
    _require_exact(errors, "城池武器", city_weapon_count, 72)

    _require_count(errors, "非纯经济世界物资", _flatten_world_item_names(world_items), 125)
    _require_count(errors, "恢复纳戒物品", ring.get("recovery"), 7)
    _require_count(errors, "宝石", ring.get("gems"), 9)
    _require_keys(errors, "特殊纳戒物品", _dict_or_empty(ring.get("special")), set(SPECIAL_RING_ITEM_DEFAULT_NAMES))
    _require_count(errors, "技能书", weapons.get("skill_books"), 72)
    _require_keys(errors, "敌方技能", _dict_or_empty(actors.get("enemy_skills")), set(ENEMY_SKILL_NAMES_BY_KEY))
    _require_keys(errors, "太虚环境", _secret_realm_environment_names(secret_realm), SECRET_REALM_ENVIRONMENT_KEYS)
    _require_count(errors, "等级显示", system.get("levels"), len(PLAYER_LEVEL_DEFS))
    _require_keys(errors, "品质显示", _dict_or_empty(system.get("quality")), set(QUALITY_DEFS))
    _require_keys(errors, "货币显示", _dict_or_empty(system.get("currency")), set(CURRENCY_DEFS))

    _validate_database_coverage(package, database, errors)
    _validate_unique_display_names(package, errors)
    return errors


def apply_world_skin_package(
    conn: sqlite3.Connection,
    package: WorldSkinPackage,
    *,
    switched_by: str = "",
    record_snapshot: bool = True,
    update_active: bool = True,
) -> dict[str, int]:
    """把皮肤包写入当前展示快照；只改展示名，不改稳定键和数值。"""

    counts: dict[str, int] = {
        "locations": 0,
        "items": 0,
        "ring_items": 0,
        "weapons": 0,
        "skills": 0,
        "monsters": 0,
        "physiques": 0,
        "system": 0,
        "events": 0,
    }
    if record_snapshot:
        snapshot_id = _insert_skin_snapshot(conn, package, switched_by)
    else:
        snapshot_id = 0

    names = package.names
    counts["locations"] += _apply_places(conn, names)
    counts["items"] += _apply_world_items(conn, names)
    counts["ring_items"] += _apply_ring_items(conn, names)
    weapon_count, skill_count = _apply_weapons(conn, names)
    counts["weapons"] += weapon_count
    counts["skills"] += skill_count
    monster_count, physique_count = _apply_actors(conn, names)
    counts["monsters"] += monster_count
    counts["physiques"] += physique_count
    counts["system"] += _apply_system_labels(conn, names)
    counts["events"] += _apply_event_snapshots(conn, names)

    if update_active:
        conn.execute(
            """
            INSERT INTO world_skin_active
            (id, skin_id, version, author, desc, switched_by, switched_at, snapshot_id)
            VALUES (1, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            ON CONFLICT(id) DO UPDATE SET
                skin_id = excluded.skin_id,
                version = excluded.version,
                author = excluded.author,
                desc = excluded.desc,
                switched_by = excluded.switched_by,
                switched_at = excluded.switched_at,
                snapshot_id = excluded.snapshot_id
            """,
            (package.skin_id, package.version, package.author, package.desc, switched_by, snapshot_id),
        )
    _refresh_runtime_skin_labels(conn)
    clear_world_skin_cache()
    return counts


def apply_active_world_skin_package(conn: sqlite3.Connection) -> dict[str, int] | None:
    """数据库启动种子写完后，按 world_skin_active 重放当前皮肤。"""

    row = conn.execute("SELECT skin_id FROM world_skin_active WHERE id = 1").fetchone()
    if not row:
        return None
    package = load_skin_package(str(row["skin_id"]))
    return apply_world_skin_package(conn, package, record_snapshot=False, update_active=False)


def current_skin_id(database: Any = db) -> str:
    """读取当前皮肤包名；缺失时使用默认皮肤。"""

    row = _active_skin_row(database)
    if not row:
        return DEFAULT_SKIN_ID
    value = _safe_skin_id(row.get("skin_id"))
    if value:
        return value
    return DEFAULT_SKIN_ID


def current_help_map_path(database: Any = db) -> str:
    """按当前皮肤包名匹配地图资源；优先 JPEG/JPG，其次 PNG。"""

    skin_id = current_skin_id(database)
    return (
        _best_help_map_path_for_skin(skin_id)
        or _best_help_map_path_for_skin(DEFAULT_SKIN_ID)
        or DEFAULT_HELP_MAP_PATH
    )


def current_help_map_file(database: Any = db) -> Path | None:
    """读取当前皮肤地图对应的本地文件，供 type=image 图文消息使用。"""

    file_path = _static_file_path(current_help_map_path(database))
    return file_path if file_path.exists() else None


def current_world_entries(database: Any = db) -> tuple[WorldSkinEntry, ...]:
    """读取当前世界名录，供帮助页和百科检索使用。"""

    return _runtime_catalog(database).entries


def clear_world_skin_cache(database: Any | None = None) -> None:
    """清理当前世界运行态缓存；切换皮肤和启动重放后调用。"""

    if database is None:
        _CATALOG_CACHE.clear()
        _DEFINITION_CACHE.clear()
        return
    db_key = _database_cache_key(database)
    for token in tuple(_CATALOG_CACHE):
        if token.db_key == db_key:
            _CATALOG_CACHE.pop(token, None)
    for key in tuple(_DEFINITION_CACHE):
        token = key[0]
        if token.db_key == db_key:
            _DEFINITION_CACHE.pop(key, None)


def _build_world_entries(database: Any) -> tuple[WorldSkinEntry, ...]:
    """从数据库构建一次完整世界名录。"""

    entries: list[WorldSkinEntry] = []
    entries.extend(_location_entries(database))
    entries.extend(_trade_location_entries(database))
    entries.extend(_exploration_location_entries(database))
    entries.extend(_special_buyer_entries(database))
    entries.extend(_recycle_location_entries(database))
    entries.extend(_item_entries(database))
    entries.extend(_ring_item_entries(database))
    entries.extend(_weapon_entries(database))
    entries.extend(_weapon_skill_entries(database))
    entries.extend(_weapon_enchant_entries(database))
    entries.extend(_monster_entries(database))
    entries.extend(_physique_entries(database))
    entries.extend(_quality_entries(database))
    entries.extend(_currency_entries(database))
    entries.extend(_player_level_entries(database))
    return tuple(_dedupe_entries(entries))


def current_world_entry(
    name: str,
    database: Any = db,
    *,
    kinds: set[str] | tuple[str, ...] | list[str] | None = None,
) -> WorldSkinEntry | None:
    """按当前世界展示名或稳定 ID 解析世界条目。"""

    value = _lookup_text(name)
    if not value:
        return None
    catalog = _runtime_catalog(database)
    allowed = {str(kind or "").strip() for kind in (kinds or ()) if str(kind or "").strip()}
    if not allowed:
        return catalog.by_name.get(value) or catalog.by_stable_id.get(value)
    for entry in catalog.entries:
        if allowed and entry.kind not in allowed:
            continue
        if value in {_lookup_text(entry.title), _lookup_text(entry.stable_id)}:
            return entry
    return None


def current_world_definition(
    name: str,
    database: Any = db,
    *,
    kinds: set[str] | tuple[str, ...] | list[str] | None = None,
) -> WorldSkinDefinition | None:
    """按当前世界展示名读取完整定义；业务展示入口优先走这里。"""

    entry = current_world_entry(name, database, kinds=kinds)
    if not entry:
        return None
    return _definition_from_entry(entry, database)


def current_world_definition_by_stable_id(
    kind: str,
    stable_id: str,
    database: Any = db,
) -> WorldSkinDefinition | None:
    """按稳定 ID 读取当前皮肤下的完整定义。"""

    clean_kind = str(kind or "").strip()
    clean_id = str(stable_id or "").strip()
    if not clean_kind or not clean_id:
        return None
    entry = _runtime_catalog(database).by_kind_stable_id.get((clean_kind, _lookup_text(clean_id)))
    if entry:
        return _definition_from_entry(entry, database)
    return _definition_from_key(clean_kind, "", clean_id, "", database)


def skin_name(path: tuple[str, ...] | list[str], stable_id: str, default: str, database: Any = db) -> str:
    """按当前皮肤包读取一个不落定义表的展示名。"""

    value = _skin_value(path, stable_id, database)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        title = str(value.get("name") or "").strip()
        if title:
            return title
    return str(default or stable_id)


def skin_record(path: tuple[str, ...] | list[str], stable_id: str, database: Any = db) -> dict[str, Any]:
    """按当前皮肤包读取一个结构化展示记录；不存在时返回空字典。"""

    value = _skin_value(path, stable_id, database)
    return dict(value) if isinstance(value, dict) else {}


def _active_skin_row(database: Any) -> dict[str, Any] | None:
    rows = _fetch_all(database, "SELECT * FROM world_skin_active LIMIT 1")
    return rows[0] if rows else None


def _active_skin_package(database: Any) -> WorldSkinPackage:
    return load_skin_package(current_skin_id(database))


def _active_skin_token(database: Any) -> WorldSkinToken:
    row = _active_skin_row(database)
    if not row:
        return WorldSkinToken(_database_cache_key(database), DEFAULT_SKIN_ID, 0, "")
    skin_id = _safe_skin_id(row.get("skin_id")) or DEFAULT_SKIN_ID
    try:
        snapshot_id = int(row.get("snapshot_id") or 0)
    except (TypeError, ValueError):
        snapshot_id = 0
    return WorldSkinToken(
        _database_cache_key(database),
        skin_id,
        snapshot_id,
        str(row.get("switched_at") or ""),
    )


def _runtime_catalog(database: Any) -> WorldSkinCatalog:
    token = _active_skin_token(database)
    cached = _CATALOG_CACHE.get(token)
    if cached:
        return cached

    entries = _build_world_entries(database)
    by_name: dict[str, WorldSkinEntry] = {}
    by_stable_id: dict[str, WorldSkinEntry] = {}
    by_kind_name: dict[tuple[str, str], WorldSkinEntry] = {}
    by_kind_stable_id: dict[tuple[str, str], WorldSkinEntry] = {}
    for entry in entries:
        title_key = _lookup_text(entry.title)
        stable_key = _lookup_text(entry.stable_id)
        if title_key:
            by_name.setdefault(title_key, entry)
            by_kind_name.setdefault((entry.kind, title_key), entry)
        if stable_key:
            by_stable_id.setdefault(stable_key, entry)
            by_kind_stable_id.setdefault((entry.kind, stable_key), entry)
    catalog = WorldSkinCatalog(
        token=token,
        entries=entries,
        by_name=by_name,
        by_stable_id=by_stable_id,
        by_kind_name=by_kind_name,
        by_kind_stable_id=by_kind_stable_id,
    )
    _CATALOG_CACHE[token] = catalog
    return catalog


def _skin_value(path: tuple[str, ...] | list[str], stable_id: str, database: Any) -> Any:
    try:
        node: Any = _active_skin_package(database).names
    except Exception:
        return None
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(str(part))
    if isinstance(node, dict):
        return node.get(str(stable_id))
    return None


def _read_literal_assignment(path: Path, variable_name: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"皮肤包文件不存在：{path.name}")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise ValueError(f"{path.name} 只能有一个 {variable_name} 字典赋值")
    assign = tree.body[0]
    if len(assign.targets) != 1 or not isinstance(assign.targets[0], ast.Name):
        raise ValueError(f"{path.name} 只能赋值给 {variable_name}")
    if assign.targets[0].id != variable_name:
        raise ValueError(f"{path.name} 必须赋值给 {variable_name}")
    value = ast.literal_eval(assign.value)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} 的 {variable_name} 必须是字典")
    return value


def _package_cache_key(skin_id: str, manifest_path: Path, names_path: Path) -> tuple[str, int, int]:
    if not manifest_path.exists():
        raise ValueError(f"皮肤包文件不存在：{manifest_path.name}")
    if not names_path.exists():
        raise ValueError(f"皮肤包文件不存在：{names_path.name}")
    return (skin_id, manifest_path.stat().st_mtime_ns, names_path.stat().st_mtime_ns)


def _drop_package_cache_for_skin(skin_id: str) -> None:
    for key in tuple(_PACKAGE_CACHE):
        if key[0] == skin_id:
            _PACKAGE_CACHE.pop(key, None)


def _database_cache_key(database: Any) -> str:
    path = getattr(database, "db_path", None)
    if path:
        try:
            return str(Path(path).resolve())
        except OSError:
            return str(path)
    return f"{type(database).__module__}.{type(database).__qualname__}:{id(database)}"


def _validate_database_coverage(package: WorldSkinPackage, database: Any, errors: list[str]) -> None:
    names = package.names
    city_ids = set(names["places"]["cities"])
    buyer_ids = set(names["places"]["buyers"])
    recycle_ids = set(names["places"]["recycles"])
    realm_ids = set(names["places"]["realm"])
    system_ids = city_ids | buyer_ids | recycle_ids | realm_ids
    for location_id in _column_values(database, "world_locations", "location_id"):
        if location_id not in system_ids:
            errors.append(f"地点未进包：{location_id}")
    for location_id in _column_values(database, "trade_locations", "location_id"):
        if location_id not in city_ids:
            errors.append(f"跑商城池未进包：{location_id}")
    for location_id in _column_values(database, "exploration_locations", "location_id"):
        if location_id not in city_ids and location_id not in realm_ids:
            errors.append(f"探险地点未进包：{location_id}")
    for location_id in _column_values(database, "special_buyers", "location_id"):
        if location_id not in buyer_ids:
            errors.append(f"特殊收购点未进包：{location_id}")
    for location_id in _column_values(database, "recycle_locations", "location_id"):
        if location_id not in recycle_ids:
            errors.append(f"回收点未进包：{location_id}")

    trade_goods = _city_trade_goods(names)
    for item_id in _column_values(database, "item_defs", "item_id", "tradeable = 1"):
        if item_id not in trade_goods:
            errors.append(f"纯经济特产未进包：{item_id}")
    world_items = _flatten_world_item_names(names["world_items"])
    for item_id in _column_values(database, "item_defs", "item_id", "tradeable = 0"):
        if item_id not in world_items:
            errors.append(f"世界物资未进包：{item_id}")

    ring_items = _ring_item_names(names)
    for item_id in _column_values(database, "ring_item_defs", "ring_item_id", "category_key != 'book'"):
        if item_id not in ring_items:
            errors.append(f"纳戒物品未进包：{item_id}")
    skill_books = _dict_or_empty(names["weapons"].get("skill_books"))
    for item_id in _column_values(database, "ring_item_defs", "ring_item_id", "category_key = 'book'"):
        if item_id not in skill_books:
            errors.append(f"技能书纳戒物品未进包：{item_id}")
    for enchant_id in _column_values(database, "weapon_enchants", "enchant_id"):
        if enchant_id not in skill_books:
            errors.append(f"技能书附魔未进包：{enchant_id}")

    city_weapons = _city_weapon_names(names)
    city_skills = _city_weapon_skill_names(names)
    for weapon_id in _column_values(database, "weapon_defs", "weapon_def_id"):
        if weapon_id not in city_weapons:
            errors.append(f"武器模板未进包：{weapon_id}")
    for skill_id in _column_values(database, "weapon_skill_defs", "skill_id"):
        if skill_id not in city_skills:
            errors.append(f"武器自带技能未进包：{skill_id}")

    for monster_id in _column_values(database, "monster_defs", "monster_id"):
        if monster_id not in names["actors"]["monsters"]:
            errors.append(f"怪物未进包：{monster_id}")
    for physique_id in _column_values(database, "physique_defs", "physique_id"):
        if physique_id not in names["actors"]["physiques"]:
            errors.append(f"体质未进包：{physique_id}")


def _validate_unique_display_names(package: WorldSkinPackage, errors: list[str]) -> None:
    buckets = {
        "地点": _place_names(package.names),
        "背包物品": {**_city_trade_goods(package.names), **_flatten_world_item_names(package.names["world_items"])},
        "纳戒物品": {**_ring_item_names(package.names), **_dict_or_empty(package.names["weapons"].get("skill_books"))},
        "武器": _city_weapon_names(package.names),
        "武器技能": _city_weapon_skill_names(package.names),
        "敌方技能": _dict_or_empty(package.names["actors"].get("enemy_skills")),
        "怪物": _dict_or_empty(package.names["actors"].get("monsters")),
        "体质": _dict_or_empty(package.names["actors"].get("physiques")),
    }
    for bucket_name, values in buckets.items():
        seen: dict[str, str] = {}
        for stable_id, title in values.items():
            clean = str(title or "").strip()
            if not clean:
                errors.append(f"{bucket_name}展示名为空：{stable_id}")
                continue
            if clean in seen:
                errors.append(f"{bucket_name}展示名重复：{clean}（{seen[clean]} / {stable_id}）")
            seen[clean] = stable_id


def _insert_skin_snapshot(conn: sqlite3.Connection, package: WorldSkinPackage, switched_by: str) -> int:
    payload = {
        "active": _fetch_conn_one(conn, "SELECT * FROM world_skin_active WHERE id = 1"),
        "quality_labels": _fetch_conn_all(conn, "SELECT * FROM quality_labels ORDER BY quality_key"),
        "currency_labels": _fetch_conn_all(conn, "SELECT * FROM currency_labels ORDER BY currency_key"),
        "player_level_labels": _fetch_conn_all(conn, "SELECT * FROM player_level_labels ORDER BY level"),
    }
    cursor = conn.execute(
        """
        INSERT INTO world_skin_snapshots (skin_id, version, payload, created_by, created_at)
        VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (package.skin_id, package.version, json.dumps(payload, ensure_ascii=False), switched_by),
    )
    return int(cursor.lastrowid or 0)


def _apply_places(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    count = 0
    places = names["places"]
    city_names = {city_id: str(city["name"]) for city_id, city in places["cities"].items()}
    realm_names = {stable_id: str(row["name"]) for stable_id, row in places["realm"].items()}
    buyer_names = {stable_id: str(row["name"]) for stable_id, row in places["buyers"].items()}
    recycle_names = {stable_id: str(row["name"]) for stable_id, row in places["recycles"].items()}
    all_places = {**city_names, **realm_names, **buyer_names, **recycle_names}
    count += _safe_update_unique_names(conn, "world_locations", "location_id", "name", all_places)
    count += _safe_update_unique_names(conn, "trade_locations", "location_id", "name", city_names)
    count += _safe_update_unique_names(conn, "exploration_locations", "location_id", "name", {**city_names, **realm_names})
    count += _safe_update_unique_names(conn, "special_buyers", "location_id", "buyer_name", buyer_names)
    count += _safe_update_unique_names(conn, "recycle_locations", "location_id", "name", recycle_names)
    for location_id, title in all_places.items():
        count += conn.execute("UPDATE players SET location_name = ? WHERE location_id = ?", (title, location_id)).rowcount
        count += conn.execute(
            "UPDATE exploration_records SET location_name = ? WHERE location_id = ? AND claimed = 0",
            (title, location_id),
        ).rowcount
        count += conn.execute(
            "UPDATE wormholes SET location_name = ? WHERE location_id = ? AND status = '开启'",
            (title, location_id),
        ).rowcount
    for location_id, title in city_names.items():
        specialties = ",".join(str(value) for value in places["cities"][location_id]["trade_goods"].values())
        count += conn.execute(
            "UPDATE trade_locations SET specialties = ? WHERE location_id = ?",
            (specialties, location_id),
        ).rowcount
        count += conn.execute("UPDATE city_world_states SET location_name = ? WHERE location_id = ?", (title, location_id)).rowcount
        count += conn.execute("UPDATE trade_goods SET home_location = ? WHERE home_location_id = ?", (title, location_id)).rowcount
        count += conn.execute(
            """
            UPDATE treasure_maps
            SET city_name = ?
            WHERE city_id = ?
              AND status IN ('拍卖中', '可拾取', '宗主待领')
            """,
            (title, location_id),
        ).rowcount
    for location_id, title in buyer_names.items():
        count += conn.execute("UPDATE war_prep_states SET buyer_name = ? WHERE location_id = ?", (title, location_id)).rowcount
    return count


def _apply_world_items(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    item_names = {**_city_trade_goods(names), **_flatten_world_item_names(names["world_items"])}
    count = _safe_update_unique_names(conn, "item_defs", "item_id", "name", item_names)
    count += _sync_trade_item_skin_metadata(conn, names)
    count += _sync_world_item_skin_metadata(conn, names)
    return count


def _apply_ring_items(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    count = _safe_update_unique_names(conn, "ring_item_defs", "ring_item_id", "name", _ring_item_names(names))
    for item_id, title in names["weapons"]["skill_books"].items():
        count += conn.execute("UPDATE ring_item_defs SET name = ? WHERE ring_item_id = ?", (title, item_id)).rowcount
        count += conn.execute("UPDATE weapon_enchants SET name = ? WHERE enchant_id = ?", (title, item_id)).rowcount
    return count


def _sync_trade_item_skin_metadata(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    """同步纯经济特产的展示产地、说明和 effect 派生文本。"""

    count = 0
    for city_id, city in names["places"]["cities"].items():
        city_name = str(city["name"])
        for item_id, item_name in city["trade_goods"].items():
            row = conn.execute("SELECT effect, desc FROM item_defs WHERE item_id = ?", (item_id,)).fetchone()
            if not row:
                continue
            effect = _json_dict(row["effect"])
            effect["world_subtype"] = city_name
            effect["world_subtype_key"] = str(city_id)
            effect["home_location"] = city_name
            effect["home_location_id"] = str(city_id)
            desc = f"{item_name}：{city_name}流通的地方特产，只服务本界商路差价和地区供需，不从探险或秘境掉落。"
            count += conn.execute(
                """
                UPDATE item_defs
                SET category = '纯经济',
                    effect = ?,
                    desc = ?
                WHERE item_id = ?
                """,
                (json.dumps(effect, ensure_ascii=False), desc, item_id),
            ).rowcount
            count += conn.execute(
                "UPDATE trade_goods SET home_location = ? WHERE item_id = ?",
                (city_name, item_id),
            ).rowcount
    return count


def _sync_world_item_skin_metadata(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    """同步非纯经济世界物资说明，避免查看详情时露出默认名。"""

    count = 0
    item_names = _flatten_world_item_names(names["world_items"])
    for item_id, item_name in item_names.items():
        row = conn.execute("SELECT category, effect, desc FROM item_defs WHERE item_id = ?", (item_id,)).fetchone()
        if not row:
            continue
        effect = _json_dict(row["effect"])
        subtype = str(effect.get("world_subtype") or row["category"] or "").strip()
        old_desc = str(row["desc"] or "")
        if "：" in old_desc:
            old_desc = old_desc.split("：", 1)[1]
        desc = f"{item_name}：{old_desc or subtype}"
        count += conn.execute(
            """
            UPDATE item_defs
            SET desc = ?
            WHERE item_id = ?
            """,
            (desc, item_id),
        ).rowcount
    return count


def _apply_weapons(conn: sqlite3.Connection, names: dict[str, Any]) -> tuple[int, int]:
    weapon_count = 0
    skill_count = 0
    for weapon_id, title in _city_weapon_names(names).items():
        weapon_count += conn.execute("UPDATE weapon_defs SET name = ? WHERE weapon_def_id = ?", (title, weapon_id)).rowcount
        weapon_count += conn.execute(
            """
            UPDATE treasure_maps
            SET weapon_name = ?
            WHERE weapon_def_id = ?
              AND status IN ('拍卖中', '可拾取', '宗主待领')
            """,
            (title, weapon_id),
        ).rowcount
    for skill_id, title in _city_weapon_skill_names(names).items():
        skill_count += conn.execute("UPDATE weapon_skill_defs SET name = ? WHERE skill_id = ?", (title, skill_id)).rowcount
    for type_key, title in _dict_or_empty(names["weapons"].get("types")).items():
        weapon_count += conn.execute("UPDATE weapon_defs SET weapon_type = ? WHERE weapon_type_key = ?", (title, type_key)).rowcount
    for city_id, city in names["places"]["cities"].items():
        city_name = str(city["name"])
        weapon_count += conn.execute("UPDATE weapon_defs SET drop_location = ? WHERE drop_location_id = ?", (city_name, city_id)).rowcount
    return weapon_count, skill_count


def _apply_actors(conn: sqlite3.Connection, names: dict[str, Any]) -> tuple[int, int]:
    monster_count = 0
    physique_count = 0
    actors = names["actors"]
    for monster_id, title in actors["monsters"].items():
        monster_count += conn.execute("UPDATE monster_defs SET name = ? WHERE monster_id = ?", (title, monster_id)).rowcount
    for kind_key, title in actors["enemy_kinds"].items():
        monster_count += conn.execute("UPDATE monster_defs SET kind = ? WHERE kind_key = ?", (title, kind_key)).rowcount
    physique_count += _safe_update_unique_names(conn, "physique_defs", "physique_id", "name", actors["physiques"])
    return monster_count, physique_count


def _apply_system_labels(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    count = 0
    system = names["system"]
    for key, title in system["quality"].items():
        count += conn.execute("UPDATE quality_labels SET label = ? WHERE quality_key = ?", (title, key)).rowcount
    for key, title in system["currency"].items():
        count += conn.execute("UPDATE currency_labels SET label = ? WHERE currency_key = ?", (title, key)).rowcount
    for level, title in system["levels"].items():
        count += conn.execute("UPDATE player_level_labels SET label = ? WHERE level = ?", (title, int(level))).rowcount
    set_enemy_skill_label_overrides(_dict_or_empty(names["actors"].get("enemy_skills")))
    return count


def _apply_event_snapshots(conn: sqlite3.Connection, names: dict[str, Any]) -> int:
    count = 0
    wormhole_names = {**names["wormhole"]["bosses"], **names["wormhole"]["war_prep_bosses"]}
    flow_names = names["wormhole"]["flows"]
    affix_names = names["wormhole"]["war_prep_affixes"]
    rows = conn.execute("SELECT wormhole_id, result FROM wormholes WHERE status = '开启'").fetchall()
    for row in rows:
        meta = _json_dict(row["result"])
        updates: dict[str, Any] = {}
        boss_key = str(meta.get("boss_key") or "")
        if boss_key in wormhole_names:
            updates["boss_name"] = wormhole_names[boss_key]
        flow_key = str(meta.get("boss_flow_key") or "")
        if flow_key in flow_names:
            meta["boss_flow"] = flow_names[flow_key]
        affix_keys = meta.get("affix_keys")
        if isinstance(affix_keys, list):
            meta["affixes"] = [affix_names.get(str(key), str(key)) for key in affix_keys]
        if meta:
            updates["result"] = json.dumps(meta, ensure_ascii=False)
        if updates:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            count += conn.execute(
                f"UPDATE wormholes SET {assignments} WHERE wormhole_id = ?",
                (*updates.values(), row["wormhole_id"]),
            ).rowcount
    return count


def _refresh_runtime_skin_labels(conn: sqlite3.Connection) -> None:
    quality_rows = conn.execute("SELECT quality_key, label FROM quality_labels").fetchall()
    set_quality_label_overrides({row["quality_key"]: row["label"] for row in quality_rows})
    currency_rows = conn.execute("SELECT currency_key, label FROM currency_labels").fetchall()
    set_currency_label_overrides({row["currency_key"]: row["label"] for row in currency_rows})
    level_rows = conn.execute("SELECT level, label FROM player_level_labels").fetchall()
    set_player_level_label_overrides({row["level"]: row["label"] for row in level_rows})
    active = conn.execute("SELECT skin_id FROM world_skin_active WHERE id = 1").fetchone()
    if active:
        package = load_skin_package(str(active["skin_id"]))
        set_enemy_skill_label_overrides(_dict_or_empty(package.names["actors"].get("enemy_skills")))


def _location_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT location_id, name, category, terrain, x, y, desc
        FROM world_locations
        ORDER BY category, name
        """,
    )
    return [
        _entry(
            "NPC地点",
            row.get("category"),
            row.get("location_id"),
            row.get("name"),
            f"坐标({row.get('x', 0)},{row.get('y', 0)})｜地形：{row.get('terrain', '')}｜{row.get('desc', '')}",
            row.get("terrain"),
        )
        for row in rows
    ]


def _trade_location_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT location_id, name, x, y, specialties
        FROM trade_locations
        ORDER BY name
        """,
    )
    return [
        _entry(
            "商路城池",
            "纯经济特产",
            row.get("location_id"),
            row.get("name"),
            f"坐标({row.get('x', 0)},{row.get('y', 0)})｜特产：{row.get('specialties', '')}",
            row.get("specialties"),
        )
        for row in rows
    ]


def _exploration_location_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT location_id, name, x, y, recommended_level, min_level, max_level, desc
        FROM exploration_locations
        ORDER BY recommended_level, name
        """,
    )
    return [
        _entry(
            "探险地点",
            "探险",
            row.get("location_id"),
            row.get("name"),
            (
                f"坐标({row.get('x', 0)},{row.get('y', 0)})｜"
                f"推荐{player_level_label(row.get('recommended_level', 1))}｜"
                f"怪物{player_level_label(row.get('min_level', 1))}-{player_level_label(row.get('max_level', 1))}｜"
                f"{row.get('desc', '')}"
            ),
            row.get("desc"),
        )
        for row in rows
    ]


def _special_buyer_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT location_id, buyer_name, item_ids, price_factor, x, y
        FROM special_buyers
        ORDER BY buyer_name
        """,
    )
    return [
        _entry(
            "特殊收购点",
            "战备回收",
            row.get("location_id"),
            row.get("buyer_name"),
            f"坐标({row.get('x', 0)},{row.get('y', 0)})｜倍率：{row.get('price_factor', 1)}｜收购物：{row.get('item_ids', '')}",
            row.get("item_ids"),
        )
        for row in rows
    ]


def _recycle_location_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT location_id, name, recycle_type, price_factor, x, y, desc
        FROM recycle_locations
        ORDER BY recycle_type, name
        """,
    )
    return [
        _entry(
            "回收点",
            row.get("recycle_type"),
            row.get("location_id"),
            row.get("name"),
            f"坐标({row.get('x', 0)},{row.get('y', 0)})｜倍率：{row.get('price_factor', 1)}｜{row.get('desc', '')}",
            row.get("recycle_type"),
        )
        for row in rows
    ]


def _item_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT item_id, name, category, quality, desc
        FROM item_defs
        ORDER BY category, name
        """,
    )
    return [
        _entry(
            "世界物品",
            row.get("category"),
            row.get("item_id"),
            row.get("name"),
            f"分类：{row.get('category', '')}｜品质：{quality_label(row.get('quality'))}｜{row.get('desc', '')}",
            row.get("quality"),
        )
        for row in rows
    ]


def _ring_item_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT ring_item_id, name, category, quality, desc
        FROM ring_item_defs
        ORDER BY category, name
        """,
    )
    return [
        _entry(
            "纳戒物品",
            row.get("category"),
            row.get("ring_item_id"),
            row.get("name"),
            f"分类：{row.get('category', '')}｜品质：{quality_label(row.get('quality'))}｜{row.get('desc', '')}",
            row.get("quality"),
        )
        for row in rows
    ]


def _weapon_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT w.weapon_def_id, w.name, w.weapon_type, w.weapon_type_key, w.drop_location, s.name AS skill_name
        FROM weapon_defs AS w
        LEFT JOIN weapon_skill_defs AS s ON s.skill_id = w.skill_id
        ORDER BY w.weapon_type, w.name
        """,
    )
    return [
        _entry(
            "武器",
            row.get("weapon_type"),
            row.get("weapon_def_id"),
            row.get("name"),
            f"类型：{row.get('weapon_type', '')}｜规则键：{row.get('weapon_type_key', '')}｜产地：{row.get('drop_location', '')}｜自带技能：{row.get('skill_name', '')}",
            row.get("drop_location"),
            row.get("skill_name"),
        )
        for row in rows
    ]


def _weapon_skill_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT skill_id, name, effect_desc
        FROM weapon_skill_defs
        ORDER BY name
        """,
    )
    return [
        _entry("武器技能", "自带技能", row.get("skill_id"), row.get("name"), str(row.get("effect_desc", "")))
        for row in rows
    ]


def _weapon_enchant_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT enchant_id, name, effect
        FROM weapon_enchants
        ORDER BY name
        """,
    )
    return [
        _entry("技能书附魔", "附魔", row.get("enchant_id"), row.get("name"), f"效果：{row.get('effect', '')}")
        for row in rows
    ]


def _monster_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT monster_id, name, kind, kind_key, level, drop_item_id
        FROM monster_defs
        ORDER BY level, name
        """,
    )
    return [
        _entry(
            "怪物",
            row.get("kind"),
            row.get("monster_id"),
            row.get("name"),
            f"类型：{row.get('kind', '')}｜规则键：{row.get('kind_key', '')}｜等级：{player_level_label(row.get('level', 1))}｜偏向掉落：{row.get('drop_item_id', '')}",
            row.get("drop_item_id"),
        )
        for row in rows
    ]


def _physique_entries(database: Any) -> list[WorldSkinEntry]:
    rows = _fetch_all(
        database,
        """
        SELECT physique_id, name, grade, kind, level, desc
        FROM physique_defs
        ORDER BY level, physique_value, name
        """,
    )
    return [
        _entry(
            "体质",
            row.get("grade") or row.get("kind"),
            row.get("physique_id"),
            row.get("name"),
            f"阶位：{row.get('grade', '')}｜流派：{row.get('kind', '')}｜等级要求：{player_level_label(row.get('level', 1))}｜{row.get('desc', '')}",
            row.get("kind"),
        )
        for row in rows
    ]


def _quality_entries(database: Any = db) -> list[WorldSkinEntry]:
    labels = {
        str(row.get("quality_key") or ""): str(row.get("label") or "")
        for row in _fetch_all(database, "SELECT quality_key, label FROM quality_labels")
    }
    return [
        _entry(
            "品质",
            "显示名",
            key,
            labels.get(key) or quality_label(key),
            f"稳定键：{key}｜倍率：{data.get('factor')}｜排序：{data.get('rank')}｜掉落权重：{data.get('drop_weight')}",
        )
        for key, data in QUALITY_DEFS.items()
    ]


def _currency_entries(database: Any = db) -> list[WorldSkinEntry]:
    rows = {
        str(row.get("currency_key") or ""): dict(row)
        for row in _fetch_all(database, "SELECT currency_key, label, desc FROM currency_labels")
    }
    return [
        _entry(
            "货币",
            "显示名",
            key,
            str(rows.get(key, {}).get("label") or currency_name(key)),
            f"稳定键：{key}｜{rows.get(key, {}).get('desc') or data.get('desc', '')}",
        )
        for key, data in CURRENCY_DEFS.items()
    ]


def _player_level_entries(database: Any = db) -> list[WorldSkinEntry]:
    rows = {
        int(row.get("level") or 0): dict(row)
        for row in _fetch_all(database, "SELECT level, label, desc FROM player_level_labels")
    }
    return [
        _entry(
            "等级显示",
            "显示名",
            str(level),
            str(rows.get(level, {}).get("label") or player_level_label(level)),
            f"稳定数字：{level}｜{rows.get(level, {}).get('desc') or data.get('desc', '')}",
        )
        for level, data in PLAYER_LEVEL_DEFS.items()
    ]


def _entry(
    kind: object,
    group: object,
    stable_id: object,
    title: object,
    summary: object,
    *keywords: object,
) -> WorldSkinEntry:
    clean_title = str(title or stable_id or "").strip()
    clean_id = str(stable_id or clean_title).strip()
    return WorldSkinEntry(
        kind=str(kind or "世界").strip(),
        group=str(group or "未分组").strip(),
        stable_id=clean_id,
        title=clean_title,
        summary=str(summary or "").strip(),
        keywords=_keywords(clean_id, clean_title, *keywords),
    )


def _keywords(*values: object) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            result.append(text)
            for part in text.replace("，", ",").replace("、", ",").split(","):
                part = part.strip()
                if part:
                    result.append(part)
    return tuple(dict.fromkeys(result))


def _dedupe_entries(entries: list[WorldSkinEntry]) -> list[WorldSkinEntry]:
    result: list[WorldSkinEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = (entry.kind, entry.group, entry.stable_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _safe_skin_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "-", text).strip(".-")
    return safe or DEFAULT_SKIN_ID


def _static_file_exists(public_path: str) -> bool:
    return _static_file_path(public_path).exists()


def _static_file_path(public_path: str) -> Path:
    relative = str(public_path or "").lstrip("/").split("/")
    return SERVER_ROOT.joinpath(*relative)


def _best_help_map_path_for_skin(skin_id: str) -> str:
    skin = _safe_skin_id(skin_id)
    if not skin:
        return ""

    candidates: list[tuple[int, int, str]] = []
    for order, ext in enumerate(SKIN_HELP_MAP_EXTENSIONS):
        public_path = f"{SKIN_HELP_MAP_DIR}/{skin}.{ext}"
        file_path = _static_file_path(public_path)
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        candidates.append((order, size, public_path))

    if not candidates:
        return ""
    return min(candidates)[2]


def _definition_from_entry(entry: WorldSkinEntry, database: Any) -> WorldSkinDefinition | None:
    return _definition_from_key(entry.kind, entry.group, entry.stable_id, entry.title, database)


def _definition_from_key(
    kind: str,
    group: str,
    stable_id: str,
    title: str,
    database: Any,
) -> WorldSkinDefinition | None:
    clean_kind = str(kind or "").strip()
    clean_id = str(stable_id or "").strip()
    if not clean_kind or not clean_id:
        return None
    token = _active_skin_token(database)
    cache_key = (token, clean_kind, clean_id)
    if cache_key in _DEFINITION_CACHE:
        return _copy_definition(_DEFINITION_CACHE[cache_key])

    row = _definition_row(clean_kind, clean_id, database)
    if not row:
        _DEFINITION_CACHE[cache_key] = None
        return None
    clean_title = str(title or row.get("name") or row.get("label") or clean_id).strip()
    definition = WorldSkinDefinition(
        clean_kind,
        str(group or "").strip(),
        clean_id,
        clean_title,
        _row_with_skin_title(row, clean_title),
    )
    _DEFINITION_CACHE[cache_key] = definition
    return _copy_definition(definition)


def _copy_definition(definition: WorldSkinDefinition | None) -> WorldSkinDefinition | None:
    if definition is None:
        return None
    return WorldSkinDefinition(
        definition.kind,
        definition.group,
        definition.stable_id,
        definition.title,
        dict(definition.row),
    )


def _definition_row(kind: str, stable_id: str, database: Any) -> dict[str, Any] | None:
    table_info = WORLD_DEFINITION_TABLES.get(str(kind or "").strip())
    if not table_info:
        return None
    table, key = table_info
    return _fetch_one(database, f"SELECT * FROM {table} WHERE {key} = ?", (str(stable_id or "").strip(),))


def _row_with_skin_title(row: dict[str, Any], title: str) -> dict[str, Any]:
    result = dict(row)
    clean_title = str(title or "").strip()
    if clean_title and "name" in result:
        result["name"] = clean_title
    elif clean_title and "label" in result:
        result["label"] = clean_title
    return result


def _lookup_text(value: object) -> str:
    return str(value or "").strip().casefold()


def _fetch_one(database: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    try:
        row = database.fetch_one(sql, params)
    except Exception:
        return None
    return dict(row) if row else None


def _fetch_all(database: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return list(database.fetch_all(sql, params))
    except Exception:
        return []


def _dict_at(source: Any, key: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(source, dict):
        errors.append(f"配置段不是字典：{key}")
        return {}
    value = source.get(key)
    if not isinstance(value, dict):
        errors.append(f"缺少配置段：{key}")
        return {}
    return value


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _require_count(errors: list[str], label: str, value: Any, expected: int) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} 必须是字典")
        return
    _require_exact(errors, label, len(value), expected)


def _require_exact(errors: list[str], label: str, actual: int, expected: int) -> None:
    if actual != expected:
        errors.append(f"{label} 数量错误：{actual}，应为 {expected}")


def _require_keys(errors: list[str], label: str, value: dict[str, Any], expected: set[str]) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label} 缺少：{', '.join(missing)}")
    if extra:
        errors.append(f"{label} 多余：{', '.join(extra)}")


def _require_text(errors: list[str], label: str, value: Any) -> None:
    if not str(value or "").strip():
        errors.append(f"{label} 不能为空")


def _column_values(database: Any, table: str, column: str, where: str = "") -> set[str]:
    clause = f" WHERE {where}" if where else ""
    rows = _fetch_all(database, f"SELECT DISTINCT {column} AS value FROM {table}{clause}")
    return {str(row.get("value") or "").strip() for row in rows if str(row.get("value") or "").strip()}


def _place_names(names: dict[str, Any]) -> dict[str, str]:
    places = names["places"]
    result: dict[str, str] = {}
    for group in ("cities", "realm", "buyers", "recycles"):
        for stable_id, row in places[group].items():
            result[stable_id] = str(row["name"])
    return result


def _city_trade_goods(names: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for city in names["places"]["cities"].values():
        result.update({str(key): str(value) for key, value in city["trade_goods"].items()})
    return result


def _city_weapon_names(names: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for city in names["places"]["cities"].values():
        for weapon_id, weapon in city["weapons"].items():
            result[str(weapon_id)] = str(weapon["name"])
    return result


def _city_weapon_skill_names(names: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for city in names["places"]["cities"].values():
        for weapon in city["weapons"].values():
            innate = weapon["innate_skill"]
            result[str(innate["skill_id"])] = str(innate["name"])
    return result


def _flatten_world_item_names(world_items: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for category in world_items.values():
        if not isinstance(category, dict):
            continue
        for subtype in category.values():
            if isinstance(subtype, dict):
                result.update({str(key): str(value) for key, value in subtype.items()})
    return result


def _ring_item_names(names: dict[str, Any]) -> dict[str, str]:
    ring = names["ring"]
    result: dict[str, str] = {}
    for group in ("recovery", "gems", "special"):
        result.update({str(key): str(value) for key, value in ring[group].items()})
    return result


def _secret_realm_environment_names(secret_realm: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for env_id, row in _dict_or_empty(secret_realm.get("environments")).items():
        if isinstance(row, dict):
            result[str(env_id)] = str(row.get("name") or "")
    return result


def _safe_update_unique_names(
    conn: sqlite3.Connection,
    table: str,
    id_column: str,
    name_column: str,
    values: dict[str, Any],
) -> int:
    """两阶段更新唯一名称列，避免换皮时新旧名称互相占位。"""

    clean_values = {str(stable_id): str(title) for stable_id, title in values.items()}
    if not clean_values:
        return 0
    marker = f"__world_skin_swap__{table}__"
    count = 0
    for stable_id in clean_values:
        count += conn.execute(
            f"UPDATE {table} SET {name_column} = ? WHERE {id_column} = ?",
            (f"{marker}{stable_id}", stable_id),
        ).rowcount
    for stable_id, title in clean_values.items():
        count += conn.execute(
            f"UPDATE {table} SET {name_column} = ? WHERE {id_column} = ?",
            (title, stable_id),
        ).rowcount
    return count


def _fetch_conn_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetch_conn_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
