from __future__ import annotations

from pathlib import Path

from brandi_dog.agents import (
    HeuristicAgent,
    ImperfectInformationMonteCarloAgent,
    MonteCarloAgent,
    RandomLegalAgent,
)


BOT_LEVELS = ("Idiot", "Easy", "Medium", "Hard", "Cheater")


def build_bot(level: str, seed: int):
    normalized = _normalize_level(level)
    if normalized == "Idiot":
        return RandomLegalAgent(seed=seed)
    if normalized == "Easy":
        return HeuristicAgent(seed=seed)
    if normalized == "Medium":
        from brandi_dog.agents.deep_learning_agent import DeepLearningAgent

        return DeepLearningAgent(
            seed=seed,
            weights_path=str(_default_rl_checkpoint()),
            device="cpu",
        )
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


def _default_rl_checkpoint() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "brandi_dog" / "agents" / "reinforcement_learning" / "checkpoints" / "agent_0" / "checkpoint_agent_0_final.pt"
