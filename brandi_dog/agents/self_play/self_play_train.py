from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import random
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from brandi_dog.agents import AdvancedHeuristicAgent, HeuristicAgent, MonteCarloAgent
from brandi_dog.agents.deep_learning_agent import DeepLearningAgent
from brandi_dog.agents.reinforcement_learning.config import PlayerSlotConfig, RLTrainingConfig, RewardWeights
from brandi_dog.agents.reinforcement_learning.rl_trainer import TrainableRankingPolicy
from brandi_dog.agents.reinforcement_learning.rollout import PolicyUpdateDiagnostics, safe_zone_score
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import PlayerId, RoundStage, Team, active_swap_player, team_of


@dataclass(frozen=True)
class OpponentSpec:
    name: str
    kind: str
    weight: float
    checkpoint_path: Optional[str] = None


@dataclass(frozen=True)
class GameOutcome:
    winner: Optional[Team]
    trained_team: Team
    opponent: str
    turns: int
    capped: bool
    score_a: int
    score_b: int
    reward: float
    update: PolicyUpdateDiagnostics = PolicyUpdateDiagnostics()


@dataclass(frozen=True)
class EvaluationSummary:
    opponent: str
    games: int
    winrate: float
    score_a_avg: float
    score_b_avg: float


@dataclass(frozen=True)
class IterationLog:
    iteration: int
    candidate_checkpoint: str
    champion_checkpoint: str
    train_games: int
    train_winrate: float
    capped_games: int
    average_reward: float
    opponent_cycle: str
    winrate_vs_heuristic: float
    winrate_vs_ranking_model_v2: float
    winrate_vs_old_champion: float
    winrate_vs_monte_carlo: Optional[float]
    promoted: bool
    reason: str


def load_agent_from_checkpoint(path: str, seed: int, device: str = "auto", encoder: str = "v2") -> DeepLearningAgent:
    return DeepLearningAgent(seed=seed, weights_path=path, device=device, encoder=encoder)


def build_opponent_pool(
    champion_checkpoint: str,
    older_checkpoints: list[str],
    ranking_checkpoint: str,
) -> list[OpponentSpec]:
    pool = [
        OpponentSpec("current_champion", "deep_learning", 0.50, champion_checkpoint),
        OpponentSpec("heuristic", "heuristic", 0.15),
        OpponentSpec("ranking_model_v2", "deep_learning", 0.10, ranking_checkpoint),
    ]
    if older_checkpoints:
        per_old_checkpoint = 0.25 / len(older_checkpoints)
        pool.extend(
            OpponentSpec(f"older_champion_{index}", "deep_learning", per_old_checkpoint, checkpoint)
            for index, checkpoint in enumerate(older_checkpoints, start=1)
        )
    else:
        # No older checkpoints yet; give that mass to current champion self-play.
        pool[0] = OpponentSpec("current_champion", "deep_learning", 0.75, champion_checkpoint)
    return pool


def sample_opponent(pool: list[OpponentSpec], rng: random.Random) -> OpponentSpec:
    total = sum(max(0.0, item.weight) for item in pool)
    if total <= 0:
        raise ValueError("Opponent pool has no positive weights")
    draw = rng.random() * total
    running = 0.0
    for item in pool:
        running += max(0.0, item.weight)
        if draw <= running:
            return item
    return pool[-1]


def build_agent_from_spec(spec: OpponentSpec, seed: int, device: str, encoder: str):
    if spec.kind == "deep_learning":
        if spec.checkpoint_path is None:
            raise ValueError(f"Opponent {spec.name} requires checkpoint_path")
        return load_agent_from_checkpoint(spec.checkpoint_path, seed=seed, device=device, encoder=encoder)
    if spec.kind == "heuristic":
        return HeuristicAgent(seed=seed)
    if spec.kind == "advanced_heuristic":
        return AdvancedHeuristicAgent(seed=seed)
    if spec.kind == "monte_carlo":
        return MonteCarloAgent(seed=seed, rollout_workers=1)
    raise ValueError(f"Unsupported opponent kind: {spec.kind}")


