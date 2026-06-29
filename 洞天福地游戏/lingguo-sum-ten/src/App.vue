<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  fetchLingguoConfig,
  finishLingguoRound,
  startLingguoRound,
  type LingguoConfigResponse,
  type LingguoFinishResponse,
  type LingguoRoundResponse,
} from "./api/dongtian";
import { assetUrl, mountFruitGame, type FruitGameApi, type RoundSettlePayload } from "./game/fruitGame";

const boardRef = ref<HTMLElement | null>(null);
const boardWrapRef = ref<HTMLElement | null>(null);
const selRectRef = ref<HTMLElement | null>(null);
const scoreRef = ref<HTMLElement | null>(null);
const clearedCellsRef = ref<HTMLElement | null>(null);
const validClearsRef = ref<HTMLElement | null>(null);
const forbiddenRef = ref<HTMLElement | null>(null);
const difficultyLabelRef = ref<HTMLElement | null>(null);
const difficultyDescRef = ref<HTMLElement | null>(null);
const fruitNameRef = ref<HTMLElement | null>(null);
const fruitImgRef = ref<HTMLImageElement | null>(null);
const toastRef = ref<HTMLElement | null>(null);
const newBtnRef = ref<HTMLButtonElement | null>(null);
const newBtnHeaderRef = ref<HTMLButtonElement | null>(null);
const settleBtnRef = ref<HTMLButtonElement | null>(null);
const settleBtnHeaderRef = ref<HTMLButtonElement | null>(null);
const timerFillRef = ref<HTMLElement | null>(null);
const timerLabelRef = ref<HTMLElement | null>(null);

let api: FruitGameApi | null = null;
const config = ref<LingguoConfigResponse | null>(null);
const round = ref<LingguoRoundResponse | null>(null);
const loading = ref(true);
const bootError = ref("");
const settleOpen = ref(false);
const settling = ref(false);
const settleError = ref("");
const settlePayload = ref<RoundSettlePayload | null>(null);
const settleResult = ref<LingguoFinishResponse | null>(null);
const copied = ref(false);
const needsSettleRetry = computed(() => Boolean(settleError.value && !settleResult.value));

const settleFruitUrl = computed(() => {
  const file = settlePayload.value?.fruitFile;
  return file ? assetUrl(`assets/fruits/${file}`) : "";
});

async function ensureConfig(force = false): Promise<LingguoConfigResponse> {
  if (config.value && !force) return config.value;
  config.value = await fetchLingguoConfig();
  return config.value;
}

async function startRound(silent = false): Promise<void> {
  if (needsSettleRetry.value) return;
  loading.value = true;
  bootError.value = "";
  settleOpen.value = false;
  settleResult.value = null;
  settleError.value = "";
  copied.value = false;
  try {
    let currentConfig = await ensureConfig();
    try {
      round.value = await startLingguoRound(currentConfig.game_token);
    } catch {
      currentConfig = await ensureConfig(true);
      round.value = await startLingguoRound(currentConfig.game_token);
    }
    api?.newGame({ round: round.value, silent });
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : "洞天入口暂时没有回应。";
  } finally {
    loading.value = false;
  }
}

async function onRoundSettle(payload: RoundSettlePayload): Promise<void> {
  if (!config.value) {
    settleError.value = "启动凭证缺失，请重新进入小游戏。";
    settleOpen.value = true;
    return;
  }
  settlePayload.value = payload;
  settleOpen.value = true;
  settling.value = true;
  settleResult.value = null;
  settleError.value = "";
  try {
    settleResult.value = await finishLingguoRound({
      gameToken: config.value.game_token,
      sessionId: payload.sessionId,
      roundToken: payload.roundToken,
      score: payload.score,
      clearedCells: payload.clearedCells,
      validClears: payload.validClears,
      elapsedSeconds: payload.elapsedSeconds,
    });
  } catch (error) {
    settleError.value = error instanceof Error ? error.message : "结算失败，请重新开局。";
  } finally {
    settling.value = false;
  }
}

async function retrySettle(): Promise<void> {
  if (!settlePayload.value || settling.value) return;
  await onRoundSettle(settlePayload.value);
}

async function copyCode(): Promise<void> {
  const code = settleResult.value?.code;
  if (!code) return;
  try {
    await writeClipboard(`洞天兑换 ${code}`);
    copied.value = true;
    window.setTimeout(() => {
      copied.value = false;
    }, 1600);
  } catch {
    copied.value = false;
  }
}

