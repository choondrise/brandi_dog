from __future__ import annotations

import csv
import json
import math
import random
from collections import deque
from pathlib import Path
from typing import Optional

from brandi_dog.agents import AdvancedHeuristicAgent, HeuristicAgent, MonteCarloAgent, RandomLegalAgent
from brandi_dog.agents.deep_learning_agent import DeepLearningAgent
from brandi_dog.agents.supervised_learning.model import torch
from brandi_dog.engine.actions import Action
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PlayerId, RoundStage, Team, team_of

from .config import PlayerSlotConfig, RLTrainingConfig
from .reward import ShapedReward
from .rollout import EvaluationResult, GameRolloutResult, PolicyUpdateDiagnostics, safe_zone_score


class TrainableRankingPolicy:
    """Train-time wrapper around the existing deep-learning agent encoder path."""

    def __init__(self, config: RLTrainingConfig):
        if torch is None:
            raise ImportError("PyTorch is required for RL fine-tuning")
        self.config = config
        self.rng = random.Random(config.seed)
        self.delegate = DeepLearningAgent(
            seed=config.seed,
            weights_path=config.initial_model_path,
            device=config.device,
            encoder=config.encoder,
        )
        self.device = self.delegate.device
        self.model = self.delegate.model
        self.feature_dim = self.delegate.feature_dim
        self.hidden_dim = config.hidden_dim or self._checkpoint_hidden_dim(config.initial_model_path)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=config.learning_rate)
        self._empty_state = torch.empty(0, dtype=torch.float32, device=self.device)
        self.saved_log_probs: list = []
        self.saved_entropies: list = []
        self.saved_selected_probs: list[float] = []
        self.saved_rewards: list[float] = []
        self.decisions = 0
        self.explored_actions = 0
        self.greedy_actions = 0
        self.sampled_actions = 0

    def select_action(self, engine: GameEngine, state: GameState, training: bool = True, epsilon: float = 0.0) -> Action:
        if state.round_stage != RoundStage.PLAY_LOOP:
            return self.delegate.fallback_agent.select_action(engine, state)

        actions = self.delegate._candidate_actions(engine, state)
        if not actions:
            return self.delegate.fallback_agent.select_action(engine, state)
        if len(actions) == 1:
            return actions[0]

        features = self.delegate._encode_live_actions(engine, state, actions)
        action_tensor = torch.tensor(features, dtype=torch.float32, device=self.device)
        scores = self.model(self._empty_state, action_tensor)
        scaled_scores = scores / self.config.temperature
        probs = torch.softmax(scaled_scores, dim=0)

        if training and self.rng.random() < epsilon:
            action_index = self.rng.randrange(len(actions))
            self.explored_actions += 1
        elif training:
            action_index = int(torch.multinomial(probs, 1).detach().cpu()[0])
            self.sampled_actions += 1
        else:
            action_index = int(torch.argmax(probs).detach().cpu())
            self.greedy_actions += 1

        if training:
            log_probs = torch.log_softmax(scaled_scores, dim=0)
            entropy = -(probs * log_probs).sum()
            self.saved_log_probs.append(log_probs[action_index])
            self.saved_entropies.append(entropy)
            self.saved_selected_probs.append(float(probs[action_index].detach().cpu()))
            self.decisions += 1
        return actions[action_index]

    def add_reward(self, reward: float) -> None:
        if self.saved_log_probs:
            self.saved_rewards.append(float(reward))

    def finish_game_update(self) -> PolicyUpdateDiagnostics:
        if not self.saved_log_probs:
            self._clear_episode_buffers()
            return PolicyUpdateDiagnostics()

        rewards = list(self.saved_rewards)
        if len(rewards) < len(self.saved_log_probs):
            rewards.extend([0.0] * (len(self.saved_log_probs) - len(rewards)))
        elif len(rewards) > len(self.saved_log_probs):
            rewards = rewards[: len(self.saved_log_probs)]

        returns: list[float] = []
        running = 0.0
        for reward in reversed(rewards):
            running = reward + self.config.gamma * running
            returns.append(running)
        returns.reverse()

        returns_tensor = torch.tensor(returns, dtype=torch.float32, device=self.device)
        if self.config.normalize_returns and returns_tensor.numel() > 1:
            std = returns_tensor.std(unbiased=False)
            if float(std.detach().cpu()) > 1e-8:
                returns_tensor = (returns_tensor - returns_tensor.mean()) / (std + 1e-8)

        policy_terms = [-log_prob * ret for log_prob, ret in zip(self.saved_log_probs, returns_tensor)]
        loss = torch.stack(policy_terms).sum()
        avg_entropy = float(torch.stack(self.saved_entropies).mean().detach().cpu()) if self.saved_entropies else 0.0
        if self.config.entropy_bonus:
            loss = loss - self.config.entropy_bonus * torch.stack(self.saved_entropies).sum()

        before_params = [param.detach().clone() for param in self.model.parameters() if param.requires_grad]
        self.optimizer.zero_grad()
        loss.backward()
        grad_norm = self._grad_norm()
        self.optimizer.step()
        weight_delta_norm = self._weight_delta_norm(before_params)

        warning_parts = []
        if grad_norm <= self.config.grad_warn_threshold:
            warning_parts.append(f"gradient norm is very small ({grad_norm:.3e})")
        if weight_delta_norm <= self.config.weight_change_warn_threshold:
            warning_parts.append(f"weight delta is very small ({weight_delta_norm:.3e})")
        warning = "; ".join(warning_parts)
        if warning:
            print(f"RL warning: {warning}", flush=True)

        diagnostics = PolicyUpdateDiagnostics(
            loss=float(loss.detach().cpu()),
            entropy=avg_entropy,
            avg_selected_action_prob=sum(self.saved_selected_probs) / max(1, len(self.saved_selected_probs)),
            grad_norm=grad_norm,
            weight_delta_norm=weight_delta_norm,
            decisions=self.decisions,
            explored_actions=self.explored_actions,
            greedy_actions=self.greedy_actions,
            sampled_actions=self.sampled_actions,
            warning=warning,
        )
        self._clear_episode_buffers()
        return diagnostics

    def save_checkpoint(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state": self.model.state_dict(),
                "state_dim": 0,
                "action_dim": self.feature_dim,
                "hidden_dim": self.hidden_dim,
                "format": "rl_finetuned_grouped_ranking_scorer",
                "encoder": self.delegate.encoder_name,
            },
            str(path),
        )

    def _clear_episode_buffers(self) -> None:
        self.saved_log_probs.clear()
        self.saved_entropies.clear()
        self.saved_selected_probs.clear()
        self.saved_rewards.clear()
        self.decisions = 0
        self.explored_actions = 0
        self.greedy_actions = 0
        self.sampled_actions = 0

    def _grad_norm(self) -> float:
        total = 0.0
        for param in self.model.parameters():
            if param.grad is not None:
                total += float(param.grad.detach().data.norm(2).cpu()) ** 2
        return math.sqrt(total)

    def _weight_delta_norm(self, before_params: list) -> float:
        total = 0.0
        for before, after in zip(before_params, (p for p in self.model.parameters() if p.requires_grad)):
            total += float((after.detach() - before).data.norm(2).cpu()) ** 2
        return math.sqrt(total)

    def _checkpoint_hidden_dim(self, path: str) -> int:
        checkpoint = torch.load(path, map_location="cpu")
        return int(checkpoint.get("hidden_dim", 128))


