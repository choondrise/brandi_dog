from __future__ import annotations

from brandi_dog.agents import (
    HeuristicAgent,
    ImperfectInformationMonteCarloAgent,
    MonteCarloAgent,
    RandomLegalAgent,
)


BOT_LEVELS = ("Idiot", "Easy", "Hard", "Cheater")


def build_bot(level: str, seed: int):
    normalized = _normalize_level(level)
    if normalized == "Idiot":
        return RandomLegalAgent(seed=seed)
    if normalized == "Easy":
        return HeuristicAgent(seed=seed)
    # TODO: Re-enable Medium after production hosting includes torch and the RL checkpoint artifact.
    if normalized == "Hard":
        return ImperfectInformationMonteCarloAgent(seed=seed, top_k=3, rollouts_per_action=2, rollout_workers=1)
    if normalized == "Cheater":
        return MonteCarloAgent(seed=seed, top_k=3, rollouts_per_action=2, rollout_workers=1)
    raise ValueError(f"Unknown bot level: {level}")


def _normalize_level(level: str) -> str:
    for known in BOT_LEVELS:
        if known.lower() == level.lower():
            return known
    raise ValueError(f"Unknown bot level: {level}")
