(function () {
  "use strict";

  const GAME_KEY = "zhuiyuan-hundred-floor";
  const API_BASE = `/xiuxian/dongtian/${GAME_KEY}`;
  const W = 400;
  const H = 600;
  const DURATION_SECONDS = 90;
  const PLAYER_SPEED = 4.7;
  const GRAVITY = 0.45;
  const PLAYER_W = 24;
  const PLAYER_H = 32;
  const PLATFORM_H = 10;
  const SPIKE_ZONE_H = 22;
  const STORAGE_KEY = "dongtian_zhuiyuan_best";

  const PLAT_NORMAL = 0;
  const PLAT_MOVING = 1;
  const PLAT_BREAKABLE = 2;
  const PLAT_SPIKE = 3;

  const canvas = document.getElementById("gameCanvas");
  const ctx = canvas.getContext("2d");
  const startScreen = document.getElementById("start-screen");
  const resultScreen = document.getElementById("result-screen");
  const startBtn = document.getElementById("start-btn");
  const restartBtn = document.getElementById("restart-btn");
  const retryFinishBtn = document.getElementById("retry-finish-btn");
  const copyCommandBtn = document.getElementById("copy-command-btn");
  const copyCodeBtn = document.getElementById("copy-code-btn");
  const bestScoreStart = document.getElementById("best-score-start");
  const startStatus = document.getElementById("start-status");
  const resultTitle = document.getElementById("result-title");
  const resultSummary = document.getElementById("result-summary");
  const resultStatus = document.getElementById("result-status");
  const codeBlock = document.getElementById("code-block");
  const commandText = document.getElementById("command-text");
  const codeText = document.getElementById("code-text");
  const rewardPreview = document.getElementById("reward-preview");
  const touchLeftBtn = document.getElementById("touch-left");
  const touchRightBtn = document.getElementById("touch-right");
  const wrapper = document.getElementById("game-wrapper");

  let renderScale = 1;

  let configData = null;
  let session = null;
  let gameState = "loading";
  let player = null;
  let platforms = [];
  let particles = [];
  let keys = {};
  let layers = 0;
  let bestLayers = 0;
  let frameCount = 0;
  let roundStartAt = 0;
  let scrollSpeed = 1;
  let finishPayload = null;
  let finishing = false;
  let loopId = 0;
  let lastTimestamp = 0;
  let hazardRun = 0;
  let spikeRun = 0;

  function setViewportHeight() {
    const height = Math.max(320, Math.round(window.visualViewport?.height || window.innerHeight));
    document.documentElement.style.setProperty("--app-height", `${height}px`);
    setupCanvasScale();
  }

  function setupCanvasScale() {
    const scale = Math.max(1, Math.min(2.5, window.devicePixelRatio || 1));
    if (scale === renderScale && canvas.width === Math.round(W * scale)) return;
    renderScale = scale;
    canvas.width = Math.round(W * renderScale);
    canvas.height = Math.round(H * renderScale);
    ctx.setTransform(renderScale, 0, 0, renderScale, 0, 0);
    ctx.imageSmoothingEnabled = true;
  }

  function endpoint(route) {
    return `${API_BASE}/${route}`;
  }

  async function request(path, options = {}) {
    const res = await fetch(endpoint(path), {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...options
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "洞天入口暂时没有回应。");
    return data;
  }

  async function loadConfig() {
    try {
      configData = await request("config", { method: "GET", headers: undefined });
      startBtn.disabled = false;
      startBtn.textContent = "踏入坠渊";
      startStatus.textContent = "洞天凭证已就绪。";
    } catch (error) {
      startBtn.disabled = true;
      startStatus.textContent = error.message || "洞天入口暂时没有回应。";
    }
  }

  async function startRound() {
    if (!configData?.game_token || finishing) return;
    startBtn.disabled = true;
    startBtn.textContent = "开局中";
    startStatus.textContent = "正在凝结本局凭证。";
    try {
      const round = await request("start", {
        method: "POST",
        body: JSON.stringify({ gameToken: configData.game_token })
      });
      session = {
        gameToken: configData.game_token,
        sessionId: round.session_id,
        roundToken: round.round_token
      };
      startGame();
    } catch (error) {
      startBtn.disabled = false;
      startBtn.textContent = "踏入坠渊";
      startStatus.textContent = error.message || "开局失败，请稍后再试。";
    }
  }

  function startGame() {
    cancelAnimationFrame(loopId);
    startScreen.classList.add("hidden");
    resultScreen.classList.add("hidden");
    codeBlock.classList.add("hidden");
    copyCommandBtn.classList.add("hidden");
    copyCodeBtn.classList.add("hidden");
    retryFinishBtn.classList.add("hidden");
    rewardPreview.innerHTML = "";
    resultStatus.textContent = "";
    finishPayload = null;
    finishing = false;
    layers = 0;
    frameCount = 0;
    scrollSpeed = 1;
    hazardRun = 0;
    spikeRun = 0;
    particles = [];
    platforms = [];
    roundStartAt = Date.now();
    lastTimestamp = 0;
    player = {
      x: W / 2 - PLAYER_W / 2,
      y: H / 2,
      vx: 0,
      vy: 0,
      onGround: false,
      facing: 1,
      walkFrame: 0,
      walkTimer: 0,
      alive: true
    };

    platforms.push(createPlatform(W / 2 - 42, H / 2 + PLAYER_H, 84, PLAT_NORMAL));
    for (let y = H / 2 + 82; y < H + 50; y += 48 + Math.random() * 18) addRandomPlatform(y);
    for (let y = H / 2 - 58; y > 60; y -= 50 + Math.random() * 18) addRandomPlatform(y);

    gameState = "playing";
    loopId = requestAnimationFrame(gameLoop);
  }

  function difficultyByLayer(layer) {
    const t = Math.min(1, Math.max(0, layer / 140));
    const curve = t * t;
    return {
      scrollSpeed: 1.0 + curve * 4.0,
      gapMin: 42 + t * 20,
      gapRand: 24 + t * 18,
      spikeChance: layer < 10 ? 0 : 0.02 + curve * 0.18,
      breakChance: layer < 6 ? 0.03 : 0.08 + curve * 0.16,
      moveChance: 0.12 + t * 0.14
    };
  }

  function createPlatform(x, y, width, type) {
    return {
      x,
      y,
      w: width,
      h: PLATFORM_H,
      type,
      moveSpeed: (Math.random() * 1.35 + 0.7) * (Math.random() < 0.5 ? 1 : -1),
      breaking: false,
      breakTimer: 0,
      broken: false,
      shimmer: Math.random() * Math.PI * 2
    };
  }

  function addRandomPlatform(y) {
    const width = 58 + Math.random() * 44;
    const x = Math.random() * (W - width);
    const type = getRandomPlatformType();
    platforms.push(createPlatform(x, y, width, type));
  }

  function getRandomPlatformType() {
    const difficulty = difficultyByLayer(layers);
    let type = PLAT_NORMAL;
    const roll = Math.random();
    if (roll < difficulty.spikeChance) type = PLAT_SPIKE;
    else if (roll < difficulty.spikeChance + difficulty.breakChance) type = PLAT_BREAKABLE;
    else if (roll < difficulty.spikeChance + difficulty.breakChance + difficulty.moveChance) type = PLAT_MOVING;

    const isHazard = type === PLAT_SPIKE || type === PLAT_BREAKABLE;
    if ((isHazard && hazardRun >= 2) || (type === PLAT_SPIKE && spikeRun >= 1)) {
      type = Math.random() < 0.55 ? PLAT_NORMAL : PLAT_MOVING;
    }
    if (type === PLAT_SPIKE) {
      spikeRun += 1;
      hazardRun += 1;
    } else if (type === PLAT_BREAKABLE) {
      spikeRun = 0;
      hazardRun += 1;
    } else {
      spikeRun = 0;
      hazardRun = 0;
    }
    return type;
  }

  function gameLoop(timestamp) {
    if (gameState !== "playing") return;
    if (!lastTimestamp) lastTimestamp = timestamp;
    let dt = timestamp - lastTimestamp;
    lastTimestamp = timestamp;
    if (dt > 50) dt = 50;
    update();
    render();
    loopId = requestAnimationFrame(gameLoop);
  }

  function update() {
    if (!player) return;
    frameCount += 1;
    const left = remainingSeconds();
    if (left <= 0) {
      endRun("timeout");
      return;
    }

    const difficulty = difficultyByLayer(layers);
    scrollSpeed = difficulty.scrollSpeed;

    if (keys.ArrowLeft || keys.a || keys.A) {
      player.vx = -PLAYER_SPEED;
      player.facing = -1;
    } else if (keys.ArrowRight || keys.d || keys.D) {
      player.vx = PLAYER_SPEED;
      player.facing = 1;
    } else {
      player.vx *= 0.7;
    }

    if (Math.abs(player.vx) > 0.5) {
      player.walkTimer += 1;
      if (player.walkTimer > 6) {
        player.walkTimer = 0;
        player.walkFrame = (player.walkFrame + 1) % 4;
      }
    } else {
      player.walkFrame = 0;
      player.walkTimer = 0;
    }

    player.vy += GRAVITY;
    if (player.vy > 12) player.vy = 12;
    player.x += player.vx;
    player.y += player.vy;
    player.onGround = false;
    if (player.x < 0) player.x = 0;
    if (player.x + PLAYER_W > W) player.x = W - PLAYER_W;

    if (player.vy >= 0) {
      for (const platform of platforms) {
        if (platform.broken) continue;
        if (collideWithPlatform(player, platform)) {
          if (platform.type === PLAT_SPIKE) {
            endRun("spike");
            return;
          }
          if (platform.type === PLAT_BREAKABLE && !platform.breaking) {
            platform.breaking = true;
            platform.breakTimer = 20;
          }
          player.y = platform.y - PLAYER_H;
          player.vy = 0;
          player.onGround = true;
          if (platform.type === PLAT_MOVING) player.x += platform.moveSpeed;
        }
      }
    }

    for (const platform of platforms) {
      platform.y -= scrollSpeed;
      if (platform.type === PLAT_MOVING && !platform.broken) {
        platform.x += platform.moveSpeed;
        if (platform.x <= 0 || platform.x + platform.w >= W) platform.moveSpeed *= -1;
        platform.x = Math.max(0, Math.min(W - platform.w, platform.x));
      }
      if (platform.breaking && !platform.broken) {
        platform.breakTimer -= 1;
        if (platform.breakTimer <= 0) {
          platform.broken = true;
          spawnBreakParticles(platform);
        }
      }
    }

    player.y -= scrollSpeed;
    platforms = platforms.filter((platform) => platform.y > -30);
    let lowestY = 0;
    for (const platform of platforms) lowestY = Math.max(lowestY, platform.y);
    while (lowestY < H + 20) {
      const nextDifficulty = difficultyByLayer(layers);
      lowestY += nextDifficulty.gapMin + Math.random() * nextDifficulty.gapRand;
      addRandomPlatform(lowestY);
    }

    if (frameCount % 30 === 0) layers += 1;
    if (player.y < SPIKE_ZONE_H) {
      endRun("ceiling");
      return;
    }
    if (player.y > H + 50) {
      endRun("fall");
      return;
    }

    for (const particle of particles) {
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += 0.15;
      particle.life -= 1;
    }
    particles = particles.filter((particle) => particle.life > 0);
  }

  function collideWithPlatform(pl, platform) {
    const playerBottom = pl.y + PLAYER_H;
    const playerPrevBottom = playerBottom - pl.vy;
    const feetInRange = playerBottom >= platform.y && playerPrevBottom <= platform.y + 4;
    const horizontalOverlap = pl.x + PLAYER_W > platform.x + 4 && pl.x < platform.x + platform.w - 4;
    return feetInRange && horizontalOverlap;
  }

  function spawnBreakParticles(platform) {
    for (let i = 0; i < 6; i += 1) {
      particles.push({
        x: platform.x + Math.random() * platform.w,
        y: platform.y,
        vx: (Math.random() - 0.5) * 3,
        vy: Math.random() * -3,
        life: 20 + Math.random() * 15,
        color: "#facc15",
        size: 3 + Math.random() * 3
      });
    }
  }

  function endRun(reason) {
    if (gameState !== "playing") return;
    gameState = "ended";
    cancelAnimationFrame(loopId);
    if (player) player.alive = false;
    updateBest();
    finishPayload = {
      gameToken: session?.gameToken,
      sessionId: session?.sessionId,
      roundToken: session?.roundToken,
      layers,
      score: layers,
      elapsedSeconds: elapsedSeconds(),
      deathReason: reason,
      frameCount
    };
    showPendingResult(reason);
    finishRun();
  }

  function showPendingResult(reason) {
    resultTitle.textContent = reason === "timeout" ? "九十息已至" : "坠渊止步";
    resultSummary.textContent = `本次到达 ${layers} 层。`;
    resultStatus.textContent = "正在把坠渊回响凝成兑换码。";
    codeBlock.classList.add("hidden");
    copyCommandBtn.classList.add("hidden");
    copyCodeBtn.classList.add("hidden");
    retryFinishBtn.classList.add("hidden");
    rewardPreview.innerHTML = "";
    resultScreen.classList.remove("hidden");
  }

  async function finishRun() {
    if (!finishPayload || finishing) return;
    finishing = true;
    retryFinishBtn.classList.add("hidden");
    resultStatus.textContent = "正在校验本局成绩。";
    try {
      const issued = await request("finish", {
        method: "POST",
        body: JSON.stringify(finishPayload)
      });
      const code = issued.code || "";
      const acceptedLayers = Number(issued.accepted_layers ?? finishPayload.layers ?? 0);
      const acceptedScore = Number(issued.accepted_score ?? acceptedLayers * 20);
      resultTitle.textContent = "坠渊止步";
      resultSummary.textContent = `认可 ${acceptedLayers} 层｜${acceptedScore} 分。兑换码十分钟内有效。`;
      commandText.textContent = code ? `洞天兑换 ${code}` : "";
      codeText.textContent = code;
      codeBlock.classList.toggle("hidden", !code);
      copyCommandBtn.classList.toggle("hidden", !code);
      copyCodeBtn.classList.toggle("hidden", !code);
      rewardPreview.innerHTML = "";
      for (const item of (issued.reward_preview || []).slice(0, 6)) {
        const line = String(item || "").trim();
        if (!line) continue;
        const span = document.createElement("span");
        span.textContent = line;
        rewardPreview.appendChild(span);
      }
      resultStatus.textContent = issued.message || "回到机器人发送洞天兑换即可领取。";
    } catch (error) {
      resultStatus.textContent = `${error.message || "结算失败"}，可以重试结算本局。`;
      retryFinishBtn.classList.remove("hidden");
    } finally {
      finishing = false;
    }
  }

  function updateBest() {
    if (layers > bestLayers) {
      bestLayers = layers;
      try {
        localStorage.setItem(STORAGE_KEY, String(bestLayers));
      } catch {}
      bestScoreStart.textContent = String(bestLayers);
    }
  }

  function elapsedSeconds() {
    if (!roundStartAt) return 0;
    return Math.max(0, Math.min(DURATION_SECONDS, Math.floor((Date.now() - roundStartAt) / 1000)));
  }

  function remainingSeconds() {
    return Math.max(0, DURATION_SECONDS - elapsedSeconds());
  }

  function render() {
    ctx.clearRect(0, 0, W, H);
    drawBackground();

    for (const platform of platforms) {
      if (!platform.broken) drawPlatform(platform);
    }
    drawAbyssMist();
    if (player?.alive) drawPlayer();
    drawParticles();
    drawCeilingSpikes();
    drawHud();
  }

  function drawBackground() {
    const pulse = Math.sin(frameCount * 0.015);
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "#172032");
    bg.addColorStop(0.36, "#0d172b");
    bg.addColorStop(0.72, "#080d1c");
    bg.addColorStop(1, "#03050d");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    const halo = ctx.createRadialGradient(W / 2, 92, 10, W / 2, 92, 210);
    halo.addColorStop(0, `rgba(45, 212, 191, ${0.2 + pulse * 0.03})`);
    halo.addColorStop(0.46, "rgba(56, 189, 248, 0.06)");
    halo.addColorStop(1, "rgba(2, 6, 23, 0)");
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, W, H);

    const bottom = ctx.createRadialGradient(W / 2, H + 70, 20, W / 2, H + 70, 260);
    bottom.addColorStop(0, "rgba(20, 184, 166, 0.18)");
    bottom.addColorStop(0.44, "rgba(124, 58, 237, 0.08)");
    bottom.addColorStop(1, "rgba(2, 6, 23, 0)");
    ctx.fillStyle = bottom;
    ctx.fillRect(0, 0, W, H);

    ctx.strokeStyle = "rgba(148, 163, 184, 0.032)";
    ctx.lineWidth = 1;
    for (let x = 18; x < W; x += 44) {
      ctx.beginPath();
      ctx.moveTo(x + Math.sin(frameCount * 0.01 + x) * 3, 0);
      ctx.lineTo(x - 18, H);
      ctx.stroke();
    }

    ctx.save();
    ctx.globalAlpha = 0.14;
    ctx.strokeStyle = "#67e8f9";
    ctx.lineWidth = 1;
    for (let i = 0; i < 7; i += 1) {
      const y = ((i * 112 + frameCount * 0.42) % (H + 130)) - 76;
      const x = i % 2 === 0 ? 34 : W - 58;
      ctx.beginPath();
      ctx.arc(x, y, 17 + (i % 3) * 4, 0, Math.PI * 2);
      ctx.moveTo(x - 20, y);
      ctx.lineTo(x + 20, y);
      ctx.moveTo(x, y - 20);
      ctx.lineTo(x, y + 20);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPlatform(platform) {
    const colors = {
      [PLAT_NORMAL]: { top: "#86efac", body: "#166534", edge: "#bbf7d0", glow: "rgba(34,197,94,0.28)" },
      [PLAT_MOVING]: { top: "#7dd3fc", body: "#1d4ed8", edge: "#e0f2fe", glow: "rgba(56,189,248,0.3)" },
      [PLAT_BREAKABLE]: { top: "#fde68a", body: "#a16207", edge: "#fef3c7", glow: "rgba(250,204,21,0.26)" },
      [PLAT_SPIKE]: { top: "#fda4af", body: "#9f1239", edge: "#ffe4e6", glow: "rgba(251,113,133,0.3)" }
    };
    const c = colors[platform.type];
    let shakeX = 0;
    if (platform.breaking) {
      shakeX = (Math.random() - 0.5) * 4;
      ctx.globalAlpha = Math.max(0.32, platform.breakTimer / 20);
    }
    const x = platform.x + shakeX;
    const y = platform.y;
    const shimmer = Math.sin(frameCount * 0.06 + platform.shimmer) * 0.45 + 0.55;

    ctx.save();
    ctx.shadowBlur = 10 + shimmer * 4;
    ctx.shadowColor = c.glow;
    const stone = ctx.createLinearGradient(0, y, 0, y + platform.h + 7);
    stone.addColorStop(0, c.top);
    stone.addColorStop(0.28, c.body);
    stone.addColorStop(1, "#020617");
    ctx.fillStyle = stone;
    roundRect(x, y + 1, platform.w, platform.h + 5, 5);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.fillStyle = c.top;
    roundRect(x + 4, y, platform.w - 8, 4, 3);
    ctx.fill();

    ctx.strokeStyle = `rgba(236, 253, 245, ${0.14 + shimmer * 0.16})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + 8, y + 2);
    ctx.lineTo(x + platform.w - 8, y + 2);
    ctx.stroke();

    ctx.fillStyle = "rgba(15, 23, 42, 0.34)";
    for (let sx = x + 12; sx < x + platform.w - 10; sx += 22) {
      ctx.fillRect(sx, y + 7, 10, 1.4);
    }

    ctx.strokeStyle = c.edge;
    ctx.globalAlpha = 0.22;
    ctx.beginPath();
    ctx.moveTo(x + 8, y + platform.h + 4);
    ctx.quadraticCurveTo(x + platform.w * 0.5, y + platform.h + 9, x + platform.w - 8, y + platform.h + 4);
    ctx.stroke();
    ctx.globalAlpha = platform.breaking ? Math.max(0.32, platform.breakTimer / 20) : 1;

    if (platform.type === PLAT_SPIKE) {
      ctx.fillStyle = "#fecdd3";
      ctx.strokeStyle = "rgba(127, 29, 29, 0.52)";
      ctx.lineWidth = 1;
      for (let sx = x + 5; sx < x + platform.w - 6; sx += 11) {
        ctx.beginPath();
        ctx.moveTo(sx, y);
        ctx.lineTo(sx + 4.5, y - 9);
        ctx.lineTo(sx + 9, y);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    if (platform.type === PLAT_MOVING) {
      ctx.fillStyle = "rgba(224, 242, 254, 0.88)";
      ctx.font = "900 10px Microsoft YaHei, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(platform.moveSpeed > 0 ? "流" : "返", x + platform.w / 2, y + 11);
    }

    if (platform.type === PLAT_BREAKABLE) {
      ctx.strokeStyle = "rgba(69, 26, 3, 0.56)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x + platform.w * 0.28, y + 1);
      ctx.lineTo(x + platform.w * 0.4, y + platform.h + 4);
      ctx.moveTo(x + platform.w * 0.7, y);
      ctx.lineTo(x + platform.w * 0.62, y + platform.h + 5);
      ctx.stroke();
    }

    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function drawAbyssMist() {
    ctx.save();
    for (let i = 0; i < 4; i += 1) {
      const y = ((frameCount * (0.18 + i * 0.04) + i * 156) % (H + 120)) - 60;
      const mist = ctx.createLinearGradient(0, y, W, y + 38);
      mist.addColorStop(0, "rgba(45, 212, 191, 0)");
      mist.addColorStop(0.42, `rgba(45, 212, 191, ${0.026 + i * 0.008})`);
      mist.addColorStop(1, "rgba(14, 165, 233, 0)");
      ctx.fillStyle = mist;
      ctx.fillRect(0, y, W, 42);
    }
    ctx.restore();
  }

  function drawPlayer() {
    const px = Math.round(player.x);
    const py = Math.round(player.y);
    const cx = px + PLAYER_W / 2;
    const f = player.facing;
    const bob = player.onGround ? Math.sin(frameCount * 0.18) * 0.6 : -1.5;
    const robeSway = player.onGround && Math.abs(player.vx) > 0.5 ? [-1.6, 0.5, 1.6, 0.5][player.walkFrame] : 0;

    ctx.save();
    ctx.fillStyle = "rgba(0, 0, 0, 0.34)";
    ctx.beginPath();
    ctx.ellipse(cx, py + PLAYER_H + 2, 15, 4.2, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 18;
    ctx.shadowColor = "rgba(94, 234, 212, 0.28)";
    ctx.strokeStyle = "rgba(94, 234, 212, 0.38)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.ellipse(cx, py + 18 + bob, 18, 25, -0.12 * f, 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.fillStyle = "#111827";
    ctx.beginPath();
    ctx.moveTo(cx - 7, py + 2 + bob);
    ctx.quadraticCurveTo(cx, py - 4 + bob, cx + 7, py + 2 + bob);
    ctx.lineTo(cx + 8, py + 12 + bob);
    ctx.quadraticCurveTo(cx, py + 16 + bob, cx - 8, py + 12 + bob);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#fde68a";
    ctx.beginPath();
    ctx.arc(cx + f * 1.4, py + 7 + bob, 5.6, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "#fef3c7";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(cx - 5, py + 2 + bob);
    ctx.lineTo(cx + 5, py + 2 + bob);
    ctx.stroke();

    const robe = ctx.createLinearGradient(0, py + 10, 0, py + PLAYER_H + 2);
    robe.addColorStop(0, "#34d399");
    robe.addColorStop(0.55, "#0f766e");
    robe.addColorStop(1, "#064e3b");
    ctx.fillStyle = robe;
    ctx.beginPath();
    ctx.moveTo(cx - 8, py + 13 + bob);
    ctx.lineTo(cx + 8, py + 13 + bob);
    ctx.lineTo(cx + 12 + robeSway, py + 30);
    ctx.quadraticCurveTo(cx, py + 35, cx - 12 + robeSway, py + 30);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "rgba(240, 253, 250, 0.72)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, py + 14 + bob);
    ctx.lineTo(cx + robeSway * 0.7, py + 31);
    ctx.stroke();

    ctx.strokeStyle = "#fef3c7";
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(cx - f * 7, py + 17 + bob);
    ctx.lineTo(cx - f * 14, py + 24);
    ctx.moveTo(cx + f * 7, py + 17 + bob);
    ctx.lineTo(cx + f * 14, py + 12);
    ctx.stroke();

    ctx.strokeStyle = "rgba(125, 211, 252, 0.92)";
    ctx.lineWidth = 1.6;
    ctx.shadowBlur = 10;
    ctx.shadowColor = "rgba(125, 211, 252, 0.5)";
    ctx.beginPath();
    ctx.moveTo(cx + f * 13, py + 11);
    ctx.lineTo(cx + f * 24, py + 2);
    ctx.stroke();

    ctx.shadowBlur = 0;
    ctx.fillStyle = "#0f172a";
    ctx.beginPath();
    ctx.arc(cx + f * 2.5, py + 7 + bob, 1.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "rgba(251, 191, 36, 0.74)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, py + 18 + bob, 10.5, 0.16 * Math.PI, 0.86 * Math.PI);
    ctx.stroke();
    ctx.restore();
  }

  function drawParticles() {
    for (const particle of particles) {
      ctx.globalAlpha = Math.min(1, particle.life / 40);
      ctx.shadowBlur = 8;
      ctx.shadowColor = particle.color;
      ctx.fillStyle = particle.color;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.size / 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
  }

  function drawCeilingSpikes() {
    const gradient = ctx.createLinearGradient(0, 0, 0, SPIKE_ZONE_H + 20);
    gradient.addColorStop(0, "rgba(220, 38, 38, 0.78)");
    gradient.addColorStop(0.62, "rgba(127, 29, 29, 0.18)");
    gradient.addColorStop(1, "rgba(248, 113, 113, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, SPIKE_ZONE_H + 20);
    ctx.fillStyle = "#fda4af";
    ctx.strokeStyle = "rgba(127, 29, 29, 0.7)";
    ctx.lineWidth = 1;
    for (let x = -4; x < W; x += 18) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + 9, SPIKE_ZONE_H + 2);
      ctx.lineTo(x + 18, 0);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }

  function drawHud() {
    const danger = remainingSeconds() <= 15 ? Math.sin(frameCount * 0.18) * 0.18 + 0.82 : 1;
    ctx.save();
    ctx.font = "900 17px Microsoft YaHei, sans-serif";
    ctx.textAlign = "left";
    drawJadeBadge(10, 28, 104, 30, "rgba(6, 78, 59, 0.68)", "rgba(167, 243, 208, 0.28)");
    ctx.fillStyle = "#f8fafc";
    ctx.globalAlpha = danger;
    ctx.fillText(`${remainingSeconds()} 息`, 20, 49);
    ctx.globalAlpha = 1;

    ctx.textAlign = "right";
    drawJadeBadge(W - 124, 28, 114, 30, "rgba(69, 26, 3, 0.62)", "rgba(253, 230, 138, 0.28)");
    ctx.fillStyle = "#fef3c7";
    ctx.fillText(`${layers} 层`, W - 20, 49);

    ctx.textAlign = "center";
    ctx.font = "900 12px Microsoft YaHei, sans-serif";
    ctx.fillStyle = "rgba(226, 232, 240, 0.78)";
    ctx.fillText("坠渊百层", W / 2, 22);

    const progress = elapsedSeconds() / DURATION_SECONDS;
    const bar = ctx.createLinearGradient(76, 67, W - 76, 67);
    bar.addColorStop(0, "#5eead4");
    bar.addColorStop(0.6, "#38bdf8");
    bar.addColorStop(1, "#fbbf24");
    ctx.fillStyle = "rgba(15, 23, 42, 0.72)";
    roundRect(76, 64, W - 152, 5, 3);
    ctx.fill();
    ctx.fillStyle = bar;
    roundRect(76, 64, (W - 152) * progress, 5, 3);
    ctx.fill();
    ctx.restore();
  }

  function drawJadeBadge(x, y, w, h, fill, stroke) {
    ctx.save();
    ctx.shadowBlur = 12;
    ctx.shadowColor = stroke;
    ctx.fillStyle = fill;
    roundRect(x, y, w, h, 8);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1;
    roundRect(x + 0.5, y + 0.5, w - 1, h - 1, 8);
    ctx.stroke();
    ctx.restore();
  }

  function roundRect(x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h - radius);
    ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    ctx.lineTo(x + radius, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  function bindTouchButton(button, key) {
    const down = (event) => {
      event.preventDefault();
      keys[key] = true;
      button.classList.add("pressed");
    };
    const up = (event) => {
      event?.preventDefault?.();
      keys[key] = false;
      button.classList.remove("pressed");
    };
    button.addEventListener("touchstart", down, { passive: false });
    button.addEventListener("touchend", up, { passive: false });
    button.addEventListener("touchcancel", up, { passive: false });
    button.addEventListener("mousedown", down);
    button.addEventListener("mouseup", up);
    button.addEventListener("mouseleave", up);
  }

  async function copyText(button, text, copiedText) {
    const original = button.textContent;
    try {
      await writeClipboard(text);
      button.textContent = copiedText;
    } catch {
      button.textContent = "请长按复制";
    }
    setTimeout(() => {
      button.textContent = original;
    }, 1500);
  }

  async function writeClipboard(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    document.execCommand("copy");
    area.remove();
  }

  function initBest() {
    try {
      bestLayers = Math.max(0, Number(localStorage.getItem(STORAGE_KEY) || 0));
    } catch {
      bestLayers = 0;
    }
    bestScoreStart.textContent = String(bestLayers);
  }

  document.addEventListener("keydown", (event) => {
    keys[event.key] = true;
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(event.key)) event.preventDefault();
  });
  document.addEventListener("keyup", (event) => {
    keys[event.key] = false;
  });
  startBtn.addEventListener("click", startRound);
  restartBtn.addEventListener("click", startRound);
  retryFinishBtn.addEventListener("click", finishRun);
  copyCommandBtn.addEventListener("click", (event) => copyText(event.currentTarget, commandText.textContent, "已复制命令"));
  copyCodeBtn.addEventListener("click", (event) => copyText(event.currentTarget, codeText.textContent, "已复制兑换码"));
  bindTouchButton(touchLeftBtn, "ArrowLeft");
  bindTouchButton(touchRightBtn, "ArrowRight");
  setViewportHeight();
  window.addEventListener("resize", setViewportHeight);
  window.addEventListener("orientationchange", setViewportHeight);
  window.visualViewport?.addEventListener("resize", setViewportHeight);
  window.visualViewport?.addEventListener("scroll", setViewportHeight);
  initBest();
  resizeObserver();
  loadConfig();

  function resizeObserver() {
    const update = () => {
      wrapper.style.setProperty("--noop", String(Date.now()));
    };
    window.addEventListener("resize", update);
    update();
  }
})();
