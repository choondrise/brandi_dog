from __future__ import annotations

import math
import random
from typing import Optional

from brandi_dog.agents import action_evaluation
from brandi_dog.agents.monte_carlo_imperfect import ImperfectInformationMonteCarloAgent
from brandi_dog.engine.actions import Action, DiscardHandAction, SkipTurnAction, SwapCardAction
from brandi_dog.engine.cards import Card, Rank
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PlayerId,
    PositionKind,
    RoundStage,
    Team,
    active_swap_player,
    get_pawn_position,
    hand_of,
    player_pawns,
    pawn_safe_entry_ready,
    team_of,
    teammate_of,
)

ENTRY_RANKS = {Rank.ACE, Rank.KING, Rank.JOKER}

ENTRY_KEEP_STRENGTH: dict[Rank, int] = {
    Rank.JOKER: 100,
    Rank.ACE: 90,
    Rank.KING: 80,
}

TACTICAL_GIVE_STRENGTH: dict[Rank, int] = {
    Rank.SEVEN: 100,
    Rank.FOUR: 92,
    Rank.JACK: 86,
    Rank.QUEEN: 64,
    Rank.TEN: 58,
    Rank.NINE: 52,
    Rank.EIGHT: 46,
    Rank.SIX: 40,
    Rank.FIVE: 34,
    Rank.THREE: 28,
    Rank.TWO: 20,
}

PERSONAL_KEEP_STRENGTH: dict[Rank, int] = {
    Rank.JOKER: 130,
    Rank.ACE: 115,
    Rank.KING: 105,
    Rank.SEVEN: 95,
    Rank.FOUR: 88,
    Rank.JACK: 82,
    Rank.QUEEN: 62,
    Rank.TEN: 56,
    Rank.NINE: 50,
    Rank.EIGHT: 44,
    Rank.SIX: 38,
    Rank.FIVE: 32,
    Rank.THREE: 26,
    Rank.TWO: 20,
}


