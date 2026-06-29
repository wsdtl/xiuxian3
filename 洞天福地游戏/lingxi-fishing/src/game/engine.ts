import { GameScene, Fish, Seaweed, CaughtFishRecord } from './types';
import {
  WATER_LEVEL_RATIO,
  HOOK_X_RATIO,
  FISH_SPAWN_INTERVAL_MIN,
  FISH_SPAWN_INTERVAL_MAX,
  DEPTH_BONUS_MAX,
} from './constants';
import { spawnFish, updateFish, isFishOffScreen, checkHookCollision } from './fish';
import { createHook, updateHook, isHookAtSurface, getHookDepthRatio } from './hook';

export interface EngineCallbacks {
  onScoreUpdate: (baseScore: number, combo: number, depthBonus: number, totalScore: number, fish: Fish) => void;
  onTimeUpdate: (timeLeft: number) => void;
  onGameEnd: (caughtFish: CaughtFishRecord[]) => void;
}

export function createScene(canvasWidth: number, canvasHeight: number): GameScene {
  const waterLevel = canvasHeight * WATER_LEVEL_RATIO;
  const hookX = canvasWidth * HOOK_X_RATIO;

  const seaweeds: Seaweed[] = [];
  for (let i = 0; i < 12; i++) {
    seaweeds.push({
      x: Math.random() * canvasWidth,
      height: 40 + Math.random() * 60,
      phase: Math.random() * Math.PI * 2,
      color: ['#2D8B46', '#1E6B33', '#3DA85C'][Math.floor(Math.random() * 3)],
    });
  }

  return {
    fishes: [],
    hook: createHook(hookX, waterLevel, canvasHeight),
    bubbles: [],
    seaweeds,
    scorePopups: [],
    waterLevel,
    canvasWidth,
    canvasHeight,
    gameTime: 0,
    nextFishSpawn: 0.5,
  };
}

export function resetScene(scene: GameScene): void {
  scene.fishes = [];
  scene.bubbles = [];
  scene.scorePopups = [];
  scene.gameTime = 0;
  scene.nextFishSpawn = 0.5;
  scene.hook = createHook(scene.canvasWidth * HOOK_X_RATIO, scene.waterLevel, scene.canvasHeight);

  for (const sw of scene.seaweeds) {
    sw.phase = Math.random() * Math.PI * 2;
  }
}

function spawnBubble(scene: GameScene): void {
  if (scene.bubbles.length > 20) return;
  scene.bubbles.push({
    x: Math.random() * scene.canvasWidth,
    y: scene.canvasHeight - Math.random() * 40,
    radius: 2 + Math.random() * 4,
    speed: 20 + Math.random() * 40,
    opacity: 0.3 + Math.random() * 0.4,
  });
}

export function updateScene(
  scene: GameScene,
  dt: number,
  spacePressed: boolean,
  durationSeconds: number,
  combo: number,
  callbacks: EngineCallbacks
): number {
  scene.gameTime += dt;

  // Update time
  const timeLeft = Math.max(0, Math.max(1, durationSeconds) - scene.gameTime);
  callbacks.onTimeUpdate(timeLeft);

  if (timeLeft <= 0) return 0;

  // Spawn fish
  scene.nextFishSpawn -= dt;
  if (scene.nextFishSpawn <= 0) {
    const fish = spawnFish(scene);
    if (fish) scene.fishes.push(fish);
    scene.nextFishSpawn =
      FISH_SPAWN_INTERVAL_MIN + Math.random() * (FISH_SPAWN_INTERVAL_MAX - FISH_SPAWN_INTERVAL_MIN);
  }

  // Spawn bubbles
  if (Math.random() < 0.1) spawnBubble(scene);

  // Update hook
  const prevY = scene.hook.y;
  updateHook(scene.hook, scene.waterLevel, spacePressed, dt);

  // Update fishes
  for (const fish of scene.fishes) {
    if (!fish.caught) {
      updateFish(fish, dt);
    } else if (fish.caught && scene.hook.hasCatch === fish) {
      // Fish follows hook
      fish.x = scene.hook.x;
      fish.y = scene.hook.y;
    }
  }

  // Check collisions (only when hook is dropping)
  if (scene.hook.isDropping && !scene.hook.hasCatch) {
    for (const fish of scene.fishes) {
      if (checkHookCollision(fish, scene.hook.x, scene.hook.y, 8)) {
        fish.caught = true;
        scene.hook.hasCatch = fish;
        scene.hook.isDropping = false;
        break;
      }
    }
  }

  // Check if retracted catch reached surface
  if (scene.hook.hasCatch) {
    const caughtFish = scene.hook.hasCatch;
    if (isHookAtSurface(scene.hook, scene.waterLevel)) {
      const depthRatio = getHookDepthRatio(
        { ...scene.hook, y: prevY },
        scene.waterLevel,
        scene.canvasHeight
      );
      const baseScore = caughtFish.type.score;
      const depthBonus = Math.floor(baseScore * depthRatio * DEPTH_BONUS_MAX);
      const comboMultiplier = 1 + (combo - 1) * 0.5;
      const totalScore = Math.floor((baseScore + depthBonus) * comboMultiplier);

      callbacks.onScoreUpdate(baseScore, combo, depthBonus, totalScore, caughtFish);

      // Score popup
      scene.scorePopups.push({
        x: scene.hook.x,
        y: scene.waterLevel,
        score: totalScore,
        combo,
        depthBonus,
        opacity: 1,
        offsetY: 0,
        createdAt: scene.gameTime,
      });

      // Remove caught fish
      scene.fishes = scene.fishes.filter((f) => f.id !== caughtFish.id);
      scene.hook.hasCatch = false;
    }
  }

  // Remove off-screen fish
  scene.fishes = scene.fishes.filter(
    (f) => !isFishOffScreen(f, scene.canvasWidth) || f.caught
  );

  // Update bubbles
  for (const b of scene.bubbles) {
    b.y -= b.speed * dt;
    b.opacity -= 0.1 * dt;
  }
  scene.bubbles = scene.bubbles.filter((b) => b.y > scene.waterLevel && b.opacity > 0);

  // Update seaweed
  for (const sw of scene.seaweeds) {
    sw.phase += 1.5 * dt;
  }

  // Update score popups
  for (const sp of scene.scorePopups) {
    sp.offsetY += 40 * dt;
    sp.opacity -= 0.6 * dt;
  }
  scene.scorePopups = scene.scorePopups.filter(
    (sp) => sp.opacity > 0
  );

  return timeLeft;
}
