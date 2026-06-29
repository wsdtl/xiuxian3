const API_BASE = "/xiuxian/dongtian/lingguo-sum-ten";

export interface LingguoDifficulty {
  key: string;
  label: string;
  description: string;
  forbidden_enabled: boolean;
  sprinkle_pairs: number;
  forbidden_cell_rate: number;
}

export interface LingguoGameConfig {
  game_duration: number;
  score_cap: number;
  sum_target: number;
  cols: number;
  rows: number;
  round_ttl_minutes: number;
  round_min_seconds: number;
  difficulty_profiles: LingguoDifficulty[];
}

export interface LingguoConfigResponse {
  game_key: string;
  game_title: string;
  game_token: string;
  token_expires_at: string;
  config: LingguoGameConfig;
}

export interface LingguoRoundResponse {
  game_key: string;
  session_id: string;
  round_token: string;
  issued_at: string;
  expires_at: string;
  game_duration: number;
  score_cap: number;
  sum_target: number;
  cols: number;
  rows: number;
  round_min_seconds: number;
  difficulty: LingguoDifficulty;
}

export interface LingguoFinishPayload {
  gameToken: string;
  sessionId: string;
  roundToken: string;
  score: number;
  clearedCells: number;
  validClears: number;
  elapsedSeconds: number;
}

export interface LingguoFinishResponse {
  code: string;
  game_key: string;
  game_title: string;
  expires_at: string;
  accepted_score: number;
  cleared_cells: number;
  valid_clears: number;
  elapsed_seconds: number;
  difficulty: string;
  reward_preview: string[];
  message: string;
}

export async function fetchLingguoConfig(): Promise<LingguoConfigResponse> {
  return requestJson<LingguoConfigResponse>(`${API_BASE}/config`);
}

export async function startLingguoRound(gameToken: string): Promise<LingguoRoundResponse> {
  return requestJson<LingguoRoundResponse>(`${API_BASE}/start`, {
    method: "POST",
    body: JSON.stringify({ gameToken }),
  });
}

export async function finishLingguoRound(
  payload: LingguoFinishPayload
): Promise<LingguoFinishResponse> {
  return requestJson<LingguoFinishResponse>(`${API_BASE}/finish`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorText(body) || `请求失败：${response.status}`);
  }
  return body as T;
}

function errorText(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  return "";
}
