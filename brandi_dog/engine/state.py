from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, IntEnum
from typing import Optional, Tuple


class Team(Enum):
    A = "A"
    B = "B"


class PlayerId(IntEnum):
    A1 = 0
    B1 = 1
    A2 = 2
    B2 = 3


PLAY_ORDER: tuple[PlayerId, PlayerId, PlayerId, PlayerId] = (
    PlayerId.A1,
    PlayerId.B1,
    PlayerId.A2,
    PlayerId.B2,
)

SWAP_SELECTION_ORDER: tuple[PlayerId, PlayerId, PlayerId, PlayerId] = (
    PlayerId.A1,
    PlayerId.A2,
    PlayerId.B1,
    PlayerId.B2,
)

TEAM_PLAYERS: dict[Team, tuple[PlayerId, PlayerId]] = {
    Team.A: (PlayerId.A1, PlayerId.A2),
    Team.B: (PlayerId.B1, PlayerId.B2),
}

TEAM_OF_PLAYER: dict[PlayerId, Team] = {
    PlayerId.A1: Team.A,
    PlayerId.A2: Team.A,
    PlayerId.B1: Team.B,
    PlayerId.B2: Team.B,
}

TEAMMATE_OF: dict[PlayerId, PlayerId] = {
    PlayerId.A1: PlayerId.A2,
    PlayerId.A2: PlayerId.A1,
    PlayerId.B1: PlayerId.B2,
    PlayerId.B2: PlayerId.B1,
}


class RoundStage(Enum):
    TEAM_SWAPS = "TEAM_SWAPS"
    PLAY_LOOP = "PLAY_LOOP"
    GAME_OVER = "GAME_OVER"


class PositionKind(Enum):
    BASE = "BASE"
    TRACK = "TRACK"
    SAFE = "SAFE"


@dataclass(frozen=True)
class Position:
    kind: PositionKind
    index: Optional[int] = None


@dataclass(frozen=True)
class PawnRef:
    owner: PlayerId
    number: int


@dataclass(frozen=True)
class GameState:
    round_stage: RoundStage
    deal_round_index: int
    round_starter: PlayerId
    play_current: PlayerId
    swap_cursor: int
    swap_selections: tuple[Optional[int], Optional[int], Optional[int], Optional[int]]
    active_deal_size: int
    hands: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]
    pawn_positions: tuple[Position, ...]
    pawn_safe_entry_ready: tuple[bool, ...]
    draw_pile: tuple[int, ...]
    discard_pile: tuple[int, ...]
    winner: Optional[Team] = None


def pawn_to_index(pawn: PawnRef) -> int:
    if pawn.number < 0 or pawn.number > 3:
        raise ValueError(f"Invalid pawn number: {pawn.number}")
    return int(pawn.owner) * 4 + pawn.number


def index_to_pawn(index: int) -> PawnRef:
    if index < 0 or index >= 16:
        raise ValueError(f"Invalid pawn index: {index}")
    owner = PlayerId(index // 4)
    return PawnRef(owner=owner, number=index % 4)


def player_pawns(player: PlayerId) -> tuple[PawnRef, PawnRef, PawnRef, PawnRef]:
    return (
        PawnRef(player, 0),
        PawnRef(player, 1),
        PawnRef(player, 2),
        PawnRef(player, 3),
    )


def base_position() -> Position:
    return Position(PositionKind.BASE, None)


def track_position(index: int) -> Position:
    return Position(PositionKind.TRACK, index)


def safe_position(index: int) -> Position:
    return Position(PositionKind.SAFE, index)


def get_pawn_position(state: GameState, pawn: PawnRef) -> Position:
    return state.pawn_positions[pawn_to_index(pawn)]


def set_pawn_position(state: GameState, pawn: PawnRef, position: Position) -> GameState:
    as_list = list(state.pawn_positions)
    as_list[pawn_to_index(pawn)] = position
    return replace(state, pawn_positions=tuple(as_list))


def pawn_safe_entry_ready(state: GameState, pawn: PawnRef) -> bool:
    return state.pawn_safe_entry_ready[pawn_to_index(pawn)]


def set_pawn_safe_entry_ready(state: GameState, pawn: PawnRef, ready: bool) -> GameState:
    as_list = list(state.pawn_safe_entry_ready)
    as_list[pawn_to_index(pawn)] = ready
    return replace(state, pawn_safe_entry_ready=tuple(as_list))


def hand_of(state: GameState, player: PlayerId) -> tuple[int, ...]:
    return state.hands[int(player)]


def set_hand(state: GameState, player: PlayerId, hand: tuple[int, ...]) -> GameState:
    as_list = list(state.hands)
    as_list[int(player)] = hand
    return replace(state, hands=tuple(as_list))


def active_swap_player(state: GameState) -> PlayerId:
    return SWAP_SELECTION_ORDER[state.swap_cursor]


def next_in_play_order(player: PlayerId) -> PlayerId:
    idx = PLAY_ORDER.index(player)
    return PLAY_ORDER[(idx + 1) % len(PLAY_ORDER)]


def team_of(player: PlayerId) -> Team:
    return TEAM_OF_PLAYER[player]


def teammate_of(player: PlayerId) -> PlayerId:
    return TEAMMATE_OF[player]


def player_finished(state: GameState, player: PlayerId) -> bool:
    return all(get_pawn_position(state, pawn).kind == PositionKind.SAFE for pawn in player_pawns(player))


def team_winner(state: GameState) -> Optional[Team]:
    team_a_done = player_finished(state, PlayerId.A1) and player_finished(state, PlayerId.A2)
    if team_a_done:
        return Team.A
    team_b_done = player_finished(state, PlayerId.B1) and player_finished(state, PlayerId.B2)
    if team_b_done:
        return Team.B
    return None


def empty_swap_selections() -> tuple[None, None, None, None]:
    return (None, None, None, None)


def initial_hands() -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    return ((), (), (), ())


def initial_pawn_positions() -> tuple[Position, ...]:
    return tuple(base_position() for _ in range(16))


def initial_pawn_safe_entry_ready() -> tuple[bool, ...]:
    return tuple(False for _ in range(16))
