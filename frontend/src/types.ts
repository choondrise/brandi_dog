export type Seat = "A1" | "B1" | "A2" | "B2";
export type BotLevel = "Idiot" | "Easy" | "Medium" | "Hard" | "Cheater";

export interface SeatInfo {
  seat: Seat;
  team: "A" | "B";
  occupant: "human" | "bot";
  human_name: string | null;
  bot_level: BotLevel;
}

export interface PublicSession {
  game_id: string;
  phase: "LOBBY" | "PLAYING" | "FINISHED";
  seats: Record<Seat, SeatInfo>;
}

export interface CardInfo {
  id: number;
  rank: string;
  label: string;
  asset: string;
}

export interface PawnInfo {
  id: string;
  owner: Seat;
  number: number;
  color: string;
  position: {
    kind: "BASE" | "TRACK" | "SAFE";
    index: number | null;
  };
}

export interface ActionPawnRef {
  id: string;
  owner: Seat;
  number: number;
}

export interface ActionMoveInfo {
  pawn: ActionPawnRef;
  steps: number;
  preferSafeEntry: boolean;
}

export interface ActionInfo {
  id: number;
  type: string;
  player: Seat;
  label: string;
  card?: CardInfo;
  representedRank: string | null;
  pawns: ActionPawnRef[];
  moves: ActionMoveInfo[];
  steps: number | null;
  direction: "FORWARD" | "BACKWARD" | null;
  preferSafeEntry: boolean | null;
}

export interface GamePayload {
  phase: "TEAM_SWAPS" | "PLAY_LOOP" | "GAME_OVER";
  dealRoundIndex: number;
  activeDealSize: number;
  roundStarter: Seat;
  playCurrent: Seat;
  activePlayer: Seat | null;
  winner: "A" | "B" | null;
  pawns: PawnInfo[];
  hands: Record<Seat, { count: number; cards: CardInfo[] | null }>;
  legalActions: ActionInfo[];
  discardCount: number;
  drawCount: number;
}

export interface AppPayload {
  session: PublicSession;
  game: GamePayload | null;
  viewerSeat: Seat | null;
  isHost: boolean;
}
