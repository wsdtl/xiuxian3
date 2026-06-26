from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import HTMLResponse

from ..public_url import server_uses_https
from .service import service


router = APIRouter(prefix="/xiuxian/user-groups")


@router.get("", response_class=HTMLResponse)
async def user_group_page() -> str:
    """返回轻量用户组后台页面。"""

    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>修仙用户组</title>
  <style>
    body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f7f4;color:#202124}
    main{max-width:760px;margin:32px auto;padding:0 18px}
    section{border:1px solid #d8d8d0;background:#fff;border-radius:6px;padding:18px;margin:14px 0}
    button{border:1px solid #1f5f4a;background:#24765a;color:#fff;border-radius:4px;padding:8px 12px;cursor:pointer}
    button.secondary{border-color:#8b8b82;background:#fff;color:#202124}
    code{background:#eeeeea;border-radius:4px;padding:2px 5px}
    .muted{color:#696963}
    .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    pre{white-space:pre-wrap;background:#f2f2ee;border-radius:4px;padding:10px}
  </style>
</head>
<body>
<main>
  <h1>修仙用户组</h1>
  <section>
    <h2>用户组后台登录</h2>
    <p class="muted">生成登录码后，用已有修仙角色的账号发送：<code>用户组后台登录 登录码</code></p>
    <div class="row">
      <button onclick="createChallenge()">生成登录码</button>
      <button class="secondary" onclick="checkLogin()">检查登录</button>
    </div>
    <p id="challenge"></p>
  </section>
  <section>
    <h2>绑定新入口</h2>
    <p class="muted">登录后生成一次性绑定码，再到新账号发送：<code>绑定用户组 绑定码</code></p>
    <div class="row">
      <button onclick="createBindCode()">生成绑定码</button>
      <button class="secondary" onclick="loadIdentities()">刷新已绑定 ID</button>
    </div>
    <p id="bindCode"></p>
    <pre id="identities"></pre>
  </section>
</main>
<script>
async function createChallenge(){
  const res = await fetch('/xiuxian/user-groups/api/login-challenge', {method:'POST'});
  const data = await res.json();
  document.getElementById('challenge').innerHTML = `登录码：<code>${data.challenge_id}</code>`;
}
async function checkLogin(){
  const res = await fetch('/xiuxian/user-groups/api/login-status');
  const data = await res.json();
  document.getElementById('challenge').textContent = data.confirmed ? `已登录：${data.player_id}` : '还没有确认登录';
}
async function createBindCode(){
  const res = await fetch('/xiuxian/user-groups/api/bind-code', {method:'POST'});
  const data = await res.json();
  if(!res.ok){ document.getElementById('bindCode').textContent = data.detail || '生成失败'; return; }
  document.getElementById('bindCode').innerHTML = `绑定码：<code>${data.code}</code>`;
}
async function loadIdentities(){
  const res = await fetch('/xiuxian/user-groups/api/identities');
  const data = await res.json();
  document.getElementById('identities').textContent = JSON.stringify(data, null, 2);
}
</script>
</body>
</html>
"""


@router.post("/api/login-challenge")
async def create_login_challenge(response: Response) -> dict:
    """创建浏览器用户组后台登录挑战，并写入短期 session cookie。"""

    data = service.create_login_challenge()
    response.set_cookie(
        "xiuxian_user_group_session",
        data["session_id"],
        max_age=data["expires_in_seconds"],
        httponly=True,
        samesite="lax",
        secure=server_uses_https(),
    )
    return data


@router.get("/api/login-status")
async def login_status(
    xiuxian_user_group_session: str | None = Cookie(default=None),
) -> dict:
    """查询当前浏览器 session 是否已经由消息入口确认。"""

    return service.login_status(xiuxian_user_group_session or "")


@router.post("/api/bind-code")
async def create_bind_code(
    xiuxian_user_group_session: str | None = Cookie(default=None),
) -> dict:
    """为已登录用户组生成一次性绑定码。"""

    try:
        return service.create_bind_code(xiuxian_user_group_session or "")
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/api/identities")
async def identities(
    xiuxian_user_group_session: str | None = Cookie(default=None),
) -> list[dict]:
    """列出当前用户组已绑定入口身份。"""

    try:
        return service.identities(xiuxian_user_group_session or "")
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
