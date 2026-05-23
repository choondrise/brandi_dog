from __future__ import annotations

import argparse
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable, Optional

from .dataset_builder import build_dataset
from .dataset_types import DatasetBuildResult


def build_parallel_dataset(
    output_path: str,
    num_games: int,
    workers: int,
    seed: int = 0,
    max_turns: Optional[int] = None,
    max_samples: Optional[int] = None,
    shard_dir: Optional[str] = None,
    candidate_alternatives_per_source: int = 10,
    append: bool = False,
    print_progress: bool = True,
) -> DatasetBuildResult:
    """Build dataset shards in independent worker processes and merge them."""

    if workers <= 0:
        raise ValueError("workers must be greater than zero")
    if num_games <= 0:
        raise ValueError("num_games must be greater than zero")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shard_root = Path(shard_dir) if shard_dir is not None else output.parent / (output.stem + "_shards")
    shard_root.mkdir(parents=True, exist_ok=True)

    game_splits = _split_count(num_games, workers)
    sample_splits = _split_count(max_samples, workers) if max_samples is not None else [None for _ in range(workers)]
    tasks = []
    for worker_id, worker_games in enumerate(game_splits):
        if worker_games <= 0:
            continue
        tasks.append(
            {
                "worker_id": worker_id,
                "output_path": str(shard_root / f"shard_{worker_id:03d}.jsonl"),
                "num_games": worker_games,
                "seed": seed + worker_id * 100_000,
                "max_turns": max_turns,
                "max_samples": sample_splits[worker_id],
                "candidate_alternatives_per_source": candidate_alternatives_per_source,
                "print_progress": print_progress,
            }
        )

    with Pool(processes=min(workers, len(tasks))) as pool:
        results = pool.map(_build_worker_shard, tasks)

    mode = "a" if append else "w"
    with output.open(mode, encoding="utf-8") as merged:
        for task in tasks:
            shard_path = Path(task["output_path"])
            if shard_path.exists():
                with shard_path.open("r", encoding="utf-8") as shard:
                    for line in shard:
                        merged.write(line)

    return DatasetBuildResult(
        output_path=str(output),
        games_played=sum(result.games_played for result in results),
        decisions_seen=sum(result.decisions_seen for result in results),
        samples_written=sum(result.samples_written for result in results),
    )


def _build_worker_shard(task: dict) -> DatasetBuildResult:
    return build_dataset(
        output_path=task["output_path"],
        num_games=task["num_games"],
        seed=task["seed"],
        max_turns=task["max_turns"],
        max_samples=task["max_samples"],
        candidate_alternatives_per_source=task["candidate_alternatives_per_source"],
        print_progress=task["print_progress"],
        worker_id=task["worker_id"],
    )


def _split_count(total: Optional[int], parts: int) -> list[Optional[int]]:
    if total is None:
        return [None for _ in range(parts)]
    base = total // parts
    remainder = total % parts
    return [base + (1 if index < remainder else 0) for index in range(parts)]


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Collect imitation-learning JSONL samples in parallel shards.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--games", type=int, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--shard-dir", default=None)
    parser.add_argument("--candidate-alternatives", type=int, default=10)
    parser.add_argument("--append", action="store_true", help="Append merged shards to output instead of overwriting it.")
    parser.add_argument("--quiet", action="store_true", help="Do not print per-game worker progress.")
    args = parser.parse_args(argv)
    result = build_parallel_dataset(
        output_path=args.output,
        num_games=args.games,
        workers=args.workers,
        seed=args.seed,
        max_turns=args.max_turns,
        max_samples=args.max_samples,
        shard_dir=args.shard_dir,
        candidate_alternatives_per_source=args.candidate_alternatives,
        append=args.append,
        print_progress=not args.quiet,
    )
    print(result)


if __name__ == "__main__":
    main()
