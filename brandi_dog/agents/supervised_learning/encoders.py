from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Optional

from brandi_dog.engine.board import ENTRY_INDEX_BY_PLAYER, MAIN_TRACK_LENGTH, entry_index

from .dataset_types import EncodedSample

POSITION_KINDS = ("BASE", "TRACK", "SAFE")
ACTION_TYPES = (
    "SwapCardAction",
    "PlayStepCardAction",
    "PlayEnterAction",
    "PlaySevenSplitAction",
    "PlayJackSwapAction",
    "DiscardHandAction",
    "SkipTurnAction",
)
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "JK")
RELATIONS = ("active", "partner", "opponent")


@dataclass(frozen=True)
class EncodingSummary:
    raw_samples_read: int
    encoded_samples_written: int
    skipped_samples: int
    feature_dim: Optional[int]
    average_candidates: float


class PartialInformationEncoder:
    """Encoder v1 for supervised ranking.

    The encoder intentionally uses partial information: the active player's own
    hand is rank-encoded, while partner/opponent hands are represented only by
    card counts. Raw dataset fields such as other hands and draw-pile order are
    ignored here for policy-fair training.
    """

    def encode_raw_sample(self, sample: dict[str, Any]) -> Optional[dict[str, Any]]:
        candidate_ids = list(sample.get("candidate_action_ids") or [])
        expert_action_id = sample.get("expert_action_id")
        if expert_action_id not in candidate_ids:
            return None
        if len(candidate_ids) < 2:
            return None

        actions_by_id = {action.get("id"): action for action in sample.get("legal_actions", [])}
        if any(action_id not in actions_by_id for action_id in candidate_ids):
            return None

        active_player = int(sample.get("player", 0))
        state_features = self.encode_state(
            sample.get("state", {}),
            active_player=active_player,
            cards_by_id=sample.get("cards_by_id", {}),
        )
        candidate_features = [
            state_features + self.encode_action(actions_by_id[action_id], active_player=active_player)
            for action_id in candidate_ids
        ]
        feature_dim = len(candidate_features[0])
        if any(len(features) != feature_dim for features in candidate_features):
            return None

        return {
            "candidate_features": candidate_features,
            "target_index": candidate_ids.index(expert_action_id),
            "metadata": {
                "game_id": sample.get("game_id"),
                "turn_index": sample.get("turn_index"),
                "player": active_player,
                "team": sample.get("team"),
                "expert_action_id": expert_action_id,
                "candidate_action_ids": candidate_ids,
                "legal_action_count": sample.get("legal_action_count", len(sample.get("legal_actions", []))),
            },
        }

    def encode_sample(self, sample: dict[str, Any]) -> EncodedSample:
        """Backward-compatible in-memory representation for the existing trainer."""

        encoded = self.encode_raw_sample(sample)
        if encoded is None:
            raise ValueError("Sample is not encodable")
        metadata = encoded["metadata"]
        return EncodedSample(
            state_features=[],
            action_features=encoded["candidate_features"],
            target_index=encoded["target_index"],
            candidate_action_ids=list(metadata["candidate_action_ids"]),
        )

    def encode_state(
        self,
        state: dict[str, Any],
        active_player: int,
        cards_by_id: Optional[dict[str, Any]] = None,
    ) -> list[float]:
        cards_by_id = cards_by_id or {}
        features: list[float] = []
        active_team = _team_index(active_player)
        partner = _partner(active_player)
        opponents = _opponents(active_player)

        features.extend(_one_hot(active_player, 4))
        features.extend(_one_hot(active_team, 2))
        features.append(_safe_float(state.get("deal_round_index"), scale=20.0))
        features.append(_safe_float(state.get("active_deal_size"), scale=6.0))

        hands = _hands(state)
        features.extend(_rank_counts_from_hand(hands[active_player], cards_by_id))
        features.append(float(len(hands[partner])) / 6.0)
        for opponent in opponents:
            features.append(float(len(hands[opponent])) / 6.0)

        positions = _positions(state)
        safe_ready = state.get("pawn_safe_entry_ready") or [False for _ in range(16)]
        for relation in range(len(RELATIONS)):
            pawn_indices = _pawn_indices_for_relation(active_player, relation)
            relation_positions = [positions[index] for index in pawn_indices]
            features.extend(_zone_counts(relation_positions))
            features.append(_average_progress(relation_positions))

        for pawn_index, position in enumerate(positions):
            owner = pawn_index // 4
            relation = _owner_relation(owner, active_player)
            features.extend(_one_hot(relation, len(RELATIONS)))
            kind = position.get("kind", "BASE")
            features.extend(_one_hot(POSITION_KINDS.index(kind) if kind in POSITION_KINDS else -1, len(POSITION_KINDS)))
            raw_index = position.get("index")
            features.append(-1.0 if raw_index is None else float(raw_index) / float(MAIN_TRACK_LENGTH))
            features.append(1.0 if pawn_index < len(safe_ready) and safe_ready[pawn_index] else 0.0)
            features.append(_pawn_progress_feature(position))
        return features

    def encode_action(self, action: dict[str, Any], active_player: int) -> list[float]:
        features: list[float] = []
        action_type = action.get("type", "")
        features.extend(_one_hot(ACTION_TYPES.index(action_type) if action_type in ACTION_TYPES else -1, len(ACTION_TYPES)))

        card = action.get("card") or {}
        rank = card.get("rank")
        features.extend(_one_hot(RANKS.index(rank) if rank in RANKS else -1, len(RANKS)))

        flags = action.get("flags") or {}
        for flag in ("is_capture", "is_discard", "is_noop", "enters_from_base", "enters_safe_zone_or_home"):
            features.append(1.0 if flags.get(flag) else 0.0)

        steps = action.get("steps") or []
        total_steps = sum(_safe_number(step) for step in steps)
        features.append(float(total_steps) / 13.0 if steps else 0.0)
        features.append(float(len(steps)) / 7.0)

        pawns = action.get("pawns") or []
        features.append(float(len(pawns)) / 8.0)
        relation_flags = [0.0, 0.0, 0.0]
        for pawn in pawns:
            owner = int(pawn.get("owner", -1))
            relation = _owner_relation(owner, active_player)
            if 0 <= relation < len(relation_flags):
                relation_flags[relation] = 1.0
        features.extend(relation_flags)

        from_positions = action.get("from_positions") or []
        to_positions = action.get("to_positions") or []
        progress_delta = 0.0
        for before, after in zip(from_positions, to_positions):
            if before is None or after is None:
                continue
            progress_delta += _pawn_progress_feature(after) - _pawn_progress_feature(before)
        features.append(progress_delta / max(1.0, float(len(pawns))))
        return features


