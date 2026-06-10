# 修仙专用后端

这是一个以 `修仙` 玩法为唯一业务核心的 FastAPI + WebSocket 项目。当前业务包已经从旧的 `src/修仙` 升格为项目根目录下的 `修仙/`，配置只加载 `auto/` 公共启动模块和 `修仙/` 玩法模块。

## 启动

```powershell
conda run -n ws python main.py
```

默认读取项目根目录 `.env`：

```text
APP_HOST=0.0.0.0
APP_PORT=1234
PROJECT_DOMAIN=frp.dengxiaonan.cn
APP_MODULE_GROUPS=["auto"]
APP_MODULES=[]
APP_ROUTER_FOLDERS=[]
APP_ROUTER_GROUPS=["修仙"]
APP_ROUTER_CHILD_FOLDERS=[]
```

本地接口：

```text
http://127.0.0.1:1234
ws://127.0.0.1:1234/ws/bot/{client_id}
```

帮助页：

```text
http://127.0.0.1:1234/xiuxian/help
```

## 项目目录

```text
main.py                 FastAPI 应用入口
launch/                 启动、配置、日志、生命周期、WS 适配器
auto/                   自动启动的公共模块，目前用于 FastAPICache
修仙/                   修仙玩法根包，唯一业务模块
test/                   修仙自查、冒烟、WS 触发和压力测试
static/                 预留静态目录，目前不承接修仙帮助页
```

`修仙/` 根目录放公共能力：

```text
__init__.py             修仙根 router，数据库启动/关闭事件
sql.py                  sqlite 建表、种子数据、基础读写
common.py               CoreService、玩家状态、库存、每日加成、通用工具
constants.py            全局常量
rules.py                等级、收益、升级、回收、附魔等公式
combat_core.py          探险、虫洞、首领、对战共用战斗核心
combat_log_text.py      战斗日志摘要/详细模式文本
weapon_core.py          武器实例、掉落、初始武器
wormhole_service.py     异界虫洞公共服务
item_effects.py         可使用物品效果
format_text.py          富文本排版工具
markdown_utils.py       markdown 按钮工具
reply.py                回复统一包装、玩家头、按钮补齐
architecture.md         架构和扩展教程
完整设定.md             玩法总设定
富文本规则.md           回复格式、提示、按钮规则
地图绘制资料.md         地图坐标和绘制资料
```

中文二级组件只负责自己的命令入口和业务，不互相导入；跨组件复用能力上收到 `修仙/` 根目录公共模块。

## 二级组件

```text
修仙帮助/        帮助网页、帮助图、指南
修仙百科/        设定和数据库资料问答
后台接口/        预留 web 后台 API
玩家/            创建、信息、状态、签到、休息、日志设置
背包/            占负重物品和使用入口
纳戒/            不占负重物品、洗髓
保险箱/          冻结保存物品、宝石、备用武器
修仙物品/        物品定义查看
源库/            源石存取、结息、升级
商场/            跑商、导航、买卖、特殊出售
探险/            普通探险和太虚秘境
武器/            武器列表、查看、升级、附魔、回收
装备/            装备升级、开孔、镶嵌、宝石
铭刻/            装备、武器、技能、附魔显示名
二手市场/        玩家间交易
对战/            切磋、决斗、抢劫、仇恨
异界虫洞/        虫洞入口和奖励
首领/            岁时情劫首领
修仙界历史/      风云榜、早报、历史、人物志
数据库备份/      服务关闭前备份数据库
```

## 命令总览

命令以代码中的 `@WsMessageHandler.handler(...)` 为准，下面按组件统筹。

```text
修仙帮助：帮助、修仙帮助、指南
修仙百科：修仙百科 问题

玩家：创建用户、改名、修仙信息、状态、修仙日记、自动用药、战斗日志、签到、新手礼包、休息、结束休息/休息结束
背包：背包、使用
纳戒：纳戒、洗髓
保险箱：保险箱/查看保险箱、存入保险箱/存保险箱/放入保险箱、取出保险箱/取保险箱
修仙物品：查看修仙物品/修仙物品查看/查看

源库：源库、源库结息、升级源库/源库升级、存入源石/源石存入、取出源石/源石取出
商场：商场、商场列表、商场详情、商场行情、商场购买、商场出售、商场自动出售、商场推荐、跑商记录、跑商限制、跑商奖励、特殊收购、特殊出售、特殊自动出售/自动出售战利品、导航/去/来
探险：位置/地图、探险列表、探险、探险状态、结束探险/探险结束、探险记录

武器：武器、查看武器、武器传奇、切换武器、升级武器、回收武器、回收技能书、附魔武器
装备：装备、装备升级/升、孔位、开孔、镶嵌、拆卸、宝石升级、回收宝石、宝石
铭刻：铭刻、铭刻之羽、铭刻装备、铭刻武器、铭刻附魔、铭刻技能
二手市场：二手市场/小黄鱼、二手市场上架/小黄鱼上架、二手市场下架/小黄鱼下架、二手市场购买/小黄鱼购买

对战：切磋、接受切磋、拒绝切磋、决斗、接受决斗、拒绝决斗、决斗记录、抢劫
异界虫洞：虫洞、虫洞状态、挑战虫洞、虫洞排行、虫洞奖励
首领：首领/岁时情劫、首领状态/岁时情劫状态、挑战首领/挑战岁时情劫、首领排行/岁时情劫排行、首领奖励/岁时情劫奖励
修仙界历史：风云榜、修仙早报、修仙界历史、人物志
```

需要对方的命令支持玩家名或平台 `@`。WS 层会把 `[CQ:at,qq=xxx]` 转成内部 id 并压平空格，业务层继续按玩家名或 id 解析。

## 消息协议

客户端请求：

```json
{
  "code": 202,
  "type": "text",
  "message": "修仙信息",
  "request_id": "本次请求唯一 id"
}
```

流程：

```text
WS 收包 -> JSON 校验 -> request_id 幂等保护 -> 命令匹配 -> 后台任务执行 -> manager.send 回复
```

修仙组件回复统一走 `修仙/reply.py`：文本会加玩家头，默认转 markdown，并补业务手写按钮、预测按钮、当前组件按钮和默认按钮；图片消息不额外加标题。

## 文档和帮助页

- 每个二级组件保留 `说明.md`，帮助页启动时递归读取 `修仙/` 下所有 `.md` 并缓存。
- 首页“主要命令”从各组件 `说明.md` 的 `## 命令` 章节生成。
- 修改 Markdown、数据库种子或百科资料后，需要重启项目刷新帮助页和百科缓存。
- 更完整的业务边界看 `修仙/architecture.md`，数值设定看 `修仙/完整设定.md`，回复格式看 `修仙/富文本规则.md`。

## 验证

```powershell
& "D:\Program Files\miniconda\envs\ws\python.exe" -m compileall 修仙 test
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_冒烟测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_架构业务自查.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_ws触发测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_markdown按钮测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_新表记录测试.py
& "D:\Program Files\miniconda\envs\ws\python.exe" test\修仙_命令压力测试.py
```
