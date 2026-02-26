from __future__ import annotations

from brandi_dog.engine.actions import DiscardHandAction, MoveDirection, PlayStepCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.rules import apply_action
from brandi_dog.engine.state import PawnRef, PlayerId, PositionKind

from .helpers import blank_state, make_engine, place_track, rank_card_id, with_player_hand


def test_backward_four_blocked_by_occupied_entry_but_allowed_from_entry_start() -> None:
    engine = make_engine()
    four = rank_card_id(engine, Rank.FOUR)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (four,))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 2)
    state = place_track(state, PawnRef(PlayerId.A1, 1), 0)

    actions = engine.legal_actions(state)

    blocked = any(
        isinstance(action, PlayStepCardAction)
        and action.card_id == four
        and action.pawn == PawnRef(PlayerId.A1, 0)
        and action.direction == MoveDirection.BACKWARD
        and action.steps == 4
        for action in actions
    )
    assert not blocked

    allowed_from_entry = any(
        isinstance(action, PlayStepCardAction)
        and action.card_id == four
        and action.pawn == PawnRef(PlayerId.A1, 1)
        and action.direction == MoveDirection.BACKWARD
        and action.steps == 4
        for action in actions
    )
    assert allowed_from_entry


def test_other_entry_is_skipped_for_counting_when_unoccupied() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (two,))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 15)

    actions = engine.legal_actions(state)
    move = next(
        action
        for action in actions
        if isinstance(action, PlayStepCardAction)
        and action.pawn == PawnRef(PlayerId.A1, 0)
        and action.card_id == two
        and action.steps == 2
        and action.direction == MoveDirection.FORWARD
    )

    next_state = apply_action(state, move, engine.cards_by_id)
    final_position = next_state.pawn_positions[0]
    assert final_position.kind == PositionKind.TRACK
    assert final_position.index == 18


def test_other_occupied_entry_blocks_passage() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (two,))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 15)
    state = place_track(state, PawnRef(PlayerId.B1, 0), 16)

    actions = engine.legal_actions(state)
    assert actions == (DiscardHandAction(player=PlayerId.A1),)
