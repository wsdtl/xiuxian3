# 修仙模块架构和扩展教程

本文按当前代码整理，冲突时以代码为准。`src/修仙` 是一个 `APP_ROUTER_GROUPS` 玩法模块：根目录放公共能力，中文二级包按玩法拆分并挂载 WS 命令。

## 当前进度

- 已落地玩家、背包、纳戒、修仙物品、源库、二手市场、商场、探险、武器、装备、铭刻、对战、异界虫洞、首领、修仙界历史、数据库备份。
- 当前 HTTP 路由只保留占位 `url.py`，玩法主要走 WS 命令触发。
- 数据库使用 sqlite3，schema 版本为 `SCHEMA_VERSION = 2026052602`；从 `2026052502` 升级会补充 `players.battle_log_detail`，从 `2026052601` 升级会补充抢劫和仇恨表，无法迁移的旧版本才会按最新 schema 重建。
- 行为沉淀使用长期表：`game_logs` 记关键行为流水，`player_lifetime_stats` 接清理前的累计统计，`player_journals` 记玩家日记摘要，`player_titles` 记动态称号，`daily_fortunes` 记每日气运，`weapon_legends` 记武器传奇。
- 二级包都已补齐 `说明.md`，作为单个组件的使用和扩展说明。
- 当前测试覆盖：冒烟测试、WS 触发测试、命令压力测试、架构业务自查、compileall。

## 命名规则

- 中文只用于业务模块目录名，例如 `玩家`、`源库`、`纳戒`、`商场`。
- Python 文件名、类名、函数名、变量名统一用英文。
- 玩家可见命令和回复文本使用中文。
- 命令入口以当前代码显式注册为准；保留的别名也属于正式入口，不再额外兼容未注册的旧口令。

## 目录结构

根目录公共文件：

```text
src/修仙/
  __init__.py              模块入口，注册数据库启动和关闭事件
  url.py                   HTTP router 占位
  sql.py                   sqlite 建表、种子数据和基础读写
  constants.py             全局常量
  rules.py                 等级、战斗、回收、升级等公式
  common.py                CoreService、全服日状态和共享工具
  item_effects.py          可使用物品效果
  weapon_core.py           武器实例、初始武器、掉落武器
  combat_core.py           探险、虫洞、首领、对战共用战斗结算
  combat_log_text.py       战斗日志简要摘要和详细模式判断
  wormhole_service.py      异界虫洞公共服务
  format_text.py           修仙富文本排版工具
  markdown_utils.py        markdown 和按钮工具
  reply.py                 修仙回复包装，文本回复统一升级 markdown 并附带玩家头和按钮
  富文本规则.md             修仙文本、提示、按钮和正文卡规则
  完整设定.md             当前玩法总设定
  architecture.md          当前架构说明
```

二级玩法包：

```text
玩家/            创建用户、修仙信息、状态、修仙日记、签到、新手礼包、休息、帮助图
背包/            占负重库存和恢复类使用入口
纳戒/            不占负重库存和洗髓入口
修仙物品/        查看修仙物品定义
源库/            源石存储、结息、升级、存取
二手市场/        玩家间一包商品交易
商场/            跑商、导航、特殊出售、每日跑商奖励
探险/            30 分钟预计算、掉落、结束探险领取
武器/            武器列表、详情、传奇、升级、附魔、武器/技能书回收
装备/            装备、开孔、镶嵌、宝石升级和回收
铭刻/            装备、武器、自带技能、附魔的显示名改造
对战/            切磋、押注决斗、抢劫、仇恨、接受/拒绝、记录
异界虫洞/        虫洞命令入口，业务复用根目录 wormhole_service.py
首领/            岁时情劫命令入口和节气/节日首领逻辑
修仙界历史/      风云榜、修仙早报、修仙界历史、人物志
数据库备份/      关闭服务时备份修仙数据库
```

二级包常规结构：

```text
玩法名/
  __init__.py      只挂载 @WsMessageHandler.handler 命令
  service.py       只写本玩法业务
  说明.md          本玩法说明
```

## 生命周期

- `src/修仙/__init__.py` 注册 `OnEvent.connect(priority=50)`，启动时执行 `db.init()`。
- `src/修仙/数据库备份/__init__.py` 注册 `OnEvent.disconnect(priority=100)`，关闭时先备份数据库。
- `src/修仙/__init__.py` 注册 `OnEvent.disconnect(priority=50)`，关闭时释放数据库连接。
- 如果关闭回调按倒序执行，备份优先级应保持高于数据库关闭优先级。

## 消息传播

