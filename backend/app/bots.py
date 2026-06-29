from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from brandi_dog.agents import (
    DeepLearningAgent,
    HeuristicAgent,
    ImperfectInformationMonteCarloAgent,
    MonteCarloAgent,
    RandomLegalAgent,
)


BOT_LEVELS = ("Idiot", "Easy", "Medium", "Hard", "Cheater")
DEFAULT_MEDIUM_WEIGHTS = (
    Path(__file__).resolve().parents[2]
    / "brandi_dog"
    / "agents"
    / "reinforcement_learning"
    / "checkpoints"
    / "agent_0"
    / "checkpoint_agent_0_final.pt"
)


def build_bot(level: str, seed: int):
    normalized = _normalize_level(level)
    if normalized == "Idiot":
        return RandomLegalAgent(seed=seed)
    if normalized == "Easy":
        return HeuristicAgent(seed=seed)
    if normalized == "Medium":
        return _shared_medium_bot()
    if normalized == "Hard":
        return ImperfectInformationMonteCarloAgent(seed=seed, top_k=3, rollouts_per_action=2, rollout_workers=1)
    if normalized == "Cheater":
        return MonteCarloAgent(seed=seed, top_k=3, rollouts_per_action=2, rollout_workers=1)
    raise ValueError(f"Unknown bot level: {level}")


@lru_cache(maxsize=1)
def _shared_medium_bot():
    weights_path = Path(os.environ.get("BRANDI_MEDIUM_WEIGHTS", str(DEFAULT_MEDIUM_WEIGHTS)))
    if not weights_path.exists():
        raise RuntimeError(f"Medium bot checkpoint not found: {weights_path}")
    return DeepLearningAgent(seed=0, weights_path=str(weights_path), device=os.environ.get("BRANDI_MEDIUM_DEVICE", "auto"), encoder="auto")


def _normalize_level(level: str) -> str:
    for known in BOT_LEVELS:
        if known.lower() == level.lower():
            return known
    raise ValueError(f"Unknown bot level: {level}")
