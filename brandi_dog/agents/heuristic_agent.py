from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Optional

from brandi_dog.agents.action_generation import (
    AgentActionGenerationPolicy,
    movement_pawns_for_owner,
    movement_pawns_for_owners,
    prune_to_capture_candidates_when_available,
    represented_ranks_for_card,
)
from brandi_dog.engine.actions import (
    Action,
    DiscardHandAction,
    MoveDirection,
    PlayEnterAction,
    PlayJackSwapAction,
    PlaySevenSplitAction,
    PlayStepCardAction,
    SevenSubMove,
    SkipTurnAction,
    SwapCardAction,
)
from brandi_dog.engine.board import MAIN_TRACK_LENGTH, SimulatedPath, entry_index, simulate_step_move
from brandi_dog.engine.cards import Card, NUMERIC_FORWARD_VALUES, Rank
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine import rules as engine_rules
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    PositionKind,
    RoundStage,
    TEAM_PLAYERS,
    active_swap_player,
    get_pawn_position,
    hand_of,
    next_in_play_order,
    pawn_safe_entry_ready,
    player_pawns,
    team_of,
)

ENTRY_RANKS = {Rank.ACE, Rank.KING, Rank.JOKER}

NO_ENTRY_SWAP_STRENGTH: dict[Rank, int] = {
    Rank.SEVEN: 11,
    Rank.FOUR: 10,
    Rank.JACK: 9,
    Rank.QUEEN: 8,
    Rank.TEN: 7,
    Rank.NINE: 6,
    Rank.EIGHT: 5,
    Rank.SIX: 4,
    Rank.FIVE: 3,
    Rank.THREE: 2,
    Rank.TWO: 1,
}

ENTRY_SWAP_GIVE_PRIORITY: dict[Rank, int] = {
    Rank.JOKER: 1,
    Rank.KING: 2,
    Rank.ACE: 3,
}

FALLBACK_KEEP_STRENGTH: dict[Rank, int] = {
    Rank.JOKER: 100,
    Rank.ACE: 95,
    Rank.KING: 90,
    Rank.SEVEN: 80,
    Rank.FOUR: 70,
    Rank.JACK: 60,
    Rank.QUEEN: 50,
    Rank.TEN: 45,
    Rank.NINE: 40,
    Rank.EIGHT: 35,
    Rank.SIX: 30,
    Rank.FIVE: 25,
    Rank.THREE: 20,
    Rank.TWO: 10,
}

SEVEN_OPTION_SAMPLE_LIMIT = 24
SEVEN_PLAN_BUILD_ATTEMPTS = 16
SEVEN_PRIORITY_FRACTION = 0.6
JOKER_RANK_ACTION_TYPES = (
    PlayEnterAction,
    PlayStepCardAction,
    PlaySevenSplitAction,
    PlayJackSwapAction,
)
JOKER_REPRESENT_ORDER: tuple[Rank, ...] = (
    Rank.ACE,
    Rank.KING,
    Rank.SEVEN,
    Rank.JACK,
    Rank.FOUR,
    Rank.QUEEN,
    Rank.TEN,
    Rank.NINE,
    Rank.EIGHT,
    Rank.SIX,
    Rank.FIVE,
    Rank.THREE,
    Rank.TWO,
)


@dataclass(frozen=True)
class _ActionFeatures:
    action: Action
    safe_progress: int
    deepest_safe_index: int
    capture_count: int
    seven_capture: bool
    entry_priority: int
    furthest_progress: int
    starts_new_circle: bool


@dataclass(frozen=True)
class _SevenMoveCandidate:
    move: SevenSubMove
    path: SimulatedPath
    next_state: GameState
    safe_gain: int
    capture_count: int
    unblocks_entry: bool
    pawn_progress: int