def train_chunk(
    policy: TrainableRankingPolicy,
    opponent_pool: list[OpponentSpec],
    games: int,
    seed: int,
    epsilon: float,
    max_turns: int,
    device: str,
    encoder: str,
) -> list[GameOutcome]:
    outcomes: list[GameOutcome] = []
    for game_index in range(games):
        opponent = opponent_pool[game_index % len(opponent_pool)]
        trained_team = Team.A if game_index % 2 == 0 else Team.B
        outcome = _run_training_game(
            policy=policy,
            opponent=opponent,
            trained_team=trained_team,
            seed=seed + game_index,
            epsilon=epsilon,
            max_turns=max_turns,
            device=device,
            encoder=encoder,
        )
        outcomes.append(outcome)
        if (game_index + 1) % 100 == 0 or game_index + 1 == games:
            print(
                f"  train game {game_index + 1}/{games}: opponent={opponent.name} "
                f"trained_team={trained_team.value} winner={None if outcome.winner is None else outcome.winner.value} "
                f"reward={outcome.reward:.1f} loss={outcome.update.loss}",
                flush=True,
            )
    return outcomes


def _run_training_game(
    policy: TrainableRankingPolicy,
    opponent: OpponentSpec,
    trained_team: Team,
    seed: int,
    epsilon: float,
    max_turns: int,
    device: str,
    encoder: str,
) -> GameOutcome:
    engine = GameEngine(seed=seed)
    state = engine.reset()
    opponent_1 = build_agent_from_spec(opponent, seed=seed * 17 + 1, device=device, encoder=encoder)
    opponent_2 = build_agent_from_spec(opponent, seed=seed * 17 + 2, device=device, encoder=encoder)
    if trained_team == Team.A:
        agents = {
            PlayerId.A1: policy,
            PlayerId.A2: policy,
            PlayerId.B1: opponent_1,
            PlayerId.B2: opponent_2,
        }
    else:
        agents = {
            PlayerId.A1: opponent_1,
            PlayerId.A2: opponent_2,
            PlayerId.B1: policy,
            PlayerId.B2: policy,
        }
    turns = 0
    while state.round_stage != RoundStage.GAME_OVER and turns < max_turns:
        actor = active_swap_player(state) if state.round_stage == RoundStage.TEAM_SWAPS else state.play_current
        agent = agents[actor]
        if agent is policy:
            action = policy.select_action(engine, state, training=True, epsilon=epsilon)
        else:
            action = agent.select_action(engine, state)
        state = engine.step(state, action)
        turns += 1

    capped = state.round_stage != RoundStage.GAME_OVER
    winner = state.winner
    reward = 100.0 if winner == trained_team else -100.0
    if policy.saved_log_probs:
        policy.saved_rewards = [0.0] * max(0, len(policy.saved_log_probs) - 1) + [reward]
    update = policy.finish_game_update()
    score_a, score_b = safe_zone_score(state)
    return GameOutcome(
        winner=winner,
        trained_team=trained_team,
        opponent=opponent.name,
        turns=turns,
        capped=capped,
        score_a=score_a,
        score_b=score_b,
        reward=reward,
        update=update,
    )


def evaluate_agent(
    candidate_checkpoint: str,
    opponent: OpponentSpec,
    games: int,
    seed: int,
    max_turns: int,
    device: str,
    encoder: str,
    workers: int = 1,
) -> EvaluationSummary:
    jobs = [(candidate_checkpoint, opponent, seed + game_index, max_turns, device, encoder) for game_index in range(games)]
    if workers > 1 and len(jobs) > 1:
        context = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=context) as executor:
            outcomes = list(executor.map(_evaluate_game_worker, jobs))
    else:
        outcomes = [_evaluate_game_worker(job) for job in jobs]

    wins = sum(1 for winner, _, _ in outcomes if winner == Team.A)
    score_a_total = sum(score_a for _, score_a, _ in outcomes)
    score_b_total = sum(score_b for _, _, score_b in outcomes)
    return EvaluationSummary(
        opponent=opponent.name,
        games=games,
        winrate=wins / games if games else 0.0,
        score_a_avg=score_a_total / games if games else 0.0,
        score_b_avg=score_b_total / games if games else 0.0,
    )


