from __future__ import annotations

from typing import Iterable, Optional

from brandi_dog.engine import rules as engine_rules
from brandi_dog.engine.actions import (
    Action,
    DiscardHandAction,
    MoveDirection,
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

JOKER_ACTION_TYPES = (PlayEnterAction, PlayStepCardAction, PlaySevenSplitAction, PlayJackSwapAction)
CARD_ORDER: dict[Rank, int] = {
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


def active_player_for_state(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def candidate_actions(engine: GameEngine, state: GameState) -> tuple[Action, ...]:
    legal = engine.legal_actions(state)
    if not legal:
        return ()
    filtered = filter_redundant_joker_actions(state, legal, engine.cards_by_id)
    filtered = filter_duplicate_base_entries(filtered)
    filtered = simplify_seven_actions(filtered)
    filtered = dedupe_actions(filtered, engine.cards_by_id)
    if filtered:
        return tuple(filtered)
    fallback = [action for action in legal if isinstance(action, (DiscardHandAction, SkipTurnAction))]
    return tuple(fallback or legal)


def filter_redundant_joker_actions(
    state: GameState,
    actions: Iterable[Action],
    cards_by_id: dict[int, Card],
) -> list[Action]:
    if state.round_stage != RoundStage.PLAY_LOOP:
        return list(actions)
    player = state.play_current
    non_joker_ranks = {
        cards_by_id[card_id].rank
        for card_id in hand_of(state, player)
        if cards_by_id[card_id].rank != Rank.JOKER
    }
    filtered: list[Action] = []
    for action in actions:
        if not isinstance(action, JOKER_ACTION_TYPES):
            filtered.append(action)
            continue
        if cards_by_id[action.card_id].rank == Rank.JOKER and action.represented_rank in non_joker_ranks:
            continue
        filtered.append(action)
    return filtered


def filter_duplicate_base_entries(actions: Iterable[Action]) -> list[Action]:
    seen: set[tuple[PlayerId, int, Rank]] = set()
    filtered: list[Action] = []
    for action in actions:
        if not isinstance(action, PlayEnterAction):
            filtered.append(action)
            continue
        key = (action.player, action.card_id, action.represented_rank)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(action)
    return filtered


def simplify_seven_actions(actions: Iterable[Action]) -> list[Action]:
    filtered: list[Action] = []
    for action in actions:
        if not isinstance(action, PlaySevenSplitAction):
            filtered.append(action)
            continue
        if len(action.moves) == 1 and action.moves[0].steps == 7:
            filtered.append(action)
    return filtered


def rank_actions(
    engine: GameEngine,
    state: GameState,
    actions: Iterable[Action],
    team: Team,
) -> list[Action]:
    return sorted(
        actions,
        key=lambda action: score_action_immediate(engine, state, action, team),
        reverse=True,
    )


def score_action_immediate(engine: GameEngine, state: GameState, action: Action, team: Team) -> tuple[float, int, int]:
    next_state = apply_action_for_simulation(engine, state, action)
    if next_state is None:
        return (-1_000_000.0, -action_card_id(action), 0)

    safe_gain = _team_safe_progress_gain(state, next_state, team)
    entry_gain = 1 if isinstance(action, PlayEnterAction) and team_of(action.pawn.owner) == team else 0
    captures = _capture_count_for_team(state, next_state, team)
    progress_gain = _team_progress(next_state, team) - _team_progress(state, team)
    avoids_new_circle = 0 if starts_new_circle(state, action) else 1
    score = (safe_gain * 10_000.0) + (entry_gain * 3_000.0) + (captures * 2_000.0) + progress_gain + avoids_new_circle
    return (score, -action_card_id(action), -CARD_ORDER.get(action_rank(action, engine.cards_by_id), 0))


def score_state_for_team(state: GameState, team: Team) -> float:
    if state.winner == team:
        return 1_000_000.0
    if state.winner is not None and state.winner != team:
        return -1_000_000.0

    opponent = Team.B if team == Team.A else Team.A
    return _raw_team_score(state, team) - _raw_team_score(state, opponent)


def apply_action_for_simulation(engine: GameEngine, state: GameState, action: Action) -> Optional[GameState]:
    try:
        # Use apply_action directly instead of GameEngine.step. GameEngine.step automatically
        # deals the next round when all hands are empty; limited-horizon rollouts must stop
        # before that new random deal affects evaluation.
        return engine_rules.apply_action(state, action, engine.cards_by_id)
    except ValueError:
        return None


def is_end_of_current_round(state: GameState) -> bool:
    return state.round_stage == RoundStage.GAME_OVER or engine_rules.all_hands_empty(state)


def dedupe_actions(actions: Iterable[Action], cards_by_id: dict[int, Card]) -> list[Action]:
    deduped: dict[tuple, Action] = {}
    for action in actions:
        key = action_key(action, cards_by_id)
        current = deduped.get(key)
        if current is None or action_card_id(action) < action_card_id(current):
            deduped[key] = action
    return list(deduped.values())


def action_key(action: Action, cards_by_id: dict[int, Card]) -> tuple:
    if isinstance(action, SwapCardAction):
        return ("swap", action.player, cards_by_id[action.card_id].rank)
    if isinstance(action, PlayEnterAction):
        return ("enter", action.player, cards_by_id[action.card_id].rank, action.represented_rank)
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
    if isinstance(action, PlaySevenSplitAction):
        return (
            "seven",
            action.player,
            cards_by_id[action.card_id].rank,
            action.represented_rank,
            tuple((move.pawn, move.steps, move.prefer_safe_entry) for move in action.moves),
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
    if isinstance(action, DiscardHandAction):
        return ("discard", action.player)
    if isinstance(action, SkipTurnAction):
        return ("skip", action.player)
    return ("raw", repr(action))


def action_card_id(action: Action) -> int:
    if isinstance(action, (SwapCardAction, PlayEnterAction, PlayStepCardAction, PlaySevenSplitAction, PlayJackSwapAction)):
        return action.card_id
    return 10_000


def action_rank(action: Action, cards_by_id: dict[int, Card]) -> Rank:
    card_id = action_card_id(action)
    if card_id in cards_by_id:
        return cards_by_id[card_id].rank
    return Rank.TWO


def moved_pawns(action: Action) -> tuple[PawnRef, ...]:
    if isinstance(action, PlayEnterAction):
        return (action.pawn,)
    if isinstance(action, PlayStepCardAction):
        return (action.pawn,)
    if isinstance(action, PlaySevenSplitAction):
        return tuple(move.pawn for move in action.moves)
    if isinstance(action, PlayJackSwapAction):
        return (action.source, action.target)
    return ()


def starts_new_circle(state: GameState, action: Action) -> bool:
    if isinstance(action, PlayStepCardAction):
        if action.direction != MoveDirection.FORWARD or not pawn_safe_entry_ready(state, action.pawn):
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


def pawn_progress(state: GameState, pawn: PawnRef) -> int:
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


def _team_safe_progress_gain(before: GameState, after: GameState, team: Team) -> int:
    gain = 0
    for player in TEAM_PLAYERS[team]:
        for pawn in player_pawns(player):
            before_pos = get_pawn_position(before, pawn)
            after_pos = get_pawn_position(after, pawn)
            if after_pos.kind != PositionKind.SAFE or after_pos.index is None:
                continue
            if before_pos.kind != PositionKind.SAFE:
                gain += after_pos.index + 1
            elif before_pos.index is not None and after_pos.index > before_pos.index:
                gain += after_pos.index - before_pos.index
    return gain


def _capture_count_for_team(before: GameState, after: GameState, team: Team) -> int:
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


def _team_progress(state: GameState, team: Team) -> int:
    return sum(pawn_progress(state, pawn) for player in TEAM_PLAYERS[team] for pawn in player_pawns(player))


def _raw_team_score(state: GameState, team: Team) -> float:
    score = 0.0
    for player in TEAM_PLAYERS[team]:
        for pawn in player_pawns(player):
            position = get_pawn_position(state, pawn)
            if position.kind == PositionKind.BASE:
                score -= 25.0
            elif position.kind == PositionKind.SAFE and position.index is not None:
                score += 500.0 + (position.index * 75.0)
            elif position.kind == PositionKind.TRACK:
                score += pawn_progress(state, pawn) * 4.0
    return score
