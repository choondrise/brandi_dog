from __future__ import annotations

from dataclasses import replace

from brandi_dog.engine.actions import PlayStepCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.rules import apply_action
from brandi_dog.engine.state import PawnRef, PlayerId, PositionKind, pawn_safe_entry_ready

from .helpers import blank_state, make_engine, place_track, rank_card_id, with_player_hand


def test_forward_move_can_choose_safe_entry_or_continue_track() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO)
    pawn = PawnRef(PlayerId.A1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (two,))
    state = place_track(state, pawn, 63)

    actions = engine.legal_actions(state)
    candidates = [
        action
        for action in actions
        if isinstance(action, PlayStepCardAction)
        and action.card_id == two
        and action.pawn == pawn
        and action.steps == 2
    ]

    enter_safe = next(action for action in candidates if action.prefer_safe_entry)
    continue_track = next(action for action in candidates if not action.prefer_safe_entry)

    safe_state = apply_action(state, enter_safe, engine.cards_by_id)
    safe_position = safe_state.pawn_positions[0]
    assert safe_position.kind == PositionKind.SAFE
    assert safe_position.index == 0

    track_state = apply_action(state, continue_track, engine.cards_by_id)
    track_position = track_state.pawn_positions[0]
    assert track_position.kind == PositionKind.TRACK
    assert track_position.index == 1


def test_landing_on_own_entry_persists_safe_entry_eligibility_across_turns() -> None:
    engine = make_engine()
    first_ace = rank_card_id(engine, Rank.ACE, occurrence=0)
    second_ace = rank_card_id(engine, Rank.ACE, occurrence=1)
    pawn = PawnRef(PlayerId.A1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (first_ace,))
    state = place_track(state, pawn, 63)

    first_action = next(
        action
        for action in engine.legal_actions(state)
        if isinstance(action, PlayStepCardAction)
        and action.card_id == first_ace
        and action.pawn == pawn
        and action.steps == 1
    )

    after_first = apply_action(state, first_action, engine.cards_by_id)
    assert after_first.pawn_positions[0].kind == PositionKind.TRACK
    assert after_first.pawn_positions[0].index == 0
    assert pawn_safe_entry_ready(after_first, pawn)

    state_again = replace(after_first, play_current=PlayerId.A1)
    state_again = with_player_hand(state_again, PlayerId.A1, (second_ace,))

    second_action = next(
        action
        for action in engine.legal_actions(state_again)
        if isinstance(action, PlayStepCardAction)
        and action.card_id == second_ace
        and action.pawn == pawn
        and action.steps == 1
        and action.prefer_safe_entry
    )

    after_second = apply_action(state_again, second_action, engine.cards_by_id)
    assert after_second.pawn_positions[0].kind == PositionKind.SAFE
    assert after_second.pawn_positions[0].index == 0

