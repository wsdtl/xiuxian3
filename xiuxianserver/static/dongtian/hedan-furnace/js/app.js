const API_BASE = "/xiuxian/dongtian/hedan-furnace";
const TILE_NAMES = {
  2: "一转丹胚",
  4: "二转丹胚",
  8: "灵露丹",
  16: "玉髓丹",
  32: "玄元丹",
  64: "紫府丹",
  128: "金纹丹",
  256: "九窍丹",
  512: "大还丹",
  1024: "天元丹",
  2048: "合道丹",
  4096: "造化丹",
};

const state = {
  gameToken: "",
  sessionId: "",
  roundToken: "",
  duration: 150,
  difficulty: null,
  board: emptyBoard(),
  score: 0,
  maxTile: 2,
  mergeCount: 0,
  moveCount: 0,
  startedAt: 0,
  timerId: 0,
  running: false,
  finishing: false,
  minSettleSeconds: 10,
};

const el = {
  board: document.querySelector("#board"),
  score: document.querySelector("#score"),
  maxTile: document.querySelector("#maxTile"),
  mergeCount: document.querySelector("#mergeCount"),
  moveCount: document.querySelector("#moveCount"),
  timeLeft: document.querySelector("#timeLeft"),
  difficultyLabel: document.querySelector("#difficultyLabel"),
  difficultyText: document.querySelector("#difficultyText"),
  startButton: document.querySelector("#startButton"),
  finishButton: document.querySelector("#finishButton"),
  againButton: document.querySelector("#againButton"),
  statusText: document.querySelector("#statusText"),
  settlement: document.querySelector("#settlement"),
  settleMessage: document.querySelector("#settleMessage"),
  codeBlock: document.querySelector("#codeBlock"),
  commandBox: document.querySelector("#commandBox"),
  codeBox: document.querySelector("#codeBox"),
  rewardPreview: document.querySelector("#rewardPreview"),
  copyCommandButton: document.querySelector("#copyCommandButton"),
  copyCodeButton: document.querySelector("#copyCodeButton"),
};

bootstrap();

async function bootstrap() {
  bindInput();
  render();
  try {
    const data = await getJson(`${API_BASE}/config`);
    state.gameToken = data.game_token;
    const config = data.config || {};
    state.duration = Number(config.game_duration || 150);
    state.minSettleSeconds = Number(config.round_min_seconds || state.minSettleSeconds || 10);
    el.timeLeft.textContent = String(state.duration);
    el.statusText.textContent = "洞天凭证已就绪。";
    el.startButton.disabled = false;
  } catch (error) {
    el.statusText.textContent = messageOf(error, "洞天凭证获取失败，请稍后重进。");
    el.startButton.disabled = true;
  }
}

el.startButton.addEventListener("click", startRound);
el.finishButton.addEventListener("click", () => finishRound("主动收火。"));
el.againButton.addEventListener("click", () => {
  if (!el.settlement.hidden && state.roundToken && !el.codeBox.textContent.trim()) {
    finishRound("重试收火。");
    return;
  }
  startRound();
});
el.copyCommandButton.addEventListener("click", () => copySettlementText(el.commandBox.textContent, el.copyCommandButton, "已复制兑换命令"));
el.copyCodeButton.addEventListener("click", () => copySettlementText(el.codeBox.textContent, el.copyCodeButton, "已复制兑换码"));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    settleIfExpired();
  }
});
window.addEventListener("focus", settleIfExpired);

async function startRound() {
  if (!state.gameToken || state.running) {
    return;
  }
  resetRound();
  el.statusText.textContent = "炉火正在升起。";
  el.startButton.disabled = true;
  try {
    const data = await postJson(`${API_BASE}/start`, { gameToken: state.gameToken });
    state.sessionId = data.session_id;
    state.roundToken = data.round_token;
    state.duration = Number(data.game_duration || state.duration || 150);
    state.minSettleSeconds = Number(data.round_min_seconds || state.minSettleSeconds || 10);
    state.difficulty = data.difficulty || { label: "真火炉", description: "炉火平稳。", start_tiles: 2, four_rate: 0.1 };
    el.difficultyLabel.textContent = state.difficulty.label || "真火炉";
    el.difficultyText.textContent = state.difficulty.description || "炉火平稳。";
    seedBoard(Number(state.difficulty.start_tiles || 2));
    state.startedAt = Date.now();
    state.running = true;
    el.statusText.textContent = "滑动或方向键合丹。";
    el.finishButton.disabled = false;
    tick();
    state.timerId = window.setInterval(tick, 250);
    render();
  } catch (error) {
    el.statusText.textContent = messageOf(error, "开炉失败，请重新进入洞天。");
    el.startButton.disabled = false;
  }
}

