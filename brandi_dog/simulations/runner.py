from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
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
from metrics import ExperimentResult, GameResult, TeamGameStats, aggregate_game_results


SingleGameResult = GameResult


def run_single_game(config: ExperimentConfig) -> GameResult:
    return _run_single_game(config, game_seed=config.seed)


def run_experiment(config: ExperimentConfig) -> ExperimentResult:
    if config.num_games <= 0:
        raise ValueError("num_games must be greater than zero")
    if config.max_turns is not None and config.max_turns <= 0:
        raise ValueError("max_turns must be greater than zero when provided")

    if config.print_progress:
        print("Team A: {}, Team B: {}".format(config.team_a_label, config.team_b_label), flush=True)
        turn_cap = config.max_turns if config.max_turns is not None else "none"
        print("Turn cap: {}".format(turn_cap), flush=True)

    game_results_list: list[GameResult] = []
    for game_index in range(config.num_games):
        game_result = _run_single_game(config, game_seed=config.seed + game_index)
        game_results_list.append(game_result)
        if config.print_progress:
            print("Game {}: {}".format(game_index + 1, game_result.total_score), flush=True)

    game_results = tuple(game_results_list)
    experiment_result = aggregate_game_results(config.experiment_name, game_results)
    _write_experiment_result(config, experiment_result, game_results)
    if config.print_progress:
        _print_agent_stats(config)
    return experiment_result


def _print_agent_stats(config: ExperimentConfig) -> None:
    printed_header = False
    for player, agent in config.agents_by_player.items():
        report_stats = getattr(agent, "report_stats", None)
        if not callable(report_stats):
            continue
        if not printed_header:
            print("Agent stats:", flush=True)
            printed_header = True
        print(f"  {player.name}: {report_stats()}", flush=True)


def _run_single_game(config: ExperimentConfig, game_seed: int) -> GameResult:
    engine = GameEngine(seed=game_seed)
    state = engine.reset()
    game_length = 0
    captures_by_team = {Team.A: 0, Team.B: 0}
    discards_by_team = {Team.A: 0, Team.B: 0}
    score_sequence: list[str] = []
    previous_score = _score_text(state)

    while state.round_stage != RoundStage.GAME_OVER:
        if config.max_turns is not None and game_length >= config.max_turns:
            break

        active_player = _active_player(state)
        active_team = team_of(active_player)
        agent = config.agents_by_player[active_player]
        action = agent.select_action(engine, state)

        previous_state = state
        state = engine.step(state, action)

        game_length += 1
        captures_by_team[active_team] += _count_captures(previous_state, state, active_team)
        if _is_discard_or_noop_action(action):
            discards_by_team[active_team] += 1

        current_score = _score_text(state)
        if current_score != previous_score:
            score_sequence.append(current_score)
            previous_score = current_score

    capped = state.round_stage != RoundStage.GAME_OVER
    winner = state.winner if state.winner is not None else _leading_team(state)
    if winner is None and not capped:
        raise RuntimeError("Game reached GAME_OVER without a winning team")

    team_a_safe = _team_safe_count(state, Team.A)
    team_b_safe = _team_safe_count(state, Team.B)
    return GameResult(
        winner=winner,
        game_length=game_length,
        capped=capped,
        team_a=TeamGameStats(
            captures=captures_by_team[Team.A],
            discards=discards_by_team[Team.A],
            pawns_in_safe=team_a_safe,
        ),
        team_b=TeamGameStats(
            captures=captures_by_team[Team.B],
            discards=discards_by_team[Team.B],
            pawns_in_safe=team_b_safe,
        ),
        total_score=f"{team_a_safe}-{team_b_safe}",
        score_sequence=tuple(score_sequence),
    )


def _active_player(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def _count_captures(previous_state: GameState, next_state: GameState, active_team: Team) -> int:
    captures = 0
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
    safe_count = _team_safe_count(state, team)
    progress = 0
    for player in TEAM_PLAYERS[team]:
        for pawn in player_pawns(player):
            progress += _pawn_progress(state, pawn)
    return safe_count, progress


def _team_safe_count(state: GameState, team: Team) -> int:
    return sum(
        1
        for player in TEAM_PLAYERS[team]
        for pawn in player_pawns(player)
        if get_pawn_position(state, pawn).kind == PositionKind.SAFE
    )


def _score_text(state: GameState) -> str:
    return f"{_team_safe_count(state, Team.A)}-{_team_safe_count(state, Team.B)}"


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
    output_path = config.output_path if config.output_path is not None else _generated_output_path(config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": _json_ready(asdict(experiment_result)),
        "games": [_json_ready(asdict(result)) for result in game_results],
    }
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)
        output_file.write("\n")


def _generated_output_path(config: ExperimentConfig) -> Path:
    data_dir = Path(__file__).resolve().parent / "data"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(config.experiment_name)
    filename = f"{slug}_games-{config.num_games}_seed-{config.seed}_{timestamp}.json"
    return data_dir / filename


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "experiment"


def _json_ready(value: Any) -> Any:
    if isinstance(value, Team):
        return value.value
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
