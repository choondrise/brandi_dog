from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from brandi_dog.engine.state import GameState, PlayerId, PositionKind, Team, team_of


@dataclass(frozen=True)
class PolicyUpdateDiagnostics:
    loss: Optional[float] = None
    entropy: float = 0.0
    avg_selected_action_prob: float = 0.0
    grad_norm: float = 0.0
    weight_delta_norm: float = 0.0
    decisions: int = 0
    explored_actions: int = 0
    greedy_actions: int = 0
    sampled_actions: int = 0
    warning: str = ""


@dataclass(frozen=True)
class EvaluationResult:
    games: int
    win_rate: float
    avg_reward: float


@dataclass(frozen=True)
class GameRolloutResult:
    game_index: int
    rl_player: PlayerId
    rl_team: Team
    winner: Optional[Team]
    turns: int
    capped: bool
    score_a: int
    score_b: int
    total_reward: float
    update: PolicyUpdateDiagnostics = PolicyUpdateDiagnostics()
    epsilon: float = 0.0
    temperature: float = 1.0
    learning_rate: float = 0.0
    checkpoint_path: Optional[str] = None
    eval_win_rate: Optional[float] = None
    eval_avg_reward: Optional[float] = None


def safe_zone_score(state: GameState) -> tuple[int, int]:
    team_a = 0
    team_b = 0
    for index, position in enumerate(state.pawn_positions):
        if position.kind != PositionKind.SAFE:
            continue
        if team_of(PlayerId(index // 4)) == Team.A:
            team_a += 1
        else:
            team_b += 1
    return team_a, team_b
