from __future__ import annotations

from pathlib import Path
from typing import Optional

from brandi_dog.agents.advanced_heuristic_agent import AdvancedHeuristicAgent
from brandi_dog.agents.heuristic_agent import HeuristicAgent
from brandi_dog.engine import rules as engine_rules
from brandi_dog.engine.actions import (
    Action,
    DiscardHandAction,
    PlayEnterAction,
    PlayJackSwapAction,
    PlaySevenSplitAction,
    PlayStepCardAction,
    SkipTurnAction,
    SwapCardAction,
)
from brandi_dog.engine.board import MAIN_TRACK_LENGTH
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    PositionKind,
    RoundStage,
    active_swap_player,
    get_pawn_position,
    team_of,
)

from brandi_dog.agents.supervised_learning.encoders import (
    ACTION_TYPES,
    RANKS,
    PartialInfoPerspectiveEncoderV2,
    PartialInformationEncoder,
)
from brandi_dog.agents.supervised_learning.model import RankingScorer, torch
from brandi_dog.agents.supervised_learning.serializers import serialize_card_map, serialize_state


class DeepLearningAgent:
    """Agent that scores candidate actions with a trained imitation ranking model.

    The model is only trained for PLAY_LOOP decisions. Swap and other non-play
    phases are delegated to HeuristicAgent.
    """

    def __init__(
        self,
        seed: Optional[int],
        weights_path: str,
        device: str = "auto",
        fallback_agent: Optional[HeuristicAgent] = None,
        candidate_agent: Optional[AdvancedHeuristicAgent] = None,
        encoder: str = "auto",
    ):
        if torch is None:
            raise ImportError("PyTorch is required to use DeepLearningAgent")
        self.weights_path = Path(weights_path)
        self.device = self._select_device(device)
        self.fallback_agent = fallback_agent if fallback_agent is not None else HeuristicAgent(seed=seed)
        self.candidate_agent = candidate_agent if candidate_agent is not None else AdvancedHeuristicAgent(seed=seed)

        checkpoint = torch.load(str(self.weights_path), map_location=self.device)
        self.feature_dim = int(checkpoint["action_dim"])
        self.encoder_name = self._resolve_encoder_name(encoder, self.feature_dim)
        self.encoder = PartialInfoPerspectiveEncoderV2() if self.encoder_name == "v2" else PartialInformationEncoder()
        hidden_dim = int(checkpoint.get("hidden_dim", 128))
        self.model = RankingScorer(state_dim=0, action_dim=self.feature_dim, hidden_dim=hidden_dim).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()
        self._empty_state = torch.empty(0, dtype=torch.float32, device=self.device)

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        if state.round_stage != RoundStage.PLAY_LOOP:
            return self.fallback_agent.select_action(engine, state)

        actions = self._candidate_actions(engine, state)
        if not actions:
            return self.fallback_agent.select_action(engine, state)
        if len(actions) == 1:
            return actions[0]

        features = self._encode_live_actions(engine, state, actions)
        action_tensor = torch.tensor(features, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            scores = self.model(self._empty_state, action_tensor)
        best_index = int(torch.argmax(scores).detach().cpu())
        return actions[best_index]

    def _candidate_actions(self, engine: GameEngine, state: GameState) -> tuple[Action, ...]:
        # Use the same kind of candidate reduction that made the expert fast, especially for large seven turns.
        candidate_actions = self.candidate_agent.candidate_actions(engine, state)
        if candidate_actions:
            return candidate_actions
        return engine.legal_actions(state)

    def _encode_live_actions(self, engine: GameEngine, state: GameState, actions: tuple[Action, ...]) -> list[list[float]]:
        active_player = int(state.play_current)
        state_payload = serialize_state(state)
        state_features = self.encoder.encode_state(
            state_payload,
            active_player=active_player,
            cards_by_id=serialize_card_map(engine.cards_by_id),
        )
        encoded: list[list[float]] = []
        for action in actions:
            if self.encoder_name == "v2":
                action_payload = self._live_action_payload(engine, state, action)
                feature_vector = state_features + self.encoder.encode_action(action_payload, state=state_payload, active_player=active_player)
            else:
                feature_vector = state_features + self._encode_live_action(engine, state, action, active_player)
            if len(feature_vector) != self.feature_dim:
                raise ValueError(
                    f"Feature dimension mismatch: model expects {self.feature_dim}, encoder produced {len(feature_vector)}"
                )
            encoded.append(feature_vector)
        return encoded


    def _live_action_payload(self, engine: GameEngine, state: GameState, action: Action) -> dict:
        next_state = self._try_apply_action(engine, state, action)
        moved_pawns = self._moved_pawns(action)
        card_id = getattr(action, "card_id", None)
        card = engine.cards_by_id.get(card_id) if card_id is not None else None
        return {
            "type": type(action).__name__,
            "card_id": card_id,
            "card": None if card is None else {"id": card.card_id, "rank": card.rank.value},
            "pawns": [self._pawn_payload(pawn) for pawn in moved_pawns],
            "from_positions": [self._position_payload(get_pawn_position(state, pawn)) for pawn in moved_pawns],
            "to_positions": [self._position_payload(get_pawn_position(next_state, pawn)) for pawn in moved_pawns] if next_state is not None else [],
            "steps": self._action_steps(action),
            "flags": self._action_flags(state, next_state, action, moved_pawns),
        }

    def _pawn_payload(self, pawn: PawnRef) -> dict[str, int]:
        return {"owner": int(pawn.owner), "number": pawn.number, "index": int(pawn.owner) * 4 + pawn.number}

    def _position_payload(self, position) -> dict:
        return {"kind": position.kind.value, "index": position.index}

    def _encode_live_action(
        self,
        engine: GameEngine,
        state: GameState,
        action: Action,
        active_player: int,
    ) -> list[float]:
        features: list[float] = []
        action_type = type(action).__name__
        features.extend(self._one_hot(ACTION_TYPES.index(action_type) if action_type in ACTION_TYPES else -1, len(ACTION_TYPES)))

        rank = self._action_rank(engine, action)
        features.extend(self._one_hot(RANKS.index(rank) if rank in RANKS else -1, len(RANKS)))

        next_state = self._try_apply_action(engine, state, action)
        moved_pawns = self._moved_pawns(action)
        flags = self._action_flags(state, next_state, action, moved_pawns)
        for flag in ("is_capture", "is_discard", "is_noop", "enters_from_base", "enters_safe_zone_or_home"):
            features.append(1.0 if flags[flag] else 0.0)

        steps = self._action_steps(action)
        features.append(float(sum(steps)) / 13.0 if steps else 0.0)
        features.append(float(len(steps)) / 7.0)

        features.append(float(len(moved_pawns)) / 8.0)
        relation_flags = [0.0, 0.0, 0.0]
        for pawn in moved_pawns:
            relation = self._owner_relation(int(pawn.owner), active_player)
            if 0 <= relation < len(relation_flags):
                relation_flags[relation] = 1.0
        features.extend(relation_flags)

        progress_delta = 0.0
        if next_state is not None:
            for pawn in moved_pawns:
                progress_delta += self._pawn_progress_feature(get_pawn_position(next_state, pawn)) - self._pawn_progress_feature(
                    get_pawn_position(state, pawn)
                )
        features.append(progress_delta / max(1.0, float(len(moved_pawns))))
        return features

    def _action_flags(
        self,
        state: GameState,
        next_state: Optional[GameState],
        action: Action,
        moved_pawns: tuple[PawnRef, ...],
    ) -> dict[str, bool]:
        return {
            "is_capture": self._is_capture(state, next_state, action) if next_state is not None else False,
            "is_discard": isinstance(action, DiscardHandAction),
            "is_noop": isinstance(action, SkipTurnAction),
            "enters_from_base": isinstance(action, PlayEnterAction),
            "enters_safe_zone_or_home": self._enters_safe_zone(state, next_state, moved_pawns) if next_state is not None else False,
        }

    def _try_apply_action(self, engine: GameEngine, state: GameState, action: Action) -> Optional[GameState]:
        try:
            if isinstance(action, SwapCardAction):
                return engine_rules._apply_swap_action(state, action)
            if isinstance(action, SkipTurnAction):
                return engine_rules.apply_action(state, action, engine.cards_by_id)
            if isinstance(action, DiscardHandAction):
                return engine_rules._apply_discard_hand_action(state, action)
            if isinstance(action, PlayEnterAction):
                return engine_rules._apply_play_enter_action(state, action, engine.cards_by_id)
            if isinstance(action, PlayStepCardAction):
                return engine_rules._apply_play_step_action(state, action, engine.cards_by_id)
            if isinstance(action, PlayJackSwapAction):
                return engine_rules._apply_play_jack_action(state, action, engine.cards_by_id)
            if isinstance(action, PlaySevenSplitAction):
                return engine_rules._apply_play_seven_action(state, action, engine.cards_by_id)
            return engine_rules.apply_action(state, action, engine.cards_by_id)
        except ValueError:
            return None

    def _is_capture(self, before: GameState, after: Optional[GameState], action: Action) -> bool:
        if after is None:
            return False
        actor = getattr(action, "player", None)
        if actor is None:
            return False
        actor_team = team_of(actor)
        for index, (before_pos, after_pos) in enumerate(zip(before.pawn_positions, after.pawn_positions)):
            owner = PlayerId(index // 4)
            if team_of(owner) == actor_team:
                continue
            if before_pos.kind != PositionKind.BASE and after_pos.kind == PositionKind.BASE:
                return True
        return False

    def _enters_safe_zone(self, before: GameState, after: Optional[GameState], pawns: tuple[PawnRef, ...]) -> bool:
        if after is None:
            return False
        for pawn in pawns:
            before_pos = get_pawn_position(before, pawn)
            after_pos = get_pawn_position(after, pawn)
            if before_pos.kind != PositionKind.SAFE and after_pos.kind == PositionKind.SAFE:
                return True
        return False

    def _moved_pawns(self, action: Action) -> tuple[PawnRef, ...]:
        if isinstance(action, PlayEnterAction):
            return (action.pawn,)
        if isinstance(action, PlayStepCardAction):
            return (action.pawn,)
        if isinstance(action, PlaySevenSplitAction):
            return tuple(move.pawn for move in action.moves)
        if isinstance(action, PlayJackSwapAction):
            return (action.source, action.target)
        return ()

    def _action_steps(self, action: Action) -> list[int]:
        if isinstance(action, PlayStepCardAction):
            return [action.steps]
        if isinstance(action, PlaySevenSplitAction):
            return [move.steps for move in action.moves]
        return []

    def _action_rank(self, engine: GameEngine, action: Action) -> Optional[str]:
        card_id = getattr(action, "card_id", None)
        if card_id is None or card_id not in engine.cards_by_id:
            return None
        return engine.cards_by_id[card_id].rank.value

    def _owner_relation(self, owner: int, active_player: int) -> int:
        if owner == active_player:
            return 0
        if owner == self._partner(active_player):
            return 1
        return 2

    def _partner(self, player: int) -> int:
        return {0: 2, 2: 0, 1: 3, 3: 1}.get(player, 0)

    def _pawn_progress_feature(self, position) -> float:
        if position.kind == PositionKind.BASE:
            return 0.0
        if position.kind == PositionKind.SAFE:
            return 1.0 + (0.0 if position.index is None else float(position.index) / 4.0)
        if position.kind == PositionKind.TRACK:
            return 0.25 + (0.0 if position.index is None else float(position.index) / float(MAIN_TRACK_LENGTH))
        return 0.0

    def _one_hot(self, index: int, size: int) -> list[float]:
        return [1.0 if idx == index else 0.0 for idx in range(size)]


    def _resolve_encoder_name(self, encoder: str, feature_dim: int) -> str:
        if encoder not in {"auto", "v1", "v2"}:
            raise ValueError("encoder must be one of: auto, v1, v2")
        if encoder != "auto":
            return encoder
        # Current known dimensions: V1=214, V2=270. Keep this explicit so
        # loading the wrong encoder fails early instead of producing bad actions.
        if feature_dim == 270:
            return "v2"
        return "v1"

    def _select_device(self, device: str):
        if torch is None:
            raise ImportError("PyTorch is required to use DeepLearningAgent")
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        requested = torch.device(device)
        if requested.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is False")
        return requested
