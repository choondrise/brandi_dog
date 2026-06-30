from __future__ import annotations

import json
import os
import random
import threading
from pathlib import Path
from typing import Optional

from brandi_dog.agents.advanced_heuristic_agent import AdvancedHeuristicAgent
from brandi_dog.agents.supervised_learning.dataset_builder import build_decision_sample
from brandi_dog.agents.supervised_learning.serializers import serialize_action, serialize_card_map, serialize_state
from brandi_dog.engine.actions import Action, SwapCardAction
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PlayerId, RoundStage, active_swap_player, team_of


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class HumanDatasetLogger:
    """Append-only raw JSONL collector for human imitation datasets.

    The collector never keeps dataset rows in memory. Each human decision is
    serialized and flushed to the configured file immediately. PLAY_LOOP rows are
    compatible with the existing supervised-learning encoder pipeline. TEAM_SWAPS
    rows use the same top-level shape in a separate file for a future swap model.
    """

    def __init__(self) -> None:
        self.enabled = _env_enabled("BRANDI_COLLECT_HUMAN_DATASET")
        data_dir = Path(os.getenv("BRANDI_DATASET_DIR", "backend/data")).resolve()
        self.turn_path = Path(os.getenv("BRANDI_TURN_DATASET_PATH", str(data_dir / "human_turn_decisions.jsonl"))).resolve()
        self.swap_path = Path(os.getenv("BRANDI_SWAP_DATASET_PATH", str(data_dir / "human_swap_decisions.jsonl"))).resolve()
        self.alternatives_per_source = int(os.getenv("BRANDI_DATASET_CANDIDATE_ALTERNATIVES", "10"))
        self._lock = threading.Lock()
        self._fallback_rankers: dict[int, AdvancedHeuristicAgent] = {}

    def log_human_decision(
        self,
        *,
        game_id: str,
        turn_index: int,
        engine: GameEngine,
        state: GameState,
        legal_actions: tuple[Action, ...],
        chosen_action: Action,
        human_name: str,
        token_hint: str,
    ) -> None:
        if not self.enabled or len(legal_actions) <= 1:
            return
        if state.round_stage == RoundStage.PLAY_LOOP:
            sample = self._turn_sample(
                game_id=game_id,
                turn_index=turn_index,
                engine=engine,
                state=state,
                legal_actions=legal_actions,
                chosen_action=chosen_action,
                human_name=human_name,
                token_hint=token_hint,
            )
            self._append_jsonl(self.turn_path, sample)
            return
        if state.round_stage == RoundStage.TEAM_SWAPS and isinstance(chosen_action, SwapCardAction):
            sample = self._swap_sample(
                game_id=game_id,
                turn_index=turn_index,
                engine=engine,
                state=state,
                legal_actions=legal_actions,
                chosen_action=chosen_action,
                human_name=human_name,
                token_hint=token_hint,
            )
            self._append_jsonl(self.swap_path, sample)

    def _turn_sample(
        self,
        *,
        game_id: str,
        turn_index: int,
        engine: GameEngine,
        state: GameState,
        legal_actions: tuple[Action, ...],
        chosen_action: Action,
        human_name: str,
        token_hint: str,
    ) -> dict:
        seed = self._sample_seed(game_id, turn_index, int(state.play_current))
        sample = build_decision_sample(
            game_id=game_id,
            turn_index=turn_index,
            engine=engine,
            state=state,
            legal_actions=legal_actions,
            expert_action=chosen_action,
            expert_agent_name="HumanPlayer",
            rng=random.Random(seed),
            ranking_agent=None,
            fallback_ranking_agent=self._fallback_ranker(seed),
            alternatives_per_source=self.alternatives_per_source,
        )
        sample["human"] = {"name": human_name, "token_hint": token_hint}
        sample["source"] = "online_backend"
        return sample

    def _swap_sample(
        self,
        *,
        game_id: str,
        turn_index: int,
        engine: GameEngine,
        state: GameState,
        legal_actions: tuple[Action, ...],
        chosen_action: Action,
        human_name: str,
        token_hint: str,
    ) -> dict:
        player = active_swap_player(state)
        if chosen_action not in legal_actions:
            legal_actions = tuple(legal_actions) + (chosen_action,)
        action_ids = {action: f"a{index}" for index, action in enumerate(legal_actions)}
        candidate_action_ids = [action_ids[action] for action in legal_actions]
        return {
            "game_id": game_id,
            "turn_index": turn_index,
            "player": int(player),
            "team": team_of(player).value,
            "expert_agent": "HumanPlayer",
            "state": serialize_state(state),
            "cards_by_id": serialize_card_map(engine.cards_by_id),
            "legal_action_count": len(legal_actions),
            "serialized_action_scope": "candidate_actions",
            "legal_actions": [serialize_action(action, action_ids[action], engine, state) for action in legal_actions],
            "expert_action_id": action_ids[chosen_action],
            "candidate_action_ids": candidate_action_ids,
            "human": {"name": human_name, "token_hint": token_hint},
            "source": "online_backend",
            "dataset_kind": "team_swap",
        }

    def _append_jsonl(self, path: Path, sample: dict) -> None:
        line = json.dumps(sample, separators=(",", ":")) + "\n"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as output:
                output.write(line)
                output.flush()

    def _fallback_ranker(self, seed: int) -> AdvancedHeuristicAgent:
        ranker = self._fallback_rankers.get(seed)
        if ranker is None:
            ranker = AdvancedHeuristicAgent(seed=seed)
            self._fallback_rankers[seed] = ranker
            if len(self._fallback_rankers) > 32:
                oldest = next(iter(self._fallback_rankers))
                self._fallback_rankers.pop(oldest, None)
        return ranker

    @staticmethod
    def _sample_seed(game_id: str, turn_index: int, player: int) -> int:
        value = 17_029 + turn_index * 1_003 + player * 97
        for char in game_id:
            value = (value * 131 + ord(char)) % 2_147_483_647
        return value

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "turn_path": str(self.turn_path),
            "swap_path": str(self.swap_path),
            "candidate_alternatives_per_source": self.alternatives_per_source,
        }