客户端连接：

```text
/ws/bot/{client_id}
```

标准输入：

```json
{
  "code": 202,
  "type": "text",
  "message": "修仙信息",
  "request_id": "本次请求唯一 id"
}
```

传播流程：

1. WS 驱动收到文本并解析 JSON。
2. 协议校验要求 `code/type/message/request_id` 都存在，正常通讯 `code` 为 `202`。
3. WS 层按 `client_id + request_id` 做短期幂等保护，重复请求直接返回 `code=202`。
4. 驱动按命令匹配触发器，未命中返回 `code=404`。
5. 命中后创建后台任务，并把当前 `request_id` 放入 WS 请求上下文。
6. `WsMessageHandler` 拆出 `cmd` 和 `message`。
7. 精确命令取第一个空格前文本为 `cmd`，空格后原文为 `message`。
8. WS 层会先把 `[CQ:at,qq=xxx]` 转成 `xxx`，再压平多余空格。
9. 修仙命令通常只接收 `client_id` 和 `message`。
10. 业务返回文本后，`send_reply` 发给当前 `client_id`。
11. 文本回复会自动加 `【玩家名·称号 Lv.等级】` 前缀；图片回复不额外加标题。
12. 修仙文本回复都会经 `send_reply` 转成 markdown，并自动补玩家头、当前组件按钮和默认按钮；手写 `<休息>` 这类标记会优先转成业务按钮。

## 参数约定

- `client_id`：玩家唯一 id，来自 WS 路由。
- `message`：触发命令后的业务参数，保持用户原文结构，不再随意 split 成列表。
- `raw_message`：完整原始文本，仅高级自定义功能需要。
- `message_data`：完整 WS JSON；一般业务不需要读取，`request_id` 由 WS 层自动维护。
- `match`：正则触发时的匹配对象；修仙当前主要使用精确命令。

## Markdown 按钮

- 按钮工具统一放在 `src/修仙/markdown_utils.py`，二级包不要再复制一份。
- `button("修仙信息")` 默认 `button_type=1`；需要其它按钮行为时再显式传参。
- `MarkdownKeyboard` 最多 25 个按钮，每行最多 3 个，超过 25 个会自动截断。
- 修仙回复层额外限制每条消息最多 15 个按钮。
- 业务失败、条件不满足、需要告诉用户下一步时，`T.hint()` 会调用 `T.tip()` 生成斜体提示，并把建议原文放到正文末尾。
- 建议文案要写给用户看，例如 `发送：商场列表 查看地点，再发送：导航 地点名`。
- 回复层不再从建议文案里猜按钮；没有 `<命令>` 标记时，也会因为默认按钮统一作为 `markdown` 发送。
- 想生成按钮时由业务手写 `<命令>`，例如 `血气不足，可以先<休息>`。
- 尖括号里的内容会原样作为按钮命令，是否能点击执行由业务自己控制。
- 需要显示文字和实际命令不同时，使用 `<实际命令:显示文字>`，例如 `<商场推荐:去商场>`。
- 默认按钮来自 `reply.py` 的 `DEFAULT_BUTTONS`，当前为 `指南`、`探险`、`状态`。
- 当前组件按钮来自 `reply.py` 的 `CONTEXT_BUTTONS_BY_GROUP`，只在自动补齐阶段使用。
- 最终顺序是业务手写按钮、当前组件按钮、默认按钮，并按顺序去重。
- `指南` 和帮助图这类导航页可通过 `auto_buttons=False`、`default_buttons=False` 关闭自动补齐。

## 玩家引用

- 当前正式对外输入优先使用玩家名称，因为新接口 id 很长。
- 涉及对方的命令也可以直接@对方；用户不需要手动输入长 id。
- WS 层会把平台 @ 码转成内部标识，业务层继续按名称或内部标识解析。
- 名称唯一，避免同名玩家导致对战、购买、接受请求时无法分辨。

## 本体和行商化身

- 本体：探险、休息、首领、虫洞、切磋、押注决斗、抢劫。
- 行商化身：跑商、导航、商场买卖、特殊出售、二手市场。
- 探险中可以跑商，因为行商化身在外行动。
- 探险中不能主动挑战首领、虫洞或玩家对战，因为这些都要求本体空闲；但正在探险中的玩家可以作为抢劫目标，防守方使用探险开始快照。
- 抢劫会产生仇恨；有仇恨关系时，`修仙信息` 和 `状态` 展示当前对自己仇恨最高的死敌和报复指数，报复指数 = 仇恨值 x 20，最高 100。

## 库存边界

背包：

