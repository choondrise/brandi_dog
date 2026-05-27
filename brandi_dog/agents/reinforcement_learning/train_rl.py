from __future__ import annotations

import argparse
from typing import Iterable, Optional

from .config import PlayerSlotConfig, RLTrainingConfig, RewardWeights
from .rl_trainer import RLTrainer


def parse_player_slot(raw: str) -> PlayerSlotConfig:
    """Parse policy or policy:weights_path into a player slot config."""

    parts = raw.split(":", 1)
    if len(parts) == 1:
        return PlayerSlotConfig(policy=parts[0])
    return PlayerSlotConfig(policy=parts[0], weights_path=parts[1])


def build_config_from_args(args: argparse.Namespace) -> RLTrainingConfig:
    players = (
        parse_player_slot(args.player_0),
        parse_player_slot(args.player_1),
        parse_player_slot(args.player_2),
        parse_player_slot(args.player_3),
    )
    reward_weights = RewardWeights(
        win_reward=args.reward_win,
        loss_penalty=args.reward_loss,
        team_progress_scale=args.reward_team_progress,
        partner_progress_scale=args.reward_partner_progress,
        opponent_progress_scale=args.reward_opponent_progress,
        safe_entry_reward=args.reward_safe_entry,
        capture_reward=args.reward_capture,
        discard_penalty=args.reward_discard,
        sent_back_penalty=args.reward_sent_back,
        terminal_progress_scale=args.reward_terminal_progress,
    )
    return RLTrainingConfig(
        initial_model_path=args.initial_model_path,
        total_games=args.total_games,
        checkpoint_every_games=args.checkpoint_every_games,
        checkpoint_dir=args.checkpoint_dir,
        trained_agent_id=args.trained_agent_id,
        seed=args.seed,
        learning_rate=args.lr,
        exploration_rate=args.epsilon,
        epsilon_decay=args.epsilon_decay,
        min_epsilon=args.min_epsilon,
        temperature=args.temperature,
        gamma=args.gamma,
        entropy_bonus=args.entropy_bonus_coef,
        normalize_returns=not args.no_normalize_returns,
        max_turns=args.max_turns,
        rotate_trained_agent_positions=args.rotate_positions,
        output_log_path=args.output_log_path,
        log_format=args.log_format,
        device=args.device,
        encoder=args.encoder,
        hidden_dim=args.hidden_dim,
        recent_window=args.recent_window,
        eval_enabled=args.eval_enabled,
        eval_every_games=args.eval_every_games,
        eval_games=args.eval_games,
        eval_rotate_positions=not args.no_eval_rotate_positions,
        grad_warn_threshold=args.grad_warn_threshold,
        weight_change_warn_threshold=args.weight_change_warn_threshold,
        reward_weights=reward_weights,
        players=players,
    )


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Fine-tune a trained deep-learning ranking model with simple policy-gradient RL.")
    parser.add_argument("--initial-model-path", required=True, help="Path to an existing ranking/imitation .pt checkpoint.")
    parser.add_argument("--total-games", type=int, default=100)
    parser.add_argument("--checkpoint-every-games", type=int, default=25)
    parser.add_argument("--checkpoint-dir", default="brandi_dog/agents/reinforcement_learning/checkpoints")
    parser.add_argument("--trained-agent-id", type=int, default=0, help="Physical seat id 0..3 when position rotation is disabled.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--epsilon", type=float, default=0.10, help="Initial epsilon-greedy random exploration rate.")
    parser.add_argument("--epsilon-decay", type=float, default=1.0)
    parser.add_argument("--min-epsilon", type=float, default=0.02)
    parser.add_argument("--temperature", type=float, default=1.0, help="Softmax temperature for training-time sampling.")
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--entropy-bonus-coef", type=float, default=0.001)
    parser.add_argument("--no-normalize-returns", action="store_true")
    parser.add_argument("--max-turns", type=int, default=1000)
    parser.add_argument("--rotate-positions", action="store_true")
    parser.add_argument("--output-log-path")
    parser.add_argument("--log-format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, ...")
    parser.add_argument("--encoder", default="auto", choices=("auto", "v1", "v2"))
    parser.add_argument("--hidden-dim", type=int)
    parser.add_argument("--recent-window", type=int, default=100)
    parser.add_argument("--eval-enabled", action="store_true")
    parser.add_argument("--eval-every-games", type=int, default=25)
    parser.add_argument("--eval-games", type=int, default=0)
    parser.add_argument("--no-eval-rotate-positions", action="store_true")
    parser.add_argument("--grad-warn-threshold", type=float, default=1e-8)
    parser.add_argument("--weight-change-warn-threshold", type=float, default=1e-10)
    parser.add_argument("--reward-win", type=float, default=100.0)
    parser.add_argument("--reward-loss", type=float, default=-100.0)
    parser.add_argument("--reward-team-progress", type=float, default=0.5)
    parser.add_argument("--reward-partner-progress", type=float, default=0.25)
    parser.add_argument("--reward-opponent-progress", type=float, default=-0.5)
    parser.add_argument("--reward-safe-entry", type=float, default=5.0)
    parser.add_argument("--reward-capture", type=float, default=2.0)
    parser.add_argument("--reward-discard", type=float, default=-0.35)
    parser.add_argument("--reward-sent-back", type=float, default=-5.0)
    parser.add_argument("--reward-terminal-progress", type=float, default=1.0)
    parser.add_argument("--player-0", default="rl_agent")
    parser.add_argument("--player-1", default="advanced_heuristic_agent")
    parser.add_argument("--player-2", default="advanced_heuristic_agent")
    parser.add_argument("--player-3", default="advanced_heuristic_agent")
    args = parser.parse_args(argv)

    config = build_config_from_args(args)
    trainer = RLTrainer(config)
    trainer.train()


if __name__ == "__main__":
    main()
