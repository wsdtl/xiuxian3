# 世界皮肤包元数据文件。
# 这是“受限 Python 数据文件”，不是可执行插件：加载器只会读取 PACKAGE 这个字面量字典。
# 允许修改：display_name、version、author、desc 这类说明文字。
# 不要修改：package_format、schema_version、skin_id、files、entry_count 等校验字段，除非同步改加载器和校验逻辑。
# 不要添加 import、函数调用、变量拼接或运行时代码；后续加载必须继续使用 ast.literal_eval 安全读取。

PACKAGE = {
    # 皮肤包格式版本。当前 v4 表示 names.py 使用 Python 字面量，并且城池下合并了特产和武器。
    "package_format": 4,
    # 结构版本号。用于判断配置结构是否和当前代码约定一致，不是玩家可见版本。
    "schema_version": 2026062601,
    # 包唯一 ID。目录名、切换命令、回滚记录都会用它；上线后不要随便改。
    "skin_id": "default",
    # 玩家/管理员看到的包名，可以按风格改。
    "display_name": "默认修仙界",
    # 包内容版本，只用于人工审计和升级记录。
    "version": "2026.06.24-test.3",
    # 作者或维护者说明。
    "author": "xiuxianserver",
    # 包用途说明。建议写清楚这是正式包、基准包还是临时包。
    "desc": "当前修仙界展示名镜像，用作基准包和回滚校验包。",
    # 创建日期，仅作记录。
    "created_at": "2026-06-24",
    # 本包实际参与加载的数据文件。目前只允许 names.py。
    "files": ["names.py"],
    # 下面三个数量用于校验是否漏项：正常换皮只改名字，不改这些数字。
    "entry_count": 653,
    "database_source_count": 568,
    "constant_count": 85,
    # 格式说明给人看，也给审计时快速确认边界；业务代码不应该依赖这些中文说明。
    "format_notes": {
        "python_data": "Restricted Python literal data package; parse with ast.parse + ast.literal_eval, never import.",
        "places": "places 按上级实体组织地点；cities 下直接维护城名、用途、特产和武器",
        "city_weapons": "places.cities.*.weapons 中每个武器同时维护 name 和 innate_skill.name；skill_id 是稳定键，不能改",
        "skill_books": "weapons.skill_books 同步 ring_item_defs.name 和 weapon_enchants.name",
        "special_ring_items": "ring.special 只放开孔器、洗髓液、淬锋丹",
        "city_hierarchy": "places.cities contains city name, roles, trade_goods, and weapons as one upper-level entity.",
    },
}
