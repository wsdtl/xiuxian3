# 世界皮肤包元数据文件。
# 这是“受限 Python 数据文件”，不是可执行插件：加载器只会读取 PACKAGE 这个字面量字典。
# 允许修改：display_name、version、author、desc 这类说明文字。
# 不要修改：package_format、schema_version、skin_id、files、entry_count 等校验字段，除非同步改加载器和校验逻辑。
# 不要添加 import、函数调用、变量拼接或运行时代码；后续加载必须继续使用 ast.literal_eval 安全读取。

PACKAGE = {
    "package_format": 4,
    "schema_version": 2026062601,
    "skin_id": "perfect_world",
    "display_name": "完美世界",
    "version": "2026.06.24-official.3",
    "author": "xiuxianserver",
    "desc": "大荒、石村、虚神界、补天阁、百断山、十凶宝术、至尊骨、帝关和仙古体系正式皮肤；粒度不足处用骨文与宝具设定缝合。等级显示改为完整修行路，从搬血开门推进到祭道之上，不使用数值。",
    "created_at": "2026-06-24",
    "files": ["names.py"],
    "entry_count": 653,
    "database_source_count": 568,
    "constant_count": 85,
    "format_notes": {
        "python_data": "Restricted Python literal data package; parse with ast.parse + ast.literal_eval, " "never import.",
        "places": "places 按上级实体组织地点；cities 下直接维护城名、用途、特产和武器",
        "city_weapons": "places.cities.*.weapons 中每个武器同时维护 name 和 innate_skill.name；skill_id 是稳定键，不能改",
        "skill_books": "weapons.skill_books 同步 ring_item_defs.name 和 weapon_enchants.name",
        "special_ring_items": "ring.special 只放开孔器、洗髓液、淬锋丹",
        "city_hierarchy": "places.cities contains city name, roles, trade_goods, and weapons as one " "upper-level entity.",
    },
}
