from __future__ import annotations

from brandi_dog.engine.actions import MoveDirection, PlayJackSwapAction, PlayStepCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.state import PawnRef, PlayerId

from .helpers import blank_state, make_engine, place_safe, place_track, rank_card_id, with_player_hand


def test_jack_allows_only_direct_play_source_and_target() -> None:
    engine = make_engine()
    jack = rank_card_id(engine, Rank.JACK)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (jack,))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 5)
    state = place_track(state, PawnRef(PlayerId.B1, 0), 20)

    actions = engine.legal_actions(state)
    valid_swap = PlayJackSwapAction(
        player=PlayerId.A1,
        card_id=jack,
        represented_rank=Rank.JACK,
        source=PawnRef(PlayerId.A1, 0),
        target=PawnRef(PlayerId.B1, 0),
    )
    assert valid_swap in actions

    state_target_on_entry = place_track(state, PawnRef(PlayerId.B1, 0), 16)
    actions_target_on_entry = engine.legal_actions(state_target_on_entry)
    assert not any(isinstance(action, PlayJackSwapAction) for action in actions_target_on_entry)

    state_source_on_entry = place_track(state, PawnRef(PlayerId.A1, 0), 0)
    actions_source_on_entry = engine.legal_actions(state_source_on_entry)
    assert not any(isinstance(action, PlayJackSwapAction) for action in actions_source_on_entry)


def test_joker_cannot_enter_safe_with_last_remaining_pawn() -> None:
    engine = make_engine()
    joker = rank_card_id(engine, Rank.JOKER)
    two = rank_card_id(engine, Rank.TWO)

    last_pawn = PawnRef(PlayerId.A1, 3)

    base_state = blank_state(engine)
    base_state = place_safe(base_state, PawnRef(PlayerId.A1, 0), 1)
    base_state = place_safe(base_state, PawnRef(PlayerId.A1, 1), 2)
    base_state = place_safe(base_state, PawnRef(PlayerId.A1, 2), 3)
    base_state = place_track(base_state, last_pawn, 63)

    joker_state = with_player_hand(base_state, PlayerId.A1, (joker,))
    joker_actions = engine.legal_actions(joker_state)
    forbidden = any(
        isinstance(action, PlayStepCardAction)
        and action.card_id == joker
        and action.represented_rank == Rank.TWO
        and action.pawn == last_pawn
        and action.steps == 2
        and action.direction == MoveDirection.FORWARD
        for action in joker_actions
    )
    assert not forbidden

    two_state = with_player_hand(base_state, PlayerId.A1, (two,))
    two_actions = engine.legal_actions(two_state)
    allowed = any(
        isinstance(action, PlayStepCardAction)
        and action.card_id == two
        and action.pawn == last_pawn
        and action.steps == 2
        and action.direction == MoveDirection.FORWARD
        for action in two_actions
    )
    assert allowed


def test_finished_player_controls_teammate_pawns() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO)

    state = blank_state(engine, play_current=PlayerId.A2)
    state = with_player_hand(state, PlayerId.A2, (two,))

    state = place_safe(state, PawnRef(PlayerId.A2, 0), 0)
    state = place_safe(state, PawnRef(PlayerId.A2, 1), 1)
    state = place_safe(state, PawnRef(PlayerId.A2, 2), 2)
    state = place_safe(state, PawnRef(PlayerId.A2, 3), 3)

    state = place_track(state, PawnRef(PlayerId.A1, 0), 5)

    actions = engine.legal_actions(state)
    step_actions = [action for action in actions if isinstance(action, PlayStepCardAction)]

    assert any(action.pawn.owner == PlayerId.A1 for action in step_actions)
    assert not any(action.pawn.owner == PlayerId.A2 for action in step_actions)