- 保存占负重物品。
- 适合跑商特产、怪物战利品和普通掉落。
- 有格子上限、负重上限和物品堆叠上限。

纳戒：

- 保存不占负重物品。
- 适合恢复类、福袋、洗髓液、开孔器、宝石、技能书、铭刻之羽等。
- 宝石单独按名称和等级存入 `gem_items`。

武器库：

- 武器是独立实例，保存在 `player_weapons`。
- 同名武器用 `武器#ID`、等级、攻击、品质、附魔数区分。

装备：

- 创建玩家时默认拥有所有装备位。
- 装备不进入背包或纳戒。

## 数据边界

- 二级包之间不要互相导入。
- 需要跨玩法复用的能力放到根目录公共模块。
- 战斗统一走 `combat_core.py`。
- 武器实例统一走 `weapon_core.py`。
- 玩家、库存、源石、装备加成、天气、灵潮等通用能力统一走 `common.py`。
- 闪避、恢复、探险、跑商、抗暴这类百分比加成在 `common.py` 汇总后统一做收益递减封顶；固定血气、精神、防御仍按数值直接相加。
- 异界虫洞业务放根目录 `wormhole_service.py`，商场只负责尝试发现虫洞。

## 数据库对象

`sql.py` 当前维护 52 张表，按用途分组如下：

```text
schema_meta                 schema 版本、大事记和少量全局键值
physique_defs               体质定义
players                     玩家主档
source_vaults               源库

backpack_items              背包物品
ring_items                  纳戒物品
gem_items                   宝石库存
item_defs                   背包物品定义
equipment_item_defs         纳戒/消耗/技能书等定义

second_hand_listings        二手市场上架
second_hand_records         二手市场成交记录

trade_locations             跑商地点
trade_goods                 跑商商品
trade_prices                跑商价格
trade_heat                  跑商热度
trade_records               跑商交易记录
trade_daily_rewards         每日跑商奖励
trade_limits                每日跑商限制
special_buyers              特殊收购点
recycle_locations           回收地点
weapon_recycle_records      武器回收记录
gem_recycle_records         宝石回收记录
book_recycle_records        技能书回收记录

exploration_locations       探险地点
exploration_records         探险记录和待领取结果
monster_defs                怪物定义

weapon_skill_defs           武器自带技能定义
weapon_defs                 武器模板
player_weapons              玩家武器实例
weapon_enchants             武器附魔实例
weapon_enchant_names        武器技能/附魔铭刻名

fixed_equipment             装备实例
fixed_equipment_inlays      装备镶嵌
inscription_feathers        铭刻之羽

seasonal_boss_reward_rates  首领奖励掉率配置
seasonal_boss_events        首领事件
seasonal_boss_participants  首领参与记录

duel_requests               切磋/决斗请求
duel_records                切磋/决斗记录
robbery_records             抢劫记录
player_hatreds              玩家仇恨/报复指数
combat_logs                 战斗详细日志，保留 7 天

wormholes                   异界虫洞事件
wormhole_participants       虫洞参与记录
wormhole_notices            虫洞通知去重

game_logs                   关键行为流水
player_journals             修仙日记摘要
player_titles               动态称号
player_lifetime_stats       清理前沉淀的玩家长期统计
daily_fortunes              每日气运
daily_newspapers            修仙早报缓存
weapon_legends              武器传奇
```

直接流水清理：

- `combat_logs` 保留 7 天，只保留详细战斗文本。
- `trade_prices`、`trade_heat`、`trade_daily_rewards`、`trade_limits`、`daily_fortunes` 保留 30 天。
- `daily_newspapers` 保留 30 天。
- `game_logs`、`trade_records`、`second_hand_records`、三类回收记录、已领取探险记录、已领取虫洞/首领参与记录、虫洞通知、对战记录和抢劫记录保留 30 天。
- 清理每天最多触发一次，入口沿用探险、对战、虫洞、首领等玩法入口的 `cleanup_battle_records()`。
- 第一次启用长期统计时只记录起点，不回填旧记录；之后每次清理会先把到期明细汇总进 `player_lifetime_stats`，再删除明细。
- 未领取探险、未领取虫洞/首领奖励不会被 30 天清理误删，等玩家领取后再进入后续清理周期。

## 命令入口

玩家：

```text
帮助 / 修仙帮助
指南
创建用户 名称
改名 新名称
修仙信息
状态
修仙日记
自动用药
自动用药 开启 / 自动用药 关闭
战斗日志
战斗日志 开启 / 战斗日志 关闭
签到
新手礼包
休息
结束休息 / 休息结束
```

