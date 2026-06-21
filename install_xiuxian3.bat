@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title xiuxian3 安装 (Windows)

set "LINE========================================="
set "GITHUB_REPO=https://github.com/wsdtl/xiuxian3.git"
set "DEFAULT_NAME=xiuxian3"
set "DEFAULT_SPORT=1234"
set "DEFAULT_NPORT=8080"

if not defined DIR (
    set "DIR=%USERPROFILE%\%DEFAULT_NAME%"
)

:menu
cls
echo %LINE%
echo xiuxian3 — FastAPI 服务端 + NoneBot 插件
echo 仓库: https://github.com/wsdtl/xiuxian3
echo 安装目录: %DIR%
echo %LINE%
echo A. 前台启动(服务端+机器人需两个窗口，见说明)
echo B. 安装
echo C. 更新
echo D. 更新依赖
echo E. 修改安装目录
echo %LINE%
set "choice="
set /p choice=请选择:
if /i "!choice!"=="A" goto run_hint
if /i "!choice!"=="B" goto install
if /i "!choice!"=="C" goto update
if /i "!choice!"=="D" goto update_deps
if /i "!choice!"=="E" goto set_dir
goto menu

:set_dir
set /p DIR=请输入安装根目录(绝对路径):
goto menu

:run_hint
echo.
echo 请先在一个终端运行: %DIR%\run_server.bat
echo 再在另一个终端运行: %DIR%\run_bot.bat
echo 或使用 install 后生成的 start_all.bat（会开两个窗口）
pause
goto menu

:check_python
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    echo 需要 Python 3.10+，请从 https://www.python.org 安装并勾选 Add to PATH
    pause
    exit /b 1
)
exit /b 0

:install
call :check_python
if errorlevel 1 goto menu
set "ACTION=install"
goto do_sync

:update
call :check_python
if errorlevel 1 goto menu
set "ACTION=update"
goto do_sync

:do_sync
cls
echo [1/6] 准备目录...
if not exist "%DIR%" mkdir "%DIR%"
if not exist "%DIR%\server" mkdir "%DIR%\server"
if not exist "%DIR%\bot\src\plugins" mkdir "%DIR%\bot\src\plugins"
if not exist "%DIR%\logs" mkdir "%DIR%\logs"

set "SRC=%DIR%\.src_xiuxian3"
echo [2/6] 获取源码...
if exist "%SRC%\.git" (
    git -C "%SRC%" pull --ff-only
) else (
    if exist "%SRC%" rmdir /s /q "%SRC%"
    git clone --depth 1 %GITHUB_REPO% "%SRC%"
)
if errorlevel 1 (
    echo git 失败，请安装 Git 并检查网络
    pause
    goto menu
)

echo [3/6] 复制 server 与插件...
xcopy /E /Y /I "%SRC%\xiuxianserver\*" "%DIR%\server\" >nul
if exist "%DIR%\bot\src\plugins\xiuxianplugin" rmdir /s /q "%DIR%\bot\src\plugins\xiuxianplugin"
xcopy /E /Y /I "%SRC%\xiuxianplugin" "%DIR%\bot\src\plugins\xiuxianplugin\" >nul

if /i "%ACTION%"=="install" (
    set /p SERVER_PORT=修仙服务端端口 [!DEFAULT_SPORT!]:
    if "!SERVER_PORT!"=="" set "SERVER_PORT=%DEFAULT_SPORT%"
    set /p SUPERUSERS=主人QQ [!123456!]:
    if "!SUPERUSERS!"=="" set "SUPERUSERS=123456"
    set /p NICKNAME=机器人昵称 [!修仙助手!]:
    if "!NICKNAME!"=="" set "NICKNAME=修仙助手"
    set /p NB_PORT=NoneBot端口 [!DEFAULT_NPORT!]:
    if "!NB_PORT!"=="" set "NB_PORT=%DEFAULT_NPORT%"
    call :write_server_env
    call :write_bot_env
    call :write_pyproject
) else (
    for /f "tokens=2 delims==" %%a in ('findstr /B "SERVER_PORT=" "%DIR%\server\.env" 2^>nul') do set "SERVER_PORT=%%a"
    if not defined SERVER_PORT set "SERVER_PORT=%DEFAULT_SPORT%"
)

call :patch_api
call :create_venv
call :pip_install
call :write_bat_launchers

echo.
echo 安装/更新完成: %DIR%
echo 服务端: http://127.0.0.1:!SERVER_PORT!
echo OneBot: ws://127.0.0.1:!NB_PORT!/onebot/v11/ws
echo 双击 start_all.bat 或分别运行 run_server.bat / run_bot.bat
pause
goto menu

