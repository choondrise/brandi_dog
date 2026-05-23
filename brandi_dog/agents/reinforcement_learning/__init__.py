"""Reinforcement-learning fine-tuning tools for ranking/imitation agents.

This package is intentionally separate from ``agents.supervised_learning``.
It imports the trained ranking scorer and encoders as dependencies, but keeps RL
rollouts, rewards, checkpointing, and training configuration isolated.

Example:
    python -m brandi_dog.agents.reinforcement_learning.train_rl \
        --initial-model-path data/ranking_model_v2.pt \
        --total-games 100 \
        --checkpoint-every-games 25 \
        --trained-agent-id 0 \
        --rotate-positions
"""

from .config import PlayerSlotConfig, RLTrainingConfig, RewardWeights
from .reward import RewardBreakdown, ShapedReward
from .rl_trainer import RLTrainer, train_rl

__all__ = [
    "PlayerSlotConfig",
    "RLTrainer",
    "RLTrainingConfig",
    "RewardWeights",
    "RewardBreakdown",
    "ShapedReward",
    "train_rl",
]
