import { Clock3, Flame, Trophy } from 'lucide-react';
import { useGameStore } from '@/store/gameStore';

export default function GameHUD() {
  const { score, timeLeft, combo, lastCatchScore, lastCatchCombo, statusText, requestFinish } = useGameStore();

  const minutes = Math.floor(timeLeft / 60);
  const seconds = Math.floor(timeLeft % 60);
  const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
  const hasComboData = lastCatchCombo > 0;
  const displayCombo = combo > 0 ? combo : lastCatchCombo;
  const comboMultiplier = displayCombo > 0 ? (1 + (displayCombo - 1) * 0.5).toFixed(1) : '1.0';
  const comboTitle = combo > 0 ? '当前连击' : '最近连击';
  const isUrgent = timeLeft <= 10;

  return (
    <div className="pointer-events-none absolute left-0 right-0 top-0 z-10 px-3 py-3 text-white md:px-6 md:py-4">
      <div className="grid grid-cols-2 items-start gap-2 md:grid-cols-[minmax(152px,auto)_minmax(220px,1fr)_minmax(152px,auto)] md:gap-4">
        <div className="flex min-w-[112px] items-center gap-2 rounded-lg border border-white/20 bg-slate-950/32 px-3 py-2 shadow-[0_12px_35px_rgba(2,6,23,0.22)] backdrop-blur-md md:min-w-[152px] md:px-4 md:col-start-1 md:row-start-1 md:justify-self-start">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-amber-300/20 text-amber-200">
          <Trophy className="h-4 w-4" strokeWidth={2.5} />
        </span>
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-100/75">分数</div>
          <div className="tabular-nums text-xl font-black leading-tight md:text-2xl">{score}</div>
        </div>
        </div>

        <div
          className={`flex min-w-[112px] items-center justify-end gap-2 rounded-lg border px-3 py-2 shadow-[0_12px_35px_rgba(2,6,23,0.22)] backdrop-blur-md md:min-w-[152px] md:px-4 md:col-start-3 md:row-start-1 md:justify-self-end ${
            isUrgent
              ? 'animate-pulse border-red-200/35 bg-red-500/42'
              : 'border-white/20 bg-slate-950/32'
          }`}
        >
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${isUrgent ? 'bg-red-200/20 text-red-100' : 'bg-cyan-200/18 text-cyan-100'}`}>
            <Clock3 className="h-4 w-4" strokeWidth={2.5} />
          </span>
          <div className="text-right">
            <div className={`text-[10px] font-bold uppercase tracking-[0.18em] ${isUrgent ? 'text-red-100/80' : 'text-cyan-100/75'}`}>
              时间
            </div>
            <div className={`tabular-nums text-xl font-black leading-tight md:text-2xl ${isUrgent ? 'text-red-50' : 'text-white'}`}>
              {timeStr}
            </div>
          </div>
        </div>

        {hasComboData && (
          <div className="col-span-2 flex justify-center md:col-span-1 md:col-start-2 md:row-start-1">
            <div className="flex w-full max-w-[22rem] items-center justify-between gap-3 rounded-lg border border-orange-200/30 bg-orange-500/32 px-3 py-2 shadow-[0_12px_35px_rgba(249,115,22,0.2)] backdrop-blur-md md:w-auto md:min-w-[240px] md:px-4">
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-orange-200/20 text-orange-100">
                  <Flame className="h-4 w-4" fill="currentColor" strokeWidth={2.4} />
                </span>
                <div className="min-w-0">
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-orange-100/75">{comboTitle}</div>
                  <div className="truncate text-sm font-black leading-tight text-white md:text-lg">连击 {displayCombo}</div>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="tabular-nums text-lg font-black leading-tight text-orange-50 md:text-xl">x{comboMultiplier}</div>
                <div className="tabular-nums text-[10px] font-bold text-orange-100/80 md:text-xs">+{lastCatchScore}</div>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-center">
        <button
          type="button"
          onClick={requestFinish}
          className="pointer-events-auto rounded-lg border border-white/20 bg-slate-950/40 px-4 py-2 text-xs font-black text-white shadow-[0_12px_35px_rgba(2,6,23,0.2)] backdrop-blur-md transition active:scale-[0.98] md:text-sm"
        >
          收竿结算
        </button>
      </div>
      {statusText && (
        <div className="mt-2 flex justify-center">
          <div className="rounded-lg border border-amber-100/25 bg-amber-400/16 px-3 py-2 text-center text-xs font-bold text-amber-50 shadow-[0_12px_35px_rgba(2,6,23,0.18)] backdrop-blur-md md:text-sm">
            {statusText}
          </div>
        </div>
      )}
    </div>
  );
}
