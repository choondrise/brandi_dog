from __future__ import annotations

import csv
import json
from dataclasses import asdict
from typing import Any, Optional

from brandi_dog.engine.actions import Action, DiscardHandAction, SkipTurnAction
from brandi_dog.engine.board import MAIN_TRACK_LENGTH, entry_index
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
    index_to_pawn,
    pawn_safe_entry_ready,
    player_pawns,
    team_of,
)

from config import ExperimentConfig
from metrics import ExperimentResult, GameResult, aggregate_game_results


SingleGameResult = GameResult


def run_single_game(config: ExperimentConfig) -> GameResult:
    game_result, _ = _run_single_game(config, game_seed=config.seed)
    return game_result


def run_experiment(config: ExperimentConfig) -> ExperimentResult:
    if config.num_games <= 0:
        raise ValueError("num_games must be greater than zero")
    if config.max_turns is not None and config.max_turns <= 0:
        raise ValueError("max_turns must be greater than zero when provided")
    if config.experiment_runs <= 0:
        raise ValueError("experiment_runs must be greater than zero")

    game_results_list: list[GameResult] = []
    move_analysis_rows: list[tuple[int, int, int]] = []
    turn_counter = 0

    for experiment_index in range(config.experiment_runs):
        for game_index in range(config.num_games):
            game_seed = config.seed + (experiment_index * config.num_games) + game_index
            game_result, turn_counter = _run_single_game(
                config,
                game_seed=game_seed,
                move_analysis_rows=move_analysis_rows if config.move_analysis_path is not None else None,
                turn_counter=turn_counter,
            )
            game_results_list.append(game_result)

    game_results = tuple(game_results_list)
    experiment_result = aggregate_game_results(config.experiment_name, game_results)
    _write_experiment_result(config, experiment_result, game_results)
    if config.move_analysis_path is not None:
        _write_move_analysis(config.move_analysis_path, move_analysis_rows)
    return experiment_result


def _run_single_game(
    config: ExperimentConfig,
    game_seed: int,
    move_analysis_rows: Optional[list[tuple[int, int, int]]] = None,
    turn_counter: int = 0,
) -> tuple[GameResult, int]:
    engine = GameEngine(seed=game_seed)
    state = engine.reset()
    game_length = 0
    captures = 0
    discard_or_noop_actions = 0

    while state.round_stage != RoundStage.GAME_OVER:
        if config.max_turns is not None and game_length >= config.max_turns:
            break

        active_player = _active_player(state)
        agent = config.agents_by_player[active_player]
        if move_analysis_rows is not None:
            turn_counter += 1
            move_analysis_rows.append(
                (_agent_id(active_player), turn_counter, _moves_available(agent, engine, state))
            )
        action = agent.select_action(engine, state)

        previous_state = state
        state = engine.step(state, action)

        game_length += 1
        captures += _count_captures(previous_state, state, active_player)
        if _is_discard_or_noop_action(action):
            discard_or_noop_actions += 1

    capped = state.round_stage != RoundStage.GAME_OVER
    winner = state.winner if state.winner is not None else _leading_team(state)
    if winner is None and not capped:
        raise RuntimeError("Game reached GAME_OVER without a winning team")

    return (
        GameResult(
            winner=winner,
            game_length=game_length,
            captures=captures,
            discard_or_noop_actions=discard_or_noop_actions,
            capped=capped,
        ),
        turn_counter,
    )


def _agent_id(player: PlayerId) -> int:
    return int(player) + 1


def _moves_available(agent: object, engine: GameEngine, state: GameState) -> int:
    candidate_actions = getattr(agent, "candidate_actions", None)
    if callable(candidate_actions):
        return len(candidate_actions(engine, state))
    return len(engine.legal_actions(state))


def _active_player(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def _count_captures(previous_state: GameState, next_state: GameState, active_player: PlayerId) -> int:
    captures = 0
    active_team = team_of(active_player)

    for index, (previous_position, next_position) in enumerate(
        zip(previous_state.pawn_positions, next_state.pawn_positions)
    ):
        pawn = index_to_pawn(index)
        if team_of(pawn.owner) == active_team:
            continue
        if previous_position.kind == PositionKind.BASE:
            continue
        if next_position.kind == PositionKind.BASE:
            captures += 1

    return captures


def _leading_team(state: GameState) -> Optional[Team]:
    team_a_score = _team_score(state, Team.A)
    team_b_score = _team_score(state, Team.B)
    if team_a_score > team_b_score:
        return Team.A
    if team_b_score > team_a_score:
        return Team.B
    return None


def _team_score(state: GameState, team: Team) -> tuple[int, int]:
    safe_count = 0
    progress = 0
    for player in TEAM_PLAYERS[team]:
        for pawn in player_pawns(player):
            position = get_pawn_position(state, pawn)
            if position.kind == PositionKind.SAFE:
                safe_count += 1
            progress += _pawn_progress(state, pawn)
    return safe_count, progress


def _pawn_progress(state: GameState, pawn: PawnRef) -> int:
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


def _is_discard_or_noop_action(action: Action) -> bool:
    return isinstance(action, (DiscardHandAction, SkipTurnAction))


def _write_experiment_result(
    config: ExperimentConfig,
    experiment_result: ExperimentResult,
    game_results: tuple[GameResult, ...],
) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": _json_ready(asdict(experiment_result)),
        "games": [_json_ready(asdict(result)) for result in game_results],
    }
    with config.output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)
        output_file.write("\n")


def _write_move_analysis(path, rows: list[tuple[int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(("agent_id", "turn", "moves_available"))
        writer.writerows(rows)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Team):
        return value.value
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
