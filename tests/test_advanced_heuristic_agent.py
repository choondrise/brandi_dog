from __future__ import annotations

from dataclasses import replace

import pytest

from brandi_dog.agents import AdvancedHeuristicAgent
from brandi_dog.engine.actions import PlayEnterAction, PlaySevenSplitAction, PlayStepCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.state import PawnRef, PlayerId

from .helpers import blank_state, make_engine, place_track, rank_card_id, with_player_hand


def _set_safe_ready(state, pawn: PawnRef, ready: bool):
    values = list(state.pawn_safe_entry_ready)
    values[int(pawn.owner) * 4 + pawn.number] = ready
    return replace(state, pawn_safe_entry_ready=tuple(values))


def test_advanced_heuristic_agent_is_plug_and_play_and_selects_legal_action() -> None:
    engine = make_engine()
    ace = rank_card_id(engine, Rank.ACE)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace,))

    action = AdvancedHeuristicAgent(seed=1).select_action(engine, state)

    assert action in engine.legal_actions(state)
    assert isinstance(action, PlayEnterAction)


def test_advanced_heuristic_prioritizes_board_intention_for_safe_entry() -> None:
    engine = make_engine()
    six = rank_card_id(engine, Rank.SIX)
    ace = rank_card_id(engine, Rank.ACE)
    pawn = PawnRef(PlayerId.A1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (six, ace))
    state = place_track(state, pawn, 59)
    state = _set_safe_ready(state, pawn, True)

    action = AdvancedHeuristicAgent(seed=2, style="defensive", top_n_intentions=3).select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == six
    assert action.pawn == pawn
    assert action.prefer_safe_entry


def test_aggressive_style_prefers_capture_over_base_entry_when_both_available() -> None:
    engine = make_engine()
    three = rank_card_id(engine, Rank.THREE)
    mover = PawnRef(PlayerId.A1, 0)
    victim = PawnRef(PlayerId.B1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (three,))
    state = place_track(state, mover, 10)
    state = place_track(state, victim, 13)

    action = AdvancedHeuristicAgent(seed=3, style="aggressive", top_n_intentions=3).select_action(engine, state)

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == three
    assert action.pawn == mover


def test_advanced_heuristic_uses_broad_intention_before_fallback() -> None:
    engine = make_engine()
    three = rank_card_id(engine, Rank.THREE)
    mover = PawnRef(PlayerId.A1, 0)
    victim = PawnRef(PlayerId.B1, 0)

    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (three,))
    state = place_track(state, mover, 10)
    state = place_track(state, victim, 13)
    agent = AdvancedHeuristicAgent(seed=6, style="defensive", top_n_intentions=1)

    action = agent.select_action(engine, state)
    stats = agent.report_stats()

    assert isinstance(action, PlayStepCardAction)
    assert action.card_id == three
    assert stats["fallback_decisions"] == 0
    assert stats["matched_by_kind"]["any_capture"] == 1


def test_invalid_advanced_heuristic_style_is_rejected() -> None:
    with pytest.raises(ValueError, match="style"):
        AdvancedHeuristicAgent(style="reckless")


def test_advanced_heuristic_reports_intention_stats() -> None:
    engine = make_engine()
    ace = rank_card_id(engine, Rank.ACE)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace,))
    agent = AdvancedHeuristicAgent(seed=4)

    agent.select_action(engine, state)
    stats = agent.report_stats()

    assert stats["total_play_decisions"] == 1
    assert stats["intention_matched_decisions"] == 1
    assert stats["fallback_decisions"] == 0
    assert stats["matched_by_kind"]["enter_base"] == 1


def test_advanced_heuristic_simplifies_seven_splits_when_many_team_pawns_are_movable() -> None:
    engine = make_engine()
    seven = rank_card_id(engine, Rank.SEVEN)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (seven,))
    for index, pawn in enumerate(
        (
            PawnRef(PlayerId.A1, 0),
            PawnRef(PlayerId.A1, 1),
            PawnRef(PlayerId.A1, 2),
            PawnRef(PlayerId.A1, 3),
        )
    ):
        state = place_track(state, pawn, 5 + (index * 5))

    engine_options = engine.legal_actions(state)
    engine_sevens = [action for action in engine_options if isinstance(action, PlaySevenSplitAction)]
    agent = AdvancedHeuristicAgent(seed=5, simplify_seven_pawn_threshold=3)

    reduced = agent.candidate_actions(engine, state)
    reduced_sevens = [action for action in reduced if isinstance(action, PlaySevenSplitAction)]

    assert len(engine_sevens) > len(reduced_sevens)
    assert reduced_sevens
    assert all(len(action.moves) == 1 and action.moves[0].steps == 7 for action in reduced_sevens)
    assert all(action in engine_options for action in reduced_sevens)
    assert agent.report_stats()["seven_simplified_decisions"] == 1
    assert agent.report_stats()["seven_actions_removed"] == len(engine_sevens) - len(reduced_sevens)
