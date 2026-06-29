import { create } from 'zustand';
import { GameState, CaughtFishRecord } from '@/game/types';
import type { FishingGameConfig, FishingRoundStart } from '@/api/dongtian';

interface GameStore {
  gameState: GameState;
  score: number;
  timeLeft: number;
  combo: number;
  caughtFish: CaughtFishRecord[];
  lastCatchScore: number;
  lastCatchCombo: number;
  gameToken: string;
  gameTokenExpiresAt: string;
  sessionId: string;
  roundToken: string;
  roundExpiresAt: string;
  gameDuration: number;
  roundMinSeconds: number;
  startedAt: number;
  statusText: string;

  setGameState: (state: GameState) => void;
  setScore: (score: number) => void;
  setTimeLeft: (time: number) => void;
  addCombo: () => void;
  resetCombo: () => void;
  addCaughtFish: (record: CaughtFishRecord) => void;
  setLastCatch: (score: number, combo: number) => void;
  setGameConfig: (config: FishingGameConfig) => void;
  setRound: (round: FishingRoundStart) => void;
  clearRound: () => void;
  finishGame: () => void;
  requestFinish: () => boolean;
  setStatusText: (text: string) => void;
  resetGame: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  gameState: 'idle',
  score: 0,
  timeLeft: 90,
  combo: 0,
  caughtFish: [],
  lastCatchScore: 0,
  lastCatchCombo: 0,
  gameToken: '',
  gameTokenExpiresAt: '',
  sessionId: '',
  roundToken: '',
  roundExpiresAt: '',
  gameDuration: 90,
  roundMinSeconds: 10,
  startedAt: 0,
  statusText: '',

  setGameState: (gameState) => set({ gameState }),
  setScore: (score) => set({ score }),
  setTimeLeft: (timeLeft) => set({ timeLeft }),
  addCombo: () => set((s) => ({ combo: s.combo + 1 })),
  resetCombo: () => set({ combo: 0 }),
  addCaughtFish: (record) =>
    set((s) => ({ caughtFish: [...s.caughtFish, record] })),
  setLastCatch: (score, combo) => set({ lastCatchScore: score, lastCatchCombo: combo }),
  setGameConfig: (config) =>
    set({
      gameToken: config.game_token,
      gameTokenExpiresAt: config.token_expires_at,
      gameDuration: Math.max(1, Number(config.config?.game_duration || 90)),
      roundMinSeconds: Math.max(0, Number(config.config?.round_min_seconds || 10)),
    }),
  setRound: (round) =>
    set({
      sessionId: round.session_id,
      roundToken: round.round_token,
      roundExpiresAt: round.expires_at,
      startedAt: Date.now(),
      statusText: '',
    }),
  clearRound: () => set({ sessionId: '', roundToken: '', roundExpiresAt: '' }),
  finishGame: () => set({ gameState: 'ended' }),
  requestFinish: () => {
    const state = useGameStore.getState();
    if (state.gameState !== 'playing') return false;
    const elapsed = state.startedAt ? Math.floor((Date.now() - state.startedAt) / 1000) : 0;
    const wait = Math.max(0, state.roundMinSeconds - elapsed);
    if (wait > 0) {
      set({ statusText: `灵溪还没完全归档，还需 ${wait} 秒后才能收竿。` });
      return false;
    }
    set({ gameState: 'ended', statusText: '' });
    return true;
  },
  setStatusText: (statusText) => set({ statusText }),
  resetGame: () =>
    set((s) => ({
      gameState: 'idle',
      score: 0,
      timeLeft: s.gameDuration || 90,
      combo: 0,
      caughtFish: [],
      lastCatchScore: 0,
      lastCatchCombo: 0,
      sessionId: '',
      roundToken: '',
      roundExpiresAt: '',
      startedAt: 0,
      statusText: '',
      gameToken: s.gameToken,
      gameTokenExpiresAt: s.gameTokenExpiresAt,
      gameDuration: s.gameDuration,
      roundMinSeconds: s.roundMinSeconds,
    })),
}));
