import type { LingguoDifficulty, LingguoRoundResponse } from "../api/dongtian";

const DRAG_PX = 12;

export interface FruitTheme {
  id: string;
  name: string;
  file: string;
}

const FRUITS: readonly FruitTheme[] = [
  { id: "apple", name: "朱果", file: "apple.svg" },
  { id: "orange", name: "橙灵果", file: "orange.svg" },
  { id: "strawberry", name: "赤莓", file: "strawberry.svg" },
  { id: "cherry", name: "樱珠", file: "cherry.svg" },
  { id: "watermelon", name: "碧瓤瓜", file: "watermelon.svg" },
];

type GridCell = number | null;
type Grid = GridCell[][];
type ToastKind = "info" | "bad" | "good";

export interface RoundSettlePayload {
  score: number;
  clearedCells: number;
  validClears: number;
  elapsedSeconds: number;
  fruitName: string;
  fruitFile: string;
  difficultyLabel: string;
  sessionId: string;
  roundToken: string;
}

export interface FruitGameElements {
  boardEl: HTMLElement;
  boardWrap: HTMLElement;
  selRect: HTMLElement;
  scoreEl: HTMLElement;
  clearedCellsEl: HTMLElement;
  validClearsEl: HTMLElement;
  forbiddenEl: HTMLElement;
  difficultyLabelEl: HTMLElement;
  difficultyDescEl: HTMLElement;
  fruitNameEl: HTMLElement;
  fruitImgEl: HTMLImageElement;
  toastEl: HTMLElement;
  newGameBtns: HTMLButtonElement[];
  settleBtns: HTMLButtonElement[];
  timerFillEl: HTMLElement;
  timerLabelEl: HTMLElement;
  onRoundSettle?: (payload: RoundSettlePayload) => void;
  onNewRound?: () => void;
}

export interface NewGameOptions {
  round: LingguoRoundResponse;
  silent?: boolean;
}

export interface FruitGameApi {
  newGame: (opts: NewGameOptions) => void;
  setNewRoundHandler: (handler: (() => void) | null) => void;
  destroy: () => void;
}

interface CellPos {
  r: number;
  c: number;
}

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!;
}

export function assetUrl(path: string): string {
  const cleanPath = path.replace(/^\/+/, "");
  return `${import.meta.env.BASE_URL}${cleanPath}`;
}