def _evaluate_game_worker(job) -> tuple[Optional[Team], int, int]:
    candidate_checkpoint, opponent, seed, max_turns, device, encoder = job
    engine = GameEngine(seed=seed)
    state = engine.reset()
    candidate_a1 = load_agent_from_checkpoint(candidate_checkpoint, seed=seed * 31 + 1, device=device, encoder=encoder)
    candidate_a2 = load_agent_from_checkpoint(candidate_checkpoint, seed=seed * 31 + 2, device=device, encoder=encoder)
    opponent_b1 = build_agent_from_spec(opponent, seed=seed * 31 + 3, device=device, encoder=encoder)
    opponent_b2 = build_agent_from_spec(opponent, seed=seed * 31 + 4, device=device, encoder=encoder)
    agents = {
        PlayerId.A1: candidate_a1,
        PlayerId.A2: candidate_a2,
        PlayerId.B1: opponent_b1,
        PlayerId.B2: opponent_b2,
    }
    turns = 0
    while state.round_stage != RoundStage.GAME_OVER and turns < max_turns:
        actor = active_swap_player(state) if state.round_stage == RoundStage.TEAM_SWAPS else state.play_current
        state = engine.step(state, agents[actor].select_action(engine, state))
        turns += 1
    score_a, score_b = safe_zone_score(state)
    return state.winner, score_a, score_b


def should_promote(
    vs_champion: EvaluationSummary,
    vs_heuristic: EvaluationSummary,
    promote_threshold: float,
    min_heuristic_winrate: float,
) -> tuple[bool, str]:
    if vs_champion.winrate < promote_threshold:
        return False, f"candidate winrate vs old champion {vs_champion.winrate:.3f} < threshold {promote_threshold:.3f}"
    if vs_heuristic.winrate < min_heuristic_winrate:
        return False, f"candidate heuristic winrate {vs_heuristic.winrate:.3f} < minimum {min_heuristic_winrate:.3f}"
    return True, "candidate passed champion and heuristic gates"


def save_training_log(log_path: Path, row: IterationLog) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists() or log_path.stat().st_size == 0
    with log_path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.__dict__.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row.__dict__)
    json_path = log_path.with_suffix(".jsonl")
    with json_path.open("a") as fh:
        fh.write(json.dumps(row.__dict__, sort_keys=True) + "\n")


def copy_promoted_champion(candidate_path: Path, champions_dir: Path, iteration: int) -> Path:
    champions_dir.mkdir(parents=True, exist_ok=True)
    promoted_path = champions_dir / f"champion_iter_{iteration}.pt"
    shutil.copy2(candidate_path, promoted_path)
    latest_path = champions_dir / "champion_latest.pt"
    shutil.copy2(candidate_path, latest_path)
    return promoted_path