class PartialInfoPerspectiveEncoderV2:
    """Perspective-normalized encoder v2.

    V2 intentionally avoids absolute player/team/seat ids in model features.
    Metadata still keeps those ids for diagnostics. All state and action features
    are represented from the active player's perspective: self, partner,
    opponent_1, opponent_2.
    """

    def encode_raw_sample(self, sample: dict[str, Any]) -> Optional[dict[str, Any]]:
        candidate_ids = list(sample.get("candidate_action_ids") or [])
        expert_action_id = sample.get("expert_action_id")
        if expert_action_id not in candidate_ids or len(candidate_ids) < 2:
            return None
        actions_by_id = {action.get("id"): action for action in sample.get("legal_actions", [])}
        if any(action_id not in actions_by_id for action_id in candidate_ids):
            return None
        active_player = int(sample.get("player", 0))
        state = sample.get("state", {})
        cards_by_id = sample.get("cards_by_id", {})
        state_features = self.encode_state(state, active_player=active_player, cards_by_id=cards_by_id)
        candidate_features = [
            state_features + self.encode_action(actions_by_id[action_id], state=state, active_player=active_player)
            for action_id in candidate_ids
        ]
        feature_dim = len(candidate_features[0])
        if any(len(features) != feature_dim for features in candidate_features):
            return None
        target_index = candidate_ids.index(expert_action_id)
        if target_index < 0 or target_index >= len(candidate_features):
            return None
        return {
            "candidate_features": candidate_features,
            "target_index": target_index,
            "metadata": {
                "encoder": "v2",
                "game_id": sample.get("game_id"),
                "turn_index": sample.get("turn_index"),
                "player": active_player,
                "team": sample.get("team"),
                "expert_action_id": expert_action_id,
                "candidate_action_ids": candidate_ids,
                "legal_action_count": sample.get("legal_action_count", len(sample.get("legal_actions", []))),
            },
        }

    def encode_state(self, state: dict[str, Any], active_player: int, cards_by_id: Optional[dict[str, Any]] = None) -> list[float]:
        cards_by_id = cards_by_id or {}
        features: list[float] = []
        hands = _hands(state)
        positions = _positions(state)
        safe_ready = state.get("pawn_safe_entry_ready") or [False for _ in range(16)]
        perspective_players = _perspective_players(active_player)

        features.append(_safe_float(state.get("deal_round_index"), scale=20.0))
        features.append(_safe_float(state.get("active_deal_size"), scale=6.0))
        features.append(float(len(hands[active_player])) / 6.0)
        features.extend(_rank_counts_from_hand(hands[active_player], cards_by_id))
        for role in ("partner", "opponent_1", "opponent_2"):
            features.append(float(len(hands[perspective_players[role]])) / 6.0)

        role_progress: dict[str, list[float]] = {}
        for role in ("self", "partner", "opponent_1", "opponent_2"):
            owner = perspective_players[role]
            pawn_positions = [positions[owner * 4 + pawn] for pawn in range(4)]
            progress_values = [_owner_progress_feature(position, owner) for position in pawn_positions]
            role_progress[role] = progress_values
            features.extend(_zone_counts(pawn_positions))
            features.extend(_progress_stats(progress_values))
            features.append(sum(1 for value in progress_values if value >= 0.85) / 4.0)
            features.append(sum(1 for pawn in range(4) if safe_ready[owner * 4 + pawn]) / 4.0)

        self_total = sum(role_progress["self"])
        partner_total = sum(role_progress["partner"])
        opponent_1_total = sum(role_progress["opponent_1"])
        opponent_2_total = sum(role_progress["opponent_2"])
        team_total = self_total + partner_total
        enemy_total = opponent_1_total + opponent_2_total
        features.extend([
            self_total / 4.0,
            partner_total / 4.0,
            (opponent_1_total + opponent_2_total) / 8.0,
            team_total / 8.0,
            enemy_total / 8.0,
            (team_total - enemy_total) / 8.0,
        ])

        for role in ("self", "partner", "opponent_1", "opponent_2"):
            owner = perspective_players[role]
            for pawn in range(4):
                pawn_index = owner * 4 + pawn
                position = positions[pawn_index]
                features.extend(_one_hot(_role_index(role), 4))
                features.extend(_one_hot(_position_kind_index(position), len(POSITION_KINDS)))
                features.append(_relative_track_feature(position, active_player))
                features.append(_owner_progress_feature(position, owner))
                features.append(1.0 if pawn_index < len(safe_ready) and safe_ready[pawn_index] else 0.0)
        return features

    def encode_action(self, action: dict[str, Any], state: dict[str, Any], active_player: int) -> list[float]:
        features: list[float] = []
        action_type = action.get("type", "")
        features.extend(_one_hot(ACTION_TYPES.index(action_type) if action_type in ACTION_TYPES else -1, len(ACTION_TYPES)))
        card = action.get("card") or {}
        rank = card.get("rank")
        features.extend(_one_hot(RANKS.index(rank) if rank in RANKS else -1, len(RANKS)))
        flags = action.get("flags") or {}
        for flag in ("is_capture", "is_discard", "is_noop", "enters_from_base", "enters_safe_zone_or_home"):
            features.append(1.0 if flags.get(flag) else 0.0)

        pawns = action.get("pawns") or []
        role_flags = [0.0, 0.0, 0.0, 0.0]
        for pawn in pawns:
            role_flags[_role_index(_owner_role(int(pawn.get("owner", -1)), active_player))] = 1.0
        features.extend(role_flags)
        features.append(1.0 if role_flags[0] else 0.0)
        features.append(1.0 if role_flags[1] else 0.0)
        features.append(1.0 if role_flags[2] or role_flags[3] else 0.0)

        steps = action.get("steps") or []
        total_steps = sum(_safe_number(step) for step in steps)
        features.append(float(total_steps) / 13.0 if steps else 0.0)
        features.append(float(len(steps)) / 7.0)
        features.append(float(len(pawns)) / 8.0)

        before_progress = _progress_from_serialized_positions(action.get("from_positions") or [], pawns)
        after_progress = _progress_from_serialized_positions(action.get("to_positions") or [], pawns)
        progress_delta = sum(after_progress) - sum(before_progress)
        features.append(progress_delta / max(1.0, float(len(pawns))))

        team_delta = 0.0
        enemy_delta = 0.0
        for pawn, before, after in zip(pawns, before_progress, after_progress):
            role = _owner_role(int(pawn.get("owner", -1)), active_player)
            delta = after - before
            if role in {"self", "partner"}:
                team_delta += delta
            else:
                enemy_delta += delta
        features.append(team_delta / 8.0)
        features.append(enemy_delta / 8.0)
        features.append((team_delta - enemy_delta) / 8.0)

        from_positions = action.get("from_positions") or []
        to_positions = action.get("to_positions") or []
        features.append(1.0 if any((position or {}).get("kind") == "BASE" for position in from_positions) else 0.0)
        features.append(1.0 if any((position or {}).get("kind") == "SAFE" for position in to_positions) else 0.0)
        features.append(1.0 if rank == "JK" else 0.0)
        features.append(1.0 if rank == "7" or action_type == "PlaySevenSplitAction" else 0.0)
        features.append(1.0 if action_type == "PlaySevenSplitAction" and len(steps) > 1 else 0.0)
        features.append(1.0 if any(value >= 1.0 for value in after_progress) else 0.0)
        features.append(1.0 if team_delta > 0.0 and role_flags[1] else 0.0)
        features.append(1.0 if enemy_delta < 0.0 or flags.get("is_capture") else 0.0)
        return features


