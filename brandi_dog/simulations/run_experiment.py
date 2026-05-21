from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brandi_dog.agents import AdvancedHeuristicAgent, HeuristicAgent, LimitedHorizonMonteCarloAgent
from brandi_dog.engine.state import PlayerId

from config import ExperimentConfig
from runner import run_experiment


def build_default_config(
    num_games: int,
    seed: int,
    output_path: Path | None,
    max_turns: int,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_advanced_heuristic_vs_monte_carlo_heuristic",
        num_games=num_games,
        seed=seed,
        agents_by_player={
            PlayerId.A1: AdvancedHeuristicAgent(seed=seed * 17 + 1, style='balanced', top_n_intentions=7),
            PlayerId.B1: HeuristicAgent(seed=seed * 17 + 2),
            PlayerId.A2: AdvancedHeuristicAgent(
                seed=seed * 17 + 3, style='balanced', top_n_intentions=7),
            PlayerId.B2: HeuristicAgent(
                seed=seed * 17 + 4),
        },
        output_path=output_path,
        max_turns=max_turns,
        team_a_label="Advanced heuristic",
        team_b_label="Monte Carlo",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Brandi Dog simulation experiment.")
    parser.add_argument("--games", type=int, default=3, help="Number of games to simulate.")
    parser.add_argument("--seed", type=int, default=1, help="Base seed for the experiment.")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=500,
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