function resetRound() {
  window.clearInterval(state.timerId);
  state.sessionId = "";
  state.roundToken = "";
  state.board = emptyBoard();
  state.score = 0;
  state.maxTile = 2;
  state.mergeCount = 0;
  state.moveCount = 0;
  state.startedAt = 0;
  state.timerId = 0;
  state.running = false;
  state.finishing = false;
  el.finishButton.disabled = true;
  el.settlement.hidden = true;
  el.againButton.textContent = "再开一炉";
  el.codeBlock.hidden = true;
  el.codeBox.textContent = "";
  el.commandBox.textContent = "";
  el.rewardPreview.innerHTML = "";
  el.copyCommandButton.hidden = true;
  el.copyCodeButton.hidden = true;
  el.timeLeft.textContent = String(state.duration);
  render();
}

function seedBoard(count) {
  for (let index = 0; index < Math.max(2, Math.min(4, count)); index += 1) {
    spawnTile();
  }
}

function tick() {
  if (!state.running) {
    return;
  }
  const elapsed = elapsedSeconds();
  const left = Math.max(0, state.duration - elapsed);
  el.timeLeft.textContent = String(left);
  if (left <= 0) {
    finishRound("丹炉火候已满。");
  }
}

function settleIfExpired() {
  if (state.running && !state.finishing && elapsedSeconds() >= state.duration) {
    finishRound("丹炉火候已满。");
  }
}

function bindInput() {
  document.addEventListener("keydown", (event) => {
    const dir = {
      ArrowUp: "up",
      KeyW: "up",
      ArrowDown: "down",
      KeyS: "down",
      ArrowLeft: "left",
      KeyA: "left",
      ArrowRight: "right",
      KeyD: "right",
    }[event.code];
    if (dir) {
      event.preventDefault();
      move(dir);
    }
  });

  let startX = 0;
  let startY = 0;
  el.board.addEventListener("pointerdown", (event) => {
    startX = event.clientX;
    startY = event.clientY;
    el.board.setPointerCapture?.(event.pointerId);
  });
  el.board.addEventListener("pointerup", (event) => {
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) {
      return;
    }
    move(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up"));
  });
}

function move(direction) {
  if (!state.running || state.finishing) {
    return;
  }
  const before = JSON.stringify(state.board);
  let gained = 0;
  let merged = 0;
  const size = 4;
  const next = emptyBoard();

  for (let i = 0; i < size; i += 1) {
    const line = readLine(state.board, direction, i);
    const collapsed = collapseLine(line);
    gained += collapsed.score;
    merged += collapsed.merges;
    writeLine(next, direction, i, collapsed.line);
  }

  if (before === JSON.stringify(next)) {
    return;
  }
  state.board = next;
  state.score += gained;
  state.mergeCount += merged;
  state.moveCount += 1;
  state.maxTile = Math.max(state.maxTile, boardMax(state.board));
  spawnTile();
  render(true);
  if (isGameOver()) {
    finishRound("丹炉已满，提前收火。");
  }
}

function readLine(board, direction, index) {
  if (direction === "left") return board[index].slice();
  if (direction === "right") return board[index].slice().reverse();
  const line = [];
  for (let y = 0; y < 4; y += 1) {
    line.push(board[y][index]);
  }
  return direction === "down" ? line.reverse() : line;
}

function writeLine(board, direction, index, line) {
  const values = direction === "right" || direction === "down" ? line.slice().reverse() : line;
  if (direction === "left" || direction === "right") {
    board[index] = values;
    return;
  }
  for (let y = 0; y < 4; y += 1) {
    board[y][index] = values[y];
  }
}

function collapseLine(line) {
  const values = line.filter(Boolean);
  const output = [];
  let score = 0;
  let merges = 0;
  for (let index = 0; index < values.length; index += 1) {
    if (values[index] === values[index + 1]) {
      const merged = values[index] * 2;
      output.push(merged);
      score += merged;
      merges += 1;
      index += 1;
    } else {
      output.push(values[index]);
    }
  }
  while (output.length < 4) {
    output.push(0);
  }
  return { line: output, score, merges };
}

function spawnTile() {
  const empty = [];
  for (let y = 0; y < 4; y += 1) {
    for (let x = 0; x < 4; x += 1) {
      if (!state.board[y][x]) {
        empty.push([y, x]);
      }
    }
  }
  if (!empty.length) {
    return;
  }
  const [y, x] = empty[Math.floor(Math.random() * empty.length)];
  const fourRate = Number(state.difficulty?.four_rate ?? 0.1);
  state.board[y][x] = Math.random() < fourRate ? 4 : 2;
  state.maxTile = Math.max(state.maxTile, state.board[y][x]);
}

function isGameOver() {
  if (state.board.some((row) => row.some((value) => value === 0))) {
    return false;
  }
  for (let y = 0; y < 4; y += 1) {
    for (let x = 0; x < 4; x += 1) {
      const value = state.board[y][x];
      if (state.board[y]?.[x + 1] === value || state.board[y + 1]?.[x] === value) {
        return false;
      }
    }
  }
  return true;
}

