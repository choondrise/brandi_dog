from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from brandi_dog.engine.state import Team


@dataclass(frozen=True)
class GameResult:
    winner: Optional[Team]
    game_length: int
    captures: int
    discard_or_noop_actions: int
    capped: bool


@dataclass(frozen=True)
class ExperimentResult:
    experiment_name: str
    num_games: int
    capped_games: int
    team_0_win_rate: float
    team_1_win_rate: float
    average_game_length: float
    captures_per_game: float
    discard_or_noop_actions_per_game: float


def aggregate_game_results(experiment_name: str, game_results: Iterable[GameResult]) -> ExperimentResult:
    results = tuple(game_results)
    if not results:
        raise ValueError("Cannot aggregate an experiment with no games")

    num_games = len(results)
    team_0_wins = sum(1 for result in results if result.winner == Team.A)
    team_1_wins = sum(1 for result in results if result.winner == Team.B)
    capped_games = sum(1 for result in results if result.capped)

    return ExperimentResult(
        experiment_name=experiment_name,
        num_games=num_games,
        capped_games=capped_games,
        team_0_win_rate=team_0_wins / num_games,
        team_1_win_rate=team_1_wins / num_games,
        average_game_length=sum(result.game_length for result in results) / num_games,
        captures_per_game=sum(result.captures for result in results) / num_games,
        discard_or_noop_actions_per_game=sum(result.discard_or_noop_actions for result in results) / num_games,
    )
