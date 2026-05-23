from __future__ import annotations

import math
import random
from typing import Optional

from brandi_dog.agents import action_evaluation, AdvancedHeuristicAgent
from brandi_dog.agents.heuristic_agent import HeuristicAgent
from brandi_dog.agents.random_legal_agent import RandomLegalAgent
from brandi_dog.engine.actions import Action, DiscardHandAction, SkipTurnAction
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, RoundStage, Team, team_of


class MonteCarloAgent:
    def __init__(
        self,
        seed: int = 0,
        top_k: int = 3,
        rollouts_per_action: int = 2,
        rollout_policy: str = "advanced_heuristic",
    ):
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if rollouts_per_action <= 0:
            raise ValueError("rollouts_per_action must be greater than zero")
        if rollout_policy not in {"advanced_heuristic", "heuristic", "random"}:
            raise ValueError("rollout_policy must be one of: advanced_heuristic, heuristic, random")
        self.seed = seed
        self.top_k = top_k
        self.rollouts_per_action = rollouts_per_action
        self.rollout_policy = rollout_policy
        self.rng = random.Random(seed)

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        if state.round_stage == RoundStage.GAME_OVER:
            raise RuntimeError("No legal actions available")

        actor = action_evaluation.active_player_for_state(state)
        team = team_of(actor)
        candidates = self._rank_and_select_candidates(engine, state, team)
        if not candidates:
            raise RuntimeError("No legal actions available")

        best_action = candidates[0]
        best_score = -math.inf
        for candidate_index, candidate in enumerate(candidates):
            total = 0.0
            for rollout_index in range(self.rollouts_per_action):
                total += self._run_round_rollout(
                    state=state,
                    initial_action=candidate,
                    candidate_index=candidate_index,
                    rollout_index=rollout_index,
                    team=team,
                )
            average = total / self.rollouts_per_action
            if average > best_score:
                best_score = average
                best_action = candidate
        return best_action

    def candidate_actions(self, engine: GameEngine, state: GameState) -> tuple[Action, ...]:
        if state.round_stage == RoundStage.GAME_OVER:
            return ()
        actor = action_evaluation.active_player_for_state(state)
        team = team_of(actor)
        return tuple(self._rank_and_select_candidates(engine, state, team))

    def _rank_and_select_candidates(self, engine: GameEngine, state: GameState, team: Team) -> list[Action]:
        legal = engine.legal_actions(state)
        if not legal:
            return []
        reduced = action_evaluation.candidate_actions(engine, state)
        if not reduced:
            reduced = tuple(action for action in legal if isinstance(action, (DiscardHandAction, SkipTurnAction))) or legal
        ranked = action_evaluation.rank_actions(engine, state, reduced, team)
        return ranked[: self.top_k]

    def _run_round_rollout(
        self,
        state: GameState,
        initial_action: Action,
        candidate_index: int,
        rollout_index: int,
        team: Team,
    ) -> float:
        local_engine = GameEngine(seed=self._rollout_seed(candidate_index, rollout_index))
        rollout_state = state

        rollout_state = action_evaluation.apply_action_for_simulation(local_engine, rollout_state, initial_action)
        if rollout_state is None:
            return -1_000_000.0
        if action_evaluation.is_end_of_current_round(rollout_state):
            return action_evaluation.score_state_for_team(rollout_state, team)

        # Rollouts use action_evaluation.apply_action_for_simulation rather than
        # GameEngine.step. That intentionally avoids the automatic new deal in
        # GameEngine.step, so the horizon ends with the current card round.
        max_rollout_turns = sum(len(hand) for hand in rollout_state.hands) + 8
        turns = 0
        while not action_evaluation.is_end_of_current_round(rollout_state) and turns < max_rollout_turns:
            actor = action_evaluation.active_player_for_state(rollout_state)
            action = self._select_rollout_action(local_engine, rollout_state, candidate_index, rollout_index, turns, actor)
            next_state = action_evaluation.apply_action_for_simulation(local_engine, rollout_state, action)
            if next_state is None:
                break
            rollout_state = next_state
            turns += 1

        return action_evaluation.score_state_for_team(rollout_state, team)

    def _select_rollout_action(
        self,
        engine: GameEngine,
        state: GameState,
        candidate_index: int,
        rollout_index: int,
        turn_index: int,
        actor,
    ) -> Action:
        seed = self._rollout_seed(candidate_index, rollout_index) + (turn_index * 97) + int(actor)
        if self.rollout_policy == "random":
            return RandomLegalAgent(seed=seed).select_action(engine, state)
        if self.rollout_policy == "heuristic":
            return HeuristicAgent(seed=seed).select_action(engine, state)
        elif self.rollout_policy == "advanced_heuristic":
            return AdvancedHeuristicAgent(seed=seed, style='balanced').select_action(engine, state)
        return HeuristicAgent(seed=seed).select_action(engine, state)

    def _rollout_seed(self, candidate_index: int, rollout_index: int) -> int:
        return self.seed + (candidate_index * 10_007) + (rollout_index * 1_000_003)
