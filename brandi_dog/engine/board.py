from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .actions import MoveDirection
from .state import (
    GameState,
    PawnRef,
    PlayerId,
    Position,
    PositionKind,
    get_pawn_position,
    index_to_pawn,
    pawn_safe_entry_ready,
    pawn_to_index,
    safe_position,
    track_position,
)

MAIN_TRACK_LENGTH = 64
ENTRY_SPACING = 16
OPEN_FIELDS_TOTAL = 60
SAFE_ZONE_LENGTH = 4

ENTRY_INDEX_BY_PLAYER: dict[PlayerId, int] = {
    PlayerId.A1: 0,
    PlayerId.B1: 16,
    PlayerId.A2: 32,
    PlayerId.B2: 48,
}


def entry_index(player: PlayerId) -> int:
    return ENTRY_INDEX_BY_PLAYER[player]


def predecessor_of_entry(player: PlayerId) -> int:
    return (entry_index(player) - 1) % MAIN_TRACK_LENGTH


def next_track_index(index: int) -> int:
    return (index + 1) % MAIN_TRACK_LENGTH


def prev_track_index(index: int) -> int:
    return (index - 1) % MAIN_TRACK_LENGTH


def entry_owner(track_index: int) -> Optional[PlayerId]:
    for player, idx in ENTRY_INDEX_BY_PLAYER.items():
        if idx == track_index:
            return player
    return None


def is_entry_field(track_index: int) -> bool:
    return entry_owner(track_index) is not None


def is_open_play_field(track_index: int) -> bool:
    return not is_entry_field(track_index)


def is_direct_play_position(position: Position) -> bool:
    return position.kind == PositionKind.TRACK and position.index is not None and is_open_play_field(position.index)


def track_occupant(state: GameState, track_index: int, ignore: Optional[Iterable[PawnRef]] = None) -> Optional[PawnRef]:
    ignored = {pawn_to_index(p) for p in (ignore or ())}
    for idx, position in enumerate(state.pawn_positions):
        if idx in ignored:
            continue
        if position.kind == PositionKind.TRACK and position.index == track_index:
            return index_to_pawn(idx)
    return None


def safe_occupant(state: GameState, owner: PlayerId, safe_index: int, ignore: Optional[Iterable[PawnRef]] = None) -> Optional[PawnRef]:
    ignored = {pawn_to_index(p) for p in (ignore or ())}
    for pawn in (
        PawnRef(owner, 0),
        PawnRef(owner, 1),
        PawnRef(owner, 2),
        PawnRef(owner, 3),
    ):
        idx = pawn_to_index(pawn)
        if idx in ignored:
            continue
        position = state.pawn_positions[idx]
        if position.kind == PositionKind.SAFE and position.index == safe_index:
            return pawn
    return None


@dataclass(frozen=True)
class SimulatedPath:
    end: Position
    counted_positions: tuple[Position, ...]
    traversed_open_track_indices: tuple[int, ...]
    entered_safe_from_track: bool
    crossed_own_entry_from_behind: bool


@dataclass(frozen=True)
class EntryPath:
    end: Position


def simulate_entry_from_base(state: GameState, pawn: PawnRef) -> Optional[EntryPath]:
    start = get_pawn_position(state, pawn)
    if start.kind != PositionKind.BASE:
        return None
    target = entry_index(pawn.owner)
    if track_occupant(state, target) is not None:
        return None
    return EntryPath(end=track_position(target))


def simulate_step_move(
    state: GameState,
    pawn: PawnRef,
    direction: MoveDirection,
    steps: int,
    prefer_safe_entry: bool = True,
) -> Optional[SimulatedPath]:
    if steps <= 0:
        return None

    start = get_pawn_position(state, pawn)
    if start.kind == PositionKind.BASE:
        return None

    if direction == MoveDirection.BACKWARD:
        return _simulate_backward(state, pawn, steps)
    return _simulate_forward(state, pawn, steps, prefer_safe_entry=prefer_safe_entry)


