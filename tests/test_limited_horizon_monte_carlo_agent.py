from __future__ import annotations

from brandi_dog.agents import MonteCarloAgent
from brandi_dog.agents import action_evaluation
from brandi_dog.engine.actions import PlayEnterAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import PlayerId, RoundStage

from .helpers import blank_state, rank_card_id, with_player_hand


def test_monte_carlo_agent_selects_legal_action() -> None:
    engine = GameEngine(seed=1)
    ace = rank_card_id(engine, Rank.ACE)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace,))

    agent = MonteCarloAgent(seed=5, top_k=2, rollouts_per_action=2, rollout_policy="random")
    action = agent.select_action(engine, state)

    assert action in engine.legal_actions(state)
    assert isinstance(action, PlayEnterAction)


def test_candidate_actions_respects_top_k() -> None:
    engine = GameEngine(seed=1)
    ace = rank_card_id(engine, Rank.ACE)
    king = rank_card_id(engine, Rank.KING)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace, king))

    agent = MonteCarloAgent(seed=7, top_k=1, rollouts_per_action=1, rollout_policy="random")

    assert len(agent.candidate_actions(engine, state)) == 1


def test_simulation_apply_does_not_deal_next_round() -> None:
    engine = GameEngine(seed=1)
    ace = rank_card_id(engine, Rank.ACE)
    state = blank_state(engine)
    state = with_player_hand(state, PlayerId.A1, (ace,))
    action = next(action for action in engine.legal_actions(state) if isinstance(action, PlayEnterAction))

    simulated = action_evaluation.apply_action_for_simulation(engine, state, action)
    stepped = engine.step(state, action)

    assert simulated is not None
    assert action_evaluation.is_end_of_current_round(simulated)
    assert simulated.deal_round_index == state.deal_round_index
    assert stepped.deal_round_index == state.deal_round_index + 1
    assert stepped.round_stage == RoundStage.TEAM_SWAPS
