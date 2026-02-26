from __future__ import annotations

from dataclasses import replace

from brandi_dog.engine.cards import Rank
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    RoundStage,
    empty_swap_selections,
    initial_hands,
    initial_pawn_positions,
    safe_position,
    set_hand,
    set_pawn_position,
    track_position,
)


def make_engine(seed: int = 123) -> GameEngine:
    return GameEngine(seed=seed)


def rank_card_id(engine: GameEngine, rank: Rank, occurrence: int = 0) -> int:
    matches = [card.card_id for card in engine.cards if card.rank == rank]
    return matches[occurrence]


def blank_state(
    engine: GameEngine,
    stage: RoundStage = RoundStage.PLAY_LOOP,
    play_current: PlayerId = PlayerId.A1,
    round_starter: PlayerId = PlayerId.A1,
) -> GameState:
    draw_pile = tuple(card.card_id for card in engine.cards)
    return GameState(
        round_stage=stage,
        deal_round_index=0,
        round_starter=round_starter,
        play_current=play_current,
        swap_cursor=0,
        swap_selections=empty_swap_selections(),
        active_deal_size=0,
        hands=initial_hands(),
        pawn_positions=initial_pawn_positions(),
        draw_pile=draw_pile,
        discard_pile=(),
        winner=None,
    )


def with_player_hand(state: GameState, player: PlayerId, cards: tuple[int, ...]) -> GameState:
    return set_hand(state, player, cards)


def with_play_current(state: GameState, player: PlayerId) -> GameState:
    return replace(state, play_current=player)


def place_track(state: GameState, pawn: PawnRef, index: int) -> GameState:
    return set_pawn_position(state, pawn, track_position(index))


def place_safe(state: GameState, pawn: PawnRef, index: int) -> GameState:
    return set_pawn_position(state, pawn, safe_position(index))


def place_base(state: GameState, pawn: PawnRef) -> GameState:
    from brandi_dog.engine.state import base_position

    return set_pawn_position(state, pawn, base_position())
