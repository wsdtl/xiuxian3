(function () {
  const API_BASE = "/xiuxian/dongtian/suixing-qieyu";
  const ROUND_SECONDS = 90;
  const TIDE_SECONDS = 30;

  const timerNode = document.querySelector(".trial-timer");
  const phaseNode = document.querySelector(".trial-phase");
  const comboNode = document.querySelector(".combo-surge");
  const slashNode = document.querySelector(".slash-feed");
  const tideNode = document.querySelector(".star-tide");
  const resultNode = document.querySelector(".dongtian-result");
  const copyBtn = document.querySelector(".copy-code-btn");
  const settleBtn = document.querySelector(".settle-btn");

  let gameToken = "";
  let sessionId = "";
  let roundToken = "";
  let roundStartedAt = 0;
  let finished = false;
  let starting = false;
  let lastSnapshot = {};
  let finishResult = null;
  let frameHandle = 0;

  function safeNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? Math.max(0, number) : 0;
  }

  function showResult(html) {
    if (resultNode) resultNode.innerHTML = html;
  }

  async function requestJson(path, payload) {
    const response = await fetch(`${API_BASE}${path}`, {
      method: payload ? "POST" : "GET",
      headers: payload ? { "Content-Type": "application/json" } : {},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "洞天接口暂时没有回应。");
    }
    return data;
  }

  async function loadConfig() {
    const data = await requestJson("/config");
    gameToken = data.game_token || data.gameToken || "";
    if (!gameToken) throw new Error("洞天启动凭证缺失，请刷新重试。");
  }

  async function startRound() {
    starting = true;
    if (settleBtn) settleBtn.textContent = "开局中";
    if (!gameToken) await loadConfig();
    const data = await requestJson("/start", { gameToken });
    sessionId = data.session_id || data.sessionId || "";
    roundToken = data.round_token || data.roundToken || "";
    roundStartedAt = Date.now();
    finished = false;
    finishResult = null;
    lastSnapshot = {
      score: 0,
      cubesSliced: 0,
      strongCubes: 0,
      slowmoCubes: 0,
      misses: 0,
      maxCombo: 0,
      elapsedSeconds: 0,
      endReason: "manual",
    };
    showResult("星玉仍在云台上流转。");
    if (copyBtn) copyBtn.disabled = true;
    if (settleBtn) settleBtn.textContent = "结算本局";
    starting = false;
    scheduleClock();
  }

  function scheduleClock() {
    cancelAnimationFrame(frameHandle);
    const tick = () => {
      if (finished) return;
      const elapsed = (Date.now() - roundStartedAt) / 1000;
      const remaining = Math.max(0, ROUND_SECONDS - elapsed);
      const inTide = remaining <= TIDE_SECONDS && remaining > 0;
      window.SUIXING_TIDE_ACTIVE = inTide;
      document.body.classList.toggle("tide-mode", inTide);
      if (timerNode) timerNode.textContent = remaining.toFixed(1);
      if (phaseNode) {
        phaseNode.textContent = inTide
          ? "星潮爆发"
          : remaining <= 60
            ? "鹤影穿云"
            : "云海初开";
      }
      if (tideNode) tideNode.classList.toggle("active", inTide);
      if (remaining <= 0) {
        window.endSuixingTrial && window.endSuixingTrial("timeout");
        return;
      }
      frameHandle = requestAnimationFrame(tick);
    };
    tick();
  }

  function updateSnapshot(detail) {
    lastSnapshot = {
      ...lastSnapshot,
      ...detail,
      elapsedSeconds: Math.min(ROUND_SECONDS, Math.round((Date.now() - roundStartedAt) / 1000)),
    };
  }

  function flashSlash() {
    if (!slashNode) return;
    slashNode.classList.remove("flash");
    void slashNode.offsetWidth;
    slashNode.classList.add("flash");
  }

  function showCombo(detail) {
    if (!comboNode) return;
    const combo = safeNumber(detail.maxCombo || detail.combo);
    if (combo < 4) return;
    comboNode.textContent = combo >= 20 ? `${combo} 连斩` : `${combo} 连切`;
    comboNode.classList.remove("show");
    void comboNode.offsetWidth;
    comboNode.classList.add("show");
  }

  async function finishRound(reason) {
    if (finished) return;
    if (starting || !sessionId || !roundToken) {
      showResult("云台仍在开局，请稍候再结算。");
      return;
    }
    finished = true;
    cancelAnimationFrame(frameHandle);
    window.SUIXING_TIDE_ACTIVE = false;
    document.body.classList.remove("tide-mode");
    if (tideNode) tideNode.classList.remove("active");
    if (!sessionId || !roundToken) {
      showResult("本局没有拿到洞天单局凭证，请重新开局。");
      return;
    }
    const payload = {
      gameToken,
      sessionId,
      roundToken,
      score: safeNumber(lastSnapshot.score),
      cubesSliced: safeNumber(lastSnapshot.cubesSliced),
      strongCubes: safeNumber(lastSnapshot.strongCubes),
      slowmoCubes: safeNumber(lastSnapshot.slowmoCubes),
      misses: safeNumber(lastSnapshot.misses),
      maxCombo: safeNumber(lastSnapshot.maxCombo),
      elapsedSeconds: Math.min(ROUND_SECONDS, safeNumber(lastSnapshot.elapsedSeconds)),
      endReason: reason || lastSnapshot.endReason || "manual",
    };
    showResult("正在把碎星玉尘收束成洞天兑换码...");
    try {
      finishResult = await requestJson("/finish", payload);
      renderFinishResult(finishResult);
    } catch (error) {
      showResult(`<strong>结算失败</strong><br>${escapeHtml(error.message || String(error))}`);
    }
  }

  function renderFinishResult(data) {
    const code = data.code || "";
    const command = code ? `洞天兑换 ${code}` : "";
    const rewards = Array.isArray(data.reward_preview) ? data.reward_preview : [];
    const rewardHtml = rewards.length ? rewards.map((item) => `<div>${escapeHtml(item)}</div>`).join("") : "<div>本局没有形成奖励。</div>";
    const score = safeNumber(data.accepted_score || data.score);
    const cubes = safeNumber(data.cubes_sliced);
    const combo = safeNumber(data.max_combo);
    showResult(`
      <div>认可玉尘 <strong>${score}</strong>｜切玉 <strong>${cubes}</strong>｜最高连斩 <strong>${combo}</strong></div>
      ${code ? `<span class="dongtian-code">${escapeHtml(code)}</span>` : ""}
      ${command ? `<div>复制后回到机器人发送：<strong>${escapeHtml(command)}</strong></div>` : ""}
      <div style="margin-top:8px">${rewardHtml}</div>
    `);
    if (copyBtn) copyBtn.disabled = !command;
  }

  async function copyCommand() {
    if (!finishResult || !finishResult.code) return;
    const command = `洞天兑换 ${finishResult.code}`;
    try {
      await navigator.clipboard.writeText(command);
      copyBtn.textContent = "已复制";
      setTimeout(() => (copyBtn.textContent = "复制兑换命令"), 1200);
    } catch {
      copyBtn.textContent = "手动复制上方命令";
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.addEventListener("suixing:start", () => {
    startRound().catch((error) => {
      starting = false;
      if (settleBtn) settleBtn.textContent = "结算本局";
      showResult(`<strong>开局失败</strong><br>${escapeHtml(error.message || String(error))}`);
    });
  });
  window.addEventListener("suixing:score", (event) => updateSnapshot(event.detail || {}));
  window.addEventListener("suixing:miss", (event) => updateSnapshot(event.detail || {}));
  window.addEventListener("suixing:slice", (event) => {
    const detail = event.detail || {};
    updateSnapshot(detail);
    flashSlash();
    showCombo(detail);
  });
  window.addEventListener("suixing:finish", (event) => {
    const detail = event.detail || {};
    updateSnapshot(detail);
    finishRound(detail.endReason || "manual");
  });

  window.endSuixingTrial = function (reason) {
    if (typeof endGame === "function") {
      endGame(reason || "manual");
    }
  };

  if (copyBtn) copyBtn.addEventListener("click", copyCommand);
  if (settleBtn) {
    settleBtn.addEventListener("click", () => {
      window.endSuixingTrial && window.endSuixingTrial("manual");
    });
  }
  loadConfig().catch((error) => showResult(`<strong>启动失败</strong><br>${escapeHtml(error.message || String(error))}`));
})();
