from __future__ import annotations

import math
import multiprocessing as mp
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from typing import Optional

from brandi_dog.agents import action_evaluation, AdvancedHeuristicAgent
from brandi_dog.agents.heuristic_agent import HeuristicAgent
from brandi_dog.agents.random_legal_agent import RandomLegalAgent
from brandi_dog.engine.actions import Action, DiscardHandAction, SkipTurnAction
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PlayerId, RoundStage, Team, team_of


def _rollout_seed(base_seed: int, candidate_index: int, rollout_index: int) -> int:
    return base_seed + (candidate_index * 10_007) + (rollout_index * 1_000_003)


def _determinization_seed(base_seed: int, rollout_index: int) -> int:
    # Same rollout index uses the same hidden-card sample for every candidate.
    return base_seed + (rollout_index * 1_000_003) + 91_337


def _run_round_rollout_indexed_job(job) -> tuple[int, float]:
    candidate_index = job[2]
    return candidate_index, _run_round_rollout_job(job)


def _run_round_rollout_job(job) -> float:
    state, observer, initial_action, candidate_index, rollout_index, team, base_seed, rollout_policy = job
    local_engine = GameEngine(seed=_rollout_seed(base_seed, candidate_index, rollout_index))
    rollout_state = _determinize_hidden_hands(state, observer, random.Random(_determinization_seed(base_seed, rollout_index)))

    rollout_state = action_evaluation.apply_action_for_simulation(local_engine, rollout_state, initial_action)
    if rollout_state is None:
        return -1_000_000.0
    if action_evaluation.is_end_of_current_round(rollout_state):
        return action_evaluation.score_state_for_team(rollout_state, team)

    max_rollout_turns = sum(len(hand) for hand in rollout_state.hands) + 8
    turns = 0
    while not action_evaluation.is_end_of_current_round(rollout_state) and turns < max_rollout_turns:
        actor = action_evaluation.active_player_for_state(rollout_state)
        action = _select_rollout_action(
            local_engine,
            rollout_state,
            base_seed,
            candidate_index,
            rollout_index,
            turns,
            actor,
            rollout_policy,
        )
        next_state = action_evaluation.apply_action_for_simulation(local_engine, rollout_state, action)
        if next_state is None:
            break
        rollout_state = next_state
        turns += 1

    return action_evaluation.score_state_for_team(rollout_state, team)


def _determinize_hidden_hands(state: GameState, observer: PlayerId, rng: random.Random) -> GameState:
    """Sample plausible hidden hands for all non-observer players.

    The observer keeps their exact hand so candidate actions remain legal. Other
    players keep only their hand sizes; their concrete cards are sampled from the
    union of hidden hands and draw pile. Discard pile and board state stay fixed.

    This is an information-set determinization, not a perfect inference model.
    It assumes the observer does not know other hands or draw order.
    """

    hands = [tuple(hand) for hand in state.hands]
    hidden_players = [player for player in PlayerId if player != observer]
    unknown_cards: list[int] = []
    for player in hidden_players:
        unknown_cards.extend(hands[int(player)])
    unknown_cards.extend(state.draw_pile)
    rng.shuffle(unknown_cards)

    cursor = 0
    for player in hidden_players:
        count = len(hands[int(player)])
        hands[int(player)] = tuple(unknown_cards[cursor : cursor + count])
        cursor += count
    new_draw_pile = tuple(unknown_cards[cursor:])
    return replace(state, hands=tuple(hands), draw_pile=new_draw_pile)


def _select_rollout_action(
    engine: GameEngine,
    state: GameState,
    base_seed: int,
    candidate_index: int,
    rollout_index: int,
    turn_index: int,
    actor,
    rollout_policy: str,
) -> Action:
    seed = _rollout_seed(base_seed, candidate_index, rollout_index) + (turn_index * 97) + int(actor)
    if rollout_policy == "random":
        return RandomLegalAgent(seed=seed).select_action(engine, state)
    if rollout_policy == "heuristic":
        return HeuristicAgent(seed=seed).select_action(engine, state)
    if rollout_policy == "advanced_heuristic":
        return AdvancedHeuristicAgent(seed=seed, style="balanced").select_action(engine, state)
    return HeuristicAgent(seed=seed).select_action(engine, state)


class ImperfectInformationMonteCarloAgent:
    """Limited-horizon Monte Carlo agent with randomized hidden opponent hands.

    This class mirrors MonteCarloAgent but avoids perfect-information rollouts.
    For each rollout index, non-observer hands are re-sampled while preserving
    hand sizes. The same sampled hidden state is reused across all top-k
    candidates for that rollout index, reducing variance between candidates.
    """

    def __init__(
        self,
        seed: int = 0,
        top_k: int = 3,
        rollouts_per_action: int = 2,
        rollout_policy: str = "advanced_heuristic",
        rollout_workers: int = 1,
    ):
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if rollouts_per_action <= 0:
            raise ValueError("rollouts_per_action must be greater than zero")
        if rollout_policy not in {"advanced_heuristic", "heuristic", "random"}:
            raise ValueError("rollout_policy must be one of: advanced_heuristic, heuristic, random")
        if rollout_workers <= 0:
            raise ValueError("rollout_workers must be greater than zero")
        self.seed = seed
        self.top_k = top_k
        self.rollouts_per_action = rollouts_per_action
        self.rollout_policy = rollout_policy
        self.rollout_workers = min(4, rollout_workers)
        self.rng = random.Random(seed)
        self._rollout_executor: Optional[ProcessPoolExecutor] = None

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        if state.round_stage == RoundStage.GAME_OVER:
            raise RuntimeError("No legal actions available")

        actor = action_evaluation.active_player_for_state(state)
        team = team_of(actor)
        candidates = self._rank_and_select_candidates(engine, state, team)
        if not candidates:
            raise RuntimeError("No legal actions available")

        scores = self._score_candidates(state, actor, candidates, team)
        best_index = 0
        best_score = -math.inf
        for candidate_index, score in enumerate(scores):
            if score > best_score:
                best_score = score
                best_index = candidate_index
        return candidates[best_index]

    def _score_candidates(self, state: GameState, observer: PlayerId, candidates: list[Action], team: Team) -> list[float]:
        jobs = [
            (state, observer, candidate, candidate_index, rollout_index, team, self.seed, self.rollout_policy)
            for candidate_index, candidate in enumerate(candidates)
            for rollout_index in range(self.rollouts_per_action)
        ]
        if self.rollout_workers == 1 or len(jobs) <= 1:
            totals = [0.0 for _ in candidates]
            for job in jobs:
                candidate_index = job[3]
                totals[candidate_index] += _run_round_rollout_job(job)
            return [total / self.rollouts_per_action for total in totals]

        totals = [0.0 for _ in candidates]
        executor = self._get_rollout_executor()
        for candidate_index, score in executor.map(_run_round_rollout_indexed_job, jobs):
            totals[candidate_index] += score
        return [total / self.rollouts_per_action for total in totals]

    def _get_rollout_executor(self) -> ProcessPoolExecutor:
        if self._rollout_executor is None:
            context = mp.get_context("spawn")
            self._rollout_executor = ProcessPoolExecutor(max_workers=self.rollout_workers, mp_context=context)
        return self._rollout_executor

    def shutdown(self) -> None:
        if self._rollout_executor is not None:
            self._rollout_executor.shutdown()
            self._rollout_executor = None

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_rollout_executor"] = None
        return state

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass

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


# Short alias for imports/scripts that prefer the file name.
MonteCarloImperfectAgent = ImperfectInformationMonteCarloAgent
