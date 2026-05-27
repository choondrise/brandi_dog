from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Iterable, Optional

from brandi_dog.agents.advanced_heuristic_agent import AdvancedHeuristicAgent
from brandi_dog.agents.monte_carlo_agent import MonteCarloAgent
from brandi_dog.engine.actions import Action
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    RoundStage,
    team_of,
)

from .dataset_types import DatasetBuildConfig, DatasetBuildResult
from .serializers import serialize_action, serialize_card_map, serialize_state


class ImitationDatasetBuilder:
    """Collect raw JSONL imitation samples from expert-played games.

    Example:
        python -m brandi_dog.agents.supervised_learning.dataset_builder \
            --games 50 --seed 7 --output data/imitation.jsonl
    """

    def __init__(self, expert_agent_factory=None):
        self.expert_agent_factory = expert_agent_factory

    def build(self, config: DatasetBuildConfig) -> DatasetBuildResult:
        output_path = Path(config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        samples_written = 0
        decisions_seen = 0
        games_played = 0

        mode = "a" if config.append else "w"
        with output_path.open(mode, encoding="utf-8") as output_file:
            for game_index in range(config.num_games):
                if config.max_samples is not None and samples_written >= config.max_samples:
                    break
                game_seed = config.seed + game_index
                engine = GameEngine(seed=game_seed)
                expert = self._build_expert_agent(config, game_seed)
                hard_negative_ranker = AdvancedHeuristicAgent(seed=game_seed + 50_000_000)
                state = engine.reset()
                turn_index = 0
                games_played += 1

                capped = False
                while state.round_stage != RoundStage.GAME_OVER:
                    if config.max_turns is not None and turn_index >= config.max_turns:
                        capped = True
                        break

                    action_to_play: Optional[Action] = None
                    if state.round_stage == RoundStage.PLAY_LOOP:
                        legal_actions = engine.legal_actions(state)
                        if len(legal_actions) > 1:
                            decisions_seen += 1
                            expert_action = expert.select_action(engine, state)
                            action_to_play = expert_action
                            sample = build_decision_sample(
                                game_id=game_index,
                                turn_index=turn_index,
                                engine=engine,
                                state=state,
                                legal_actions=legal_actions,
                                expert_action=expert_action,
                                expert_agent_name=config.expert_agent_name,
                                rng=random.Random(config.seed * 1_000_003 + game_index * 10_007 + turn_index),
                                ranking_agent=expert,
                                fallback_ranking_agent=hard_negative_ranker,
                                alternatives_per_source=config.candidate_alternatives_per_source,
                            )
                            output_file.write(json.dumps(sample, separators=(",", ":")) + "\n")
                            samples_written += 1
                            if config.max_samples is not None and samples_written >= config.max_samples:
                                break

                    action = action_to_play if action_to_play is not None else expert.select_action(engine, state)
                    state = engine.step(state, action)
                    turn_index += 1

                if config.print_progress:
                    prefix = f"Worker {config.worker_id}: " if config.worker_id is not None else ""
                    status = "capped" if capped else "finished"
                    print(
                        f"{prefix}Game {game_index + 1}/{config.num_games} {status} "
                        f"after {turn_index} turns; samples={samples_written}",
                        flush=True,
                    )

        return DatasetBuildResult(
            output_path=str(output_path),
            games_played=games_played,
            decisions_seen=decisions_seen,
            samples_written=samples_written,
        )

    def _build_expert_agent(self, config: DatasetBuildConfig, seed: int):
        if self.expert_agent_factory is not None:
            return self.expert_agent_factory(seed)
        if config.expert_agent_type == "advanced_heuristic":
            return AdvancedHeuristicAgent(seed=seed)
        if config.expert_agent_type == "monte_carlo":
            return MonteCarloAgent(
                seed=seed,
                top_k=config.monte_carlo_top_k,
                rollouts_per_action=config.monte_carlo_rollouts_per_action,
                rollout_policy=config.monte_carlo_rollout_policy,
                rollout_workers=config.monte_carlo_rollout_workers,
            )
        raise ValueError(f"Unsupported expert agent type: {config.expert_agent_type}")


def build_decision_sample(
    game_id: int,
    turn_index: int,
    engine: GameEngine,
    state: GameState,
    legal_actions: tuple[Action, ...],
    expert_action: Action,
    expert_agent_name: str,
    rng: random.Random,
    ranking_agent=None,
    fallback_ranking_agent=None,
    alternatives_per_source: int = 10,
) -> dict:
    player = state.play_current
    action_ids = {action: f"a{index}" for index, action in enumerate(legal_actions)}
    if expert_action not in action_ids:
        # The expert may internally simplify candidates. Keep the sample consistent by adding its selected action.
        legal_actions = tuple(legal_actions) + (expert_action,)
        action_ids = {action: f"a{index}" for index, action in enumerate(legal_actions)}

    candidate_actions = select_candidate_actions(
        engine=engine,
        state=state,
        legal_actions=legal_actions,
        expert_action=expert_action,
        rng=rng,
        ranking_agent=ranking_agent,
        fallback_ranking_agent=fallback_ranking_agent,
        alternatives_per_source=alternatives_per_source,
    )
    candidate_action_ids = [action_ids[action] for action in candidate_actions]

    return {
        "game_id": game_id,
        "turn_index": turn_index,
        "player": int(player),
        "team": team_of(player).value,
        "expert_agent": expert_agent_name,
        "state": serialize_state(state),
        "cards_by_id": serialize_card_map(engine.cards_by_id),
        "legal_action_count": len(legal_actions),
        "serialized_action_scope": "candidate_actions",
        "legal_actions": [serialize_action(action, action_ids[action], engine, state) for action in candidate_actions],
        "expert_action_id": action_ids[expert_action],
        "candidate_action_ids": candidate_action_ids,
    }


def select_candidate_actions(
    engine: GameEngine,
    state: GameState,
    legal_actions: tuple[Action, ...],
    expert_action: Action,
    rng: random.Random,
    ranking_agent=None,
    fallback_ranking_agent=None,
    alternatives_per_source: int = 10,
) -> list[Action]:
    alternatives_per_source = max(0, min(10, alternatives_per_source))
    non_expert = [action for action in legal_actions if action != expert_action]

    rank_actions = getattr(ranking_agent, "rank_actions", None)
    if not callable(rank_actions):
        rank_actions = getattr(fallback_ranking_agent, "rank_actions", None)
    if callable(rank_actions):
        ranked = [action for action in rank_actions(engine, state, tuple(non_expert)) if action in non_expert]
    else:
        ranked = sorted(non_expert, key=repr)

    ranked_choices = ranked[:alternatives_per_source]
    ranked_set = set(ranked_choices)
    random_pool = [action for action in non_expert if action not in ranked_set]
    random_choices = rng.sample(random_pool, k=min(alternatives_per_source, len(random_pool))) if random_pool else []

    selected: list[Action] = [expert_action]
    for action in ranked_choices + random_choices:
        if action not in selected:
            selected.append(action)
    return selected


def build_dataset(
    output_path: str,
    num_games: int,
    seed: int = 0,
    max_turns: Optional[int] = None,
    max_samples: Optional[int] = None,
    candidate_alternatives_per_source: int = 10,
    append: bool = False,
    print_progress: bool = True,
    worker_id: Optional[int] = None,
    expert_agent_type: str = "advanced_heuristic",
    monte_carlo_top_k: int = 3,
    monte_carlo_rollouts_per_action: int = 2,
    monte_carlo_rollout_policy: str = "advanced_heuristic",
    monte_carlo_rollout_workers: int = 1,
) -> DatasetBuildResult:
    config = DatasetBuildConfig(
        output_path=output_path,
        num_games=num_games,
        seed=seed,
        max_turns=max_turns,
        max_samples=max_samples,
        candidate_alternatives_per_source=candidate_alternatives_per_source,
        append=append,
        print_progress=print_progress,
        worker_id=worker_id,
        expert_agent_type=expert_agent_type,
        expert_agent_name=_expert_agent_name(expert_agent_type),
        monte_carlo_top_k=monte_carlo_top_k,
        monte_carlo_rollouts_per_action=monte_carlo_rollouts_per_action,
        monte_carlo_rollout_policy=monte_carlo_rollout_policy,
        monte_carlo_rollout_workers=monte_carlo_rollout_workers,
    )
    return ImitationDatasetBuilder().build(config)


def _expert_agent_name(expert_agent_type: str) -> str:
    if expert_agent_type == "advanced_heuristic":
        return "AdvancedHeuristicAgent"
    if expert_agent_type == "monte_carlo":
        return "MonteCarloAgent"
    return expert_agent_type


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Collect raw JSONL imitation-learning samples.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--candidate-alternatives", type=int, default=10)
    parser.add_argument("--expert-agent", choices=("advanced_heuristic", "monte_carlo"), default="advanced_heuristic")
    parser.add_argument("--monte-carlo-top-k", type=int, default=3)
    parser.add_argument("--monte-carlo-rollouts-per-action", type=int, default=2)
    parser.add_argument("--monte-carlo-rollout-policy", choices=("advanced_heuristic", "heuristic", "random"), default="advanced_heuristic")
    parser.add_argument("--monte-carlo-rollout-workers", type=int, default=1)
    parser.add_argument("--append", action="store_true", help="Append samples to output instead of overwriting it.")
    parser.add_argument("--quiet", action="store_true", help="Do not print per-game progress.")
    args = parser.parse_args(argv)
    result = build_dataset(
        output_path=args.output,
        num_games=args.games,
        seed=args.seed,
        max_turns=args.max_turns,
        max_samples=args.max_samples,
        candidate_alternatives_per_source=args.candidate_alternatives,
        append=args.append,
        print_progress=not args.quiet,
        expert_agent_type=args.expert_agent,
        monte_carlo_top_k=args.monte_carlo_top_k,
        monte_carlo_rollouts_per_action=args.monte_carlo_rollouts_per_action,
        monte_carlo_rollout_policy=args.monte_carlo_rollout_policy,
        monte_carlo_rollout_workers=args.monte_carlo_rollout_workers,
    )
    print(result)


if __name__ == "__main__":
    main()
