from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brandi_dog.agents.deep_learning_agent import DeepLearningAgent

from brandi_dog.agents import AdvancedHeuristicAgent, HeuristicAgent, MonteCarloAgent, RandomLegalAgent
from brandi_dog.engine.state import PlayerId

from config import ExperimentConfig
from runner import run_experiment


def build_default_config(
    num_games: int,
    seed: int,
    output_path: Path | None,
    max_turns: int,
) -> ExperimentConfig:
    weights_path = Path(__file__).resolve().parents[2] / "data" / "ranking_model_v2.pt"
    return ExperimentConfig(
        experiment_name="ranking_model_v2_vs_reinforcement_learning_mc_300",
        num_games=num_games,
        seed=2,
        agents_by_player={
            PlayerId.A1: DeepLearningAgent(
                seed=seed * 17 + 1, weights_path=str(weights_path), device='auto'),
            PlayerId.A2: DeepLearningAgent(
                seed=seed * 17 + 2, weights_path=str(weights_path), device='auto'),
            PlayerId.B1: DeepLearningAgent(
                seed=seed * 17 + 3, weights_path='../agents/reinforcement_learning/checkpoints/agent_1/checkpoint_agent_1_final.pt', device='auto'),
            PlayerId.B2: DeepLearningAgent(
                seed=seed * 17 + 4, weights_path='../agents/reinforcement_learning/checkpoints/agent_1/checkpoint_agent_1_final.pt', device='auto'),
        },
        output_path=output_path,
        max_turns=max_turns,
        team_a_label="Ranking Model V2",
        team_b_label="Reinforcement Learning MC 300",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Brandi Dog simulation experiment.")
    parser.add_argument("--games", type=int, default=500, help="Number of games to simulate.")
    parser.add_argument("--seed", type=int, default=1, help="Base seed for the experiment.")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=1000,
        help="Safety cap for turns per game.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit JSON output path. Defaults to simulations/data/<experiment>_...json.",
    )
    args = parser.parse_args()

    result = run_experiment(build_default_config(args.games, args.seed, args.output, args.max_turns))
    print(result)


if __name__ == "__main__":
    main()