async function finishRound(reason) {
  if (state.finishing || !state.roundToken) {
    return;
  }
  if (!ensureSettleReady()) {
    return;
  }
  state.finishing = true;
  state.running = false;
  window.clearInterval(state.timerId);
  el.statusText.textContent = "正在收火结算。";
  el.finishButton.disabled = true;
  try {
    const result = await postJson(`${API_BASE}/finish`, {
      gameToken: state.gameToken,
      sessionId: state.sessionId,
      roundToken: state.roundToken,
      score: state.score,
      maxTile: state.maxTile,
      mergeCount: state.mergeCount,
      moveCount: state.moveCount,
      elapsedSeconds: elapsedSeconds(),
    });
    el.settleMessage.textContent = result.message || reason || "丹成。";
    const code = result.code || "";
    el.codeBlock.hidden = !code;
    el.commandBox.textContent = code ? `洞天兑换 ${code}` : "";
    el.codeBox.textContent = code;
    el.rewardPreview.innerHTML = "";
    for (const line of result.reward_preview || []) {
      const li = document.createElement("li");
      li.textContent = line;
      el.rewardPreview.appendChild(li);
    }
    el.settlement.hidden = false;
    el.statusText.textContent = "兑换码十分钟内有效。";
    el.copyCommandButton.hidden = !code;
    el.copyCodeButton.hidden = !code;
    el.againButton.textContent = "再开一炉";
    el.startButton.disabled = false;
    el.finishButton.disabled = true;
  } catch (error) {
    if (isTooEarlyError(error)) {
      resumeRoundAfterTooEarly(error);
      return;
    }
    el.settleMessage.textContent = `${messageOf(error, "结算失败")}，可以重试结算本局。`;
    el.codeBox.textContent = "";
    el.commandBox.textContent = "";
    el.codeBlock.hidden = true;
    el.rewardPreview.innerHTML = "";
    el.settlement.hidden = false;
    el.statusText.textContent = "请先结算本局。";
    el.againButton.textContent = "结算本局";
    el.copyCommandButton.hidden = true;
    el.copyCodeButton.hidden = true;
    el.startButton.disabled = true;
    el.finishButton.disabled = false;
  } finally {
    state.finishing = false;
  }
}

function ensureSettleReady() {
  const minSeconds = Math.max(0, Number(state.minSettleSeconds || 0));
  const elapsed = elapsedSeconds();
  if (elapsed >= minSeconds) {
    return true;
  }
  const wait = Math.max(1, minSeconds - elapsed);
  el.statusText.textContent = `炉火未稳，还需 ${wait} 秒后才能收火。`;
  el.settlement.hidden = true;
  return false;
}

function isTooEarlyError(error) {
  return messageOf(error, "").includes("结束过快");
}

function resumeRoundAfterTooEarly(error) {
  state.running = true;
  el.settlement.hidden = true;
  el.statusText.textContent = messageOf(error, "炉火未稳，请稍后再收火。");
  el.startButton.disabled = true;
  el.finishButton.disabled = false;
  if (!state.timerId) {
    tick();
    state.timerId = window.setInterval(tick, 250);
  }
}

function render(bump = false) {
  el.board.innerHTML = "";
  for (let y = 0; y < 4; y += 1) {
    for (let x = 0; x < 4; x += 1) {
      const value = state.board[y][x];
      const tile = document.createElement("div");
      tile.className = `tile ${value ? `v${Math.min(value, 4096)}` : ""}${bump && value ? " bump" : ""}`;
      if (value) {
        tile.dataset.value = String(value);
        tile.dataset.tier = value < 128 ? "small" : value < 1024 ? "medium" : "large";
        const name = document.createElement("span");
        name.className = "tile-name";
        name.textContent = TILE_NAMES[value] || "丹胚";
        const number = document.createElement("span");
        number.className = "tile-number";
        number.textContent = String(value);
        tile.append(name, number);
      }
      el.board.appendChild(tile);
    }
  }
  el.score.textContent = String(state.score);
  el.maxTile.textContent = String(state.maxTile);
  el.mergeCount.textContent = String(state.mergeCount);
  el.moveCount.textContent = String(state.moveCount);
  if (bump) {
    window.setTimeout(() => {
      document.querySelectorAll(".tile.bump").forEach((tile) => tile.classList.remove("bump"));
    }, 130);
  }
}

function emptyBoard() {
  return Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => 0));
}

function boardMax(board) {
  return Math.max(2, ...board.flat());
}

function elapsedSeconds() {
  if (!state.startedAt) {
    return 0;
  }
  return Math.min(state.duration, Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000)));
}

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  return parseJsonResponse(response);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse(response);
}

async function copySettlementText(text, button, copiedText) {
  const original = button.textContent;
  const value = String(text || "").trim();
  if (!value) {
    return;
  }
  try {
    await writeClipboard(value);
    button.textContent = copiedText;
  } catch {
    button.textContent = "请长按复制";
  }
  window.setTimeout(() => {
    button.textContent = original;
  }, 1600);
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

async function parseJsonResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "请求失败");
  }
  return data;
}

function messageOf(error, fallback) {
  return error instanceof Error && error.message ? error.message : fallback;
}
