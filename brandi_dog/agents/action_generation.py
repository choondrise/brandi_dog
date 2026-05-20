from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, TypeVar

from brandi_dog.engine.cards import Rank
from brandi_dog.engine.state import GameState, PawnRef, PlayerId, PositionKind, get_pawn_position, player_pawns


DEFAULT_JOKER_REPRESENT_ORDER: tuple[Rank, ...] = (
    Rank.ACE,
    Rank.KING,
    Rank.SEVEN,
    Rank.JACK,
    Rank.FOUR,
    Rank.QUEEN,
    Rank.TEN,
    Rank.NINE,
    Rank.EIGHT,
    Rank.SIX,
    Rank.FIVE,
    Rank.THREE,
    Rank.TWO,
)


@dataclass(frozen=True)
class AgentActionGenerationPolicy:
    suppress_redundant_joker_ranks: bool = True
    ignore_base_pawns_for_movement: bool = True
    seven_capture_only_when_available: bool = True


def represented_ranks_for_card(
    card_rank: Rank,
    non_joker_ranks_in_hand: set[Rank],
    policy: AgentActionGenerationPolicy,
) -> tuple[Rank, ...]:
    if card_rank != Rank.JOKER:
        return (card_rank,)

    if not policy.suppress_redundant_joker_ranks:
        return DEFAULT_JOKER_REPRESENT_ORDER

    filtered = tuple(rank for rank in DEFAULT_JOKER_REPRESENT_ORDER if rank not in non_joker_ranks_in_hand)
    if filtered:
        return filtered
    return DEFAULT_JOKER_REPRESENT_ORDER


def movement_pawns_for_owner(
    state: GameState,
    owner: PlayerId,
    policy: AgentActionGenerationPolicy,
) -> tuple[PawnRef, ...]:
    pawns = player_pawns(owner)
    if not policy.ignore_base_pawns_for_movement:
        return pawns
    return tuple(pawn for pawn in pawns if get_pawn_position(state, pawn).kind != PositionKind.BASE)


def movement_pawns_for_owners(
    state: GameState,
    owners: Iterable[PlayerId],
    policy: AgentActionGenerationPolicy,
) -> tuple[PawnRef, ...]:
    return tuple(pawn for owner in owners for pawn in movement_pawns_for_owner(state, owner, policy))


class CaptureCandidate(Protocol):
    capture_count: int


Candidate = TypeVar("Candidate", bound=CaptureCandidate)


def prune_to_capture_candidates_when_available(
    candidates: list[Candidate],
    policy: AgentActionGenerationPolicy,
) -> list[Candidate]:
    if not policy.seven_capture_only_when_available:
        return candidates

    capture_candidates = [candidate for candidate in candidates if candidate.capture_count > 0]
    if capture_candidates:
        return capture_candidates
    return candidates