def _simulate_forward(state: GameState, pawn: PawnRef, steps: int, prefer_safe_entry: bool) -> Optional[SimulatedPath]:
    start = get_pawn_position(state, pawn)
    counted: list[Position] = []
    traversed_open: list[int] = []

    if start.kind == PositionKind.SAFE:
        assert start.index is not None
        safe_idx = start.index
        for _ in range(steps):
            next_safe = safe_idx + 1
            if next_safe >= SAFE_ZONE_LENGTH:
                return None
            if safe_occupant(state, pawn.owner, next_safe, ignore=[pawn]) is not None:
                return None
            safe_idx = next_safe
            counted.append(safe_position(safe_idx))
        return SimulatedPath(
            end=safe_position(safe_idx),
            counted_positions=tuple(counted),
            traversed_open_track_indices=tuple(traversed_open),
            entered_safe_from_track=False,
            crossed_own_entry_from_behind=False,
        )

    if start.kind != PositionKind.TRACK or start.index is None:
        return None

    current = start.index
    remaining = steps
    can_enter_safe_now = pawn_safe_entry_ready(state, pawn)
    crossed_own_entry_from_behind = False
    entered_safe = False
    safe_idx: Optional[int] = None

    while remaining > 0:
        if safe_idx is not None:
            next_safe = safe_idx + 1
            if next_safe >= SAFE_ZONE_LENGTH:
                return None
            if safe_occupant(state, pawn.owner, next_safe, ignore=[pawn]) is not None:
                return None
            safe_idx = next_safe
            counted.append(safe_position(safe_idx))
            remaining -= 1
            continue

        if can_enter_safe_now and current == entry_index(pawn.owner) and prefer_safe_entry:
            if safe_occupant(state, pawn.owner, 0, ignore=[pawn]) is None:
                safe_idx = 0
                counted.append(safe_position(0))
                entered_safe = True
                remaining -= 1
                continue

        prev = current
        candidate = next_track_index(current)
        candidate_owner = entry_owner(candidate)
        if candidate_owner is not None and candidate_owner != pawn.owner:
            if track_occupant(state, candidate, ignore=[pawn]) is not None:
                return None
            current = candidate
            continue

        current = candidate
        if candidate_owner == pawn.owner:
            occupant = track_occupant(state, candidate, ignore=[pawn])
            if occupant is not None and (remaining - 1) > 0:
                return None
        counted.append(track_position(current))
        if is_open_play_field(current):
            traversed_open.append(current)
        remaining -= 1

        if current == entry_index(pawn.owner) and prev == predecessor_of_entry(pawn.owner):
            can_enter_safe_now = True
            crossed_own_entry_from_behind = True

    if safe_idx is not None:
        end = safe_position(safe_idx)
    else:
        end = track_position(current)

    return SimulatedPath(
        end=end,
        counted_positions=tuple(counted),
        traversed_open_track_indices=tuple(traversed_open),
        entered_safe_from_track=entered_safe,
        crossed_own_entry_from_behind=crossed_own_entry_from_behind,
    )


def _simulate_backward(state: GameState, pawn: PawnRef, steps: int) -> Optional[SimulatedPath]:
    start = get_pawn_position(state, pawn)
    if start.kind != PositionKind.TRACK or start.index is None:
        return None

    current = start.index
    remaining = steps
    counted: list[Position] = []
    traversed_open: list[int] = []

    while remaining > 0:
        candidate = prev_track_index(current)
        candidate_owner = entry_owner(candidate)
        if candidate_owner is not None and candidate_owner != pawn.owner:
            if track_occupant(state, candidate, ignore=[pawn]) is not None:
                return None
            current = candidate
            continue

        current = candidate
        if candidate_owner == pawn.owner:
            occupant = track_occupant(state, candidate, ignore=[pawn])
            if occupant is not None and (remaining - 1) > 0:
                return None
        counted.append(track_position(current))
        if is_open_play_field(current):
            traversed_open.append(current)
        remaining -= 1

    return SimulatedPath(
        end=track_position(current),
        counted_positions=tuple(counted),
        traversed_open_track_indices=tuple(traversed_open),
        entered_safe_from_track=False,
        crossed_own_entry_from_behind=False,
    )
