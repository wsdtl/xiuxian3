import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Copy, Home, RotateCcw, Sparkles, Trophy } from 'lucide-react';
import { prepareFishingRound, submitFishingResult, type FishingFinishResponse } from '@/api/dongtian';
import { FISH_TYPES } from '@/game/constants';
import { useGameStore } from '@/store/gameStore';

const fishEmojiMap: Record<string, string> = {
  clownfish: '🐠',
  blueCrucian: '🐟',
  goldfish: '✨',
  pufferfish: '🐡',
  swordfish: '⚔️',
  shark: '🦈',
  goldenDragon: '🐉',
};

export default function ResultScreen() {
  const {
    score,
    caughtFish,
    gameToken,
    sessionId,
    roundToken,
    setGameState,
    setGameConfig,
    setRound,
    clearRound,
    resetGame,
  } = useGameStore();
  const [finishResult, setFinishResult] = useState<FishingFinishResponse | null>(null);
  const [finishError, setFinishError] = useState('');
  const [settling, setSettling] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const submittedRef = useRef(false);

  const fishCountMap = useMemo(() => {
    const result: Record<string, { count: number; totalScore: number; name: string }> = {};
    for (const fish of caughtFish) {
      if (!result[fish.typeNameEn]) {
        result[fish.typeNameEn] = { count: 0, totalScore: 0, name: fish.typeName };
      }
      result[fish.typeNameEn].count++;
      result[fish.typeNameEn].totalScore += fish.score;
    }
    return result;
  }, [caughtFish]);

  const submitRound = useCallback(() => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSettling(true);
    setFinishError('');
    submitFishingResult(score, caughtFish, { gameToken, sessionId, roundToken })
      .then((result) => {
        setFinishResult(result);
        setFinishError('');
        clearRound();
      })
      .catch((error: Error) => {
        submittedRef.current = false;
        setFinishError(error.message || '洞天溪口暂时没有回应。');
      })
      .finally(() => {
        setSettling(false);
      });
  }, [score, caughtFish, gameToken, sessionId, roundToken, clearRound]);

  useEffect(() => {
    submitRound();
  }, [submitRound]);

  const handleRestart = async () => {
    if (restarting) return;
    setRestarting(true);
    setFinishError('');
    try {
      const prepared = await prepareFishingRound();
      resetGame();
      setGameConfig(prepared.config);
      setRound(prepared.round);
      setGameState('playing');
    } catch (error) {
      setFinishError(error instanceof Error ? error.message : '洞天溪口暂时没有回应。');
    } finally {
      setRestarting(false);
    }
  };

  const handleHome = () => {
    if (finishError && !finishResult) {
      setFinishError('请先结算本局，成功拿到兑换码后再返回主页。');
      return;
    }
    resetGame();
    clearRound();
  };

  const copyResultText = async (value: string, setCopied: (copied: boolean) => void) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const area = document.createElement('textarea');
        area.value = value;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.focus();
        area.select();
        document.execCommand('copy');
        area.remove();
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const handleCopyCommand = () => {
    if (!finishResult?.code) return;
    void copyResultText(`洞天兑换 ${finishResult.code}`, setCopiedCommand);
  };

  const handleCopyCode = () => {
    if (!finishResult?.code) return;
    void copyResultText(finishResult.code, setCopiedCode);
  };

  let rating = '🎣 溪畔新手';
  if (score >= 2400) rating = '👑 钓月真君';
  else if (score >= 1400) rating = '🏆 破浪名竿';
  else if (score >= 700) rating = '⭐ 灵溪钓师';
  else if (score >= 250) rating = '🎣 稳竿道人';

  return (
    <div className="absolute inset-0 z-20 overflow-y-auto overscroll-contain bg-slate-950/42 px-3 py-3 backdrop-blur-sm">
      <div className="mx-auto flex min-h-full w-full max-w-2xl items-start justify-center py-1">
        <div className="w-full rounded-lg border border-white/24 bg-slate-950/40 p-3 text-white shadow-[0_26px_90px_rgba(2,6,23,0.5)] backdrop-blur-md md:p-5">
          <div className="space-y-3 text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-amber-300/20 text-amber-100 md:h-12 md:w-12">
            <Trophy className="h-5 w-5 md:h-6 md:w-6" strokeWidth={2.4} />
          </div>

          <div className="space-y-1">
            <h2
              className="text-3xl font-black drop-shadow-[0_4px_0_rgba(8,47,73,0.65)] md:text-4xl"
              style={{ fontFamily: '"Fredoka", "Microsoft YaHei", sans-serif' }}
            >
              灵溪收竿
            </h2>
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-100/25 bg-amber-200/16 px-3 py-1 text-base font-black text-amber-100 md:text-lg">
              <Sparkles className="h-4 w-4" />
              {rating}
            </div>
          </div>

          <div className="rounded-lg border border-cyan-100/20 bg-cyan-950/26 p-3 md:p-4">
            <div className="text-xs font-bold uppercase tracking-[0.22em] text-cyan-100/72">总得分</div>
            <div
              className="mt-1 text-5xl font-black leading-none text-amber-200 drop-shadow-[0_5px_0_rgba(146,64,14,0.42)] md:text-6xl"
              style={{ fontFamily: '"Fredoka", "Microsoft YaHei", sans-serif' }}
            >
              {score}
            </div>
            <div className="mt-2 text-sm font-semibold text-cyan-50/70">共钓到 {caughtFish.length} 尾灵溪游鱼</div>
          </div>

          {Object.keys(fishCountMap).length > 0 ? (
            <div className="rounded-lg border border-white/14 bg-white/10 p-2.5 text-left md:p-3">
              <div className="mb-2 text-center text-xs font-bold uppercase tracking-[0.2em] text-white/62">
                钓获统计
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {FISH_TYPES.filter((fishType) => fishCountMap[fishType.nameEn]).map((fishType) => {
                  const stat = fishCountMap[fishType.nameEn];
                  return (
                    <div
                      key={fishType.nameEn}
                      className="flex min-h-12 items-center gap-2 rounded-lg border border-white/12 bg-slate-900/26 px-2.5 py-1.5 md:px-3 md:py-2"
                    >
                      <span className="text-lg leading-none md:text-xl">{fishEmojiMap[fishType.nameEn] || '🐟'}</span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-bold text-white">{stat.name}</div>
                        <div className="text-xs font-black text-amber-200">x{stat.count}</div>
                      </div>
                      <div className="text-sm font-black tabular-nums text-cyan-50">{stat.totalScore}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-white/14 bg-white/10 px-4 py-4 text-sm font-semibold text-white/72">
              灵溪空钩而返，下一片浪花还在等你。
            </div>
          )}

          <div className="rounded-lg border border-emerald-100/18 bg-emerald-950/24 p-3 text-left md:p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-100/70">洞天回响</div>
              {finishResult && (
                <span className="rounded-full bg-emerald-300/18 px-2.5 py-1 text-xs font-black text-emerald-100">
                  10分钟有效
                </span>
              )}
            </div>
            {!finishResult && !finishError && (
              <div className="text-sm font-semibold text-emerald-50/82">正在把这篓鱼换成洞天兑换码...</div>
            )}
            {finishError && (
              <div className="space-y-3">
                <div className="text-sm font-semibold text-rose-100">{finishError}，可以重试结算本局。</div>
                <button
                  onClick={submitRound}
                  disabled={settling}
                  className="w-full rounded-lg border border-rose-100/24 bg-rose-300/14 px-3 py-2 text-sm font-black text-rose-50 transition hover:bg-rose-300/22 disabled:cursor-wait disabled:opacity-70"
                >
                  {settling ? '重试中' : '结算本局'}
                </button>
              </div>
            )}
            {finishResult && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 gap-2">
                  <button
                    onClick={handleCopyCommand}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-emerald-100/22 bg-black/18 px-3 py-2 text-left transition hover:bg-white/10"
                  >
                    <span>
                      <span className="block text-[11px] font-bold uppercase tracking-[0.18em] text-emerald-100/60">
                        {copiedCommand ? '已复制兑换命令' : '发送给机器人'}
                      </span>
                      <span className="mt-0.5 block break-all font-mono text-base font-black tracking-wide text-white md:text-lg">
                        洞天兑换 {finishResult.code}
                      </span>
                    </span>
                    {copiedCommand ? <CheckCircle2 className="h-5 w-5 text-emerald-200" /> : <Copy className="h-5 w-5 text-emerald-100" />}
                  </button>
                  <button
                    onClick={handleCopyCode}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-cyan-100/18 bg-white/[0.08] px-3 py-2 text-left transition hover:bg-white/[0.12]"
                  >
                    <span>
                      <span className="block text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-100/60">
                        {copiedCode ? '已复制兑换码' : '仅复制兑换码'}
                      </span>
                      <span className="mt-0.5 block break-all font-mono text-sm font-black tracking-wide text-cyan-50 md:text-base">
                        {finishResult.code}
                      </span>
                    </span>
                    {copiedCode ? <CheckCircle2 className="h-5 w-5 text-cyan-100" /> : <Copy className="h-5 w-5 text-cyan-100" />}
                  </button>
                </div>
                {(finishResult.reward_preview || []).length > 0 && (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {finishResult.reward_preview?.map((line) => (
                      <div key={line} className="rounded-md border border-white/10 bg-white/10 px-2.5 py-2 text-xs font-bold text-emerald-50/90">
                        {line}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3">
            <button
              onClick={handleHome}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/18 bg-white/12 px-4 py-2.5 font-black text-white transition hover:bg-white/20"
            >
              <Home className="h-4 w-4" strokeWidth={2.4} />
              主页
            </button>
            <button
              onClick={handleRestart}
              disabled={restarting || Boolean(finishError && !finishResult)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-amber-300 via-orange-400 to-rose-400 px-4 py-2.5 font-black text-slate-900 shadow-[0_14px_35px_rgba(251,146,60,0.28)] transition hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-70"
            >
              <RotateCcw className="h-4 w-4" strokeWidth={2.4} />
              {finishError && !finishResult ? '请先结算本局' : restarting ? '开新局中' : '再来一局'}
            </button>
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
