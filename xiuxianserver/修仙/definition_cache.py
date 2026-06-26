"""修仙定义表缓存。

只缓存“定义/展示资料”：物品模板、纳戒物品模板、武器模板、地点定义、
跑商商品归属、怪物模板等。这些数据只会在启动种子或世界皮肤切换时变化。

不要在这里缓存：
- `players`、背包、纳戒、装备、银行、探险记录等玩家实时状态。
- `trade_heat`、`trade_prices`、购买锁等动态经济状态。
- 任何结算中会被本次命令修改的数据。

所有公开函数都返回拷贝，调用方可以安全地临时增删字段，不会污染缓存本体。
"""

from __future__ import annotations

import json
from threading import RLock
from typing import Any, Iterable

from .runtime_cache import database_cache_key, register_runtime_cache


_LOCK = RLock()
_CACHES: dict[str, "_DefinitionCache"] = {}


def clear_definition_cache() -> None:
    """清理所有定义表缓存。

    世界皮肤切换、数据库启动重放当前皮肤、定义表种子刷新后都应调用。
    """

    with _LOCK:
        _CACHES.clear()


def item_def_by_id(database: Any, item_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取背包物品定义。"""

    return _cache(database).item_by_id(str(item_id or "").strip())


def item_def_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取背包物品定义。"""

    return _cache(database).item_by_name(str(name or "").strip())


def ring_item_def_by_id(database: Any, item_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取纳戒物品定义。"""

    return _cache(database).ring_item_by_id(str(item_id or "").strip())


def ring_item_def_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取纳戒物品定义。"""

    return _cache(database).ring_item_by_name(str(name or "").strip())


def weapon_def_by_id(database: Any, weapon_def_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取武器模板。"""

    return _cache(database).weapon_by_id(str(weapon_def_id or "").strip())


def weapon_def_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取武器模板。"""

    return _cache(database).weapon_by_name(str(name or "").strip())


def all_weapon_defs(database: Any) -> list[dict[str, Any]]:
    """读取全部武器模板。"""

    return _copy_rows(_cache(database).weapons())


def weapon_skill_def_by_id(database: Any, skill_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取武器自带技能模板。"""

    return _cache(database).weapon_skill_by_id(str(skill_id or "").strip())


def weapon_skill_def_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取武器自带技能模板。"""

    return _cache(database).weapon_skill_by_name(str(name or "").strip())


def all_weapon_skill_defs(database: Any) -> list[dict[str, Any]]:
    """读取全部武器自带技能模板。"""

    return _copy_rows(_cache(database).weapon_skills())


def world_location_by_id(database: Any, location_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取 NPC 地点。"""

    return _cache(database).world_location_by_id(str(location_id or "").strip())


def world_location_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取 NPC 地点。"""

    return _cache(database).world_location_by_name(str(name or "").strip())


def world_location_by_point(database: Any, x: int, y: int) -> dict[str, Any] | None:
    """按坐标读取 NPC 地点。"""

    return _cache(database).world_location_by_point(int(x), int(y))


def all_world_locations(database: Any) -> list[dict[str, Any]]:
    """读取全部 NPC 地点定义。"""

    return _copy_rows(_cache(database).world_locations())


def exploration_location_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取探险地点。"""

    return _cache(database).exploration_location_by_name(str(name or "").strip())


def exploration_location_by_point(database: Any, x: int, y: int) -> dict[str, Any] | None:
    """按坐标读取探险地点。"""

    return _cache(database).exploration_location_by_point(int(x), int(y))


def all_exploration_locations(database: Any) -> list[dict[str, Any]]:
    """读取全部探险地点定义。"""

    return _copy_rows(_cache(database).exploration_locations())


def trade_location_by_id(database: Any, location_id: str) -> dict[str, Any] | None:
    """按稳定 ID 读取跑商城池。"""

    return _cache(database).trade_location_by_id(str(location_id or "").strip())


def trade_location_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取跑商城池。"""

    return _cache(database).trade_location_by_name(str(name or "").strip())


def trade_location_by_point(database: Any, x: int, y: int) -> dict[str, Any] | None:
    """按坐标读取跑商城池。"""

    return _cache(database).trade_location_by_point(int(x), int(y))


def all_trade_locations(database: Any) -> list[dict[str, Any]]:
    """读取全部跑商城池定义。"""

    return _copy_rows(_cache(database).trade_locations())


def trade_goods_by_item_id(database: Any, item_id: str) -> dict[str, Any] | None:
    """读取某个跑商商品的产地关系。"""

    return _cache(database).trade_good_by_item_id(str(item_id or "").strip())


def location_goods(database: Any, location_id: str) -> list[dict[str, Any]]:
    """读取某城池可购买的商品定义。"""

    return _cache(database).location_goods(str(location_id or "").strip())


def special_buyer_by_name(database: Any, name: str) -> dict[str, Any] | None:
    """按当前展示名读取特殊收购点。"""

    return _cache(database).special_buyer_by_name(str(name or "").strip())


def special_buyer_by_point(database: Any, x: int, y: int) -> dict[str, Any] | None:
    """按坐标读取特殊收购点。"""

    return _cache(database).special_buyer_by_point(int(x), int(y))


def all_special_buyers(database: Any) -> list[dict[str, Any]]:
    """按种子顺序读取全部特殊收购点。"""

    return _copy_rows(_cache(database).special_buyers())


def recycle_location_by_type(database: Any, recycle_type: str) -> dict[str, Any] | None:
    """按回收类型读取第一个回收建筑。"""

    return _cache(database).recycle_location_by_type(str(recycle_type or "").strip())


def recycle_location_by_name(database: Any, name: str, recycle_type: str = "") -> dict[str, Any] | None:
    """按名称读取回收建筑，可附带类型过滤。"""

    return _cache(database).recycle_location_by_name(str(name or "").strip(), str(recycle_type or "").strip())


def recycle_location_by_point(database: Any, x: int, y: int) -> dict[str, Any] | None:
    """按坐标读取回收建筑。"""

    return _cache(database).recycle_location_by_point(int(x), int(y))


def all_recycle_locations(database: Any) -> list[dict[str, Any]]:
    """读取全部回收建筑。"""

    return _copy_rows(_cache(database).recycle_locations())


def all_monster_defs(database: Any) -> list[dict[str, Any]]:
    """读取全部怪物模板。"""

    return _copy_rows(_cache(database).monsters())


def monster_defs_by_level(database: Any, min_level: int, max_level: int) -> list[dict[str, Any]]:
    """按等级区间读取怪物模板。"""

    lower = int(min_level)
    upper = int(max_level)
    rows = [
        row
        for row in _cache(database).monsters()
        if lower <= int(row.get("level", 0) or 0) <= upper
    ]
    return _copy_rows(rows)


def first_monster_def(database: Any) -> dict[str, Any] | None:
    """读取等级最低的怪物模板。"""

    rows = _cache(database).monsters()
    return _copy_row(rows[0]) if rows else None


def world_item_defs_by_categories(database: Any, category_keys: Iterable[str]) -> list[dict[str, Any]]:
    """按世界物资大类读取物品定义。"""

    keys = {str(key) for key in category_keys}
    return _copy_rows(
        row
        for row in _cache(database).items()
        if _world_category_key(row) in keys
    )


def ring_item_defs_by_categories(
    database: Any,
    category_keys: Iterable[str],
    *,
    exclude_ids: Iterable[str] = (),
    exclude_prefixes: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """按纳戒分类读取物品定义，可排除专属掉落或极版前缀。"""

    keys = {str(key) for key in category_keys}
    excluded = {str(item_id) for item_id in exclude_ids}
    prefixes = tuple(str(prefix) for prefix in exclude_prefixes)
    rows = []
    for row in _cache(database).ring_items():
        item_id = str(row.get("ring_item_id") or "")
        if item_id in excluded or item_id.startswith(prefixes):
            continue
        if str(row.get("category_key") or "") in keys:
            rows.append(row)
    return _copy_rows(rows)


class _DefinitionCache:
    """单个数据库实例的定义表缓存。

    缓存按表懒加载，只有业务第一次访问某类定义时才读库。读出后只保存
    `dict`，避免把 sqlite row 对象暴露给调用方。
    """

    def __init__(self, database: Any) -> None:
        self.database = database
        self._items: list[dict[str, Any]] | None = None
        self._ring_items: list[dict[str, Any]] | None = None
        self._weapons: list[dict[str, Any]] | None = None
        self._weapon_skills: list[dict[str, Any]] | None = None
        self._world_locations: list[dict[str, Any]] | None = None
        self._exploration_locations: list[dict[str, Any]] | None = None
        self._trade_locations: list[dict[str, Any]] | None = None
        self._trade_goods: list[dict[str, Any]] | None = None
        self._special_buyers: list[dict[str, Any]] | None = None
        self._recycle_locations: list[dict[str, Any]] | None = None
        self._monsters: list[dict[str, Any]] | None = None
        # 表数据和索引分开懒加载：列表用于全量遍历，索引用于按 ID/名称/坐标
        # 高频读取。世界皮肤切换会丢弃整个 _DefinitionCache 对象，因此这里
        # 不需要逐项失效。
        self._indexes: dict[str, dict[str, dict[str, Any]]] = {}
        self._point_indexes: dict[str, dict[tuple[int, int], dict[str, Any]]] = {}

    def items(self) -> list[dict[str, Any]]:
        if self._items is None:
            self._items = self.database.fetch_all("SELECT * FROM item_defs ORDER BY item_id")
        return self._items

    def item_by_id(self, item_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("items:item_id", self.items(), "item_id").get(item_id))

    def item_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("items:name", self.items(), "name").get(name))

    def ring_items(self) -> list[dict[str, Any]]:
        if self._ring_items is None:
            self._ring_items = self.database.fetch_all("SELECT * FROM ring_item_defs ORDER BY ring_item_id")
        return self._ring_items

    def ring_item_by_id(self, item_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("ring_items:ring_item_id", self.ring_items(), "ring_item_id").get(item_id))

    def ring_item_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("ring_items:name", self.ring_items(), "name").get(name))

    def weapons(self) -> list[dict[str, Any]]:
        if self._weapons is None:
            self._weapons = self.database.fetch_all("SELECT * FROM weapon_defs ORDER BY weapon_def_id")
        return self._weapons

    def weapon_by_id(self, weapon_def_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("weapons:weapon_def_id", self.weapons(), "weapon_def_id").get(weapon_def_id))

    def weapon_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("weapons:name", self.weapons(), "name").get(name))

    def weapon_skills(self) -> list[dict[str, Any]]:
        if self._weapon_skills is None:
            self._weapon_skills = self.database.fetch_all("SELECT * FROM weapon_skill_defs ORDER BY interval, skill_id")
        return self._weapon_skills

    def weapon_skill_by_id(self, skill_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("weapon_skills:skill_id", self.weapon_skills(), "skill_id").get(skill_id))

    def weapon_skill_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("weapon_skills:name", self.weapon_skills(), "name").get(name))

    def world_locations(self) -> list[dict[str, Any]]:
        if self._world_locations is None:
            self._world_locations = [
                _normalize_point(row)
                for row in self.database.fetch_all("SELECT * FROM world_locations ORDER BY name")
            ]
        return self._world_locations

    def world_location_by_id(self, location_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("world_locations:location_id", self.world_locations(), "location_id").get(location_id))

    def world_location_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("world_locations:name", self.world_locations(), "name").get(name))

    def world_location_by_point(self, x: int, y: int) -> dict[str, Any] | None:
        return _copy_row(self._point_index("world_locations:point", self.world_locations()).get((x, y)))

    def exploration_locations(self) -> list[dict[str, Any]]:
        if self._exploration_locations is None:
            rows = self.database.fetch_all(
                """
                SELECT e.*, COALESCE(w.terrain, '') AS terrain
                FROM exploration_locations AS e
                LEFT JOIN world_locations AS w ON w.location_id = e.location_id
                ORDER BY e.recommended_level, e.name
                """
            )
            self._exploration_locations = [_normalize_point(row) for row in rows]
        return self._exploration_locations

    def exploration_location_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("exploration_locations:name", self.exploration_locations(), "name").get(name))

    def exploration_location_by_point(self, x: int, y: int) -> dict[str, Any] | None:
        return _copy_row(self._point_index("exploration_locations:point", self.exploration_locations()).get((x, y)))

    def trade_locations(self) -> list[dict[str, Any]]:
        if self._trade_locations is None:
            rows = self.database.fetch_all(
                """
                SELECT t.*, COALESCE(w.terrain, '') AS terrain
                FROM trade_locations AS t
                LEFT JOIN world_locations AS w ON w.location_id = t.location_id
                ORDER BY t.name
                """
            )
            self._trade_locations = [_normalize_point(row) for row in rows]
        return self._trade_locations

    def trade_location_by_id(self, location_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("trade_locations:location_id", self.trade_locations(), "location_id").get(location_id))

    def trade_location_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("trade_locations:name", self.trade_locations(), "name").get(name))

    def trade_location_by_point(self, x: int, y: int) -> dict[str, Any] | None:
        return _copy_row(self._point_index("trade_locations:point", self.trade_locations()).get((x, y)))

    def trade_goods(self) -> list[dict[str, Any]]:
        if self._trade_goods is None:
            self._trade_goods = self.database.fetch_all("SELECT * FROM trade_goods ORDER BY item_id")
        return self._trade_goods

    def trade_good_by_item_id(self, item_id: str) -> dict[str, Any] | None:
        return _copy_row(self._index("trade_goods:item_id", self.trade_goods(), "item_id").get(item_id))

    def location_goods(self, location_id: str) -> list[dict[str, Any]]:
        item_rows = []
        for good in self.trade_goods():
            if str(good.get("home_location_id") or "") != location_id:
                continue
            item = self.item_by_id(str(good.get("item_id") or ""))
            if item and int(item.get("tradeable", 0) or 0):
                item_rows.append(item)
        return sorted(item_rows, key=lambda row: (int(row.get("base_price", 0) or 0), str(row.get("name") or "")))

    def special_buyers(self) -> list[dict[str, Any]]:
        if self._special_buyers is None:
            rows = self.database.fetch_all("SELECT rowid, * FROM special_buyers ORDER BY rowid")
            self._special_buyers = [_normalize_point(row) for row in rows]
        return self._special_buyers

    def special_buyer_by_name(self, name: str) -> dict[str, Any] | None:
        return _copy_row(self._index("special_buyers:buyer_name", self.special_buyers(), "buyer_name").get(name))

    def special_buyer_by_point(self, x: int, y: int) -> dict[str, Any] | None:
        return _copy_row(self._point_index("special_buyers:point", self.special_buyers()).get((x, y)))

    def recycle_locations(self) -> list[dict[str, Any]]:
        if self._recycle_locations is None:
            rows = self.database.fetch_all("SELECT rowid, * FROM recycle_locations ORDER BY rowid")
            self._recycle_locations = [_normalize_point(row) for row in rows]
        return self._recycle_locations

    def recycle_location_by_type(self, recycle_type: str) -> dict[str, Any] | None:
        for row in self.recycle_locations():
            if str(row.get("recycle_type") or "") == recycle_type:
                return _copy_row(row)
        return None

    def recycle_location_by_name(self, name: str, recycle_type: str = "") -> dict[str, Any] | None:
        for row in self.recycle_locations():
            if str(row.get("name") or "") != name:
                continue
            if recycle_type and str(row.get("recycle_type") or "") != recycle_type:
                continue
            return _copy_row(row)
        return None

    def recycle_location_by_point(self, x: int, y: int) -> dict[str, Any] | None:
        return _copy_row(self._point_index("recycle_locations:point", self.recycle_locations()).get((x, y)))

    def monsters(self) -> list[dict[str, Any]]:
        if self._monsters is None:
            self._monsters = self.database.fetch_all("SELECT * FROM monster_defs ORDER BY level, monster_id")
        return self._monsters

    def _index(self, cache_key: str, rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        """读取某张定义表的字符串索引，首次访问时构建。"""

        cached = self._indexes.get(cache_key)
        if cached is None:
            cached = {str(row.get(key) or ""): row for row in rows}
            self._indexes[cache_key] = cached
        return cached

    def _point_index(self, cache_key: str, rows: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
        """读取某张定义表的坐标索引，首次访问时构建。"""

        cached = self._point_indexes.get(cache_key)
        if cached is None:
            cached = {(int(row.get("x", 0) or 0), int(row.get("y", 0) or 0)): row for row in rows}
            self._point_indexes[cache_key] = cached
        return cached


def _cache(database: Any) -> _DefinitionCache:
    key = database_cache_key(database)
    with _LOCK:
        cached = _CACHES.get(key)
        if cached is None:
            cached = _DefinitionCache(database)
            _CACHES[key] = cached
        return cached


def _copy_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _copy_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _normalize_point(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["x"] = int(item.get("x", 0) or 0)
    item["y"] = int(item.get("y", 0) or 0)
    return item


def _world_category_key(row: dict[str, Any]) -> str:
    try:
        effect = json.loads(str(row.get("effect") or "{}"))
    except json.JSONDecodeError:
        return ""
    return str(effect.get("world_category_key") or "")


register_runtime_cache("definition_tables", clear_definition_cache)
