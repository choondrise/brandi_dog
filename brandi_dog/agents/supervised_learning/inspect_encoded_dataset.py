from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Optional


def inspect_encoded_dataset(path: str) -> dict[str, object]:
    sample_count = 0
    feature_dim = None
    first_candidate_count = None
    first_target_index = None
    values: list[float] = []
    candidate_counts: list[int] = []
    by_player: dict[str, int] = {}
    by_team: dict[str, int] = {}
    by_encoder: dict[str, int] = {}

    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            payload = json.loads(line)
            candidates = payload.get("candidate_features") or []
            if not candidates:
                continue
            sample_count += 1
            candidate_counts.append(len(candidates))
            metadata = payload.get("metadata") or {}
            by_player[str(metadata.get("player"))] = by_player.get(str(metadata.get("player")), 0) + 1
            by_team[str(metadata.get("team"))] = by_team.get(str(metadata.get("team")), 0) + 1
            by_encoder[str(metadata.get("encoder", "v1"))] = by_encoder.get(str(metadata.get("encoder", "v1")), 0) + 1
            if first_candidate_count is None:
                first_candidate_count = len(candidates)
                first_target_index = payload.get("target_index")
                feature_dim = len(candidates[0])
            for feature_vector in candidates:
                values.extend(float(value) for value in feature_vector)

    summary = {
        "samples": sample_count,
        "feature_dim": feature_dim,
        "first_sample_candidate_count": first_candidate_count,
        "first_sample_target_index": first_target_index,
        "feature_min": min(values) if values else None,
        "feature_max": max(values) if values else None,
        "feature_mean": mean(values) if values else None,
        "candidate_count_min": min(candidate_counts) if candidate_counts else None,
        "candidate_count_max": max(candidate_counts) if candidate_counts else None,
        "candidate_count_mean": mean(candidate_counts) if candidate_counts else None,
        "metadata_by_player": dict(sorted(by_player.items())),
        "metadata_by_team": dict(sorted(by_team.items())),
        "metadata_by_encoder": dict(sorted(by_encoder.items())),
        "leak_check": "V2 should not include absolute player/team ids in feature vectors; those appear only in metadata.",
    }
    print("Encoded dataset inspection:", flush=True)
    for key, value in summary.items():
        print(f"  {key}: {value}", flush=True)
    return summary


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Inspect grouped encoded ranking JSONL datasets.")
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    inspect_encoded_dataset(args.input)


if __name__ == "__main__":
    main()
