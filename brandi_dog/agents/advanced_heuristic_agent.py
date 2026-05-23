from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from brandi_dog.engine import rules as engine_rules
from brandi_dog.engine.actions import (
    Action,
    MoveDirection,
    DiscardHandAction,
    PlayEnterAction,
    PlayJackSwapAction,
    PlaySevenSplitAction,
    PlayStepCardAction,
    SkipTurnAction,
    SwapCardAction,
)
from brandi_dog.engine.board import MAIN_TRACK_LENGTH, entry_index, simulate_step_move
from brandi_dog.engine.cards import Card, Rank
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    TEAM_PLAYERS,
    GameState,
    PawnRef,
    PlayerId,
    PositionKind,
    RoundStage,
    Team,
    active_swap_player,
    get_pawn_position,
    hand_of,
    pawn_safe_entry_ready,
    player_pawns,
    team_of,
)

ENTRY_RANKS = {Rank.ACE, Rank.KING, Rank.JOKER}
CARD_VALUE: dict[Rank, int] = {
    Rank.TWO: 2,
    Rank.THREE: 3,
    Rank.FOUR: 4,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.SEVEN: 7,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.JACK: 11,
    Rank.QUEEN: 12,
    Rank.KING: 13,
    Rank.ACE: 14,
    Rank.JOKER: 15,
}


@dataclass(frozen=True)
class _Weights:
    safe_entry: float
    enter_base: float
    capture: float
    progress: float
    avoid_new_circle: float
    preserve_joker: float


@dataclass
class AdvancedHeuristicStats:
    total_play_decisions: int = 0
    intention_matched_decisions: int = 0
    fallback_decisions: int = 0
    matched_safe_entry: int = 0
    matched_enter_base: int = 0
    matched_capture: int = 0
    matched_progress: int = 0
    matched_any_safe_entry: int = 0
    matched_any_enter_base: int = 0
    matched_any_capture: int = 0
    matched_any_progress: int = 0
    seven_simplified_decisions: int = 0
    seven_actions_removed: int = 0


@dataclass(frozen=True)
class _Intention:
    kind: str
    score: float
    pawn: Optional[PawnRef] = None
    target: Optional[PawnRef] = None
    min_steps: Optional[int] = None
    max_steps: Optional[int] = None


STYLE_WEIGHTS: dict[str, _Weights] = {
    "balanced": _Weights(
        safe_entry=1000.0,
        enter_base=450.0,
        capture=650.0,
        progress=8.0,
        avoid_new_circle=150.0,
        preserve_joker=15.0,
    ),
    "aggressive": _Weights(
        safe_entry=900.0,
        enter_base=350.0,
        capture=1000.0,
        progress=10.0,
        avoid_new_circle=80.0,
        preserve_joker=5.0,
    ),
    "defensive": _Weights(
        safe_entry=1300.0,
        enter_base=600.0,
        capture=400.0,
        progress=5.0,
        avoid_new_circle=300.0,
        preserve_joker=30.0,
    ),
}