:write_server_env
(
echo PROJECT_NAME=xiuxian
echo PROJECT_DEBUG=False
echo PROJECT_TIMEZONE=Asia/Shanghai
echo PROJECT_DOMAIN=
echo.
echo SERVER_HOST=0.0.0.0
echo SERVER_PORT=!SERVER_PORT!
echo.
echo LOG_LEVEL=INFO
echo LOG_COLOR=auto
echo.
echo ROUTER_MODULE_GROUPS=["auto"]
echo ROUTER_MODULES=[]
echo ROUTER_FOLDERS=[]
echo ROUTER_GROUPS=["修仙"]
echo ROUTER_CHILD_FOLDERS=[]
) > "%DIR%\server\.env"
exit /b 0

:write_bot_env
set "SU=!SUPERUSERS:,=", "!"
set "NI=!NICKNAME:,=", "!"
(
echo ENVIRONMENT=dev
echo DRIVER=~fastapi+~httpx+~websockets+~aiohttp
) > "%DIR%\bot\.env"
(
echo LOG_LEVEL=INFO
echo SUPERUSERS = ["!SU!"]
echo COMMAND_START = [""]
echo NICKNAME = ["!NI!"]
echo DEBUG = False
echo HOST = 0.0.0.0
echo PORT = !NB_PORT!
) > "%DIR%\bot\.env.dev"
exit /b 0

:write_pyproject
(
echo [project]
echo name = "xiuxian3-bot"
echo requires-python = "^>=3.10, ^<4.0"
echo dependencies = [
echo     "nonebot2[fastapi,httpx,websockets,aiohttp]^>=2.4.4",
echo     "nonebot-adapter-onebot^>=2.4.6",
echo     "nonebot-adapter-qq^>=1.7.1",
echo     "nonebot_plugin_apscheduler",
echo     "websockets^>=12.0",
echo ]
echo.
echo [tool.nonebot]
echo plugin_dirs = ["src/plugins"]
echo builtin_plugins = ["echo"]
) > "%DIR%\bot\pyproject.toml"
exit /b 0

:patch_api
set "WS=ws://127.0.0.1:!SERVER_PORT!/ws/bot"
python -c "import re,pathlib; p=pathlib.Path(r'%DIR%\bot\src\plugins\xiuxianplugin\api.py'); t=p.read_text(encoding='utf-8'); t,n=re.subn(r'(base_url:\s*str\s*=\s*)[\"']ws://[^\"']+[\"']', r'\1\"%WS%\"', t, 1); assert n==1; p.write_text(t, encoding='utf-8')"
exit /b 0

:create_venv
if not exist "%DIR%\myenv\Scripts\python.exe" (
    echo [4/6] 创建虚拟环境...
    python -m venv "%DIR%\myenv"
)
exit /b 0

:pip_install
echo [5/6] 安装 Python 依赖...
call "%DIR%\myenv\Scripts\activate.bat"
python -m pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple >nul 2>&1
python -m pip install -U pip
python -m pip install -U -r "%DIR%\server\requirements.txt"
python -m pip install -U nb-cli "nonebot2[fastapi,httpx,websockets,aiohttp]" nonebot-adapter-onebot nonebot-adapter-qq nonebot_plugin_apscheduler websockets
exit /b 0

:write_bat_launchers
echo [6/6] 生成启动脚本...
(
echo @echo off
echo call "%DIR%\myenv\Scripts\activate.bat"
echo cd /d "%DIR%\server"
echo python main.py
echo pause
) > "%DIR%\run_server.bat"
(
echo @echo off
echo call "%DIR%\myenv\Scripts\activate.bat"
echo cd /d "%DIR%\bot"
echo nb run
echo pause
) > "%DIR%\run_bot.bat"
(
echo @echo off
echo start "xiuxian3-server" "%DIR%\run_server.bat"
echo timeout /t 3 /nobreak ^>nul
echo start "xiuxian3-bot" "%DIR%\run_bot.bat"
) > "%DIR%\start_all.bat"
exit /b 0

:update_deps
if not exist "%DIR%\myenv\Scripts\activate.bat" (
    echo 请先安装
    pause
    goto menu
)
call "%DIR%\myenv\Scripts\activate.bat"
python -m pip install -U -r "%DIR%\server\requirements.txt"
python -m pip install -U nb-cli "nonebot2[fastapi,httpx,websockets,aiohttp]" nonebot-adapter-onebot nonebot-adapter-qq nonebot_plugin_apscheduler websockets
echo 依赖已更新
pause
goto menu