from __future__ import annotations

import argparse
from pathlib import Path

from brandi_dog.agents.random_legal_agent import RandomLegalAgent

from brandi_dog.agents import HeuristicAgent
from brandi_dog.engine.state import PlayerId

from config import ExperimentConfig
from runner import run_experiment


def build_default_config(
    num_games: int,
    seed: int,
    output_path: Path,
    max_turns: int,
    experiment_runs: int,
    move_analysis_path: Path,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="heuristic_vs_heuristic",
        num_games=num_games,
        seed=seed,
        agents_by_player={
            PlayerId.A1: HeuristicAgent(seed=seed * 17 + 1),
            PlayerId.B1: HeuristicAgent(seed=seed * 17 + 2),
            PlayerId.A2: HeuristicAgent(seed=seed * 17 + 3),
            PlayerId.B2: HeuristicAgent(seed=seed * 17 + 4),
        },
        output_path=output_path,
        max_turns=max_turns,
        experiment_runs=experiment_runs,
        move_analysis_path=move_analysis_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Brandi Dog simulation experiment.")
    parser.add_argument("--games", type=int, default=3, help="Number of games to simulate.")
    parser.add_argument("--seed", type=int, default=1, help="Base seed for the experiment.")
    parser.add_argument("--runs", type=int, default=3, help="Number of times to repeat the experiment.")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=100,
        help="Safety cap for turns per game.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("simulation_results.json"),
        help="Path where JSON results will be written.",
    )
    parser.add_argument(
        "--move-analysis-output",
        type=Path,
        default=Path("move_analysis.csv"),
        help="Path where heuristic move-option counts will be written.",
    )
    args = parser.parse_args()

    result = run_experiment(
        build_default_config(
            args.games,
            args.seed,
            args.output,
            args.max_turns,
            args.runs,
            args.move_analysis_output,
        )
    )
    print(f"Wrote results to {args.output}")
    print(f"Wrote move analysis to {args.move_analysis_output}")
    print(result)


if __name__ == "__main__":
    main()
