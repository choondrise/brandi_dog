from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PlayerSlotConfig:
    """Configuration for one physical player seat.

    Supported policy names:
    - rl_agent
    - advanced_heuristic_agent
    - heuristic_agent
    - monte_carlo_agent  # expensive; use later for evaluation/fine-tuning
    - random_legal_agent
    - deep_learning_agent
    - ranking_model_agent  # backward-compatible alias
    """

    policy: str = "advanced_heuristic_agent"
    weights_path: Optional[str] = None
    encoder: str = "auto"


@dataclass(frozen=True)
class RewardWeights:
    """Configurable shaped team reward weights.

    Defaults are intentionally moderate. The imitation model is already strong,
    so huge terminal rewards can drown out useful action-level diagnostics.
    """

    win_reward: float = 100.0
    loss_penalty: float = -100.0
    team_progress_scale: float = 0.5
    partner_progress_scale: float = 0.25
    opponent_progress_scale: float = -0.25
    safe_entry_reward: float = 5.0
    capture_reward: float = 2.0
    discard_penalty: float = -0.35
    sent_back_penalty: float = -5.0
    terminal_progress_scale: float = 1.0


@dataclass(frozen=True)
class RLTrainingConfig:
    initial_model_path: str
    total_games: int = 100
    checkpoint_every_games: int = 25
    checkpoint_dir: str = "brandi_dog/agents/reinforcement_learning/checkpoints"
    trained_agent_id: int = 0
    seed: int = 0
    learning_rate: float = 1e-5
    exploration_rate: float = 0.10
    epsilon_decay: float = 1.0
    min_epsilon: float = 0.02
    temperature: float = 1.0
    gamma: float = 0.99
    entropy_bonus: float = 0.001
    normalize_returns: bool = True
    max_turns: int = 1000
    rotate_trained_agent_positions: bool = False
    output_log_path: Optional[str] = None
    log_format: str = "csv"
    device: str = "auto"
    encoder: str = "auto"
    hidden_dim: Optional[int] = None
    recent_window: int = 50
    eval_enabled: bool = False
    eval_every_games: int = 25
    eval_games: int = 0
    eval_rotate_positions: bool = True
    grad_warn_threshold: float = 1e-8
    weight_change_warn_threshold: float = 1e-10
    reward_weights: RewardWeights = field(default_factory=RewardWeights)
    players: tuple[PlayerSlotConfig, PlayerSlotConfig, PlayerSlotConfig, PlayerSlotConfig] = field(
        default_factory=lambda: (
            PlayerSlotConfig("rl_agent"),
            PlayerSlotConfig("advanced_heuristic_agent"),
            PlayerSlotConfig("advanced_heuristic_agent"),
            PlayerSlotConfig("advanced_heuristic_agent"),
        )
    )

    @property
    def entropy_bonus_coef(self) -> float:
        return self.entropy_bonus

    def checkpoint_root(self) -> Path:
        return Path(self.checkpoint_dir) / f"agent_{self.trained_agent_id}"

    def epsilon_for_game(self, game_index: int, training: bool = True) -> float:
        if not training:
            return 0.0
        decayed = self.exploration_rate * (self.epsilon_decay ** max(0, game_index - 1))
        return max(self.min_epsilon, decayed)

    def validate(self) -> None:
        if self.total_games < 1:
            raise ValueError("total_games must be >= 1")
        if self.checkpoint_every_games < 1:
            raise ValueError("checkpoint_every_games must be >= 1")
        if self.eval_every_games < 1:
            raise ValueError("eval_every_games must be >= 1")
        if not 0 <= self.trained_agent_id <= 3:
            raise ValueError("trained_agent_id must be in range 0..3")
        if self.temperature <= 0:
            raise ValueError("temperature must be > 0")
        if not 0 <= self.min_epsilon <= self.exploration_rate:
            raise ValueError("min_epsilon must be between 0 and exploration_rate")
        if len(self.players) != 4:
            raise ValueError("players must contain exactly four PlayerSlotConfig entries")
        rl_slots = [index for index, slot in enumerate(self.players) if slot.policy == "rl_agent"]
        if len(rl_slots) != 1:
            raise ValueError("Exactly one configured player slot must use policy='rl_agent'")
        if not self.rotate_trained_agent_positions and rl_slots[0] != self.trained_agent_id:
            raise ValueError("When rotation is disabled, trained_agent_id must point at the configured rl_agent slot")
        if self.log_format not in {"csv", "jsonl"}:
            raise ValueError("log_format must be either 'csv' or 'jsonl'")