class HeuristicAgent:
    def __init__(
        self,
        seed: Optional[int] = None,
        rng: Optional[random.Random] = None,
        action_policy: Optional[AgentActionGenerationPolicy] = None,
    ):
        if rng is not None and seed is not None:
            raise ValueError("Provide either seed or rng, not both")
        self.rng = rng if rng is not None else random.Random(seed)
        self.action_policy = action_policy if action_policy is not None else AgentActionGenerationPolicy()

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        actor = active_swap_player(state) if state.round_stage == RoundStage.TEAM_SWAPS else state.play_current
        options = self.candidate_actions(engine, state)
        if not options:
            raise RuntimeError("No legal actions available")
        if state.round_stage == RoundStage.TEAM_SWAPS:
            return self._select_swap_action(options, state, actor, engine.cards_by_id)
        return self._select_play_action(options, state, actor, engine.cards_by_id)

    def candidate_actions(self, engine: GameEngine, state: GameState) -> tuple[Action, ...]:
        actor = active_swap_player(state) if state.round_stage == RoundStage.TEAM_SWAPS else state.play_current
        if state.round_stage == RoundStage.TEAM_SWAPS:
            return engine.legal_actions(state)
        options = self._play_options_for_agent(engine, state)
        filtered = self._preselect_play_options(options, state, actor, engine.cards_by_id)
        legal = set(engine.legal_actions(state))
        legal_filtered = tuple(action for action in filtered if action in legal)
        if legal_filtered:
            return legal_filtered
        return tuple(legal)

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

        # If we already have multiple entry cards, pass one to teammate.
        if len(entry_card_ids) >= 2:
            entry_swaps = [action for action in swaps if cards_by_id[action.card_id].rank in ENTRY_RANKS]
            if entry_swaps:
                return self._choose_max(
                    entry_swaps,
                    key=lambda action: (
                        ENTRY_SWAP_GIVE_PRIORITY.get(cards_by_id[action.card_id].rank, 0),
                        -action.card_id,
                    ),
                )

        has_pawn_in_play = any(
            get_pawn_position(state, pawn).kind != PositionKind.BASE for pawn in player_pawns(actor)
        )

        # If we cannot enter and have no pawn in play, feed teammate the strongest non-entry card.
        if not entry_card_ids and not has_pawn_in_play:
            return self._choose_max(
                swaps,
                key=lambda action: (
                    NO_ENTRY_SWAP_STRENGTH.get(cards_by_id[action.card_id].rank, 0),
                    -action.card_id,
                ),
            )

        # Default: keep stronger cards and give a weaker one.
        return self._choose_min(
            swaps,
            key=lambda action: (
                FALLBACK_KEEP_STRENGTH.get(cards_by_id[action.card_id].rank, 0),
                action.card_id,
            ),
        )

    def _play_options_for_agent(self, engine: GameEngine, state: GameState) -> tuple[Action, ...]:
        if state.round_stage != RoundStage.PLAY_LOOP:
            return engine.legal_actions(state)

        player = state.play_current
        hand = hand_of(state, player)
        if not hand:
            return (SkipTurnAction(player=player),)

        non_joker_ranks_in_hand = {
            engine.cards_by_id[card_id].rank
            for card_id in hand
            if engine.cards_by_id[card_id].rank != Rank.JOKER
        }

        options: list[Action] = []
        for card_id in hand:
            card = engine.cards_by_id[card_id]
            options.extend(
                self._card_options_for_agent(
                    state=state,
                    player=player,
                    card_id=card_id,
                    card=card,
                    non_joker_ranks_in_hand=non_joker_ranks_in_hand,
                )
            )

        if options:
            return tuple(options)

        # Safety fallback: keep engine-level legality as final source of truth.
        fallback = engine.legal_actions(state)
        if fallback:
            return fallback
        return (DiscardHandAction(player=player),)

    def _card_options_for_agent(
        self,
        state: GameState,
        player: PlayerId,
        card_id: int,
        card: Card,
        non_joker_ranks_in_hand: set[Rank],
    ) -> list[Action]:
        represented_ranks = self._represented_ranks_for_card(card, non_joker_ranks_in_hand)
        is_joker = card.rank == Rank.JOKER

        actions: list[Action] = []
        for represented in represented_ranks:
            if represented == Rank.ACE:
                actions.extend(engine_rules._legal_entry_actions(state, player, card_id, represented))
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=1,
                        direction=MoveDirection.FORWARD,
                        is_joker=is_joker,
                    )
                )
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=11,
                        direction=MoveDirection.FORWARD,
                        is_joker=is_joker,
                    )
                )
                continue

            if represented == Rank.KING:
                actions.extend(engine_rules._legal_entry_actions(state, player, card_id, represented))
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=13,
                        direction=MoveDirection.FORWARD,
                        is_joker=is_joker,
                    )
                )
                continue

            if represented == Rank.FOUR:
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=4,
                        direction=MoveDirection.FORWARD,
                        is_joker=is_joker,
                    )
                )
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=4,
                        direction=MoveDirection.BACKWARD,
                        is_joker=is_joker,
                    )
                )
                continue

            if represented == Rank.SEVEN:
                actions.extend(self._sampled_seven_actions(state, player, card_id, represented, is_joker))
                continue

            if represented == Rank.JACK:
                actions.extend(engine_rules._legal_jack_actions(state, player, card_id, represented))
                continue

            if represented in NUMERIC_FORWARD_VALUES:
                actions.extend(
                    self._legal_step_actions_for_agent(
                        state,
                        player,
                        card_id,
                        represented,
                        steps=NUMERIC_FORWARD_VALUES[represented],
                        direction=MoveDirection.FORWARD,
                        is_joker=is_joker,
                    )
                )
                continue

            raise ValueError(f"Unsupported represented rank: {represented}")

        return actions

    def _legal_step_actions_for_agent(
        self,
        state: GameState,
        player: PlayerId,
        card_id: int,
        represented_rank: Rank,
        steps: int,
        direction: MoveDirection,
        is_joker: bool,
    ) -> list[Action]:
        owner = engine_rules._controlled_owner_for_turn(state, player)
        actions: list[Action] = []
        for pawn in movement_pawns_for_owner(state, owner, self.action_policy):
            for prefer_safe_entry, path in engine_rules._step_path_candidates(
                state,
                pawn,
                direction=direction,
                steps=steps,
            ):
                if is_joker and engine_rules._joker_last_pawn_safe_entry_violation(
                    state,
                    pawn,
                    path.entered_safe_from_track,
                ):
                    continue
                actions.append(
                    PlayStepCardAction(
                        player=player,
                        card_id=card_id,
                        represented_rank=represented_rank,
                        pawn=pawn,
                        steps=steps,
                        direction=direction,
                        prefer_safe_entry=prefer_safe_entry,
                    )
                )
        return actions

    def _represented_ranks_for_card(self, card: Card, non_joker_ranks_in_hand: set[Rank]) -> tuple[Rank, ...]:
        return represented_ranks_for_card(card.rank, non_joker_ranks_in_hand, self.action_policy)

    def _sampled_seven_actions(
        self,
        state: GameState,
        player: PlayerId,
        card_id: int,
        represented_rank: Rank,
        is_joker: bool,
    ) -> list[PlaySevenSplitAction]:
        owners = engine_rules._seven_allowed_owners(state, player)
        pawns = movement_pawns_for_owners(state, owners, self.action_policy)
        if not pawns:
            return []

        if self.action_policy.seven_capture_only_when_available:
            initial_candidates = self._seven_move_candidates(
                state=state,
                actor=player,
                pawns=pawns,
                remaining=7,
                is_joker=is_joker,
            )
            capture_openers = [candidate for candidate in initial_candidates if candidate.capture_count > 0]
            if capture_openers:
                return self._seven_actions_from_capture_openers(
                    state=state,
                    actor=player,
                    pawns=pawns,
                    card_id=card_id,
                    represented_rank=represented_rank,
                    is_joker=is_joker,
                    capture_openers=capture_openers,
                )

        selected: dict[tuple, PlaySevenSplitAction] = {}

        # Deterministic anchors to keep strategically obvious options available.
        for stochastic in (False, True):
            anchor = self._build_sampled_seven_plan(
                state=state,
                actor=player,
                pawns=pawns,
                card_id=card_id,
                represented_rank=represented_rank,
                is_joker=is_joker,
                stochastic=stochastic,
                force_four_capture=not stochastic,
            )
            if anchor is None:
                continue
            selected[self._seven_action_key(anchor)] = anchor

        attempts = 0
        while len(selected) < SEVEN_OPTION_SAMPLE_LIMIT and attempts < SEVEN_PLAN_BUILD_ATTEMPTS:
            attempts += 1
            candidate = self._build_sampled_seven_plan(
                state=state,
                actor=player,
                pawns=pawns,
                card_id=card_id,
                represented_rank=represented_rank,
                is_joker=is_joker,
                stochastic=True,
                force_four_capture=False,
            )
            if candidate is None:
                continue
            selected[self._seven_action_key(candidate)] = candidate

        return list(selected.values())

    def _seven_actions_from_capture_openers(
        self,
        state: GameState,
        actor: PlayerId,
        pawns: tuple[PawnRef, ...],
        card_id: int,
        represented_rank: Rank,
        is_joker: bool,
        capture_openers: list[_SevenMoveCandidate],
    ) -> list[PlaySevenSplitAction]:
        selected: dict[tuple, PlaySevenSplitAction] = {}
        ranked_openers = sorted(
            capture_openers,
            key=lambda candidate: (
                candidate.capture_count,
                candidate.safe_gain,
                1 if candidate.unblocks_entry else 0,
                candidate.pawn_progress,
                candidate.move.steps,
            ),
            reverse=True,
        )

        for opener in ranked_openers:
            for stochastic in (False, True):
                action = self._complete_sampled_seven_plan(
                    current_state=opener.next_state,
                    remaining=7 - opener.move.steps,
                    raw_moves=[opener.move],
                    actor=actor,
                    pawns=pawns,
                    card_id=card_id,
                    represented_rank=represented_rank,
                    is_joker=is_joker,
                    stochastic=stochastic,
                    force_four_capture=False,
                )
                if action is None:
                    continue
                selected[self._seven_action_key(action)] = action
                if len(selected) >= SEVEN_OPTION_SAMPLE_LIMIT:
                    return list(selected.values())

        return list(selected.values())

    def _complete_sampled_seven_plan(
        self,
        current_state: GameState,
        remaining: int,
        raw_moves: list[SevenSubMove],
        actor: PlayerId,
        pawns: tuple[PawnRef, ...],
        card_id: int,
        represented_rank: Rank,
        is_joker: bool,
        stochastic: bool,
        force_four_capture: bool,
    ) -> Optional[PlaySevenSplitAction]:
        while remaining > 0:
            candidates = self._seven_move_candidates(
                state=current_state,
                actor=actor,
                pawns=pawns,
                remaining=remaining,
                is_joker=is_joker,
            )
            if not candidates:
                return None

            candidates = prune_to_capture_candidates_when_available(candidates, self.action_policy)

            prioritized = self._prioritize_seven_candidates(
                candidates,
                remaining=remaining,
                force_four_capture=force_four_capture,
            )
            chosen = (
                self._choose_seven_candidate_weighted(prioritized, remaining)
                if stochastic
                else self._choose_seven_candidate_deterministic(prioritized, remaining)
            )

            raw_moves.append(chosen.move)
            current_state = chosen.next_state
            remaining -= chosen.move.steps

        moves = tuple(raw_moves)
        if not moves:
            return None
        return PlaySevenSplitAction(
            player=actor,
            card_id=card_id,
            represented_rank=represented_rank,
            moves=moves,
        )

    def _build_sampled_seven_plan(
        self,
        state: GameState,
        actor: PlayerId,
        pawns: tuple[PawnRef, ...],
        card_id: int,
        represented_rank: Rank,
        is_joker: bool,
        stochastic: bool,
        force_four_capture: bool,
    ) -> Optional[PlaySevenSplitAction]:
        current_state = state
        remaining = 7
        raw_moves: list[SevenSubMove] = []

        while remaining > 0:
            candidates = self._seven_move_candidates(
                state=current_state,
                actor=actor,
                pawns=pawns,
                remaining=remaining,
                is_joker=is_joker,
            )
            if not candidates:
                return None

            candidates = prune_to_capture_candidates_when_available(candidates, self.action_policy)

            prioritized = self._prioritize_seven_candidates(
                candidates,
                remaining=remaining,
                force_four_capture=force_four_capture,
            )
            chosen = (
                self._choose_seven_candidate_weighted(prioritized, remaining)
                if stochastic
                else self._choose_seven_candidate_deterministic(prioritized, remaining)
            )

            raw_moves.append(chosen.move)
            current_state = chosen.next_state
            remaining -= chosen.move.steps

        moves = tuple(raw_moves)
        if not moves:
            return None
        return PlaySevenSplitAction(
            player=actor,
            card_id=card_id,
            represented_rank=represented_rank,
            moves=moves,
        )

    def _seven_move_candidates(
        self,
        state: GameState,
        actor: PlayerId,
        pawns: tuple[PawnRef, ...],
        remaining: int,
        is_joker: bool,
    ) -> list[_SevenMoveCandidate]:
        friendly_players = set(TEAM_PLAYERS[team_of(actor)])
        enemy_players = {player for player in PlayerId if player not in friendly_players}
        candidates: list[_SevenMoveCandidate] = []

        for pawn in pawns:
            if get_pawn_position(state, pawn).kind == PositionKind.BASE:
                continue
            for step_count in range(1, remaining + 1):
                for prefer_safe_entry, path in engine_rules._step_path_candidates(
                    state,
                    pawn,
                    direction=MoveDirection.FORWARD,
                    steps=step_count,
                ):
                    if is_joker and engine_rules._joker_last_pawn_safe_entry_violation(
                        state, pawn, path.entered_safe_from_track
                    ):
                        continue

                    next_state = engine_rules._apply_move_path(
                        state,
                        pawn=pawn,
                        end=path.end,
                        traversed_open_track=path.traversed_open_track_indices,
                        crossed_own_entry_from_behind=path.crossed_own_entry_from_behind,
                        pass_capture=True,
                    )
                    capture_count = self._enemy_capture_count(state, next_state, enemy_players)

                    before = get_pawn_position(state, pawn)
                    after = get_pawn_position(next_state, pawn)
                    safe_gain = self._safe_gain(before.kind, before.index, after.kind, after.index)

                    candidates.append(
                        _SevenMoveCandidate(
                            move=SevenSubMove(
                                pawn=pawn,
                                steps=step_count,
                                prefer_safe_entry=prefer_safe_entry,
                            ),
                            path=path,
                            next_state=next_state,
                            safe_gain=safe_gain,
                            capture_count=capture_count,
                            unblocks_entry=(
                                before.kind == PositionKind.TRACK
                                and before.index is not None
                                and before.index == entry_index(pawn.owner)
                            ),
                            pawn_progress=self._pawn_progress(state, pawn),
                        )
                    )

        return candidates

    def _prioritize_seven_candidates(
        self,
        candidates: list[_SevenMoveCandidate],
        remaining: int,
        force_four_capture: bool,
    ) -> list[_SevenMoveCandidate]:
        if force_four_capture and remaining == 7:
            split_43_capture = [
                candidate
                for candidate in candidates
                if candidate.move.steps == 4 and candidate.capture_count > 0
            ]
            if split_43_capture:
                return split_43_capture

        safe_moves = [candidate for candidate in candidates if candidate.safe_gain > 0]
        if safe_moves:
            return safe_moves

        capture_moves = [candidate for candidate in candidates if candidate.capture_count > 0]
        if capture_moves:
            return capture_moves

        unblock_moves = [candidate for candidate in candidates if candidate.unblocks_entry]
        if unblock_moves:
            return unblock_moves

        furthest = max(candidate.pawn_progress for candidate in candidates)
        return [candidate for candidate in candidates if candidate.pawn_progress == furthest]

    def _choose_seven_candidate_deterministic(
        self,
        candidates: list[_SevenMoveCandidate],
        remaining: int,
    ) -> _SevenMoveCandidate:
        return max(
            candidates,
            key=lambda candidate: (
                candidate.safe_gain,
                candidate.capture_count,
                1 if candidate.unblocks_entry else 0,
                1 if remaining == 7 and candidate.move.steps == 4 and candidate.capture_count > 0 else 0,
                candidate.pawn_progress,
                candidate.move.steps,
            ),
        )

    def _choose_seven_candidate_weighted(
        self,
        candidates: list[_SevenMoveCandidate],
        remaining: int,
    ) -> _SevenMoveCandidate:
        weights = [self._seven_candidate_weight(candidate, remaining) for candidate in candidates]
        total = sum(weights)
        if total <= 0:
            return self.rng.choice(candidates)

        cursor = self.rng.random() * total
        cumulative = 0.0
        for candidate, weight in zip(candidates, weights):
            cumulative += weight
            if cumulative >= cursor:
                return candidate
        return candidates[-1]

    def _seven_candidate_weight(self, candidate: _SevenMoveCandidate, remaining: int) -> float:
        weight = 1.0
        weight += max(0, candidate.safe_gain) * 8.0
        weight += max(0, candidate.capture_count) * 6.0
        if candidate.unblocks_entry:
            weight += 4.0
        if remaining == 7 and candidate.move.steps == 4 and candidate.capture_count > 0:
            weight += 3.0
        weight += max(0, candidate.pawn_progress) / 25.0
        weight += candidate.move.steps / 8.0
        return weight

    def _enemy_capture_count(self, before_state: GameState, after_state: GameState, enemy_players: set[PlayerId]) -> int:
        captures = 0
        for player in enemy_players:
            for pawn in player_pawns(player):
                before = get_pawn_position(before_state, pawn)
                after = get_pawn_position(after_state, pawn)
                if before.kind != PositionKind.BASE and after.kind == PositionKind.BASE:
                    captures += 1
        return captures

    def _safe_gain(
        self,
        before_kind: PositionKind,
        before_index: Optional[int],
        after_kind: PositionKind,
        after_index: Optional[int],
    ) -> int:
        if after_kind != PositionKind.SAFE or after_index is None:
            return 0
        if before_kind != PositionKind.SAFE:
            return after_index + 1
        if before_index is None:
            return 0
        return max(0, after_index - before_index)

    def _preselect_play_options(
        self,
        options: tuple[Action, ...],
        state: GameState,
        actor: PlayerId,
        cards_by_id: dict[int, Card],
    ) -> tuple[Action, ...]:
        hand = hand_of(state, actor)
        non_joker_ranks_in_hand = {cards_by_id[card_id].rank for card_id in hand if cards_by_id[card_id].rank != Rank.JOKER}

        deduped: dict[tuple, Action] = {}
        for action in options:
            if self._is_redundant_joker_action(action, cards_by_id, non_joker_ranks_in_hand):
                continue
            key = self._action_semantic_key(action, cards_by_id)
            current = deduped.get(key)
            if current is None or self._action_card_id(action) < self._action_card_id(current):
                deduped[key] = action

        filtered = list(deduped.values())
        seven_options = [action for action in filtered if isinstance(action, PlaySevenSplitAction)]
        if len(seven_options) <= SEVEN_OPTION_SAMPLE_LIMIT:
            return tuple(filtered)

        non_seven = [action for action in filtered if not isinstance(action, PlaySevenSplitAction)]
        sampled_seven = self._sample_seven_options(seven_options, state, actor)
        return tuple(non_seven + sampled_seven)

    def _is_redundant_joker_action(
        self,
        action: Action,
        cards_by_id: dict[int, Card],
        non_joker_ranks_in_hand: set[Rank],
    ) -> bool:
        if not isinstance(action, JOKER_RANK_ACTION_TYPES):
            return False
        if cards_by_id[action.card_id].rank != Rank.JOKER:
            return False
        return action.represented_rank in non_joker_ranks_in_hand

    def _action_semantic_key(self, action: Action, cards_by_id: dict[int, Card]) -> tuple:
        if isinstance(action, SwapCardAction):
            return ("swap", action.player, cards_by_id[action.card_id].rank)

        if isinstance(action, PlayEnterAction):
            return ("enter", action.player, cards_by_id[action.card_id].rank, action.represented_rank, action.pawn)

        if isinstance(action, PlayStepCardAction):
            return (
                "step",
                action.player,
                cards_by_id[action.card_id].rank,
                action.represented_rank,
                action.pawn,
                action.steps,
                action.direction,
                action.prefer_safe_entry,
            )

        if isinstance(action, PlayJackSwapAction):
            return (
                "jack",
                action.player,
                cards_by_id[action.card_id].rank,
                action.represented_rank,
                action.source,
                action.target,
            )

        if isinstance(action, PlaySevenSplitAction):
            raw_moves = tuple((move.pawn, move.steps, move.prefer_safe_entry) for move in action.moves)
            return (
                "seven",
                action.player,
                cards_by_id[action.card_id].rank,
                action.represented_rank,
                raw_moves,
            )

        if isinstance(action, DiscardHandAction):
            return ("discard", action.player)

        if isinstance(action, SkipTurnAction):
            return ("skip", action.player)

        return ("raw", type(action).__name__, repr(action))

    def _sample_seven_options(
        self,
        seven_options: list[Action],
        state: GameState,
        actor: PlayerId,
    ) -> list[Action]:
        assert all(isinstance(action, PlaySevenSplitAction) for action in seven_options)
        typed = [action for action in seven_options if isinstance(action, PlaySevenSplitAction)]
        limit = min(SEVEN_OPTION_SAMPLE_LIMIT, len(typed))
        if len(typed) <= limit:
            return typed

        priority_pool = [
            action
            for action in typed
            if self._seven_safe_hint(action)
            or self._seven_capture_hint(action, state, actor)
            or self._seven_unblock_entry_hint(action, state)
        ]
        priority_target = min(len(priority_pool), int(limit * SEVEN_PRIORITY_FRACTION))

        selected: dict[tuple, PlaySevenSplitAction] = {}

        for anchor in self._seven_anchor_actions(typed, state):
            key = self._seven_action_key(anchor)
            selected[key] = anchor

        if priority_target > 0:
            priority_weights = [self._seven_sampling_weight(action, state, actor) for action in priority_pool]
            for action in self._weighted_sample_without_replacement(priority_pool, priority_weights, priority_target):
                key = self._seven_action_key(action)
                selected[key] = action

        if len(selected) < limit:
            remaining = [action for action in typed if self._seven_action_key(action) not in selected]
            remaining_weights = [self._seven_sampling_weight(action, state, actor) for action in remaining]
            for action in self._weighted_sample_without_replacement(
                remaining,
                remaining_weights,
                limit - len(selected),
            ):
                key = self._seven_action_key(action)
                selected[key] = action

        return list(selected.values())

    def _seven_action_key(self, action: PlaySevenSplitAction) -> tuple:
        return tuple((move.pawn, move.steps, move.prefer_safe_entry) for move in action.moves)

    def _seven_anchor_actions(self, seven_options: list[PlaySevenSplitAction], state: GameState) -> list[PlaySevenSplitAction]:
        anchors: list[PlaySevenSplitAction] = []

        split_43 = [
            action
            for action in seven_options
            if any(move.steps == 4 for move in action.moves) and any(move.steps == 3 for move in action.moves)
        ]
        if split_43:
            anchors.append(self._choose_max(split_43, key=lambda action: self._seven_moved_pawn_progress(action, state)))

        furthest = self._choose_max(seven_options, key=lambda action: self._seven_moved_pawn_progress(action, state))
        anchors.append(furthest)
        return anchors

    def _seven_sampling_weight(self, action: PlaySevenSplitAction, state: GameState, actor: PlayerId) -> float:
        weight = 1.0
        if self._seven_safe_hint(action):
            weight += 10.0
        if self._seven_capture_hint(action, state, actor):
            weight += 8.0
        if self._seven_unblock_entry_hint(action, state):
            weight += 6.0
        if any(move.steps == 4 for move in action.moves) and any(move.steps == 3 for move in action.moves):
            weight += 4.0
        weight += max(0.0, self._seven_moved_pawn_progress(action, state)) / 40.0
        return weight

    def _seven_safe_hint(self, action: PlaySevenSplitAction) -> bool:
        return any(move.prefer_safe_entry for move in action.moves)

    def _seven_capture_hint(self, action: PlaySevenSplitAction, state: GameState, actor: PlayerId) -> bool:
        enemy_players = {player for player in PlayerId if player not in TEAM_PLAYERS[team_of(actor)]}
        enemy_track_positions = {
            position.index
            for player in enemy_players
            for pawn in player_pawns(player)
            for position in [get_pawn_position(state, pawn)]
            if position.kind == PositionKind.TRACK and position.index is not None
        }
        if not enemy_track_positions:
            return False

        for move in action.moves:
            start = get_pawn_position(state, move.pawn)
            if start.kind != PositionKind.TRACK or start.index is None:
                continue
            for idx in enemy_track_positions:
                distance = (idx - start.index) % MAIN_TRACK_LENGTH
                if 0 < distance <= move.steps:
                    return True
        return False

    def _seven_unblock_entry_hint(self, action: PlaySevenSplitAction, state: GameState) -> bool:
        for move in action.moves:
            position = get_pawn_position(state, move.pawn)
            if position.kind != PositionKind.TRACK or position.index is None:
                continue
            if position.index == entry_index(move.pawn.owner):
                return True
        return False

    def _seven_moved_pawn_progress(self, action: PlaySevenSplitAction, state: GameState) -> int:
        if not action.moves:
            return -1
        return max(self._pawn_progress(state, move.pawn) for move in action.moves)

    def _weighted_sample_without_replacement(
        self,
        actions: list[Action],
        weights: list[float],
        sample_size: int,
    ) -> list[Action]:
        if sample_size <= 0 or not actions:
            return []
        if sample_size >= len(actions):
            return list(actions)

        keyed: list[tuple[float, Action]] = []
        for action, weight in zip(actions, weights):
            w = max(weight, 0.0001)
            keyed.append((self.rng.random() ** (1.0 / w), action))
        keyed.sort(key=lambda pair: pair[0], reverse=True)
        return [action for _, action in keyed[:sample_size]]

    def _select_play_action(
        self,
        options: tuple[Action, ...],
        state: GameState,
        actor: PlayerId,
        cards_by_id: dict[int, Card],
    ) -> Action:
        features = [self._analyze_action(action, state, actor, cards_by_id) for action in options]

        safe_candidates = [feature for feature in features if feature.safe_progress > 0]
        if safe_candidates:
            return self._choose_feature(
                safe_candidates,
                key=lambda feature: (
                    feature.deepest_safe_index,
                    feature.safe_progress,
                    1 if not feature.starts_new_circle else 0,
                    feature.capture_count,
                    feature.entry_priority,
                    feature.furthest_progress,
                    -self._action_card_id(feature.action),
                ),
            )

        capture_candidates = [feature for feature in features if feature.capture_count > 0]
        if capture_candidates:
            return self._choose_feature(
                capture_candidates,
                key=lambda feature: (
                    feature.capture_count,
                    1 if feature.seven_capture else 0,
                    1 if not feature.starts_new_circle else 0,
                    feature.furthest_progress,
                    feature.entry_priority,
                    -self._action_card_id(feature.action),
                ),
            )

        entry_candidates = [feature for feature in features if isinstance(feature.action, PlayEnterAction)]
        if entry_candidates:
            return self._choose_feature(
                entry_candidates,
                key=lambda feature: (
                    feature.entry_priority,
                    1 if not feature.starts_new_circle else 0,
                    feature.furthest_progress,
                    -self._action_card_id(feature.action),
                ),
            )

        move_candidates = [
            feature
            for feature in features
            if isinstance(feature.action, (PlayStepCardAction, PlaySevenSplitAction, PlayJackSwapAction))
        ]
        if move_candidates:
            return self._choose_feature(
                move_candidates,
                key=lambda feature: (
                    1 if not feature.starts_new_circle else 0,
                    feature.furthest_progress,
                    feature.capture_count,
                    feature.entry_priority,
                    -self._action_card_id(feature.action),
                ),
            )

        return self._choose_feature(
            features,
            key=lambda feature: (
                1 if not feature.starts_new_circle else 0,
                feature.furthest_progress,
                feature.capture_count,
                feature.entry_priority,
                -self._action_card_id(feature.action),
            ),
        )

    def _analyze_action(
        self,
        action: Action,
        state: GameState,
        actor: PlayerId,
        cards_by_id: dict[int, Card],
    ) -> _ActionFeatures:
        next_state = self._apply_action_unchecked(state, action, cards_by_id)

        friendly_players = set(TEAM_PLAYERS[team_of(actor)])
        enemy_players = {player for player in PlayerId if player not in friendly_players}

        safe_progress = 0
        deepest_safe_index = -1
        for player in friendly_players:
            for pawn in player_pawns(player):
                before = get_pawn_position(state, pawn)
                after = get_pawn_position(next_state, pawn)

                if after.kind != PositionKind.SAFE or after.index is None:
                    continue

                if before.kind != PositionKind.SAFE:
                    safe_progress += after.index + 1
                    deepest_safe_index = max(deepest_safe_index, after.index)
                    continue

                if before.index is None:
                    continue
                if after.index > before.index:
                    safe_progress += after.index - before.index
                    deepest_safe_index = max(deepest_safe_index, after.index)

        capture_count = 0
        for player in enemy_players:
            for pawn in player_pawns(player):
                before = get_pawn_position(state, pawn)
                after = get_pawn_position(next_state, pawn)
                if before.kind != PositionKind.BASE and after.kind == PositionKind.BASE:
                    capture_count += 1

        moved_pawns = self._moved_friendly_pawns(action, friendly_players)
        furthest_progress = max((self._pawn_progress(state, pawn) for pawn in moved_pawns), default=-1)

        entry_priority = 0
        if isinstance(action, PlayEnterAction):
            actual_rank = cards_by_id[action.card_id].rank
            if actual_rank in {Rank.ACE, Rank.KING}:
                entry_priority = 2
            elif actual_rank == Rank.JOKER:
                entry_priority = 1

        seven_capture = isinstance(action, PlaySevenSplitAction) and capture_count > 0

        return _ActionFeatures(
            action=action,
            safe_progress=safe_progress,
            deepest_safe_index=deepest_safe_index,
            capture_count=capture_count,
            seven_capture=seven_capture,
            entry_priority=entry_priority,
            furthest_progress=furthest_progress,
            starts_new_circle=self._starts_new_circle(state, action),
        )

    def _apply_action_unchecked(
        self,
        state: GameState,
        action: Action,
        cards_by_id: dict[int, Card],
    ) -> GameState:
        if isinstance(action, SwapCardAction):
            return engine_rules._apply_swap_action(state, action)
        if isinstance(action, SkipTurnAction):
            return replace(state, play_current=next_in_play_order(state.play_current))
        if isinstance(action, DiscardHandAction):
            return engine_rules._apply_discard_hand_action(state, action)
        if isinstance(action, PlayEnterAction):
            return engine_rules._apply_play_enter_action(state, action, cards_by_id)
        if isinstance(action, PlayStepCardAction):
            return engine_rules._apply_play_step_action(state, action, cards_by_id)
        if isinstance(action, PlayJackSwapAction):
            return engine_rules._apply_play_jack_action(state, action, cards_by_id)
        if isinstance(action, PlaySevenSplitAction):
            return engine_rules._apply_play_seven_action(state, action, cards_by_id)
        raise TypeError(f"Unsupported action type: {type(action)}")

    def _moved_friendly_pawns(self, action: Action, friendly_players: set[PlayerId]) -> tuple[PawnRef, ...]:
        if isinstance(action, (DiscardHandAction, SkipTurnAction, SwapCardAction)):
            return ()
        if isinstance(action, PlayEnterAction):
            return (action.pawn,) if action.pawn.owner in friendly_players else ()
        if isinstance(action, PlayStepCardAction):
            return (action.pawn,) if action.pawn.owner in friendly_players else ()
        if isinstance(action, PlaySevenSplitAction):
            return tuple(move.pawn for move in action.moves if move.pawn.owner in friendly_players)
        if isinstance(action, PlayJackSwapAction):
            moved: list[PawnRef] = []
            if action.source.owner in friendly_players:
                moved.append(action.source)
            if action.target.owner in friendly_players:
                moved.append(action.target)
            return tuple(moved)
        return ()

    def _pawn_progress(self, state: GameState, pawn: PawnRef) -> int:
        position = get_pawn_position(state, pawn)

        if position.kind == PositionKind.BASE:
            return -1
        if position.kind == PositionKind.SAFE and position.index is not None:
            return 1000 + position.index
        if position.kind == PositionKind.TRACK and position.index is not None:
            distance = (position.index - entry_index(pawn.owner)) % MAIN_TRACK_LENGTH
            if pawn_safe_entry_ready(state, pawn):
                distance += MAIN_TRACK_LENGTH
            return distance
        return -1

    def _starts_new_circle(self, state: GameState, action: Action) -> bool:
        if isinstance(action, PlayStepCardAction):
            if action.direction != MoveDirection.FORWARD:
                return False
            if not pawn_safe_entry_ready(state, action.pawn):
                return False

            path = simulate_step_move(
                state,
                action.pawn,
                direction=action.direction,
                steps=action.steps,
                prefer_safe_entry=action.prefer_safe_entry,
            )
            return (
                path is not None
                and path.crossed_own_entry_from_behind
                and path.end.kind == PositionKind.TRACK
            )

        if isinstance(action, PlaySevenSplitAction):
            return any(
                (not move.prefer_safe_entry) and pawn_safe_entry_ready(state, move.pawn)
                for move in action.moves
            )

        return False

    def _action_card_id(self, action: Action) -> int:
        if isinstance(
            action,
            (SwapCardAction, PlayEnterAction, PlayStepCardAction, PlaySevenSplitAction, PlayJackSwapAction),
        ):
            return action.card_id
        return 10_000

    def _choose_feature(self, features: list[_ActionFeatures], key) -> Action:
        best_value = max(key(feature) for feature in features)
        best = [feature for feature in features if key(feature) == best_value]
        return self.rng.choice(best).action

    def _choose_max(self, actions: list[Action], key) -> Action:
        best_value = max(key(action) for action in actions)
        best = [action for action in actions if key(action) == best_value]
        return self.rng.choice(best)

    def _choose_min(self, actions: list[Action], key) -> Action:
        best_value = min(key(action) for action in actions)
        best = [action for action in actions if key(action) == best_value]
        return self.rng.choice(best)