async function writeClipboard(text: string): Promise<void> {
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

function playAgain(): void {
  if (needsSettleRetry.value) return;
  void startRound(true);
}

onMounted(() => {
  const boardEl = boardRef.value;
  const boardWrap = boardWrapRef.value;
  const selRect = selRectRef.value;
  const scoreEl = scoreRef.value;
  const clearedCellsEl = clearedCellsRef.value;
  const validClearsEl = validClearsRef.value;
  const forbiddenEl = forbiddenRef.value;
  const difficultyLabelEl = difficultyLabelRef.value;
  const difficultyDescEl = difficultyDescRef.value;
  const fruitNameEl = fruitNameRef.value;
  const fruitImgEl = fruitImgRef.value;
  const toastEl = toastRef.value;
  const newGameBtns = [newBtnHeaderRef.value, newBtnRef.value].filter(
    (item): item is HTMLButtonElement => item != null
  );
  const settleBtns = [settleBtnHeaderRef.value, settleBtnRef.value].filter(
    (item): item is HTMLButtonElement => item != null
  );
  const timerFillEl = timerFillRef.value;
  const timerLabelEl = timerLabelRef.value;
  if (
    !boardEl ||
    !boardWrap ||
    !selRect ||
    !scoreEl ||
    !clearedCellsEl ||
    !validClearsEl ||
    !forbiddenEl ||
    !difficultyLabelEl ||
    !difficultyDescEl ||
    !fruitNameEl ||
    !fruitImgEl ||
    !toastEl ||
    newGameBtns.length === 0 ||
    settleBtns.length === 0 ||
    !timerFillEl ||
    !timerLabelEl
  ) {
    bootError.value = "小游戏挂载失败，请刷新页面。";
    loading.value = false;
    return;
  }
  api = mountFruitGame({
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
    onNewRound: () => {
      settleOpen.value = false;
    },
  });
  api.setNewRoundHandler(() => {
    void startRound(false);
  });
  void startRound(false);
});

onBeforeUnmount(() => {
  api?.destroy();
});
</script>

<template>
  <div class="min-h-[100dvh] max-w-[min(1180px,calc(100%-1rem))] mx-auto px-2 sm:px-3.5 pt-3 sm:pt-4 pb-6 sm:pb-8 box-border flex flex-col">
    <header class="flex items-center justify-between gap-2 sm:gap-3 mb-3 lg:mb-4 shrink-0">
      <div class="min-w-0">
        <p class="m-0 text-[0.72rem] sm:text-[0.8rem] text-[#94a8c4] tracking-[0.18em] uppercase">
          Dongtian Game
        </p>
        <h1 class="app-title text-[1.35rem] sm:text-[1.75rem] lg:text-[2rem] font-bold m-0 leading-tight">
          灵果凑十
        </h1>
      </div>
      <button
        ref="newBtnHeaderRef"
        type="button"
        :disabled="loading || settling || needsSettleRetry"
        class="lg:hidden shrink-0 min-h-11 whitespace-nowrap border-none py-2.5 px-3 rounded-lg text-[0.72rem] font-semibold cursor-pointer text-white bg-gradient-to-b from-[#5b73ff] via-[#4f6cf5] to-[#3d52d4] shadow-[0_2px_10px_rgba(99,102,241,0.4)] disabled:opacity-60"
      >
        新开一局
      </button>
      <button
        ref="settleBtnHeaderRef"
        type="button"
        :disabled="loading || settling"
        class="lg:hidden shrink-0 min-h-11 whitespace-nowrap border border-white/10 py-2.5 px-3 rounded-lg text-[0.72rem] font-semibold cursor-pointer text-[#e8eef5] bg-white/[0.08] disabled:opacity-60"
      >
        结算
      </button>
    </header>

    <div v-if="bootError" class="app-panel rounded-xl p-4 mb-3 text-[#ffb3c1]">
      {{ bootError }}
    </div>

    <div class="lingguo-layout flex flex-col lg:flex-row gap-4 lg:gap-6 items-stretch lg:items-start flex-1 min-h-0">
      <aside class="lingguo-rules shrink-0 lg:w-[min(286px,32%)] order-3 lg:order-1 w-full">
        <div class="app-panel rounded-xl p-4 text-[0.84rem] leading-relaxed text-[#c8d5e8]">
          <p class="m-0">
            框选一块矩形，让格内数字合计
            <strong class="text-white">{{ round?.sum_target ?? 10 }}</strong>
            即可摘下灵果。今日难度由洞天统一定下，时间到自动结算兑换码。
          </p>
        </div>
      </aside>

      <main class="lingguo-stage flex-1 min-w-0 flex justify-center items-start order-1 lg:order-2 w-full">
        <div ref="boardWrapRef" class="board-shell relative touch-none rounded-2xl p-2 sm:p-2.5 w-full max-w-full mx-auto lg:w-fit">
          <div ref="selRectRef" class="selection-rect" />
          <div id="board" ref="boardRef" />
        </div>
      </main>

      <aside class="lingguo-sidebar shrink-0 lg:w-[min(290px,32%)] flex flex-col gap-2.5 sm:gap-3 order-2 lg:order-3 w-full">
        <div class="round-timer app-panel rounded-xl py-2 sm:py-3 px-3.5">
          <div class="round-timer__row">
            <span>剩余时间</span>
            <strong ref="timerLabelRef">2:30</strong>
          </div>
          <div class="round-timer__track">
            <div ref="timerFillRef" class="round-timer__fill" />
          </div>
        </div>

        <div class="grid grid-cols-3 gap-2">
          <div class="app-panel rounded-xl py-2 px-3">
            <div class="app-muted text-[0.68rem] mb-1">得分</div>
            <div ref="scoreRef" class="text-[1.35rem] font-bold leading-none">0</div>
          </div>
          <div class="app-panel rounded-xl py-2 px-3">
            <div class="app-muted text-[0.68rem] mb-1">摘果</div>
            <div ref="clearedCellsRef" class="text-[1.35rem] font-bold leading-none">0</div>
          </div>
          <div class="app-panel rounded-xl py-2 px-3">
            <div class="app-muted text-[0.68rem] mb-1">成局</div>
            <div ref="validClearsRef" class="text-[1.35rem] font-bold leading-none">0</div>
          </div>
        </div>

        <div class="app-panel rounded-xl py-3 px-3.5">
          <div class="app-muted text-[0.7rem] mb-1">本局气象</div>
          <div ref="difficultyLabelRef" class="font-bold text-[1rem] text-[#e8eef5]">等待洞天</div>
          <div ref="difficultyDescRef" class="app-muted text-[0.74rem] mt-1 leading-snug">正在抽取本局难度。</div>
        </div>

        <div class="grid grid-cols-2 gap-2.5">
          <div class="app-panel rounded-xl py-3 px-3.5">
            <div class="app-muted text-[0.7rem] mb-1">禁用数字</div>
            <div ref="forbiddenRef" class="text-[1.45rem] font-bold leading-none text-[#94a8c4]">无</div>
          </div>
          <div class="app-panel rounded-xl py-3 px-3.5">
            <div class="app-muted text-[0.7rem] mb-1">本局灵果</div>
            <div class="flex items-center gap-2 mt-1">
              <img ref="fruitImgRef" src="" alt="" width="34" height="34" class="w-[34px] h-[34px] object-contain drop-shadow-md" />
              <span ref="fruitNameRef" class="font-semibold text-[0.9rem]">—</span>
            </div>
          </div>
        </div>

        <button
          ref="newBtnRef"
          type="button"
          :disabled="loading || settling || needsSettleRetry"
          class="hidden lg:flex justify-center w-full border-none py-2.5 px-[18px] rounded-[10px] text-[0.9rem] font-semibold cursor-pointer text-white bg-gradient-to-b from-[#5b73ff] via-[#4f6cf5] to-[#3d52d4] shadow-[0_4px_20px_rgba(99,102,241,0.45),inset_0_1px_0_rgba(255,255,255,0.18)] disabled:opacity-60"
        >
          新开一局
        </button>
        <button
          ref="settleBtnRef"
          type="button"
          :disabled="loading || settling"
          class="hidden lg:flex justify-center w-full border border-white/[0.12] py-2.5 px-[18px] rounded-[10px] text-[0.9rem] font-semibold cursor-pointer text-[#e8eef5] bg-white/[0.08] disabled:opacity-60"
        >
          结算本局
        </button>
      </aside>
    </div>
  </div>

  <div ref="toastRef" class="toast" role="status" aria-live="polite" />

  <Teleport to="body">
    <div
      v-if="settleOpen && settlePayload"
      class="settle-backdrop fixed inset-0 z-[240] flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
    >
      <div class="absolute inset-0 bg-[#0a0f14]/78 backdrop-blur-md" aria-hidden="true" />
      <div class="settle-card-anim relative w-full max-w-[min(430px,calc(100vw-2rem))] rounded-[22px] border border-solid border-white/[0.12] bg-[#141c28]/95 overflow-hidden shadow-[0_20px_70px_rgba(0,0,0,0.42)]">
        <div class="settle-shine opacity-70" aria-hidden="true" />
        <div class="relative px-6 pt-7 pb-6 sm:px-8 border-b border-white/[0.06]">
          <p class="text-[0.72rem] uppercase tracking-[0.2em] text-[#8b9cb3] m-0 mb-1.5">
            本局结束
          </p>
          <h2 class="text-[1.65rem] sm:text-[1.85rem] font-extrabold m-0 text-[#e8eef5]">
            时间到 · 洞天结算
          </h2>
          <div class="mt-4 rounded-2xl bg-black/28 border border-white/[0.07] px-5 py-5 text-center">
            <p class="text-[0.75rem] text-[#8b9cb3] m-0 mb-1">服务端认可分</p>
            <p class="text-[clamp(2.5rem,10vw,3.4rem)] font-black tabular-nums leading-none m-0 bg-gradient-to-b from-white to-[#b8c9dc] bg-clip-text text-transparent">
              {{ settleResult?.accepted_score ?? settlePayload.score }}
            </p>
            <div class="mt-4 flex flex-wrap items-center justify-center gap-2 text-[0.8rem] text-[#c8d5e8]">
              <span>{{ settlePayload.difficultyLabel }}</span>
              <span>摘果 {{ settlePayload.clearedCells }}</span>
              <span>成局 {{ settlePayload.validClears }}</span>
              <span>{{ settlePayload.elapsedSeconds }} 秒</span>
            </div>
            <div class="mt-3 flex items-center justify-center gap-2 text-[0.82rem]">
              <img :src="settleFruitUrl" :alt="settlePayload.fruitName" width="30" height="30" class="w-[30px] h-[30px] object-contain" />
              <span>{{ settlePayload.fruitName }}</span>
            </div>
          </div>

          <div v-if="settling" class="mt-4 text-center text-[#94a8c4] text-[0.88rem]">
            正在向洞天校验本局成绩……
          </div>
          <div v-else-if="settleError" class="mt-4 rounded-xl bg-[#ef476f]/10 border border-[#ef476f]/30 px-4 py-3 text-[#ffb3c1] text-[0.86rem]">
            {{ settleError }}
          </div>
          <div v-else-if="settleResult" class="mt-4 space-y-3">
            <div class="rounded-xl bg-white/[0.05] border border-white/[0.08] px-4 py-3">
              <div class="text-[0.72rem] text-[#8b9cb3] mb-1">洞天兑换码</div>
              <div class="font-black tracking-[0.12em] text-[#e8eef5] break-all">{{ settleResult.code }}</div>
            </div>
            <div class="rounded-xl bg-white/[0.04] border border-white/[0.07] px-4 py-3 text-[0.82rem] text-[#c8d5e8] leading-relaxed">
              <div v-for="line in settleResult.reward_preview" :key="line">{{ line }}</div>
              <div v-if="settleResult.reward_preview.length === 0">本局没有生成可兑换奖励。</div>
            </div>
          </div>
        </div>

        <div class="relative px-6 py-4 sm:px-8 bg-[#0f1419]/80 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <button
            v-if="settleError && !settleResult"
            type="button"
            class="py-3 rounded-xl text-[0.9rem] font-bold text-white bg-gradient-to-b from-[#4361ee] to-[#3651d4] border border-white/10 disabled:opacity-60"
            :disabled="settling"
            @click="retrySettle"
          >
            {{ settling ? "重试中" : "结算本局" }}
          </button>
          <button
            v-else
            type="button"
            class="py-3 rounded-xl text-[0.9rem] font-bold text-white bg-gradient-to-b from-[#4361ee] to-[#3651d4] border border-white/10 disabled:opacity-60"
            :disabled="!settleResult"
            @click="copyCode"
          >
            {{ copied ? "已复制兑换命令" : "复制兑换命令" }}
          </button>
          <button
            type="button"
            class="py-3 rounded-xl text-[0.9rem] font-bold text-[#e8eef5] bg-white/[0.08] border border-white/[0.12] disabled:opacity-60"
            :disabled="needsSettleRetry"
            @click="playAgain"
          >
            {{ needsSettleRetry ? "请先结算本局" : "再来一局" }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
