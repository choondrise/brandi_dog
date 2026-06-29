import type { ActionPreview, AppPayload, BotLevel, Seat } from "./types";

const fallbackBase = `${window.location.protocol}//${window.location.hostname}:8000`;
const env = (import.meta as unknown as { env?: { VITE_API_BASE?: string } }).env || {};
export const API_BASE = (env.VITE_API_BASE || fallbackBase).replace(/\/$/, "");
export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export function createSession(hostName: string) {
  return request<{ game_id: string; host_token: string; player_token: string }>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ host_name: hostName }),
  });
}

export function joinSession(gameId: string, playerName: string, preferredSeat: Seat | null = null) {
  return request<{ game_id: string; player_token: string; seat: Seat | null }>(`/api/sessions/${gameId}/join`, {
    method: "POST",
    body: JSON.stringify({ player_name: playerName, preferred_seat: preferredSeat }),
  });
}

export function getState(gameId: string, token: string | null) {
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return request<AppPayload>(`/api/sessions/${gameId}${query}`);
}

export function setSeat(gameId: string, token: string, seat: Seat | null) {
  return request<AppPayload>(`/api/sessions/${gameId}/seat`, {
    method: "POST",
    body: JSON.stringify({ token, seat }),
  });
}

export function setBot(gameId: string, token: string, seat: Seat, level: BotLevel) {
  return request<AppPayload>(`/api/sessions/${gameId}/bot`, {
    method: "POST",
    body: JSON.stringify({ token, seat, level }),
  });
}

export function startGame(gameId: string, token: string) {
  return request<AppPayload>(`/api/sessions/${gameId}/start`, {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export function playAction(gameId: string, token: string, actionKey: string) {
  return request<AppPayload>(`/api/sessions/${gameId}/action`, {
    method: "POST",
    body: JSON.stringify({ token, action_key: actionKey }),
  });
}


export function previewSevenSplit(
  gameId: string,
  token: string,
  cardId: number,
  representedRank: string,
  moves: { pawn_id: string; steps: number; prefer_safe_entry?: boolean }[],
) {
  return request<ActionPreview>(`/api/sessions/${gameId}/preview-seven`, {
    method: "POST",
    body: JSON.stringify({ token, card_id: cardId, represented_rank: representedRank, seven_moves: moves }),
  });
}

export function playSevenSplit(
  gameId: string,
  token: string,
  cardId: number,
  representedRank: string,
  moves: { pawn_id: string; steps: number; prefer_safe_entry?: boolean }[],
) {
  return request<AppPayload>(`/api/sessions/${gameId}/action`, {
    method: "POST",
    body: JSON.stringify({ token, card_id: cardId, represented_rank: representedRank, seven_moves: moves }),
  });
}
