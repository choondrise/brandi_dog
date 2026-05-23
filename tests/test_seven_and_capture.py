from __future__ import annotations

from brandi_dog.engine.actions import PlayEnterAction, PlaySevenSplitAction, SevenSubMove
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.rules import apply_action
from brandi_dog.engine.state import PawnRef, PlayerId, PositionKind

from .helpers import blank_state, make_engine, place_track, rank_card_id, with_player_hand


def _seven_actions(actions):
    return [action for action in actions if isinstance(action, PlaySevenSplitAction)]


def test_seven_single_pawn_generates_only_one_full_seven_move() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)
    pawn = PawnRef(PlayerId.A1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))
    state = place_track(state, pawn, 10)

    actions = _seven_actions(engine.legal_actions(state))

    assert actions == (
        [
            PlaySevenSplitAction(
                player=PlayerId.A1,
                card_id=seven,
                represented_rank=Rank.SEVEN,
                moves=(SevenSubMove(pawn=pawn, steps=7),),
            )
        ]
    )


def test_seven_two_pawns_generates_eight_step_distributions() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)
    first = PawnRef(PlayerId.A1, 0)
    second = PawnRef(PlayerId.A2, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))
    state = place_track(state, first, 10)
    state = place_track(state, second, 20)

    actions = _seven_actions(engine.legal_actions(state))
    step_pairs = {
        tuple((move.pawn, move.steps) for move in action.moves)
        for action in actions
    }

    assert len(actions) == 8
    assert ((second, 7),) in step_pairs
    assert ((second, 6), (first, 1)) in step_pairs
    assert ((second, 4), (first, 3)) in step_pairs
    assert ((second, 1), (first, 6)) in step_pairs
    assert ((first, 7),) in step_pairs


def test_seven_moves_furthest_pawn_first_for_allocations() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)
    behind = PawnRef(PlayerId.A1, 0)
    ahead = PawnRef(PlayerId.A2, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))
    state = place_track(state, behind, 10)
    state = place_track(state, ahead, 20)

    action = next(
        action
        for action in _seven_actions(engine.legal_actions(state))
        if len(action.moves) == 2 and {move.steps for move in action.moves} == {3, 4}
    )

    assert action.moves[0].pawn == ahead


def test_entry_card_generates_one_base_entry_action() -> None:
    engine = make_engine()
    ace = rank_card_id(engine, Rank.ACE)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace,))

    entry_actions = [action for action in engine.legal_actions(state) if isinstance(action, PlayEnterAction)]

    assert entry_actions == [
        PlayEnterAction(
            player=PlayerId.A1,
            card_id=ace,
            represented_rank=Rank.ACE,
            pawn=PawnRef(PlayerId.A1, 0),
        )
    ]


def test_joker_does_not_generate_rank_already_present_in_hand() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)
    joker = rank_card_id(engine, Rank.JOKER)
    pawn = PawnRef(PlayerId.A1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven, joker))
    state = place_track(state, pawn, 10)

    joker_as_seven = [
        action
        for action in engine.legal_actions(state)
        if isinstance(action, PlaySevenSplitAction)
        and action.card_id == joker
        and action.represented_rank == Rank.SEVEN
    ]

    assert not joker_as_seven


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

    action = next(
        candidate
        for candidate in _seven_actions(engine.legal_actions(state))
        if candidate.moves == (SevenSubMove(pawn=mover, steps=7),)
    )

    next_state = apply_action(state, action, engine.cards_by_id)

    mover_position = next_state.pawn_positions[0]
    assert mover_position.kind == PositionKind.TRACK
    assert mover_position.index == 18

    for victim in (victim_enemy_1, victim_teammate, victim_enemy_2):
        victim_position = next_state.pawn_positions[int(victim.owner) * 4 + victim.number]
        assert victim_position.kind == PositionKind.BASE
