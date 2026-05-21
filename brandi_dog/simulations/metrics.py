from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

from brandi_dog.engine.state import Team


@dataclass(frozen=True)
class TeamGameStats:
    captures: int
    discards: int
    pawns_in_safe: int


@dataclass(frozen=True)
class GameResult:
    winner: Optional[Team]
    game_length: int
    capped: bool
    team_a: TeamGameStats
    team_b: TeamGameStats
    total_score: str
    score_sequence: tuple[str, ...]


@dataclass(frozen=True)
class TeamExperimentStats:
    win_rate: float
    average_captures: float
    stddev_captures: float
    average_discards: float
    stddev_discards: float
    average_pawns_in_safe: float
    stddev_pawns_in_safe: float


@dataclass(frozen=True)
class ExperimentResult:
    experiment_name: str
    num_games: int
    capped_games: int
    average_game_length: float
    stddev_game_length: float
    team_a: TeamExperimentStats
    team_b: TeamExperimentStats


def aggregate_game_results(experiment_name: str, game_results: Iterable[GameResult]) -> ExperimentResult:
    results = tuple(game_results)
    if not results:
        raise ValueError("Cannot aggregate an experiment with no games")

    return ExperimentResult(
        experiment_name=experiment_name,
        num_games=len(results),
        capped_games=sum(1 for result in results if result.capped),
        average_game_length=_mean(result.game_length for result in results),
        stddev_game_length=_stddev(result.game_length for result in results),
        team_a=_team_experiment_stats(results, Team.A),
        team_b=_team_experiment_stats(results, Team.B),
    )


def _team_experiment_stats(results: tuple[GameResult, ...], team: Team) -> TeamExperimentStats:
    stats = [result.team_a if team == Team.A else result.team_b for result in results]
    return TeamExperimentStats(
        win_rate=sum(1 for result in results if result.winner == team) / len(results),
        average_captures=_mean(item.captures for item in stats),
        stddev_captures=_stddev(item.captures for item in stats),
        average_discards=_mean(item.discards for item in stats),
        stddev_discards=_stddev(item.discards for item in stats),
        average_pawns_in_safe=_mean(item.pawns_in_safe for item in stats),
        stddev_pawns_in_safe=_stddev(item.pawns_in_safe for item in stats),
    )


def _mean(values: Iterable[float]) -> float:
    items = tuple(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _stddev(values: Iterable[float]) -> float:
    items = tuple(values)
    if len(items) <= 1:
        return 0.0
    mean = sum(items) / len(items)
    variance = sum((item - mean) ** 2 for item in items) / len(items)
    return math.sqrt(variance)