def encode_dataset(input_jsonl: str, output_path: str, encoder_name: str = "v1") -> EncodingSummary:
    """Encode raw decision JSONL into grouped ranking JSONL samples."""

    encoder = _encoder_for_name(encoder_name)
    raw_count = 0
    written = 0
    skipped = 0
    feature_dim: Optional[int] = None
    candidate_counts: list[int] = []

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with Path(input_jsonl).open("r", encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            raw_count += 1
            if raw_count % 1000 == 0:
                print(f"Encoded progress: read {raw_count} samples", flush=True)
            sample = json.loads(line)
            encoded = encoder.encode_raw_sample(sample)
            if encoded is None:
                skipped += 1
                continue
            current_dim = len(encoded["candidate_features"][0])
            if feature_dim is None:
                feature_dim = current_dim
            if current_dim != feature_dim:
                skipped += 1
                continue
            candidate_counts.append(len(encoded["candidate_features"]))
            target.write(json.dumps(encoded, separators=(",", ":")) + "\n")
            written += 1

    summary = EncodingSummary(
        raw_samples_read=raw_count,
        encoded_samples_written=written,
        skipped_samples=skipped,
        feature_dim=feature_dim,
        average_candidates=mean(candidate_counts) if candidate_counts else 0.0,
    )
    print_encoding_summary(summary)
    _print_metadata_distribution(output_path)
    return summary


def encoded_jsonl_to_pt(input_jsonl: str, output_path: str) -> dict[str, Any]:
    """Convert grouped encoded ranking JSONL to a PyTorch .pt file.

    The saved object keeps one tensor per decision point because candidate counts
    vary across samples. Each item has shape: [num_candidates, feature_dim].
    """

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("PyTorch is required to write .pt datasets. Install torch or keep JSONL output.") from exc

    candidate_tensors = []
    target_indices = []
    metadata = []
    sample_count = 0
    feature_dim: Optional[int] = None
    candidate_counts: list[int] = []

    with Path(input_jsonl).open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            payload = json.loads(line)
            candidates = payload.get("candidate_features") or []
            if len(candidates) < 2:
                continue
            target_index = int(payload.get("target_index", -1))
            if target_index < 0 or target_index >= len(candidates):
                continue
            current_dim = len(candidates[0])
            if current_dim <= 0 or any(len(features) != current_dim for features in candidates):
                continue
            if feature_dim is None:
                feature_dim = current_dim
            if current_dim != feature_dim:
                continue

            candidate_tensors.append(torch.tensor(candidates, dtype=torch.float32))
            target_indices.append(target_index)
            metadata.append(payload.get("metadata") or {})
            candidate_counts.append(len(candidates))
            sample_count += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoder_versions = sorted({str(item.get("encoder", "v1")) for item in metadata})
    payload = {
        "samples": [
            {
                "candidate_features": features,
                "target_index": torch.tensor(target, dtype=torch.long),
                "metadata": item_metadata,
            }
            for features, target, item_metadata in zip(candidate_tensors, target_indices, metadata)
        ],
        "candidate_features": candidate_tensors,
        "target_indices": torch.tensor(target_indices, dtype=torch.long),
        "metadata": metadata,
        "feature_dim": feature_dim,
        "sample_count": sample_count,
        "average_candidates": mean(candidate_counts) if candidate_counts else 0.0,
        "format": "grouped_ranking_v2" if encoder_versions == ["v2"] else "grouped_ranking_v1",
        "encoder_versions": encoder_versions,
    }
    torch.save(payload, output)
    print_pt_summary(payload, str(output))
    return payload


def print_pt_summary(payload: dict[str, Any], output_path: str) -> None:
    print("PT conversion summary:", flush=True)
    print(f"  output_path: {output_path}", flush=True)
    print(f"  samples: {payload['sample_count']}", flush=True)
    print(f"  feature_dim: {payload['feature_dim']}", flush=True)
    print(f"  average_candidates: {payload['average_candidates']:.2f}", flush=True)


def encode_jsonl(input_path: str, output_path: str) -> int:
    """Compatibility wrapper around encode_dataset."""

    return encode_dataset(input_path, output_path, encoder_name="v1").encoded_samples_written


def iter_encoded_jsonl(input_path: str) -> Iterable[EncodedSample]:
    """Iterate either raw samples or encoded ranking samples.

    For encoded samples, action_features contains full state-action vectors and
    state_features is empty. The existing training skeleton can still consume it
    with a small trainer-side adjustment if needed.
    """

    encoder = PartialInformationEncoder()
    with Path(input_path).open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            payload = json.loads(line)
            if "candidate_features" in payload:
                metadata = payload.get("metadata") or {}
                yield EncodedSample(
                    state_features=[],
                    action_features=payload["candidate_features"],
                    target_index=int(payload["target_index"]),
                    candidate_action_ids=list(metadata.get("candidate_action_ids") or []),
                )
            else:
                yield encoder.encode_sample(payload)


def print_encoding_summary(summary: EncodingSummary) -> None:
    print("Encoding summary:", flush=True)
    print(f"  raw_samples_read: {summary.raw_samples_read}", flush=True)
    print(f"  encoded_samples_written: {summary.encoded_samples_written}", flush=True)
    print(f"  skipped_samples: {summary.skipped_samples}", flush=True)
    print(f"  feature_dim: {summary.feature_dim}", flush=True)
    print(f"  average_candidates: {summary.average_candidates:.2f}", flush=True)


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Encode and convert imitation ranking datasets.")
    subparsers = parser.add_subparsers(dest="command")

    encode_parser = subparsers.add_parser("encode", help="Encode raw imitation JSONL into grouped ranking JSONL.")
    encode_parser.add_argument("--input", required=True)
    encode_parser.add_argument("--output", required=True)
    encode_parser.add_argument("--encoder", choices=("v1", "v2"), default="v1")

    pt_parser = subparsers.add_parser("to-pt", help="Convert grouped encoded JSONL to a PyTorch .pt file.")
    pt_parser.add_argument("--input", required=True)
    pt_parser.add_argument("--output", required=True)

    parser.add_argument("--input", dest="legacy_input")
    parser.add_argument("--output", dest="legacy_output")

    args = parser.parse_args(argv)
    if args.command == "encode":
        encode_dataset(args.input, args.output, encoder_name=args.encoder)
    elif args.command == "to-pt":
        encoded_jsonl_to_pt(args.input, args.output)
    elif args.legacy_input and args.legacy_output:
        encode_dataset(args.legacy_input, args.legacy_output, encoder_name="v1")
    else:
        parser.print_help()
        raise SystemExit(2)


def _encoder_for_name(encoder_name: str):
    if encoder_name == "v1":
        return PartialInformationEncoder()
    if encoder_name == "v2":
        return PartialInfoPerspectiveEncoderV2()
    raise ValueError("encoder_name must be 'v1' or 'v2'")


def _print_metadata_distribution(encoded_path: str) -> None:
    by_player: dict[str, int] = {}
    by_team: dict[str, int] = {}
    with Path(encoded_path).open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            metadata = (json.loads(line).get("metadata") or {})
            by_player[str(metadata.get("player"))] = by_player.get(str(metadata.get("player")), 0) + 1
            by_team[str(metadata.get("team"))] = by_team.get(str(metadata.get("team")), 0) + 1
    print(f"  metadata_by_player: {dict(sorted(by_player.items()))}", flush=True)
    print(f"  metadata_by_team: {dict(sorted(by_team.items()))}", flush=True)


def _hands(state: dict[str, Any]) -> list[list[int]]:
    hands = state.get("hands") or [[], [], [], []]
    return [list(hand) for hand in hands[:4]] + [[] for _ in range(max(0, 4 - len(hands)))]


def _positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    positions = list(state.get("pawn_positions") or [])
    if len(positions) < 16:
        positions.extend({"kind": "BASE", "index": None} for _ in range(16 - len(positions)))
    return positions[:16]


def _one_hot(index: int, size: int) -> list[float]:
    return [1.0 if idx == index else 0.0 for idx in range(size)]


def _team_index(player: int) -> int:
    return 0 if player in (0, 2) else 1


def _partner(player: int) -> int:
    return {0: 2, 2: 0, 1: 3, 3: 1}.get(player, 0)


def _opponents(player: int) -> tuple[int, int]:
    return (1, 3) if _team_index(player) == 0 else (0, 2)


def _owner_relation(owner: int, active_player: int) -> int:
    if owner == active_player:
        return 0
    if owner == _partner(active_player):
        return 1
    return 2


def _pawn_indices_for_relation(active_player: int, relation: int) -> list[int]:
    if relation == 0:
        owners = (active_player,)
    elif relation == 1:
        owners = (_partner(active_player),)
    else:
        owners = _opponents(active_player)
    return [owner * 4 + pawn for owner in owners for pawn in range(4)]


def _zone_counts(positions: list[dict[str, Any]]) -> list[float]:
    total = max(1, len(positions))
    return [sum(1 for position in positions if position.get("kind") == kind) / total for kind in POSITION_KINDS]


def _average_progress(positions: list[dict[str, Any]]) -> float:
    if not positions:
        return 0.0
    return sum(_pawn_progress_feature(position) for position in positions) / len(positions)


def _rank_counts_from_hand(hand: list[int], cards_by_id: dict[str, Any]) -> list[float]:
    features = [0.0 for _ in RANKS]
    for card_id in hand:
        card = cards_by_id.get(str(card_id)) or {}
        rank = card.get("rank")
        if rank in RANKS:
            features[RANKS.index(rank)] += 1.0
    return [value / 4.0 for value in features]


def _pawn_progress_feature(position: dict[str, Any]) -> float:
    kind = position.get("kind")
    index = position.get("index")
    if kind == "BASE":
        return 0.0
    if kind == "SAFE":
        return 1.0 + (0.0 if index is None else float(index) / 4.0)
    if kind == "TRACK":
        return 0.25 + (0.0 if index is None else float(index) / float(MAIN_TRACK_LENGTH))
    return 0.0


def _safe_float(value: Any, scale: float) -> float:
    return _safe_number(value) / scale


def _safe_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _perspective_players(active_player: int) -> dict[str, int]:
    return {
        "self": active_player,
        "partner": (active_player + 2) % 4,
        "opponent_1": (active_player + 1) % 4,
        "opponent_2": (active_player + 3) % 4,
    }


def _role_index(role: str) -> int:
    return {"self": 0, "partner": 1, "opponent_1": 2, "opponent_2": 3}.get(role, 3)


def _owner_role(owner: int, active_player: int) -> str:
    players = _perspective_players(active_player)
    for role, player in players.items():
        if owner == player:
            return role
    return "opponent_2"


def _position_kind_index(position: dict[str, Any]) -> int:
    kind = position.get("kind", "BASE")
    return POSITION_KINDS.index(kind) if kind in POSITION_KINDS else -1


def _relative_track_feature(position: dict[str, Any], active_player: int) -> float:
    if position.get("kind") != "TRACK" or position.get("index") is None:
        return -1.0
    active_start = ENTRY_INDEX_BY_PLAYER[active_player]
    return float((int(position["index"]) - active_start) % MAIN_TRACK_LENGTH) / float(MAIN_TRACK_LENGTH)


def _owner_progress_feature(position: dict[str, Any], owner: int) -> float:
    kind = position.get("kind")
    index = position.get("index")
    if kind == "BASE":
        return 0.0
    if kind == "SAFE":
        return 1.0 + (0.0 if index is None else float(index) / 4.0)
    if kind == "TRACK" and index is not None:
        owner_start = ENTRY_INDEX_BY_PLAYER[owner]
        return ((int(index) - owner_start) % MAIN_TRACK_LENGTH) / float(MAIN_TRACK_LENGTH)
    return 0.0


def _progress_stats(values: list[float]) -> list[float]:
    if not values:
        return [0.0, 0.0, 0.0, 0.0]
    min_value = min(values)
    max_value = max(values)
    mean_value = sum(values) / len(values)
    return [min_value, max_value, mean_value, max_value - min_value]


def _progress_from_serialized_positions(positions: list[Optional[dict[str, Any]]], pawns: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for position, pawn in zip(positions, pawns):
        if position is None:
            values.append(0.0)
            continue
        values.append(_owner_progress_feature(position, int(pawn.get("owner", 0))))
    return values


if __name__ == "__main__":
    main()