class RLTrainer:
    def __init__(self, config: RLTrainingConfig, reward: Optional[ShapedReward] = None):
        config.validate()
        self.config = config
        self.reward = reward if reward is not None else ShapedReward(config.reward_weights)
        self.policy = TrainableRankingPolicy(config)
        self.recent_rewards: deque[float] = deque(maxlen=config.recent_window)
        self.recent_wins: deque[float] = deque(maxlen=config.recent_window)

    def train(self) -> list[GameRolloutResult]:
        results: list[GameRolloutResult] = []
        for game_index in range(1, self.config.total_games + 1):
            epsilon = self.config.epsilon_for_game(game_index, training=True)
            result = self._run_one_game(game_index, training=True, epsilon=epsilon, rotate_positions=self.config.rotate_trained_agent_positions)
            update = self.policy.finish_game_update()
            checkpoint_path = None
            eval_result = None

            if game_index % self.config.checkpoint_every_games == 0:
                checkpoint_path = self._checkpoint_path(game_index)
                self.policy.save_checkpoint(checkpoint_path)

            if self.config.eval_enabled and self.config.eval_games > 0 and game_index % self.config.eval_every_games == 0:
                eval_result = self.evaluate(self.config.eval_games)

            result = GameRolloutResult(
                **{
                    **result.__dict__,
                    "update": update,
                    "epsilon": epsilon,
                    "temperature": self.config.temperature,
                    "learning_rate": self._learning_rate(),
                    "checkpoint_path": None if checkpoint_path is None else str(checkpoint_path),
                    "eval_win_rate": None if eval_result is None else eval_result.win_rate,
                    "eval_avg_reward": None if eval_result is None else eval_result.avg_reward,
                }
            )
            results.append(result)
            self._record_recent(result)
            self._write_log_row(result)
            self._print_game_summary(result)

        final_path = self.config.checkpoint_root() / f"checkpoint_agent_{self.config.trained_agent_id}_final.pt"
        self.policy.save_checkpoint(final_path)
        print(f"Final checkpoint saved: {final_path}", flush=True)
        return results

    def evaluate(self, games: int) -> EvaluationResult:
        if games <= 0:
            return EvaluationResult(games=0, win_rate=0.0, avg_reward=0.0)
        wins = 0
        rewards = []
        for game_index in range(1, games + 1):
            result = self._run_one_game(
                game_index,
                training=False,
                epsilon=0.0,
                rotate_positions=self.config.eval_rotate_positions,
            )
            wins += int(result.winner == result.rl_team)
            rewards.append(result.total_reward)
        return EvaluationResult(games=games, win_rate=wins / games, avg_reward=sum(rewards) / len(rewards))

    def _run_one_game(self, game_index: int, training: bool, epsilon: float, rotate_positions: bool) -> GameRolloutResult:
        engine = GameEngine(seed=self.config.seed + game_index * 9973 + (0 if training else 500000))
        state = engine.reset()
        rl_player = self._rl_player_for_game(game_index, rotate_positions=rotate_positions)
        rl_team = team_of(rl_player)
        agents = self._build_agents(game_index, rl_player)

        total_reward = 0.0
        capped = False
        turns = 0
        while state.round_stage != RoundStage.GAME_OVER and turns < self.config.max_turns:
            actor = state.play_current if state.round_stage == RoundStage.PLAY_LOOP else self._swap_actor(state)
            agent = agents[actor]
            action = agent.select_action(engine, state, training=training, epsilon=epsilon) if agent is self.policy else agent.select_action(engine, state)
            before = state
            state = engine.step(state, action)
            turns += 1

            breakdown = self.reward.score_transition(before, state, rl_team, trained_player=rl_player, action=action)
            total_reward += breakdown.total
            if actor == rl_player and before.round_stage == RoundStage.PLAY_LOOP and training:
                self.policy.add_reward(breakdown.total)

        if state.round_stage != RoundStage.GAME_OVER:
            capped = True
            terminal_reward = self.reward.terminal_score(state, rl_team)
            total_reward += terminal_reward
            if training:
                self.policy.add_reward(terminal_reward)

        score_a, score_b = safe_zone_score(state)
        return GameRolloutResult(
            game_index=game_index,
            rl_player=rl_player,
            rl_team=rl_team,
            winner=state.winner,
            turns=turns,
            capped=capped,
            score_a=score_a,
            score_b=score_b,
            total_reward=total_reward,
            epsilon=epsilon,
            temperature=self.config.temperature,
            learning_rate=self._learning_rate(),
        )

    def _build_agents(self, game_index: int, rl_player: PlayerId) -> dict[PlayerId, object]:
        slots = self._slots_for_game(rl_player)
        agents = {}
        for player in PlayerId:
            slot = slots[int(player)]
            seed = self.config.seed + game_index * 101 + int(player)
            if slot.policy == "rl_agent":
                agents[player] = self.policy
            elif slot.policy == "advanced_heuristic_agent":
                agents[player] = AdvancedHeuristicAgent(seed=seed)
            elif slot.policy == "heuristic_agent":
                agents[player] = HeuristicAgent(seed=seed)
            elif slot.policy == "monte_carlo_agent":
                # Monte Carlo opponents are intentionally available but expensive.
                # Start RL against heuristic opponents; use MC later for evaluation or fine-tuning.
                agents[player] = MonteCarloAgent(seed=seed, rollouts_per_action=2)
            elif slot.policy == "random_legal_agent":
                agents[player] = RandomLegalAgent(seed=seed)
            elif slot.policy in {"deep_learning_agent", "ranking_model_agent"}:
                weights_path = slot.weights_path or self.config.initial_model_path
                agents[player] = DeepLearningAgent(seed=seed, weights_path=weights_path, device=self.config.device, encoder=slot.encoder)
            else:
                raise ValueError(f"Unsupported player policy: {slot.policy}")
        return agents

    def _slots_for_game(self, rl_player: PlayerId) -> tuple[PlayerSlotConfig, PlayerSlotConfig, PlayerSlotConfig, PlayerSlotConfig]:
        if not self.config.rotate_trained_agent_positions:
            return self.config.players

        rl_slot = next(slot for slot in self.config.players if slot.policy == "rl_agent")
        fillers = [slot for slot in self.config.players if slot.policy != "rl_agent"]
        result: list[Optional[PlayerSlotConfig]] = [None, None, None, None]
        result[int(rl_player)] = rl_slot
        filler_iter = iter(fillers)
        for idx in range(4):
            if result[idx] is None:
                result[idx] = next(filler_iter)
        return tuple(slot for slot in result if slot is not None)  # type: ignore[return-value]

    def _rl_player_for_game(self, game_index: int, rotate_positions: bool) -> PlayerId:
        if rotate_positions:
            return PlayerId((game_index - 1) % 4)
        return PlayerId(self.config.trained_agent_id)

    def _swap_actor(self, state: GameState) -> PlayerId:
        from brandi_dog.engine.state import active_swap_player

        return active_swap_player(state)

    def _checkpoint_path(self, game_index: int) -> Path:
        return self.config.checkpoint_root() / f"checkpoint_agent_{self.config.trained_agent_id}_{game_index}.pt"

    def _record_recent(self, result: GameRolloutResult) -> None:
        self.recent_rewards.append(result.total_reward)
        self.recent_wins.append(1.0 if result.winner == result.rl_team else 0.0)

    def _recent_avg_reward(self) -> float:
        return sum(self.recent_rewards) / len(self.recent_rewards) if self.recent_rewards else 0.0

    def _recent_win_rate(self) -> float:
        return sum(self.recent_wins) / len(self.recent_wins) if self.recent_wins else 0.0

    def _learning_rate(self) -> float:
        return float(self.policy.optimizer.param_groups[0]["lr"])

    def _print_game_summary(self, result: GameRolloutResult) -> None:
        winner = result.winner.value if result.winner is not None else "None"
        capped = " capped" if result.capped else ""
        update = result.update
        loss = "None" if update.loss is None else f"{update.loss:.4f}"
        print(
            f"Game {result.game_index}: RL player={int(result.rl_player)} winner={winner} "
            f"score={result.score_a}-{result.score_b} turns={result.turns}{capped} "
            f"reward={result.total_reward:.2f} avg_reward={self._recent_avg_reward():.2f} "
            f"win_rate={self._recent_win_rate():.3f} loss={loss} entropy={update.entropy:.4f} "
            f"avg_p={update.avg_selected_action_prob:.4f} grad_norm={update.grad_norm:.3e} "
            f"weight_delta={update.weight_delta_norm:.3e} lr={result.learning_rate:.2e} "
            f"epsilon={result.epsilon:.4f} temp={result.temperature:.3f}",
            flush=True,
        )
        if update.warning:
            print(f"  warning: {update.warning}", flush=True)
        if result.checkpoint_path is not None:
            print(f"Checkpoint saved: {result.checkpoint_path}", flush=True)
        if result.eval_win_rate is not None:
            print(f"Evaluation: games={self.config.eval_games} win_rate={result.eval_win_rate:.3f} avg_reward={result.eval_avg_reward:.2f}", flush=True)

    def _log_payload(self, result: GameRolloutResult) -> dict:
        return {
            "game": result.game_index,
            "rl_player": int(result.rl_player),
            "rl_team": result.rl_team.value,
            "winner": None if result.winner is None else result.winner.value,
            "turns": result.turns,
            "capped": result.capped,
            "score_a": result.score_a,
            "score_b": result.score_b,
            "total_reward": result.total_reward,
            "avg_reward_recent": self._recent_avg_reward(),
            "win_rate_recent": self._recent_win_rate(),
            "policy_loss": result.update.loss,
            "entropy": result.update.entropy,
            "avg_selected_action_prob": result.update.avg_selected_action_prob,
            "grad_norm": result.update.grad_norm,
            "weight_delta_norm": result.update.weight_delta_norm,
            "learning_rate": result.learning_rate,
            "epsilon": result.epsilon,
            "temperature": result.temperature,
            "decisions": result.update.decisions,
            "explored_actions": result.update.explored_actions,
            "sampled_actions": result.update.sampled_actions,
            "greedy_actions": result.update.greedy_actions,
            "checkpoint_path": result.checkpoint_path,
            "eval_win_rate": result.eval_win_rate,
            "eval_avg_reward": result.eval_avg_reward,
            "warning": result.update.warning,
        }

    def _write_log_row(self, result: GameRolloutResult) -> None:
        if not self.config.output_log_path:
            return
        path = Path(self.config.output_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._log_payload(result)
        if self.config.log_format == "jsonl":
            with path.open("a") as fh:
                fh.write(json.dumps(payload, sort_keys=True) + "\n")
            return

        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(payload.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(payload)


def train_rl(config: RLTrainingConfig) -> list[GameRolloutResult]:
    return RLTrainer(config).train()