背包和纳戒：

```text
背包
使用 物品名
使用 物品名 数量
纳戒
洗髓
查看修仙物品 物品名 / 修仙物品查看 物品名 / 查看 物品名
```

源库：

```text
源库
源库结息
升级源库 / 源库升级
存入源石 数量 / 源石存入 数量
取出源石 数量 / 源石取出 数量
```

二手市场：

```text
二手市场 / 小黄鱼
二手市场上架 名称 数量 总价 / 小黄鱼上架 名称 数量 总价
二手市场上架 宝石名称 等级 数量 总价
二手市场上架 武器#ID 总价
二手市场下架 / 小黄鱼下架
二手市场购买 卖家名称 / 二手市场购买@卖家 / 小黄鱼购买 卖家名称
```

商场：

```text
商场
商场列表
商场详情 地点名
商场行情 商品名
商场购买 商品名 数量
商场出售 商品名 数量
商场自动出售
商场推荐
跑商记录
跑商限制
跑商奖励
特殊收购
特殊出售 物品名 数量
特殊自动出售 / 自动出售战利品
导航 地点名 / 去 地点名 / 来 地点名
导航 x y / 去 x y / 来 x y
```

`导航 x y` 会精确写入玩家当前位置；坐标命中已知地点才使用该地点名，否则生成荒野坐标名，避免任意坐标被吸附到最近商场。

探险：

```text
位置 / 地图
探险列表
探险
探险 地点名
探险状态
结束探险 / 探险结束
探险记录
```

武器和装备：

```text
武器
查看武器 武器ID
武器传奇 武器ID
切换武器 武器ID
升级武器 武器ID
附魔武器 武器ID 技能书名
回收武器 / 回收武器 武器ID / 回收武器 武器ID 武器ID / 回收武器 全部
回收技能书 / 回收技能书 技能书名 数量 / 回收技能书 全部
装备
装备升级 装备位 / 升 装备位
孔位
孔位 装备位
开孔 装备位
镶嵌 装备位 孔位号 宝石名称
镶嵌 装备位 孔位号 宝石名称 等级
拆卸 装备位 孔位号
宝石升级 装备位 孔位号
回收宝石 / 回收宝石 宝石名称 等级 数量 / 回收宝石 全部 / 回收宝石 1级全部
宝石
```

铭刻：

```text
铭刻
铭刻之羽
铭刻 装备 装备位 新名字
铭刻 武器 武器ID 新名字
铭刻 技能 武器ID 新名字
铭刻 附魔 武器ID 附魔序号 新名字
铭刻装备 装备位 新名字
铭刻武器 武器ID 新名字
铭刻技能 武器ID 新名字
铭刻附魔 武器ID 附魔序号 新名字
```

对战：

```text
切磋 对方名称 / 切磋@对方
接受切磋 发起人名称 / 接受切磋@发起人
拒绝切磋 发起人名称 / 拒绝切磋@发起人
决斗 源石数量 对方名称 / 决斗@对方 源石数量
接受决斗 发起人名称 / 接受决斗@发起人
拒绝决斗 发起人名称 / 拒绝决斗@发起人
抢劫 对方名称 / 抢劫@对方
决斗记录
```

异界虫洞和首领：

```text
虫洞
虫洞状态
挑战虫洞
虫洞排行
虫洞奖励
首领 / 岁时情劫
首领状态 / 岁时情劫状态
挑战首领 / 挑战岁时情劫
首领排行 / 岁时情劫排行
首领奖励 / 岁时情劫奖励
```

修仙界历史：

```text
风云榜
修仙早报
修仙界历史
人物志 玩家名称 / 人物志@对方
```

## 新增玩法

新增玩法时，新建中文二级包：

```text
灵宠/
  __init__.py
  service.py
  说明.md
```

推荐流程：

1. 在 `__init__.py` 用 `@WsMessageHandler.handler(...)` 注册命令。
2. 在 `service.py` 写业务类，并继承 `CoreService`。
3. 只从根目录公共模块拿共享能力，不导入其他二级包。
4. 如果需要新表，把建表和种子数据写进 `sql.py`。
5. 如果需要新公式，写进 `rules.py`。
6. 如果需要新全局常量，写进 `constants.py`。
7. 给二级包补 `说明.md`。
8. 补冒烟测试或 WS 触发测试。

## 测试命令

```powershell
& "D:\Program Files\miniconda\envs\ws\python.exe" -m compileall src\修仙 test
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_架构业务自查.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_冒烟测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_ws触发测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_命令压力测试.py
```
