from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brandi_dog.agents.deep_learning_agent import DeepLearningAgent

from brandi_dog.agents import AdvancedHeuristicAgent, HeuristicAgent, MonteCarloAgent, RandomLegalAgent, \
    ImperfectInformationMonteCarloAgent
from brandi_dog.engine.state import PlayerId

from config import ExperimentConfig
from runner import _run_single_game, _write_experiment_result, run_experiment
from metrics import GameResult, aggregate_game_results


def build_default_config(
    num_games: int,
    seed: int,
    output_path: Path | None,
    max_turns: int,
) -> ExperimentConfig:
    root_dir = Path(__file__).resolve().parents[2]
    weights_path = root_dir / "data" / "rl_finetuned_on_monte_carlo_lr00002_anchor005_epochs1.pt"
    checkpoint_1 = root_dir / "runs" / "self_play_league" / "checkpoints" / "candidates" / "candidate_iter_1.pt"
    rl_weights_path_0 = root_dir / "brandi_dog" / "agents" / "reinforcement_learning" / "checkpoints" / "agent_0" / "checkpoint_agent_0_4000.pt"
    rl_weights_path_1 = root_dir / "brandi_dog" / "agents" / "reinforcement_learning" / "checkpoints" / "agent_0" / "checkpoint_agent_0_final.pt"
    return ExperimentConfig(
        experiment_name="advanced_heuristic_+_random_vs_random_legal",
        num_games=num_games,
        seed=seed,
        agents_by_player={
            PlayerId.A1: AdvancedHeuristicAgent(
                seed=seed * 17 + 1),
            PlayerId.A2: RandomLegalAgent(
                seed=seed * 17 + 2),
            PlayerId.B1: RandomLegalAgent(
                seed=seed * 17 + 3),
            PlayerId.B2: RandomLegalAgent(
                seed=seed * 17 + 4),
        },
        output_path=output_path,
        max_turns=max_turns,
        team_a_label="Advanced Heuristic + Random",
        team_b_label="Random + Random",
    )


def run_parallel_experiment(
    num_games: int,
    seed: int,
    output_path: Path | None,
    max_turns: int,
    workers: int,
):
    if num_games <= 0:
        raise ValueError("num_games must be greater than zero")
    if workers <= 0:
        raise ValueError("workers must be greater than zero")

    summary_config = build_default_config(num_games, seed, output_path, max_turns)
    print("Team A: {}, Team B: {}".format(summary_config.team_a_label, summary_config.team_b_label), flush=True)
    print("Turn cap: {}".format(max_turns if max_turns is not None else "none"), flush=True)
    print("Workers: {}".format(workers), flush=True)

    indexed_results: list[tuple[int, GameResult] | None] = [None] * num_games
    # Use spawn so torch/CUDA models can be initialized inside worker processes.
    mp_context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp_context) as executor:
        futures = {
            executor.submit(_run_game_worker, game_index, num_games, seed, max_turns): game_index
            for game_index in range(num_games)
        }
        for future in as_completed(futures):
            game_index, game_result = future.result()
            indexed_results[game_index] = (game_index, game_result)
            print("Game {}: {}".format(game_index + 1, game_result.total_score), flush=True)

    game_results = tuple(item[1] for item in indexed_results if item is not None)
    if len(game_results) != num_games:
        raise RuntimeError("Parallel experiment finished with missing game results")

    experiment_result = aggregate_game_results(summary_config.experiment_name, game_results)
    _write_experiment_result(summary_config, experiment_result, game_results)
    return experiment_result


def _run_game_worker(game_index: int, num_games: int, seed: int, max_turns: int | None) -> tuple[int, GameResult]:
    game_seed = seed + game_index
    config = build_default_config(1, game_seed, None, max_turns)
    return game_index, _run_single_game(config, game_seed=game_seed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Brandi Dog simulation experiment.")
    parser.add_argument("--games", type=int, default=1000, help="Number of games to simulate.")
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
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of worker processes to use. Use 1 for sequential execution.",
    )
    args = parser.parse_args()

    if args.workers == 1:
        result = run_experiment(build_default_config(args.games, args.seed, args.output, args.max_turns))
    else:
        result = run_parallel_experiment(args.games, args.seed, args.output, args.max_turns, args.workers)
    print(result)


if __name__ == "__main__":
    main()
