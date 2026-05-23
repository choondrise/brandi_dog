from __future__ import annotations

from dataclasses import replace

from brandi_dog.agents.heuristic_agent import HeuristicAgent, SEVEN_OPTION_SAMPLE_LIMIT
from brandi_dog.engine.actions import PlayEnterAction, PlaySevenSplitAction, PlayStepCardAction, SwapCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.state import PawnRef, PlayerId, RoundStage

from .helpers import (
    blank_state,
    make_engine,
    place_safe,
    place_track,
    rank_card_id,
    with_player_hand,
)


def _set_safe_ready(state, pawn: PawnRef, ready: bool):
    values = list(state.pawn_safe_entry_ready)
    values[int(pawn.owner) * 4 + pawn.number] = ready
    return replace(state, pawn_safe_entry_ready=tuple(values))


def test_swap_with_two_entry_cards_sends_entry_card_to_teammate() -> None:
    engine = make_engine()
    ace = rank_card_id(engine, Rank.ACE, occurrence=0)
    king = rank_card_id(engine, Rank.KING, occurrence=0)
    seven = rank_card_id(engine, Rank.SEVEN, occurrence=0)

    state = blank_state(engine, stage=RoundStage.TEAM_SWAPS)
    state = with_player_hand(state, PlayerId.A1, (ace, king, seven))

    agent = HeuristicAgent(seed=5)
    action = agent.select_action(engine, state)

    assert isinstance(action, SwapCardAction)
    assert engine.cards_by_id[action.card_id].rank in {Rank.ACE, Rank.KING, Rank.JOKER}


def test_swap_without_entry_and_without_pawn_in_play_sends_strongest_card() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO, occurrence=0)
    seven = rank_card_id(engine, Rank.SEVEN, occurrence=0)
    queen = rank_card_id(engine, Rank.QUEEN, occurrence=0)

    state = blank_state(engine, stage=RoundStage.TEAM_SWAPS)
    state = with_player_hand(state, PlayerId.A1, (two, queen, seven))

    agent = HeuristicAgent(seed=7)
    action = agent.select_action(engine, state)

    assert isinstance(action, SwapCardAction)
    assert action.card_id == seven


def test_prefers_enter_with_non_joker_entry_card() -> None:
    engine = make_engine()
    ace = rank_card_id(engine, Rank.ACE, occurrence=0)
    joker = rank_card_id(engine, Rank.JOKER, occurrence=0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace, joker))

    agent = HeuristicAgent(seed=11)
    action = agent.select_action(engine, state)

    assert isinstance(action, PlayEnterAction)
    assert engine.cards_by_id[action.card_id].rank in {Rank.ACE, Rank.KING}


def test_prioritizes_safe_zone_entry_over_capture() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO, occurrence=0)
    mover = PawnRef(PlayerId.A1, 0)
    victim = PawnRef(PlayerId.B1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (two,))
    state = place_track(state, mover, 63)
    state = place_track(state, victim, 1)

    agent = HeuristicAgent(seed=13)
    action = agent.select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.pawn == mover
    assert action.steps == 2
    assert action.prefer_safe_entry


def test_prioritizes_capture_when_no_safe_progress_is_available() -> None:
    engine = make_engine()
    three = rank_card_id(engine, Rank.THREE, occurrence=0)
    five = rank_card_id(engine, Rank.FIVE, occurrence=0)
    mover = PawnRef(PlayerId.A1, 0)
    victim = PawnRef(PlayerId.B1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (three, five))
    state = place_track(state, mover, 10)
    state = place_track(state, victim, 13)

    agent = HeuristicAgent(seed=17)
    action = agent.select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == three
    assert action.pawn == mover


def test_avoids_starting_new_circle_when_other_progress_move_exists() -> None:
    engine = make_engine()
    six = rank_card_id(engine, Rank.SIX, occurrence=0)
    pawn_circle = PawnRef(PlayerId.A1, 0)
    pawn_blocker = PawnRef(PlayerId.A1, 1)
    pawn_other = PawnRef(PlayerId.A1, 2)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (six,))
    state = place_track(state, pawn_circle, 63)
    state = place_safe(state, pawn_blocker, 0)
    state = place_track(state, pawn_other, 5)
    state = _set_safe_ready(state, pawn_circle, True)

    agent = HeuristicAgent(seed=19)
    action = agent.select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == six
    assert action.pawn == pawn_other


def test_prefers_safe_move_that_reaches_deeper_safe_index() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO, occurrence=0)
    pawn_from_track = PawnRef(PlayerId.A1, 0)
    pawn_inside_safe = PawnRef(PlayerId.A1, 1)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (two,))
    state = place_track(state, pawn_from_track, 0)
    state = place_safe(state, pawn_inside_safe, 1)
    state = _set_safe_ready(state, pawn_from_track, True)

    agent = HeuristicAgent(seed=23)
    action = agent.select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == two
    assert action.pawn == pawn_inside_safe


def test_preselect_prunes_joker_representations_if_rank_exists_in_hand() -> None:
    engine = make_engine()
    four = rank_card_id(engine, Rank.FOUR, occurrence=0)
    joker = rank_card_id(engine, Rank.JOKER, occurrence=0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (four, joker))
    state = place_track(state, PawnRef(PlayerId.A1, 0), 5)

    agent = HeuristicAgent(seed=29)
    options = engine.legal_actions(state)
    filtered = agent._preselect_play_options(options, state, PlayerId.A1, engine.cards_by_id)

    joker_representing_four = [
        action
        for action in filtered
        if isinstance(action, PlayStepCardAction)
        and engine.cards_by_id[action.card_id].rank == Rank.JOKER
        and action.represented_rank == Rank.FOUR
    ]
    assert not joker_representing_four


def test_preselect_samples_large_seven_action_space() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN, occurrence=0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))

    placements = (
        (PawnRef(PlayerId.A1, 0), 5),
        (PawnRef(PlayerId.A1, 1), 10),
        (PawnRef(PlayerId.A1, 2), 20),
        (PawnRef(PlayerId.A1, 3), 30),
        (PawnRef(PlayerId.A2, 0), 35),
        (PawnRef(PlayerId.A2, 1), 40),
        (PawnRef(PlayerId.A2, 2), 45),
        (PawnRef(PlayerId.A2, 3), 50),
    )
    for pawn, index in placements:
        state = place_track(state, pawn, index)

    agent = HeuristicAgent(seed=31)
    options = agent._play_options_for_agent(engine, state)
    filtered = agent._preselect_play_options(options, state, PlayerId.A1, engine.cards_by_id)
    seven_filtered = [action for action in filtered if isinstance(action, PlaySevenSplitAction)]

    assert seven_filtered
    assert len(seven_filtered) <= SEVEN_OPTION_SAMPLE_LIMIT


def test_selected_heuristic_action_is_engine_legal_after_reduced_seven_generation() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN, occurrence=0)
    state = blank_state(engine, play_current=PlayerId.B2)
    state = with_player_hand(state, PlayerId.B2, (seven,))
    state = place_track(state, PawnRef(PlayerId.B2, 0), 30)
    state = place_track(state, PawnRef(PlayerId.B1, 0), 20)

    agent = HeuristicAgent(seed=37)
    action = agent.select_action(engine, state)

    assert action in engine.legal_actions(state)
    engine.step(state, action)
