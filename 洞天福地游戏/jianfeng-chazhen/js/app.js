(function () {
  const API_BASE = "/xiuxian/dongtian/jianfeng-chazhen";
  const ROUND_SECONDS = 90;
  const BURST_SECONDS = 30;
  const MISS_LIMIT = 4;
  const MIN_SETTLE_SECONDS = 10;

  const canvas = document.getElementById("arena");
  const ctx = canvas.getContext("2d");
  const menu = document.getElementById("menu");
  const result = document.getElementById("result");
  const startBtn = document.getElementById("start");
  const againBtn = document.getElementById("again");
  const settleBtn = document.getElementById("settle");
  const copyBtn = document.getElementById("copy");
  const timeNode = document.getElementById("time");
  const phaseNode = document.getElementById("phase");
  const phaseHintNode = document.getElementById("burst");
  const scoreNode = document.getElementById("score");
  const formationsNode = document.getElementById("formations");
  const swordsNode = document.getElementById("swords");
  const gapsNode = document.getElementById("gaps");
  const comboNode = document.getElementById("combo");
  const shieldsNode = document.getElementById("shields");
  const toastNode = document.getElementById("toast");
  const fxLayer = document.getElementById("fx-layer");
  const resultTitle = document.getElementById("result-title");
  const resultLines = document.getElementById("result-lines");

  let width = 0;
  let height = 0;
  let dpr = 1;
  let center = { x: 0, y: 0 };
  let radius = 104;
  let gameToken = "";
  let sessionId = "";
  let roundToken = "";
  let startedAt = 0;
  let lastTick = 0;
  let rotation = 0;
  let direction = 1;
  let nextShiftAt = 0;
  let pendingDirection = 1;
  let shiftCueUntil = 0;
  let shiftCueStartedAt = 0;
  let gapAngle = 90;
  let running = false;
  let finishing = false;
  let raf = 0;
  let finishResult = null;
  let state = freshState();
  let display = freshDisplay();
  let impactEffects = [];
  let breakSparks = [];
  let breakSlowUntil = 0;
  let corePulseUntil = 0;

  function freshState() {
    return {
      score: 0,
      swordsInserted: 0,
      formationsBroken: 0,
      gapHits: 0,
      maxCombo: 0,
      combo: 0,
      burstSwords: 0,
      misses: 0,
      swordAngles: [],
      targetSwords: 5,
      phase: "试剑入阵",
      elapsedSeconds: 0,
      endReason: "manual",
    };
  }

  function freshDisplay() {
    return {
      score: 0,
      swordsInserted: 0,
      formationsBroken: 0,
      gapHits: 0,
      combo: 0,
      shields: MISS_LIMIT - 1,
    };
  }

  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const narrow = width <= 560;
    radius = clamp(Math.min(width, height) * 0.18, narrow ? 72 : 82, narrow ? 112 : 132);
    const topReserve = narrow ? 132 : 112;
    const lowerReserve = narrow ? 132 : 156;
    const preferredY = height * (narrow ? 0.5 : 0.45);
    center = {
      x: width / 2,
      y: clamp(preferredY, topReserve + radius, Math.max(topReserve + radius, height - lowerReserve)),
    };
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function safeNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? Math.max(0, number) : 0;
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
    const config = data.config || {};
    if (config.round_min_seconds) {
      window.JIANFENG_MIN_SETTLE_SECONDS = safeNumber(config.round_min_seconds);
    }
    if (!gameToken) throw new Error("洞天启动凭证缺失，请刷新重试。");
  }

  async function startRound() {
    startBtn.disabled = true;
    result.classList.remove("show");
    if (!gameToken) await loadConfig();
    const data = await requestJson("/start", { gameToken });
    sessionId = data.session_id || data.sessionId || "";
    roundToken = data.round_token || data.roundToken || "";
    if (!sessionId || !roundToken) throw new Error("本局凭证缺失，请重新开局。");
    state = freshState();
    display = freshDisplay();
    startedAt = performance.now();
    lastTick = startedAt;
    nextShiftAt = 1.8;
    pendingDirection = direction;
    shiftCueUntil = 0;
    shiftCueStartedAt = 0;
    rotation = Math.random() * 360;
    direction = Math.random() > 0.5 ? 1 : -1;
    gapAngle = 90;
    running = true;
    finishing = false;
    finishResult = null;
    breakSlowUntil = 0;
    corePulseUntil = 0;
    impactEffects = [];
    breakSparks = [];
    fxLayer.replaceChildren();
    copyBtn.disabled = true;
    settleBtn.disabled = false;
    menu.classList.remove("show");
    updateHud();
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(loop);
  }

  function loop(now) {
    const dt = Math.min(0.04, (now - lastTick) / 1000 || 0);
    lastTick = now;
    if (running) update(dt);
    else updateHud();
    draw();
    raf = requestAnimationFrame(loop);
  }

  function update(dt) {
    const elapsed = (performance.now() - startedAt) / 1000;
    const remaining = Math.max(0, ROUND_SECONDS - elapsed);
    state.elapsedSeconds = Math.min(ROUND_SECONDS, Math.round(elapsed));
    const burst = remaining <= BURST_SECONDS;
    const urgent = remaining <= 60;
    state.phase = burst ? "万剑归宗" : urgent ? "剑阵急转" : "试剑入阵";
    document.body.classList.toggle("burst", burst);

    const baseSpeed = 58 + state.formationsBroken * 4.8 + (urgent ? 22 : 0) + (burst ? 44 : 0);
    const cueActive = shiftCueUntil > elapsed;
    if (!cueActive && shiftCueUntil > 0) {
      direction = pendingDirection;
      shiftCueUntil = 0;
      shiftCueStartedAt = 0;
      nextShiftAt = elapsed + nextShiftDelay(elapsed, burst, urgent);
      toast(burst ? "剑势反卷" : "阵眼变相");
    }
    if (!shiftCueUntil && elapsed >= nextShiftAt) {
      pendingDirection = -direction;
      shiftCueStartedAt = elapsed;
      shiftCueUntil = elapsed + (burst ? 0.46 : urgent ? 0.54 : 0.62);
      nextShiftAt = Number.POSITIVE_INFINITY;
      toast(burst ? "剑势将反" : "阵眼蓄势");
    }
    document.body.classList.toggle("shift-cue", shiftCueUntil > elapsed);
    const breakSlow = performance.now() < breakSlowUntil;
    rotation = (rotation + direction * baseSpeed * (shiftCueUntil > elapsed ? 0.28 : 1) * (breakSlow ? 0.2 : 1) * dt) % 360;
    if (remaining <= 0) endRound("timeout");
    updateHud();
  }

  function nextShiftDelay(elapsed, burst, urgent) {
    return Math.max(0.55, 2.45 - state.formationsBroken * 0.035 - (burst ? 0.78 : urgent ? 0.35 : 0)) + Math.random() * 1.15;
  }

  function insertSword() {
    if (!running || finishing) return;
    const remaining = Math.max(0, ROUND_SECONDS - (performance.now() - startedAt) / 1000);
    const burst = remaining <= BURST_SECONDS;
    const insertAngle = normalize(90 - rotation);
    const collisionDistance = Math.max(6.2, 10.5 - state.formationsBroken * 0.06 - (burst ? 1.2 : 0));
    const collided = state.swordAngles.some((angle) => angleDistance(angle, insertAngle) < collisionDistance);
    if (collided) {
      state.misses += 1;
      state.combo = 0;
      state.score = Math.max(0, state.score - 55);
      addFloatText("-55", "bad", center.x, center.y - radius * 0.35);
      flashBody("hit-flash", 220);
      pulseNode(scoreNode.closest(".hud-block"));
      pulseNode(shieldsNode.closest("div"));
      toast(state.misses >= MISS_LIMIT ? "护心碎裂" : "剑锋相冲");
      if (state.misses >= MISS_LIMIT) {
        endRound("mistake_limit");
      }
      updateHud();
      return;
    }

    const gapHit = angleDistance(insertAngle, gapAngle) <= (burst ? 8 : 6);
    state.swordAngles.push(insertAngle);
    state.swordsInserted += 1;
    state.combo += 1;
    state.maxCombo = Math.max(state.maxCombo, state.combo);
    if (burst) state.burstSwords += 1;
    if (gapHit) state.gapHits += 1;

    const add = 8 + state.combo * 2 + (gapHit ? 32 : 0) + (burst ? 7 : 0);
    state.score += add;
    addImpactEffect(insertAngle, gapHit);
    addFloatText(gapHit ? `天隙 +${add}` : `+${add}`, gapHit ? "gap" : "", center.x, center.y - radius * 0.78);
    flashBody("hit-flash", 180);
    pulseNode(scoreNode.closest(".hud-block"));
    pulseNode(swordsNode.closest("div"));
    if (gapHit) pulseNode(gapsNode.closest("div"));
    if (state.combo >= 2) pulseNode(comboNode.closest("div"));
    toast(gapHit ? "天隙一击" : state.combo >= 10 ? `${state.combo} 连斩` : "入阵");

    if (state.swordAngles.length >= state.targetSwords) {
      const oldAngles = state.swordAngles.slice();
      const breakBonus = 70 + Math.min(180, state.combo * 3);
      state.formationsBroken += 1;
      state.score += breakBonus;
      state.swordAngles = [];
      state.targetSwords = clamp(5 + Math.floor(state.formationsBroken / 3), 5, 12);
      launchBreak(oldAngles);
      addFloatText(`破阵 +${breakBonus}`, "break", center.x, center.y - radius * 0.18);
      flashBody("break-flash", 560);
      breakSlowUntil = performance.now() + 280;
      corePulseUntil = performance.now() + 620;
      pulseNode(formationsNode.closest("div"));
      toast("破阵");
    }
    updateHud();
  }

  function endRound(reason) {
    if (!running || finishing) return;
    running = false;
    state.endReason = reason || "manual";
    document.body.classList.remove("shift-cue");
    const minSeconds = safeNumber(window.JIANFENG_MIN_SETTLE_SECONDS || MIN_SETTLE_SECONDS);
    const elapsed = (performance.now() - startedAt) / 1000;
    if (elapsed < minSeconds) {
      const waitMs = Math.ceil((minSeconds - elapsed) * 1000);
      finishing = true;
      settleBtn.disabled = true;
      showResult("剑魄正在收束，十息后结算...");
      result.classList.add("show");
      setTimeout(() => finishRound(), waitMs);
      return;
    }
    finishRound();
  }

  async function finishRound() {
    if (finishResult) return;
    finishing = true;
    settleBtn.disabled = true;
    showResult("正在把剑阵余响收束成洞天兑换码...");
    result.classList.add("show");
    const payload = {
      gameToken,
      sessionId,
      roundToken,
      score: safeNumber(state.score),
      swordsInserted: safeNumber(state.swordsInserted),
      formationsBroken: safeNumber(state.formationsBroken),
      gapHits: safeNumber(state.gapHits),
      maxCombo: safeNumber(state.maxCombo),
      burstSwords: safeNumber(state.burstSwords),
      misses: safeNumber(state.misses),
      elapsedSeconds: Math.min(ROUND_SECONDS, safeNumber(state.elapsedSeconds)),
      endReason: state.endReason || "manual",
    };
    try {
      finishResult = await requestJson("/finish", payload);
      renderFinish(finishResult);
    } catch (error) {
      showResult(`<strong>结算失败</strong><span>${escapeHtml(error.message || String(error))}</span>`);
    }
  }

  function updateHud() {
    const elapsed = running ? (performance.now() - startedAt) / 1000 : state.elapsedSeconds;
    const remaining = Math.max(0, ROUND_SECONDS - elapsed);
    const cueActive = shiftCueUntil > elapsed;
    const burst = remaining <= BURST_SECONDS;
    timeNode.textContent = remaining.toFixed(1);
    phaseNode.textContent = state.phase;
    phaseHintNode.textContent = cueActive ? "剑势将反" : burst ? "万剑归宗" : "凝神听风";
    display.score = chaseValue(display.score, state.score, 0.24, 2.4);
    display.formationsBroken = chaseValue(display.formationsBroken, state.formationsBroken, 0.34, 0.18);
    display.swordsInserted = chaseValue(display.swordsInserted, state.swordsInserted, 0.34, 0.18);
    display.gapHits = chaseValue(display.gapHits, state.gapHits, 0.34, 0.18);
    display.combo = chaseValue(display.combo, state.combo, 0.4, 0.22);
    display.shields = chaseValue(display.shields, Math.max(0, MISS_LIMIT - 1 - state.misses), 0.4, 0.22);
    scoreNode.textContent = Math.floor(display.score);
    formationsNode.textContent = Math.round(display.formationsBroken);
    swordsNode.textContent = Math.round(display.swordsInserted);
    gapsNode.textContent = Math.round(display.gapHits);
    comboNode.textContent = Math.round(display.combo);
    shieldsNode.textContent = Math.round(display.shields);
  }

  function chaseValue(current, target, ratio, minStep) {
    const diff = target - current;
    if (Math.abs(diff) <= minStep) return target;
    return current + Math.sign(diff) * Math.max(Math.abs(diff) * ratio, minStep);
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    drawBackground();
    drawCore();
    drawBlade();
  }

  function drawBackground() {
    const burst = document.body.classList.contains("burst");
    const cue = shiftCueUntil > 0;
    ctx.save();
    ctx.globalAlpha = burst ? 0.22 : cue ? 0.2 : 0.12;
    const count = burst || cue ? 44 : 34;
    for (let i = 0; i < count; i += 1) {
      const x = ((i * 97 + rotation * (cue ? 3.2 : 1.7)) % (width + 120)) - 60;
      const y = ((i * 61 + rotation * (cue ? 1.4 : 0.8)) % (height + 80)) - 40;
      ctx.beginPath();
      ctx.arc(x, y, (i % 3) + 1.2, 0, Math.PI * 2);
      ctx.fillStyle = cue ? (i % 2 ? "#fff2a8" : "#ff8f70") : i % 2 ? "#ffe082" : "#8be9ff";
      ctx.fill();
    }
    ctx.restore();
  }

  function drawCore() {
    ctx.save();
    ctx.translate(center.x, center.y);
    ctx.rotate((rotation * Math.PI) / 180);

    const pulse = corePulseProgress();
    const gradient = ctx.createRadialGradient(0, 0, 12, 0, 0, radius);
    gradient.addColorStop(0, "#fff8c9");
    gradient.addColorStop(0.42, pulse > 0 ? "#fff2a8" : "#4fd8ff");
    gradient.addColorStop(1, "#14233b");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(0, 0, radius + pulse * 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 5 + pulse * 3;
    ctx.strokeStyle = pulse > 0 ? `rgba(255, 244, 186, ${0.95})` : "rgba(255, 245, 190, 0.9)";
    ctx.stroke();

    if (pulse > 0) {
      ctx.save();
      ctx.rotate((-rotation * Math.PI) / 180);
      ctx.globalAlpha = pulse * 0.68;
      ctx.strokeStyle = "#8be9ff";
      ctx.lineWidth = 4 + pulse * 8;
      ctx.beginPath();
      ctx.arc(0, 0, radius + 18 + (1 - pulse) * 34, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (shiftCueUntil > 0) {
      const elapsed = (performance.now() - startedAt) / 1000;
      const total = Math.max(0.1, shiftCueUntil - shiftCueStartedAt);
      const progress = clamp((elapsed - shiftCueStartedAt) / total, 0, 1);
      ctx.save();
      ctx.rotate((-rotation * Math.PI) / 180);
      ctx.strokeStyle = `rgba(255, 231, 143, ${0.95 - progress * 0.25})`;
      ctx.lineWidth = 5 + progress * 8;
      ctx.beginPath();
      ctx.arc(0, 0, radius + 16 + progress * 18, 0, Math.PI * 2 * progress);
      ctx.stroke();
      ctx.fillStyle = `rgba(255, 242, 168, ${0.22 + progress * 0.14})`;
      ctx.beginPath();
      ctx.arc(0, 0, radius + 8 + progress * 8, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255, 142, 96, 0.38)";
      ctx.stroke();
      ctx.restore();
    }

    drawGapMarker();

    const now = performance.now();
    drawImpactEffects(now);
    drawBreakSparks(now);

    for (const angle of state.swordAngles) {
      drawSword(angle);
    }
    ctx.restore();

    ctx.save();
    ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
    ctx.beginPath();
    ctx.arc(center.x, center.y, radius + 18, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(139, 233, 255, 0.16)";
    ctx.lineWidth = 18;
    ctx.stroke();
    ctx.restore();
  }

  function drawSword(angle) {
    ctx.save();
    ctx.rotate((angle * Math.PI) / 180);
    ctx.strokeStyle = "rgba(238, 248, 255, 0.92)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(radius - 4, 0);
    ctx.lineTo(radius + 54, 0);
    ctx.stroke();
    ctx.fillStyle = "#ffe082";
    ctx.beginPath();
    ctx.moveTo(radius + 62, 0);
    ctx.lineTo(radius + 48, -5);
    ctx.lineTo(radius + 48, 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawGapMarker() {
    ctx.save();
    ctx.rotate((gapAngle * Math.PI) / 180);
    ctx.strokeStyle = "rgba(255, 224, 132, 0.96)";
    ctx.lineWidth = 9;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.arc(0, 0, radius + 4, -0.075, 0.075);
    ctx.stroke();
    ctx.strokeStyle = "rgba(255, 244, 186, 0.32)";
    ctx.lineWidth = 18;
    ctx.beginPath();
    ctx.arc(0, 0, radius + 6, -0.052, 0.052);
    ctx.stroke();
    ctx.restore();
  }

  function corePulseProgress() {
    if (!corePulseUntil) return 0;
    const left = corePulseUntil - performance.now();
    if (left <= 0) {
      corePulseUntil = 0;
      return 0;
    }
    return Math.sin((left / 620) * Math.PI);
  }

  function addImpactEffect(angle, strong) {
    impactEffects.push({
      angle,
      born: performance.now(),
      duration: strong ? 520 : 360,
      strong,
    });
  }

  function drawImpactEffects(now) {
    impactEffects = impactEffects.filter((effect) => now - effect.born < effect.duration);
    for (const effect of impactEffects) {
      const progress = clamp((now - effect.born) / effect.duration, 0, 1);
      ctx.save();
      ctx.rotate((effect.angle * Math.PI) / 180);
      ctx.globalAlpha = 1 - progress;
      ctx.strokeStyle = effect.strong ? "#fff2a8" : "#8be9ff";
      ctx.lineWidth = effect.strong ? 5 : 3;
      ctx.beginPath();
      ctx.arc(radius + 18 + progress * 28, 0, 10 + progress * 26, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(radius + 14, 0);
      ctx.lineTo(radius + 84 + progress * 24, 0);
      ctx.stroke();
      ctx.restore();
    }
  }

  function launchBreak(angles) {
    const now = performance.now();
    breakSparks.push(
      ...angles.map((angle, index) => ({
        angle,
        born: now + index * 12,
        duration: 620 + Math.random() * 180,
        drift: (Math.random() - 0.5) * 22,
      }))
    );
  }

  function drawBreakSparks(now) {
    breakSparks = breakSparks.filter((spark) => now - spark.born < spark.duration);
    for (const spark of breakSparks) {
      const age = now - spark.born;
      if (age < 0) continue;
      const progress = clamp(age / spark.duration, 0, 1);
      ctx.save();
      ctx.rotate((spark.angle * Math.PI) / 180);
      ctx.translate(progress * 46, spark.drift * progress);
      ctx.globalAlpha = Math.max(0, 1 - progress);
      ctx.strokeStyle = "#fff4ba";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(radius - 4, 0);
      ctx.lineTo(radius + 52 + progress * 26, 0);
      ctx.stroke();
      ctx.fillStyle = "#8be9ff";
      ctx.beginPath();
      ctx.arc(radius + 58 + progress * 22, 0, 2.5 + progress * 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  function drawBlade() {
    if (!running) return;
    ctx.save();
    const x = center.x;
    const y = height - Math.max(74, height * 0.12);
    const tipY = center.y + radius + 52;
    ctx.strokeStyle = "rgba(255, 244, 186, 0.88)";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x, y + 34);
    ctx.lineTo(x, tipY);
    ctx.stroke();
    ctx.fillStyle = "#fff4ba";
    ctx.beginPath();
    ctx.moveTo(x, tipY - 18);
    ctx.lineTo(x - 8, tipY + 5);
    ctx.lineTo(x + 8, tipY + 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function renderFinish(data) {
    const code = data.code || "";
    const command = code ? `洞天兑换 ${code}` : "";
    const rewards = Array.isArray(data.reward_preview) ? data.reward_preview : [];
    const rewardHtml = rewards.length
      ? rewards.map((item) => `<span>${escapeHtml(item)}</span>`).join("")
      : "<span>本局没有形成奖励。</span>";
    resultTitle.textContent = data.reissued ? "本局已结算" : "本局结算";
    showResult(`
      <span>认可剑意 <strong>${safeNumber(data.accepted_score || data.score)}</strong> ｜破阵 <strong>${safeNumber(data.formations_broken)}</strong> ｜天隙 <strong>${safeNumber(data.gap_hits)}</strong></span>
      ${code ? `<b class="code">${escapeHtml(code)}</b>` : ""}
      ${command ? `<span>复制后回到机器人发送：<strong>${escapeHtml(command)}</strong></span>` : ""}
      ${rewardHtml}
    `);
    copyBtn.disabled = !command;
  }

  function showResult(html) {
    resultLines.innerHTML = html;
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

  function toast(text) {
    toastNode.textContent = text;
    toastNode.classList.remove("show");
    void toastNode.offsetWidth;
    toastNode.classList.add("show");
  }

  function addFloatText(text, type, x, y) {
    const node = document.createElement("span");
    node.className = `float-text ${type || ""}`.trim();
    node.textContent = text;
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    fxLayer.appendChild(node);
    setTimeout(() => node.remove(), type === "break" || type === "gap" ? 1500 : 1200);
  }

  function pulseNode(node) {
    if (!node) return;
    node.classList.remove("pulse");
    void node.offsetWidth;
    node.classList.add("pulse");
  }

  function flashBody(className, ms) {
    document.body.classList.remove(className);
    void document.body.offsetWidth;
    document.body.classList.add(className);
    setTimeout(() => document.body.classList.remove(className), ms);
  }

  function normalize(angle) {
    return ((angle % 360) + 360) % 360;
  }

  function angleDistance(a, b) {
    const diff = Math.abs(normalize(a) - normalize(b));
    return Math.min(diff, 360 - diff);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.addEventListener("resize", resize);
  canvas.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    insertSword();
  });
  startBtn.addEventListener("click", () => {
    startRound().catch((error) => {
      startBtn.disabled = false;
      showResult(`<strong>开局失败</strong><span>${escapeHtml(error.message || String(error))}</span>`);
      result.classList.add("show");
    });
  });
  againBtn.addEventListener("click", () => {
    result.classList.remove("show");
    startRound().catch((error) => {
      showResult(`<strong>开局失败</strong><span>${escapeHtml(error.message || String(error))}</span>`);
      result.classList.add("show");
    });
  });
  settleBtn.addEventListener("click", () => endRound("manual"));
  copyBtn.addEventListener("click", copyCommand);

  resize();
  draw();
  loadConfig().catch((error) => {
    showResult(`<strong>启动失败</strong><span>${escapeHtml(error.message || String(error))}</span>`);
    result.classList.add("show");
  });
})();