export function mountFruitGame(els: FruitGameElements): FruitGameApi {
  const {
    boardEl,
    boardWrap,
    selRect,
    scoreEl,
    clearedCellsEl,
    validClearsEl,
    forbiddenEl,
    difficultyLabelEl,
    difficultyDescEl,
    fruitNameEl,
    fruitImgEl,
    toastEl,
    newGameBtns,
    settleBtns,
    timerFillEl,
    timerLabelEl,
    onRoundSettle,
    onNewRound,
  } = els;

  const playDigitWeight: readonly number[] = [
    0, 14, 14, 13, 12, 11, 9, 8, 6, 5,
  ];
  const sumTenAdjacentPairs: readonly (readonly [number, number])[] = [
    [1, 9],
    [9, 1],
    [2, 8],
    [8, 2],
    [3, 7],
    [7, 3],
    [4, 6],
    [6, 4],
    [5, 5],
  ];

  let requestNewRound: (() => void) | null = null;
  let round: LingguoRoundResponse | null = null;
  let grid: Grid = [];
  let theme!: FruitTheme;
  let forbidden = 0;
  let score = 0;
  let clearedCells = 0;
  let validClears = 0;
  let roundStartedAt = 0;
  let roundEndTime = 0;
  let timerRaf: number | null = null;
  let roundClosed = true;
  let pendingSettleTimer: ReturnType<typeof setTimeout> | undefined;

  let pointerId: number | null = null;
  let startX = 0;
  let startY = 0;
  let startCell: CellPos | null = null;
  let dragActive = false;
  let currentEndCell: CellPos | null = null;
  let hideToastTimer: ReturnType<typeof setTimeout> | undefined;

  function difficulty(): LingguoDifficulty {
    return round!.difficulty;
  }

  function durationMs(): number {
    return Math.max(1, round!.game_duration) * 1000;
  }

  function rowCount(): number {
    return Math.max(1, round!.rows);
  }

  function colCount(): number {
    return Math.max(1, round!.cols);
  }

  function sumTarget(): number {
    return Math.max(1, round!.sum_target);
  }

  function hardOn(): boolean {
    return Boolean(difficulty().forbidden_enabled);
  }

  function randomDigit(): number {
    return 1 + Math.floor(Math.random() * 9);
  }

  function weightPickFromPool(pool: readonly number[]): number {
    let total = 0;
    for (const digit of pool) total += playDigitWeight[digit] ?? 1;
    let roll = Math.random() * total;
    for (const digit of pool) {
      roll -= playDigitWeight[digit] ?? 1;
      if (roll <= 0) return digit;
    }
    return pool[pool.length - 1]!;
  }

  function randomDigitRareForbidden(value: number): number {
    const rate = Math.max(0, Math.min(0.5, difficulty().forbidden_cell_rate));
    if (Math.random() < rate) return value;
    const pool = [1, 2, 3, 4, 5, 6, 7, 8, 9].filter((digit) => digit !== value);
    return weightPickFromPool(pool);
  }

  function rollNewCellDigit(): number {
    if (hardOn()) return randomDigitRareForbidden(forbidden);
    return weightPickFromPool([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  }

  function cellKey(row: number, col: number): string {
    return `${row},${col}`;
  }

  function sprinkleSum10Pairs(pairCount: number): void {
    const used = new Set<string>();
    let placed = 0;
    const maxRows = rowCount();
    const maxCols = colCount();
    for (let attempt = 0; attempt < 500 && placed < pairCount; attempt++) {
      const horizontal = Math.random() < 0.5;
      const pair = pick(sumTenAdjacentPairs);
      if (horizontal) {
        const row = Math.floor(Math.random() * maxRows);
        const col = Math.floor(Math.random() * Math.max(1, maxCols - 1));
        const first = cellKey(row, col);
        const second = cellKey(row, col + 1);
        if (used.has(first) || used.has(second) || col + 1 >= maxCols) continue;
        grid[row][col] = pair[0];
        grid[row][col + 1] = pair[1];
        used.add(first);
        used.add(second);
      } else {
        const row = Math.floor(Math.random() * Math.max(1, maxRows - 1));
        const col = Math.floor(Math.random() * maxCols);
        const first = cellKey(row, col);
        const second = cellKey(row + 1, col);
        if (used.has(first) || used.has(second) || row + 1 >= maxRows) continue;
        grid[row][col] = pair[0];
        grid[row + 1][col] = pair[1];
        used.add(first);
        used.add(second);
      }
      placed++;
    }
  }

  function buildGrid(): void {
    grid = [];
    for (let row = 0; row < rowCount(); row++) {
      const line: GridCell[] = [];
      for (let col = 0; col < colCount(); col++) line.push(rollNewCellDigit());
      grid.push(line);
    }
    sprinkleSum10Pairs(Math.max(0, difficulty().sprinkle_pairs));
  }

  function formatRemain(ms: number): string {
    const seconds = Math.ceil(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return `${minutes}:${rest.toString().padStart(2, "0")}`;
  }

  function stopRoundTimer(): void {
    if (timerRaf !== null) {
      cancelAnimationFrame(timerRaf);
      timerRaf = null;
    }
    if (pendingSettleTimer !== undefined) {
      clearTimeout(pendingSettleTimer);
      pendingSettleTimer = undefined;
    }
  }

  function tickRoundTimer(): void {
    const left = Math.max(0, roundEndTime - Date.now());
    const ratio = durationMs() > 0 ? left / durationMs() : 0;
    timerFillEl.style.transform = `scaleX(${ratio})`;
    timerLabelEl.textContent = formatRemain(left);
    if (left <= 0) {
      timerRaf = null;
      onRoundTimeUp();
      return;
    }
    timerRaf = requestAnimationFrame(tickRoundTimer);
  }

  function startRoundTimer(): void {
    stopRoundTimer();
    roundStartedAt = Date.now();
    roundEndTime = roundStartedAt + durationMs();
    timerFillEl.style.transform = "scaleX(1)";
    timerLabelEl.textContent = formatRemain(durationMs());
    timerRaf = requestAnimationFrame(tickRoundTimer);
  }

  function elapsedSeconds(): number {
    if (!roundStartedAt) return 0;
    return Math.min(round!.game_duration, Math.max(0, Math.floor((Date.now() - roundStartedAt) / 1000)));
  }

  function secondsUntilSettleReady(): number {
    const minSeconds = Math.max(0, Number(round?.round_min_seconds || 0));
    return Math.max(0, minSeconds - elapsedSeconds());
  }

  function settleRound(reason: "manual" | "timeout"): void {
    if (!round || roundClosed) return;
    const wait = secondsUntilSettleReady();
    if (wait > 0) {
      showToast(`灵果还没完全归档，还需 ${wait} 秒后才能结算。`, "bad");
      if (reason === "timeout") {
        if (pendingSettleTimer !== undefined) clearTimeout(pendingSettleTimer);
        pendingSettleTimer = setTimeout(() => {
          pendingSettleTimer = undefined;
          settleRound("timeout");
        }, wait * 1000 + 80);
      }
      return;
    }
    roundClosed = true;
    stopRoundTimer();
    clearSelectionVisual();
    onRoundSettle?.({
      score,
      clearedCells,
      validClears,
      elapsedSeconds: elapsedSeconds(),
      fruitName: theme.name,
      fruitFile: theme.file,
      difficultyLabel: difficulty().label,
      sessionId: round.session_id,
      roundToken: round.round_token,
    });
  }

  function onRoundTimeUp(): void {
    settleRound("timeout");
  }

  function settleRoundManually(): void {
    settleRound("manual");
  }

  function setTheme(nextTheme: FruitTheme): void {
    theme = nextTheme;
    const url = assetUrl(`assets/fruits/${nextTheme.file}`);
    fruitNameEl.textContent = nextTheme.name;
    fruitImgEl.src = url;
    fruitImgEl.alt = nextTheme.name;
  }

  function updateStats(): void {
    scoreEl.textContent = String(score);
    clearedCellsEl.textContent = String(clearedCells);
    validClearsEl.textContent = String(validClears);
  }

  function newGame(opts: NewGameOptions): void {
    round = opts.round;
    onNewRound?.();
    stopRoundTimer();
    roundClosed = false;
    theme = pick(FRUITS);
    forbidden = hardOn() ? randomDigit() : 0;
    score = 0;
    clearedCells = 0;
    validClears = 0;
    difficultyLabelEl.textContent = difficulty().label;
    difficultyDescEl.textContent = difficulty().description;
    forbiddenEl.textContent = hardOn() ? String(forbidden) : "无";
    forbiddenEl.classList.toggle("text-[#ef476f]", hardOn());
    forbiddenEl.classList.toggle("text-[#94a8c4]", !hardOn());
    buildGrid();
    setTheme(theme);
    updateStats();
    renderBoard();
    startRoundTimer();
    if (!opts.silent) {
      showToast(`本局：${difficulty().label}，框选数字合计 ${sumTarget()} 即可消除。`, "info");
    }
  }

  function showToast(msg: string, kind: ToastKind, durationMs?: number): void {
    toastEl.textContent = msg;
    toastEl.className = "toast show";
    if (kind === "bad") toastEl.classList.add("bad");
    else if (kind === "good") toastEl.classList.add("good");
    if (hideToastTimer !== undefined) clearTimeout(hideToastTimer);
    const ms = durationMs ?? (kind === "info" ? 3200 : kind === "bad" ? 2400 : 1800);
    hideToastTimer = setTimeout(() => {
      toastEl.classList.remove("show", "bad", "good");
      hideToastTimer = undefined;
    }, ms);
  }

  function cellAt(row: number, col: number): HTMLElement | null {
    return boardEl.querySelector<HTMLElement>(`.cell[data-r="${row}"][data-c="${col}"]`);
  }

  function renderBoard(): void {
    boardEl.style.setProperty("--cols", String(colCount()));
    boardEl.innerHTML = "";
    for (let row = 0; row < rowCount(); row++) {
      for (let col = 0; col < colCount(); col++) {
        const value = grid[row][col];
        const div = document.createElement("div");
        div.className = "cell";
        div.dataset.r = String(row);
        div.dataset.c = String(col);
        div.style.backgroundImage = `url(${assetUrl(`assets/fruits/${theme.file}`)})`;
        const span = document.createElement("span");
        span.className = "num";
        span.textContent = value === null ? "" : String(value);
        div.appendChild(span);
        boardEl.appendChild(div);
      }
    }
  }

  function rectFromCells(
    rowA: number,
    colA: number,
    rowB: number,
    colB: number
  ): { top: number; bottom: number; left: number; right: number } {
    return {
      top: Math.min(rowA, rowB),
      bottom: Math.max(rowA, rowB),
      left: Math.min(colA, colB),
      right: Math.max(colA, colB),
    };
  }

  function sumInRect(top: number, bottom: number, left: number, right: number): number {
    let sum = 0;
    for (let row = top; row <= bottom; row++) {
      for (let col = left; col <= right; col++) {
        const value = grid[row][col];
        if (value != null) sum += value;
      }
    }
    return sum;
  }

  function countInRect(top: number, bottom: number, left: number, right: number): number {
    return (bottom - top + 1) * (right - left + 1);
  }

  function rectContainsForbidden(top: number, bottom: number, left: number, right: number): boolean {
    if (!hardOn()) return false;
    for (let row = top; row <= bottom; row++) {
      for (let col = left; col <= right; col++) {
        if (grid[row][col] === forbidden) return true;
      }
    }
    return false;
  }

  function shakeAllCells(): void {
    boardEl.querySelectorAll(".cell").forEach((el) => el.classList.add("shake"));
    setTimeout(() => {
      boardEl.querySelectorAll(".cell").forEach((el) => el.classList.remove("shake"));
    }, 500);
  }

  function updateSelectionOverlay(rowA: number, colA: number, rowB: number, colB: number): void {
    const first = cellAt(rowA, colA);
    const second = cellAt(rowB, colB);
    if (!first || !second) {
      selRect.style.display = "none";
      return;
    }
    const wrap = boardWrap.getBoundingClientRect();
    const firstRect = first.getBoundingClientRect();
    const secondRect = second.getBoundingClientRect();
    const left = Math.min(firstRect.left, secondRect.left) - wrap.left + boardWrap.scrollLeft;
    const top = Math.min(firstRect.top, secondRect.top) - wrap.top + boardWrap.scrollTop;
    const right = Math.max(firstRect.right, secondRect.right) - wrap.left + boardWrap.scrollLeft;
    const bottom = Math.max(firstRect.bottom, secondRect.bottom) - wrap.top + boardWrap.scrollTop;
    selRect.style.display = "block";
    selRect.style.left = `${left}px`;
    selRect.style.top = `${top}px`;
    selRect.style.width = `${right - left}px`;
    selRect.style.height = `${bottom - top}px`;
  }

  function clearSelectionVisual(): void {
    boardEl.querySelectorAll(".cell.selected").forEach((el) => el.classList.remove("selected"));
    selRect.style.display = "none";
  }

  function highlightRect(top: number, bottom: number, left: number, right: number): void {
    clearSelectionVisual();
    for (let row = top; row <= bottom; row++) {
      for (let col = left; col <= right; col++) {
        const el = cellAt(row, col);
        if (el) el.classList.add("selected");
      }
    }
  }

  function applyGravity(): void {
    for (let col = 0; col < colCount(); col++) {
      const kept: number[] = [];
      for (let row = 0; row < rowCount(); row++) {
        const value = grid[row][col];
        if (value !== null) kept.push(value);
      }
      const missing = rowCount() - kept.length;
      const topNew = Array.from({ length: missing }, () => rollNewCellDigit());
      const column = [...topNew, ...kept];
      for (let row = 0; row < rowCount(); row++) grid[row][col] = column[row];
    }
  }

  function tryClearRect(top: number, bottom: number, left: number, right: number): void {
    if (roundClosed) return;
    const sum = sumInRect(top, bottom, left, right);
    if (sum !== sumTarget()) {
      showToast(`区域合计 ${sum}，需要恰好 ${sumTarget()}`, "bad");
      shakeAllCells();
      return;
    }
    if (rectContainsForbidden(top, bottom, left, right)) {
      showToast(`这块里混入了禁用数字 ${forbidden}，不能消除`, "bad");
      shakeAllCells();
      return;
    }
    const count = countInRect(top, bottom, left, right);
    for (let row = top; row <= bottom; row++) {
      for (let col = left; col <= right; col++) {
        const el = cellAt(row, col);
        if (el) el.classList.add("pop");
      }
    }
    setTimeout(() => {
      if (roundClosed) return;
      for (let row = top; row <= bottom; row++) {
        for (let col = left; col <= right; col++) grid[row][col] = null;
      }
      applyGravity();
      score += count;
      clearedCells += count;
      validClears += 1;
      updateStats();
      showToast(`消除 ${count} 格，+${count} 分`, "good");
      renderBoard();
    }, 300);
  }

  function pointToCell(clientX: number, clientY: number): CellPos | null {
    const element = document.elementFromPoint(clientX, clientY);
    if (!element) return null;
    const cell = element.closest(".cell") as HTMLElement | null;
    if (!cell || !boardEl.contains(cell)) return null;
    const row = cell.dataset.r;
    const col = cell.dataset.c;
    if (row === undefined || col === undefined) return null;
    return { r: parseInt(row, 10), c: parseInt(col, 10) };
  }

  function onPointerDown(event: PointerEvent): void {
    if (roundClosed || (event.button !== undefined && event.button !== 0)) return;
    pointerId = event.pointerId;
    boardWrap.setPointerCapture(pointerId);
    startX = event.clientX;
    startY = event.clientY;
    dragActive = false;
    startCell = pointToCell(event.clientX, event.clientY);
    currentEndCell = startCell;
    event.preventDefault();
  }

  function onPointerMove(event: PointerEvent): void {
    if (roundClosed || pointerId !== event.pointerId || !startCell) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!dragActive && dx * dx + dy * dy > DRAG_PX * DRAG_PX) dragActive = true;
    if (!dragActive) return;
    const end = pointToCell(event.clientX, event.clientY);
    if (end) {
      currentEndCell = end;
      const { top, bottom, left, right } = rectFromCells(startCell.r, startCell.c, end.r, end.c);
      highlightRect(top, bottom, left, right);
      updateSelectionOverlay(startCell.r, startCell.c, end.r, end.c);
    }
    event.preventDefault();
  }

  function onPointerUp(event: PointerEvent): void {
    if (pointerId !== event.pointerId) return;
    boardWrap.releasePointerCapture(pointerId);
    pointerId = null;
    if (!startCell || roundClosed) return;

    if (!dragActive) {
      const value = grid[startCell.r][startCell.c];
      if (hardOn() && value === forbidden) {
        const el = cellAt(startCell.r, startCell.c);
        if (el) {
          el.classList.add("shake");
          setTimeout(() => el.classList.remove("shake"), 500);
        }
        showToast(`禁用数字 ${forbidden} 只提醒，不扣分`, "bad");
      }
      startCell = null;
      clearSelectionVisual();
      return;
    }

    const end = currentEndCell ?? startCell;
    const { top, bottom, left, right } = rectFromCells(startCell.r, startCell.c, end.r, end.c);
    clearSelectionVisual();
    tryClearRect(top, bottom, left, right);
    startCell = null;
    dragActive = false;
    event.preventDefault();
  }

  function onPointerCancel(event: PointerEvent): void {
    if (pointerId === event.pointerId) {
      pointerId = null;
      startCell = null;
      dragActive = false;
      clearSelectionVisual();
    }
  }

  boardWrap.addEventListener("pointerdown", onPointerDown);
  boardWrap.addEventListener("pointermove", onPointerMove);
  boardWrap.addEventListener("pointerup", onPointerUp);
  boardWrap.addEventListener("pointercancel", onPointerCancel);

  function onNewGameClick(): void {
    requestNewRound?.();
  }

  for (const btn of newGameBtns) {
    btn.addEventListener("click", onNewGameClick);
  }

  for (const btn of settleBtns) {
    btn.addEventListener("click", settleRoundManually);
  }

  return {
    newGame,
    setNewRoundHandler(handler) {
      requestNewRound = handler;
    },
    destroy() {
      boardWrap.removeEventListener("pointerdown", onPointerDown);
      boardWrap.removeEventListener("pointermove", onPointerMove);
      boardWrap.removeEventListener("pointerup", onPointerUp);
      boardWrap.removeEventListener("pointercancel", onPointerCancel);
      for (const btn of newGameBtns) {
        btn.removeEventListener("click", onNewGameClick);
      }
      for (const btn of settleBtns) {
        btn.removeEventListener("click", settleRoundManually);
      }
      stopRoundTimer();
      if (hideToastTimer !== undefined) clearTimeout(hideToastTimer);
    },
  };
}
