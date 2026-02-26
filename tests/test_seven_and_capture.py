from __future__ import annotations

from brandi_dog.engine.actions import PlaySevenSplitAction, SevenSubMove
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.rules import apply_action
from brandi_dog.engine.state import PawnRef, PlayerId, PositionKind

from .helpers import blank_state, make_engine, place_track, rank_card_id, with_player_hand


def test_seven_can_split_on_same_pawn() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 10)

    actions = engine.legal_actions(state)

    expected = PlaySevenSplitAction(
        player=PlayerId.A1,
        card_id=seven,
        represented_rank=Rank.SEVEN,
        moves=(
            SevenSubMove(pawn=PawnRef(PlayerId.A1, 0), steps=3),
            SevenSubMove(pawn=PawnRef(PlayerId.A1, 0), steps=4),
        ),
    )

    assert expected in actions


def test_seven_pass_capture_captures_traversed_open_fields() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))

    mover = PawnRef(PlayerId.A1, 0)
    victim_enemy_1 = PawnRef(PlayerId.B1, 0)
    victim_teammate = PawnRef(PlayerId.A2, 0)
    victim_enemy_2 = PawnRef(PlayerId.B2, 0)

    state = place_track(state, mover, 10)
    state = place_track(state, victim_enemy_1, 11)
    state = place_track(state, victim_teammate, 12)
    state = place_track(state, victim_enemy_2, 18)

    actions = engine.legal_actions(state)
    action = next(
        candidate
        for candidate in actions
        if isinstance(candidate, PlaySevenSplitAction)
        and candidate.moves == (SevenSubMove(pawn=mover, steps=7),)
    )

    next_state = apply_action(state, action, engine.cards_by_id)

    mover_position = next_state.pawn_positions[0]
    assert mover_position.kind == PositionKind.TRACK
    assert mover_position.index == 18

    for victim in (victim_enemy_1, victim_teammate, victim_enemy_2):
        victim_position = next_state.pawn_positions[int(victim.owner) * 4 + victim.number]
        assert victim_position.kind == PositionKind.BASE
