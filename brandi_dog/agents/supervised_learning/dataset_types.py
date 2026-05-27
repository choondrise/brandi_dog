from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DatasetBuildConfig:
    """Configuration for collecting raw imitation-learning decision samples."""

    output_path: str
    num_games: int = 1
    seed: int = 0
    max_turns: Optional[int] = None
    expert_agent_name: str = "AdvancedHeuristicAgent"
    expert_agent_type: str = "advanced_heuristic"
    monte_carlo_top_k: int = 3
    monte_carlo_rollouts_per_action: int = 2
    monte_carlo_rollout_policy: str = "advanced_heuristic"
    monte_carlo_rollout_workers: int = 1
    max_samples: Optional[int] = None
    candidate_alternatives_per_source: int = 10
    append: bool = False
    print_progress: bool = True
    worker_id: Optional[int] = None


@dataclass(frozen=True)
class EncodedSample:
    """One ranking-training example after feature extraction."""

    state_features: list[float]
    action_features: list[list[float]]
    target_index: int
    candidate_action_ids: list[str]


@dataclass(frozen=True)
class DatasetBuildResult:
    """Summary returned by dataset builders."""

    output_path: str
    games_played: int
    decisions_seen: int
    samples_written: int