def make_policy(checkpoint_path: str, output_dir: Path, args) -> TrainableRankingPolicy:
    config = RLTrainingConfig(
        initial_model_path=checkpoint_path,
        total_games=args.train_games_per_iteration,
        checkpoint_every_games=args.train_games_per_iteration,
        checkpoint_dir=str(output_dir / "unused_rltrainer_checkpoints"),
        trained_agent_id=0,
        seed=args.seed,
        learning_rate=args.lr,
        exploration_rate=args.epsilon,
        min_epsilon=0.0,
        temperature=args.temperature,
        gamma=args.gamma,
        entropy_bonus=args.entropy_bonus_coef,
        normalize_returns=True,
        max_turns=args.max_turns,
        rotate_trained_agent_positions=True,
        device=args.device,
        encoder=args.encoder,
        reward_weights=RewardWeights(win_reward=100.0, loss_penalty=-100.0),
        players=(
            PlayerSlotConfig("rl_agent"),
            PlayerSlotConfig("heuristic_agent"),
            PlayerSlotConfig("rl_agent"),
            PlayerSlotConfig("heuristic_agent"),
        ),
    )
    return TrainableRankingPolicy(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="League/self-play RL training from an existing champion checkpoint.")
    parser.add_argument("--champion-checkpoint", required=True)
    parser.add_argument("--ranking-checkpoint", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--train-games-per-iteration", type=int, default=2000)
    parser.add_argument("--eval-games", type=int, default=300)
    parser.add_argument("--mc-eval-games", type=int, default=50)
    parser.add_argument("--promote-threshold", type=float, default=0.53)
    parser.add_argument("--min-heuristic-winrate", type=float, default=0.60)
    parser.add_argument("--epsilon", type=float, default=0.10)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--entropy-bonus-coef", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=1000)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--eval-device", default="cpu", help="Device used by parallel evaluation workers. Defaults to cpu to avoid CUDA OOM.")
    parser.add_argument("--encoder", choices=("auto", "v1", "v2"), default="v2")
    parser.add_argument("--older-checkpoints", nargs="*", default=[])
    parser.add_argument("--use-mc-eval", action="store_true")
    parser.add_argument("--eval-workers", type=int, default=1)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    checkpoint_dir = output_dir / "checkpoints"
    candidate_dir = checkpoint_dir / "candidates"
    champion_dir = checkpoint_dir / "champions"
    log_path = output_dir / "self_play_log.csv"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    champion_dir.mkdir(parents=True, exist_ok=True)

    champion_checkpoint = str(Path(args.champion_checkpoint).resolve())
    ranking_checkpoint = str(Path(args.ranking_checkpoint).resolve())
    older_checkpoints = [str(Path(path).resolve()) for path in args.older_checkpoints]
    shutil.copy2(champion_checkpoint, champion_dir / "champion_start.pt")

    for iteration in range(1, args.iterations + 1):
        print(f"Iteration {iteration}/{args.iterations}: champion={champion_checkpoint}", flush=True)
        opponent_pool = build_opponent_pool(champion_checkpoint, older_checkpoints, ranking_checkpoint)
        policy = make_policy(champion_checkpoint, output_dir, args)
        train_results = train_chunk(
            policy=policy,
            opponent_pool=opponent_pool,
            games=args.train_games_per_iteration,
            seed=args.seed + iteration * 1_000_000,
            epsilon=args.epsilon,
            max_turns=args.max_turns,
            device=args.device,
            encoder=args.encoder,
        )

        candidate_path = candidate_dir / f"candidate_iter_{iteration}.pt"
        policy.save_checkpoint(candidate_path)
        print(f"Saved candidate: {candidate_path}", flush=True)

        heuristic_eval = evaluate_agent(
            str(candidate_path),
            OpponentSpec("heuristic", "heuristic", 1.0),
            args.eval_games,
            args.seed + iteration * 10_000 + 1,
            args.max_turns,
            args.eval_device,
            args.encoder,
            args.eval_workers,
        )
        ranking_eval = evaluate_agent(
            str(candidate_path),
            OpponentSpec("ranking_model_v2", "deep_learning", 1.0, ranking_checkpoint),
            args.eval_games,
            args.seed + iteration * 10_000 + 2,
            args.max_turns,
            args.eval_device,
            args.encoder,
            args.eval_workers,
        )
        champion_eval = evaluate_agent(
            str(candidate_path),
            OpponentSpec("old_champion", "deep_learning", 1.0, champion_checkpoint),
            args.eval_games,
            args.seed + iteration * 10_000 + 3,
            args.max_turns,
            args.eval_device,
            args.encoder,
            args.eval_workers,
        )
        mc_eval = None
        if args.use_mc_eval:
            mc_eval = evaluate_agent(
                str(candidate_path),
                OpponentSpec("monte_carlo", "monte_carlo", 1.0),
                args.mc_eval_games,
                args.seed + iteration * 10_000 + 4,
                args.max_turns,
                args.eval_device,
                args.encoder,
                args.eval_workers,
            )

        promoted, reason = should_promote(champion_eval, heuristic_eval, args.promote_threshold, args.min_heuristic_winrate)
        if promoted:
            promoted_path = copy_promoted_champion(candidate_path, champion_dir, iteration)
            older_checkpoints.append(champion_checkpoint)
            champion_checkpoint = str(promoted_path.resolve())

        wins = sum(1 for result in train_results if result.winner == result.trained_team)
        capped_games = sum(1 for result in train_results if result.capped)
        average_reward = sum(result.reward for result in train_results) / max(1, len(train_results))
        opponent_cycle = ",".join(opponent.name for opponent in opponent_pool)
        row = IterationLog(
            iteration=iteration,
            candidate_checkpoint=str(candidate_path),
            champion_checkpoint=champion_checkpoint,
            train_games=len(train_results),
            train_winrate=wins / max(1, len(train_results)),
            capped_games=capped_games,
            average_reward=average_reward,
            opponent_cycle=opponent_cycle,
            winrate_vs_heuristic=heuristic_eval.winrate,
            winrate_vs_ranking_model_v2=ranking_eval.winrate,
            winrate_vs_old_champion=champion_eval.winrate,
            winrate_vs_monte_carlo=None if mc_eval is None else mc_eval.winrate,
            promoted=promoted,
            reason=reason,
        )
        save_training_log(log_path, row)
        print(
            f"Evaluation iter {iteration}: train_winrate={row.train_winrate:.3f}, "
            f"heuristic={heuristic_eval.winrate:.3f}, ranking_v2={ranking_eval.winrate:.3f}, "
            f"old_champion={champion_eval.winrate:.3f}, "
            f"mc={None if mc_eval is None else round(mc_eval.winrate, 3)}, "
            f"promoted={promoted}: {reason}",
            flush=True,
        )


if __name__ == "__main__":
    main()