class BeliefMonteCarloHeuristicAgent(ImperfectInformationMonteCarloAgent):
    """Imperfect-information Monte Carlo with heuristic priors and teammate-aware swaps.

    The engine still owns all legal move generation and state transitions. This
    agent only chooses among legal actions. Play-loop decisions reuse the
    existing imperfect-information determinized rollouts, then add a small
    immediate heuristic prior. Team-swap decisions use a separate policy because
    swap value is mostly about partner needs and preserving your own playability.
    """

    def __init__(
        self,
        seed: int = 0,
        top_k: int = 7,
        rollouts_per_action: int = 8,
        rollout_policy: str = "advanced_heuristic",
        rollout_workers: int = 1,
        heuristic_prior_weight: float = 0.04,
    ):
        super().__init__(
            seed=seed,
            top_k=top_k,
            rollouts_per_action=rollouts_per_action,
            rollout_policy=rollout_policy,
            rollout_workers=rollout_workers,
        )
        self.heuristic_prior_weight = heuristic_prior_weight
        self.rng = random.Random(seed)

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        if state.round_stage == RoundStage.GAME_OVER:
            raise RuntimeError("No legal actions available")
        if state.round_stage == RoundStage.TEAM_SWAPS:
            options = engine.legal_actions(state)
            if not options:
                raise RuntimeError("No legal actions available")
            return self._select_swap_action(options, state, active_swap_player(state), engine.cards_by_id)

        actor = action_evaluation.active_player_for_state(state)
        team = team_of(actor)
        candidates = self._rank_and_select_candidates(engine, state, team)
        if not candidates:
            raise RuntimeError("No legal actions available")

        rollout_scores = super()._score_candidates(state, actor, candidates, team)
        best_index = 0
        best_score = -math.inf
        for candidate_index, candidate in enumerate(candidates):
            score = rollout_scores[candidate_index] + (self.heuristic_prior_weight * self._heuristic_prior(engine, candidate, state, team))
            if score > best_score:
                best_score = score
                best_index = candidate_index
        return candidates[best_index]

    def _rank_and_select_candidates(self, engine: GameEngine, state: GameState, team: Team) -> list[Action]:
        legal = engine.legal_actions(state)
        if not legal:
            return []
        reduced = action_evaluation.candidate_actions(engine, state)
        if not reduced:
            reduced = tuple(action for action in legal if isinstance(action, (DiscardHandAction, SkipTurnAction))) or legal
        ranked = action_evaluation.rank_actions(engine, state, reduced, team)
        return ranked[: self.top_k]

    def _heuristic_prior(self, engine: GameEngine, action: Action, state: GameState, team: Team) -> float:
        immediate = action_evaluation.score_action_immediate(engine, state, action, team)[0]
        if not math.isfinite(immediate):
            return -1_000_000.0
        return immediate

    def _select_swap_action(
        self,
        options: tuple[Action, ...],
        state: GameState,
        actor: PlayerId,
        cards_by_id: dict[int, Card],
    ) -> Action:
        swaps = [action for action in options if isinstance(action, SwapCardAction)]
        if not swaps:
            return self.rng.choice(options)

        hand = hand_of(state, actor)
        entry_card_ids = [card_id for card_id in hand if cards_by_id[card_id].rank in ENTRY_RANKS]
        protected_card_ids: set[int] = set()
        if len(entry_card_ids) == 1 and not self._has_active_track_pawn(state, actor):
            protected_card_ids.add(entry_card_ids[0])

        allowed_swaps = [action for action in swaps if action.card_id not in protected_card_ids]
        if not allowed_swaps:
            allowed_swaps = swaps

        teammate = teammate_of(actor)
        teammate_has_base_pawns = self._base_pawn_count(state, teammate) > 0
        teammate_has_active_pawns = self._has_active_track_pawn(state, teammate)
        teammate_can_enter_safe = self._has_safe_entry_ready_track_pawn(state, teammate)

        if teammate_has_base_pawns:
            entry_swaps = [action for action in allowed_swaps if cards_by_id[action.card_id].rank in ENTRY_RANKS]
            if entry_swaps:
                return self._choose_min(
                    entry_swaps,
                    key=lambda action: (
                        ENTRY_KEEP_STRENGTH.get(cards_by_id[action.card_id].rank, 0),
                        action.card_id,
                    ),
                )

        if teammate_has_active_pawns or teammate_can_enter_safe:
            tactical_swaps = [action for action in allowed_swaps if cards_by_id[action.card_id].rank in TACTICAL_GIVE_STRENGTH]
            if tactical_swaps:
                return self._choose_max(
                    tactical_swaps,
                    key=lambda action: (
                        TACTICAL_GIVE_STRENGTH.get(cards_by_id[action.card_id].rank, 0)
                        + (30 if teammate_can_enter_safe and cards_by_id[action.card_id].rank in {Rank.FOUR, Rank.SEVEN} else 0),
                        -action.card_id,
                    ),
                )

        return self._choose_min(
            allowed_swaps,
            key=lambda action: (
                PERSONAL_KEEP_STRENGTH.get(cards_by_id[action.card_id].rank, 0),
                action.card_id,
            ),
        )

    def _has_active_track_pawn(self, state: GameState, player: PlayerId) -> bool:
        return any(get_pawn_position(state, pawn).kind == PositionKind.TRACK for pawn in player_pawns(player))

    def _has_safe_entry_ready_track_pawn(self, state: GameState, player: PlayerId) -> bool:
        return any(
            get_pawn_position(state, pawn).kind == PositionKind.TRACK and pawn_safe_entry_ready(state, pawn)
            for pawn in player_pawns(player)
        )

    def _base_pawn_count(self, state: GameState, player: PlayerId) -> int:
        return sum(1 for pawn in player_pawns(player) if get_pawn_position(state, pawn).kind == PositionKind.BASE)

    def _choose_max(self, actions: list[Action], key) -> Action:
        best_value = max(key(action) for action in actions)
        best = [action for action in actions if key(action) == best_value]
        return self.rng.choice(best)

    def _choose_min(self, actions: list[Action], key) -> Action:
        best_value = min(key(action) for action in actions)
        best = [action for action in actions if key(action) == best_value]
        return self.rng.choice(best)
