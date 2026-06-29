import { useRef, useCallback, useEffect } from 'react';
import { GameScene } from '@/game/types';
import { createScene, resetScene, updateScene, EngineCallbacks } from '@/game/engine';
import { render } from '@/game/renderer';
import { useGameStore } from '@/store/gameStore';
import { WATER_LEVEL_RATIO, HOOK_X_RATIO } from '@/game/constants';

function syncCanvasDisplaySize(canvas: HTMLCanvasElement) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  return { width, height };
}

export function useGameLoop(canvasRef: React.RefObject<HTMLCanvasElement | null>) {
  const sceneRef = useRef<GameScene | null>(null);
  const animFrameRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const spacePressedRef = useRef<boolean>(false);
  const hookWentDeepRef = useRef<boolean>(false);

  const setGameState = useGameStore((s) => s.setGameState);
  const setScore = useGameStore((s) => s.setScore);
  const setTimeLeft = useGameStore((s) => s.setTimeLeft);
  const addCombo = useGameStore((s) => s.addCombo);
  const resetCombo = useGameStore((s) => s.resetCombo);
  const addCaughtFish = useGameStore((s) => s.addCaughtFish);
  const setLastCatch = useGameStore((s) => s.setLastCatch);
  const setStatusText = useGameStore((s) => s.setStatusText);

  const initScene = useCallback((width: number, height: number) => {
    sceneRef.current = createScene(width, height);
  }, []);

  const syncSceneSize = useCallback((width: number, height: number) => {
    if (!sceneRef.current) {
      initScene(width, height);
      return;
    }

    const scene = sceneRef.current;
    if (scene.canvasWidth === width && scene.canvasHeight === height) return;

    scene.canvasWidth = width;
    scene.canvasHeight = height;
    scene.waterLevel = height * WATER_LEVEL_RATIO;
    scene.hook.x = width * HOOK_X_RATIO;
    scene.hook.maxDepth = height - 30;
    scene.hook.y = Math.min(scene.hook.y, scene.hook.maxDepth);
  }, [initScene]);

  const gameLoop = useCallback(
    (timestamp: number) => {
      if (!sceneRef.current || !canvasRef.current) return;

      const { width, height } = syncCanvasDisplaySize(canvasRef.current);
      syncSceneSize(width, height);

      const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.05);
      lastTimeRef.current = timestamp;
      if (dt <= 0) {
        animFrameRef.current = requestAnimationFrame(gameLoop);
        return;
      }

      const scene = sceneRef.current;
      const ctx = canvasRef.current.getContext('2d');
      if (!ctx) return;

      const callbacks: EngineCallbacks = {
        onScoreUpdate: (_baseScore, _combo, _depthBonus, totalScore, fish) => {
          const state = useGameStore.getState();
          setScore(state.score + totalScore);
          addCombo();
          setLastCatch(totalScore, state.combo + 1);
          addCaughtFish({
            typeName: fish.type.name,
            typeNameEn: fish.type.nameEn,
            score: totalScore,
            timestamp: Date.now(),
          });
        },
        onTimeUpdate: (timeLeft) => {
          setTimeLeft(timeLeft);
        },
        onGameEnd: () => {
          setGameState('ended');
        },
      };

      const stateSnapshot = useGameStore.getState();
      const combo = stateSnapshot.combo;
      const timeLeft = updateScene(scene, dt, spacePressedRef.current, stateSnapshot.gameDuration, combo, callbacks);

      // Track if hook went deep (below surface + margin)
      if (scene.hook.y > scene.waterLevel + 20) {
        hookWentDeepRef.current = true;
      }

      // Reset combo if hook returned to surface without catch
      if (
        hookWentDeepRef.current &&
        scene.hook.y <= scene.waterLevel + 2 &&
        !scene.hook.hasCatch
      ) {
        hookWentDeepRef.current = false;
        if (useGameStore.getState().combo > 0) {
          resetCombo();
        }
      }

      if (timeLeft <= 0) {
        setStatusText('');
        setGameState('ended');
        render(ctx, scene);
        return;
      }

      render(ctx, scene);
      animFrameRef.current = requestAnimationFrame(gameLoop);
    },
    [canvasRef, syncSceneSize, setGameState, setScore, setTimeLeft, addCombo, resetCombo, addCaughtFish, setLastCatch]
  );

  const startGame = useCallback(() => {
    if (!canvasRef.current) return;
    const { width, height } = syncCanvasDisplaySize(canvasRef.current);

    syncSceneSize(width, height);
    if (!sceneRef.current) return;
    resetScene(sceneRef.current);

    hookWentDeepRef.current = false;
    setTimeLeft(useGameStore.getState().gameDuration);
    setStatusText('');
    lastTimeRef.current = performance.now();
    animFrameRef.current = requestAnimationFrame(gameLoop);
  }, [canvasRef, syncSceneSize, gameLoop, setTimeLeft, setStatusText]);

  const ambientLoop = useCallback(
    (timestamp: number) => {
      if (!canvasRef.current) return;

      const { width, height } = syncCanvasDisplaySize(canvasRef.current);
      syncSceneSize(width, height);

      const scene = sceneRef.current;
      const ctx = canvasRef.current.getContext('2d');
      if (!scene || !ctx) return;

      const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.05);
      lastTimeRef.current = timestamp;
      scene.gameTime += Math.max(dt, 0);
      scene.hook.y = scene.waterLevel;
      scene.hook.hasCatch = false;
      scene.hook.isDropping = false;

      for (const sw of scene.seaweeds) {
        sw.phase += 1.1 * dt;
      }

      render(ctx, scene);
      animFrameRef.current = requestAnimationFrame(ambientLoop);
    },
    [canvasRef, syncSceneSize]
  );

  const startAmbient = useCallback(() => {
    if (!canvasRef.current) return;
    lastTimeRef.current = performance.now();
    animFrameRef.current = requestAnimationFrame(ambientLoop);
  }, [canvasRef, ambientLoop]);

  const stopGame = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
  }, []);

  // Keyboard events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        spacePressedRef.current = true;
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        spacePressedRef.current = false;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  const gameState = useGameStore((s) => s.gameState);

  // Start/stop based on gameState
  useEffect(() => {
    if (gameState === 'playing') {
      startGame();
    } else if (gameState === 'idle') {
      startAmbient();
    }
    return () => stopGame();
  }, [gameState, startGame, startAmbient, stopGame]);

  return { startGame, stopGame };
}