class AdvancedHeuristicAgent:
    def __init__(
        self,
        seed: Optional[int] = None,
        rng: Optional[random.Random] = None,
        style: str = "balanced",
        top_n_intentions: int = 3,
        simplify_seven_pawn_threshold: int = 4,
    ):
        if rng is not None and seed is not None:
            raise ValueError("Provide either seed or rng, not both")
        if style not in STYLE_WEIGHTS:
            raise ValueError("style must be one of: balanced, aggressive, defensive")
        if top_n_intentions <= 0:
            raise ValueError("top_n_intentions must be greater than zero")
        if simplify_seven_pawn_threshold < 0:
            raise ValueError("simplify_seven_pawn_threshold must be non-negative")
        self.rng = rng if rng is not None else random.Random(seed)
        self.style = style
        self.weights = STYLE_WEIGHTS[style]
        self.top_n_intentions = top_n_intentions
        self.simplify_seven_pawn_threshold = simplify_seven_pawn_threshold
        self.stats = AdvancedHeuristicStats()

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        options = self.candidate_actions(engine, state)
        if not options:
            raise RuntimeError("No legal actions available")
        actor = active_swap_player(state) if state.round_stage == RoundStage.TEAM_SWAPS else state.play_current
        if state.round_stage == RoundStage.TEAM_SWAPS:
            return self._select_swap_action(options, state, actor, engine.cards_by_id)
        return self._select_play_action(engine, state, options, actor)

    def candidate_actions(self, engine: GameEngine, state: GameState) -> tuple[Action, ...]:
        options = engine.legal_actions(state)
        if state.round_stage != RoundStage.PLAY_LOOP:
            return options
        return self._simplify_large_team_sevens(engine, state, options)

    def _simplify_large_team_sevens(
        self,
        engine: GameEngine,
        state: GameState,
        options: tuple[Action, ...],
    ) -> tuple[Action, ...]:
        seven_actions = [action for action in options if isinstance(action, PlaySevenSplitAction)]
        if not seven_actions:
            return options

        team = team_of(state.play_current)
        movable_pawns = self._team_movable_seven_pawns(state, team)
        if len(movable_pawns) <= self.simplify_seven_pawn_threshold:
            return options

        non_seven = [action for action in options if not isinstance(action, PlaySevenSplitAction)]
        simplified = self._single_pawn_seven_actions(engine, state, seven_actions, movable_pawns)
        if not simplified:
            return options

        self.stats.seven_simplified_decisions += 1
        self.stats.seven_actions_removed += max(0, len(seven_actions) - len(simplified))
        return tuple(non_seven + simplified)

    def _team_movable_seven_pawns(self, state: GameState, team: Team) -> tuple[PawnRef, ...]:
        return tuple(
            pawn
            for player in TEAM_PLAYERS[team]
            for pawn in player_pawns(player)
            if get_pawn_position(state, pawn).kind != PositionKind.BASE
        )

    def _single_pawn_seven_actions(
        self,
        engine: GameEngine,
        state: GameState,
        seven_actions: list[PlaySevenSplitAction],
        movable_pawns: tuple[PawnRef, ...],
    ) -> list[Action]:
        movable = set(movable_pawns)
        selected: dict[tuple[int, Rank, PlayerId, PawnRef, bool], PlaySevenSplitAction] = {}
        for action in seven_actions:
            if len(action.moves) != 1:
                continue
            move = action.moves[0]
            if move.pawn not in movable or move.steps != 7:
                continue
            key = (action.card_id, action.represented_rank, action.player, move.pawn, move.prefer_safe_entry)
            selected[key] = action
        return sorted(selected.values(), key=lambda action: (self._action_card_value(engine, action), action.card_id, repr(action)))

    def rank_actions(self, engine: GameEngine, state: GameState, actions: tuple[Action, ...]) -> list[Action]:
        """Return actions ordered from best to worst by this agent's immediate heuristic score."""

        if state.round_stage == RoundStage.TEAM_SWAPS:
            actor = active_swap_player(state)
        else:
            actor = state.play_current
        team = team_of(actor)
        return sorted(
            list(actions),
            key=lambda action: (
                -self._score_action(engine, state, action, team),
                self._action_card_value(engine, action),
                self._action_card_id(action),
                repr(action),
            ),
        )

    def reset_stats(self) -> None:
        self.stats = AdvancedHeuristicStats()

    def report_stats(self) -> dict[str, object]:
        total = self.stats.total_play_decisions
        fallback_rate = self.stats.fallback_decisions / total if total else 0.0
        intention_rate = self.stats.intention_matched_decisions / total if total else 0.0
        return {
            "style": self.style,
            "top_n_intentions": self.top_n_intentions,
            "total_play_decisions": total,
            "intention_matched_decisions": self.stats.intention_matched_decisions,
            "fallback_decisions": self.stats.fallback_decisions,
            "intention_match_rate": intention_rate,
            "fallback_rate": fallback_rate,
            "seven_simplified_decisions": self.stats.seven_simplified_decisions,
            "seven_actions_removed": self.stats.seven_actions_removed,
            "matched_by_kind": {
                "safe_entry": self.stats.matched_safe_entry,
                "enter_base": self.stats.matched_enter_base,
                "capture": self.stats.matched_capture,
                "progress": self.stats.matched_progress,
                "any_safe_entry": self.stats.matched_any_safe_entry,
                "any_enter_base": self.stats.matched_any_enter_base,
                "any_capture": self.stats.matched_any_capture,
                "any_progress": self.stats.matched_any_progress,
            },
        }

    def _select_swap_action(
        self,
        options: tuple[Action, ...],
        state: GameState,
        actor: PlayerId,
        cards_by_id: dict[int, Card],
    ) -> Action:
        swaps = [action for action in options if isinstance(action, SwapCardAction)]
        if not swaps:
            return options[0]
        hand = hand_of(state, actor)
        entry_cards = [card_id for card_id in hand if cards_by_id[card_id].rank in ENTRY_RANKS]
        if len(entry_cards) >= 2:
            entry_swaps = [action for action in swaps if cards_by_id[action.card_id].rank in ENTRY_RANKS]
            if entry_swaps:
                return min(entry_swaps, key=lambda action: (CARD_VALUE[cards_by_id[action.card_id].rank], action.card_id))
        return min(swaps, key=lambda action: (CARD_VALUE.get(cards_by_id[action.card_id].rank, 0), action.card_id))

    def _select_play_action(
        self,
        engine: GameEngine,
        state: GameState,
        options: tuple[Action, ...],
        actor: PlayerId,
    ) -> Action:
        self.stats.total_play_decisions += 1
        team = team_of(actor)
        intentions = self._top_intentions(state, team)
        for intention in intentions:
            matches = [action for action in options if self._matches_intention(engine, state, action, intention, team)]
            if matches:
                self.stats.intention_matched_decisions += 1
                self._record_intention_match(intention.kind)
                return self._best_action_by_score(engine, state, matches, team)

        for intention in self._broad_intentions():
            matches = [action for action in options if self._matches_intention(engine, state, action, intention, team)]
            if matches:
                self.stats.intention_matched_decisions += 1
                self._record_intention_match(intention.kind)
                return self._best_action_by_score(engine, state, matches, team)

        self.stats.fallback_decisions += 1
        return self._best_action_by_score(engine, state, list(options), team)

    def _record_intention_match(self, kind: str) -> None:
        if kind == "safe_entry":
            self.stats.matched_safe_entry += 1
        elif kind == "enter_base":
            self.stats.matched_enter_base += 1
        elif kind == "capture":
            self.stats.matched_capture += 1
        elif kind == "progress":
            self.stats.matched_progress += 1
        elif kind == "any_safe_entry":
            self.stats.matched_any_safe_entry += 1
        elif kind == "any_enter_base":
            self.stats.matched_any_enter_base += 1
        elif kind == "any_capture":
            self.stats.matched_any_capture += 1
        elif kind == "any_progress":
            self.stats.matched_any_progress += 1

    def _broad_intentions(self) -> tuple[_Intention, ...]:
        return (
            _Intention(kind="any_safe_entry", score=self.weights.safe_entry),
            _Intention(kind="any_enter_base", score=self.weights.enter_base),
            _Intention(kind="any_capture", score=self.weights.capture),
            _Intention(kind="any_progress", score=self.weights.progress),
        )

    def _top_intentions(self, state: GameState, team: Team) -> list[_Intention]:
        intentions: list[_Intention] = []
        team_pawns = tuple(pawn for player in TEAM_PLAYERS[team] for pawn in player_pawns(player))
        enemy_pawns = tuple(pawn for player in PlayerId if team_of(player) != team for pawn in player_pawns(player))

        for pawn in team_pawns:
            position = get_pawn_position(state, pawn)
            if position.kind == PositionKind.BASE:
                intentions.append(_Intention(kind="enter_base", score=self.weights.enter_base, pawn=pawn))
                continue

            safe_steps = self._safe_entry_steps(state, pawn)
            if safe_steps is not None:
                intentions.append(
                    _Intention(
                        kind="safe_entry",
                        score=self.weights.safe_entry + self._pawn_progress(state, pawn),
                        pawn=pawn,
                        min_steps=safe_steps,
                        max_steps=13,
                    )
                )

            capture_steps, target = self._nearest_capture(state, pawn, enemy_pawns)
            if capture_steps is not None:
                intentions.append(
                    _Intention(
                        kind="capture",
                        score=self.weights.capture + self._pawn_progress(state, target),
                        pawn=pawn,
                        target=target,
                        min_steps=capture_steps,
                        max_steps=capture_steps,
                    )
                )

            intentions.append(
                _Intention(
                    kind="progress",
                    score=self.weights.progress * self._pawn_progress(state, pawn),
                    pawn=pawn,
                    min_steps=1,
                    max_steps=13,
                )
            )

        intentions.sort(key=lambda intention: intention.score, reverse=True)
        return intentions[: self.top_n_intentions]

    def _matches_intention(
        self,
        engine: GameEngine,
        state: GameState,
        action: Action,
        intention: _Intention,
        team: Team,
    ) -> bool:
        if intention.kind == "enter_base":
            return isinstance(action, PlayEnterAction) and team_of(action.pawn.owner) == team
        if intention.kind == "any_enter_base":
            return isinstance(action, PlayEnterAction) and team_of(action.pawn.owner) == team

        if intention.pawn is not None and intention.pawn not in self._moved_pawns(action):
            return False

        if intention.min_steps is not None and not self._action_can_cover_steps(action, intention.pawn, intention.min_steps, intention.max_steps):
            return False

        next_state = self._try_apply_action(engine, state, action)
        if next_state is None:
            return False

        if intention.kind == "safe_entry":
            assert intention.pawn is not None
            before = get_pawn_position(state, intention.pawn)
            after = get_pawn_position(next_state, intention.pawn)
            return before.kind != PositionKind.SAFE and after.kind == PositionKind.SAFE

        if intention.kind == "any_safe_entry":
            return self._safe_entry_gain(state, next_state, team) > 0

        if intention.kind == "capture":
            if intention.target is None:
                return False
            before = get_pawn_position(state, intention.target)
            after = get_pawn_position(next_state, intention.target)
            return before.kind != PositionKind.BASE and after.kind == PositionKind.BASE

        if intention.kind == "any_capture":
            return self._capture_count(state, next_state, team) > 0

        if intention.kind == "progress":
            assert intention.pawn is not None
            return self._pawn_progress(next_state, intention.pawn) > self._pawn_progress(state, intention.pawn)

        if intention.kind == "any_progress":
            return self._team_progress(next_state, team) > self._team_progress(state, team)

        return False

    def _best_action_by_score(self, engine: GameEngine, state: GameState, actions: list[Action], team: Team) -> Action:
        scored = [(self._score_action(engine, state, action, team), action) for action in actions]
        best_score = max(score for score, _ in scored)
        best = [action for score, action in scored if score == best_score]
        return min(best, key=lambda action: (self._action_card_value(engine, action), self._action_card_id(action), repr(action)))

    def _score_action(self, engine: GameEngine, state: GameState, action: Action, team: Team) -> float:
        next_state = self._try_apply_action(engine, state, action)
        if next_state is None:
            return -1_000_000.0
        score = 0.0
        score += self.weights.safe_entry * self._safe_entry_gain(state, next_state, team)
        score += self.weights.enter_base * self._entry_gain(action, team)
        score += self.weights.capture * self._capture_count(state, next_state, team)
        score += self.weights.progress * (self._team_progress(next_state, team) - self._team_progress(state, team))
        if not self._starts_new_circle(state, action):
            score += self.weights.avoid_new_circle
        if self._action_card_rank(engine, action) == Rank.JOKER:
            score -= self.weights.preserve_joker
        return score

    def _safe_entry_steps(self, state: GameState, pawn: PawnRef) -> Optional[int]:
        for steps in range(1, 14):
            path = simulate_step_move(state, pawn, direction=MoveDirection.FORWARD, steps=steps, prefer_safe_entry=True)
            if path is not None and path.end.kind == PositionKind.SAFE:
                return steps
        return None

    def _nearest_capture(self, state: GameState, pawn: PawnRef, enemy_pawns: tuple[PawnRef, ...]) -> tuple[Optional[int], Optional[PawnRef]]:
        position = get_pawn_position(state, pawn)
        if position.kind != PositionKind.TRACK or position.index is None:
            return None, None
        best_steps: Optional[int] = None
        best_target: Optional[PawnRef] = None
        for target in enemy_pawns:
            target_position = get_pawn_position(state, target)
            if target_position.kind != PositionKind.TRACK or target_position.index is None:
                continue
            distance = (target_position.index - position.index) % MAIN_TRACK_LENGTH
            if distance <= 0 or distance > 13:
                continue
            if best_steps is None or distance < best_steps:
                best_steps = distance
                best_target = target
        return best_steps, best_target

    def _action_can_cover_steps(
        self,
        action: Action,
        pawn: Optional[PawnRef],
        min_steps: int,
        max_steps: Optional[int],
    ) -> bool:
        if pawn is None:
            return True
        if isinstance(action, PlayStepCardAction):
            return action.pawn == pawn and min_steps <= action.steps <= (max_steps or min_steps)
        if isinstance(action, PlaySevenSplitAction):
            return any(move.pawn == pawn and min_steps <= move.steps <= (max_steps or min_steps) for move in action.moves)
        return min_steps == 0

    def _try_apply_action(self, engine: GameEngine, state: GameState, action: Action) -> Optional[GameState]:
        try:
            if isinstance(action, SwapCardAction):
                return engine_rules._apply_swap_action(state, action)
            if isinstance(action, SkipTurnAction):
                return engine_rules.apply_action(state, action, engine.cards_by_id)
            if isinstance(action, DiscardHandAction):
                return engine_rules._apply_discard_hand_action(state, action)
            if isinstance(action, PlayEnterAction):
                return engine_rules._apply_play_enter_action(state, action, engine.cards_by_id)
            if isinstance(action, PlayStepCardAction):
                return engine_rules._apply_play_step_action(state, action, engine.cards_by_id)
            if isinstance(action, PlayJackSwapAction):
                return engine_rules._apply_play_jack_action(state, action, engine.cards_by_id)
            if isinstance(action, PlaySevenSplitAction):
                return engine_rules._apply_play_seven_action(state, action, engine.cards_by_id)
            return engine_rules.apply_action(state, action, engine.cards_by_id)
        except ValueError:
            return None

    def _moved_pawns(self, action: Action) -> tuple[PawnRef, ...]:
        if isinstance(action, PlayEnterAction):
            return (action.pawn,)
        if isinstance(action, PlayStepCardAction):
            return (action.pawn,)
        if isinstance(action, PlaySevenSplitAction):
            return tuple(move.pawn for move in action.moves)
        if isinstance(action, PlayJackSwapAction):
            return (action.source, action.target)
        return ()

    def _safe_entry_gain(self, before: GameState, after: GameState, team: Team) -> int:
        gain = 0
        for player in TEAM_PLAYERS[team]:
            for pawn in player_pawns(player):
                before_pos = get_pawn_position(before, pawn)
                after_pos = get_pawn_position(after, pawn)
                if before_pos.kind != PositionKind.SAFE and after_pos.kind == PositionKind.SAFE:
                    gain += 1
                elif before_pos.kind == PositionKind.SAFE and after_pos.kind == PositionKind.SAFE:
                    if before_pos.index is not None and after_pos.index is not None and after_pos.index > before_pos.index:
                        gain += 1
        return gain

    def _entry_gain(self, action: Action, team: Team) -> int:
        if isinstance(action, PlayEnterAction) and team_of(action.pawn.owner) == team:
            return 1
        return 0

    def _capture_count(self, before: GameState, after: GameState, team: Team) -> int:
        captures = 0
        for player in PlayerId:
            if team_of(player) == team:
                continue
            for pawn in player_pawns(player):
                before_pos = get_pawn_position(before, pawn)
                after_pos = get_pawn_position(after, pawn)
                if before_pos.kind != PositionKind.BASE and after_pos.kind == PositionKind.BASE:
                    captures += 1
        return captures

    def _team_progress(self, state: GameState, team: Team) -> int:
        return sum(self._pawn_progress(state, pawn) for player in TEAM_PLAYERS[team] for pawn in player_pawns(player))

    def _pawn_progress(self, state: GameState, pawn: PawnRef) -> int:
        position = get_pawn_position(state, pawn)
        if position.kind == PositionKind.BASE:
            return 0
        if position.kind == PositionKind.SAFE and position.index is not None:
            return 1000 + position.index
        if position.kind == PositionKind.TRACK and position.index is not None:
            progress = 1 + ((position.index - entry_index(pawn.owner)) % MAIN_TRACK_LENGTH)
            if pawn_safe_entry_ready(state, pawn):
                progress += MAIN_TRACK_LENGTH
            return progress
        return 0

    def _starts_new_circle(self, state: GameState, action: Action) -> bool:
        if isinstance(action, PlayStepCardAction):
            if not pawn_safe_entry_ready(state, action.pawn):
                return False
            path = simulate_step_move(
                state,
                action.pawn,
                direction=action.direction,
                steps=action.steps,
                prefer_safe_entry=action.prefer_safe_entry,
            )
            return path is not None and path.crossed_own_entry_from_behind and path.end.kind == PositionKind.TRACK
        if isinstance(action, PlaySevenSplitAction):
            return any((not move.prefer_safe_entry) and pawn_safe_entry_ready(state, move.pawn) for move in action.moves)
        return False

    def _action_card_id(self, action: Action) -> int:
        if isinstance(action, (SwapCardAction, PlayEnterAction, PlayStepCardAction, PlaySevenSplitAction, PlayJackSwapAction)):
            return action.card_id
        return 10_000

    def _action_card_rank(self, engine: GameEngine, action: Action) -> Optional[Rank]:
        card_id = self._action_card_id(action)
        if card_id in engine.cards_by_id:
            return engine.cards_by_id[card_id].rank
        return None

    def _action_card_value(self, engine: GameEngine, action: Action) -> int:
        rank = self._action_card_rank(engine, action)
        if rank is None:
            return 10_000
        return CARD_VALUE.get(rank, 0)
