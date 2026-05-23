from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum, IntEnum
from typing import Any, Optional

from brandi_dog.engine import rules as engine_rules
from brandi_dog.engine.actions import (
    Action,
    DiscardHandAction,
    MoveDirection,
    PlayEnterAction,
    PlayJackSwapAction,
    PlaySevenSplitAction,
    PlayStepCardAction,
    SevenSubMove,
    SkipTurnAction,
    SwapCardAction,
)
from brandi_dog.engine.cards import Card
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    Position,
    PositionKind,
    RoundStage,
    Team,
    get_pawn_position,
    pawn_to_index,
    team_of,
)


def serialize_state(state: GameState) -> dict[str, Any]:
    """Serialize every GameState field for future offline experiments."""

    return {
        "round_stage": state.round_stage.value,
        "deal_round_index": state.deal_round_index,
        "round_starter": int(state.round_starter),
        "play_current": int(state.play_current),
        "swap_cursor": state.swap_cursor,
        "swap_selections": [selection for selection in state.swap_selections],
        "active_deal_size": state.active_deal_size,
        "hands": [[card_id for card_id in hand] for hand in state.hands],
        "pawn_positions": [serialize_position(position) for position in state.pawn_positions],
        "pawn_safe_entry_ready": [bool(value) for value in state.pawn_safe_entry_ready],
        "draw_pile": list(state.draw_pile),
        "discard_pile": list(state.discard_pile),
        "winner": state.winner.value if state.winner is not None else None,
    }


def serialize_position(position: Position) -> dict[str, Any]:
    return {"kind": position.kind.value, "index": position.index}


def serialize_pawn(pawn: PawnRef) -> dict[str, int]:
    return {"owner": int(pawn.owner), "number": pawn.number, "index": pawn_to_index(pawn)}


def serialize_card(card: Optional[Card]) -> Optional[dict[str, Any]]:
    if card is None:
        return None
    return {"id": card.card_id, "rank": card.rank.value}



def serialize_card_map(cards_by_id: dict[int, Card]) -> dict[str, dict[str, Any]]:
    return {str(card_id): serialize_card(card) for card_id, card in sorted(cards_by_id.items())}

def serialize_action(
    action: Action,
    action_id: str,
    engine: GameEngine,
    state: GameState,
) -> dict[str, Any]:
    """Serialize an action with structured fields and derived move flags."""

    next_state = _try_apply_action(engine, state, action)
    card_id = _action_card_id(action)
    card = engine.cards_by_id.get(card_id) if card_id is not None else None
    moved_pawns = _moved_pawns(action)
    payload: dict[str, Any] = {
        "id": action_id,
        "type": type(action).__name__,
        "card_id": card_id,
        "card": serialize_card(card),
        "represented_rank": getattr(action, "represented_rank", None).value if getattr(action, "represented_rank", None) is not None else None,
        "player": int(getattr(action, "player")) if hasattr(action, "player") else None,
        "team": team_of(getattr(action, "player")).value if hasattr(action, "player") else None,
        "pawns": [serialize_pawn(pawn) for pawn in moved_pawns],
        "from_positions": [_position_for_pawn(state, pawn) for pawn in moved_pawns],
        "to_positions": [_position_for_pawn(next_state, pawn) for pawn in moved_pawns] if next_state is not None else [],
        "steps": _action_steps(action),
        "direction": action.direction.value if isinstance(action, PlayStepCardAction) else None,
        "flags": {
            "is_capture": _is_capture(state, next_state, action) if next_state is not None else False,
            "is_discard": isinstance(action, DiscardHandAction),
            "is_noop": isinstance(action, SkipTurnAction),
            "enters_from_base": isinstance(action, PlayEnterAction),
            "enters_safe_zone_or_home": _enters_safe_zone(state, next_state, moved_pawns) if next_state is not None else False,
        },
        "raw_fields": _raw_dataclass_fields(action),
        "raw_repr": repr(action),
    }
    if isinstance(action, PlaySevenSplitAction):
        payload["seven_moves"] = [serialize_seven_submove(move) for move in action.moves]
    if isinstance(action, PlayJackSwapAction):
        payload["source"] = serialize_pawn(action.source)
        payload["target"] = serialize_pawn(action.target)
    return payload


def serialize_seven_submove(move: SevenSubMove) -> dict[str, Any]:
    return {"pawn": serialize_pawn(move.pawn), "steps": move.steps, "prefer_safe_entry": move.prefer_safe_entry}


def _position_for_pawn(state: Optional[GameState], pawn: PawnRef) -> Optional[dict[str, Any]]:
    if state is None:
        return None
    return serialize_position(get_pawn_position(state, pawn))


def _raw_dataclass_fields(action: Action) -> dict[str, Any]:
    if not is_dataclass(action):
        return {}
    return _json_ready(asdict(action))


def _json_ready(value: Any) -> Any:
    if isinstance(value, IntEnum):
        return int(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _action_card_id(action: Action) -> Optional[int]:
    return getattr(action, "card_id", None)


def _action_steps(action: Action) -> list[int]:
    if isinstance(action, PlayStepCardAction):
        return [action.steps]
    if isinstance(action, PlaySevenSplitAction):
        return [move.steps for move in action.moves]
    return []


def _moved_pawns(action: Action) -> tuple[PawnRef, ...]:
    if isinstance(action, PlayEnterAction):
        return (action.pawn,)
    if isinstance(action, PlayStepCardAction):
        return (action.pawn,)
    if isinstance(action, PlaySevenSplitAction):
        return tuple(move.pawn for move in action.moves)
    if isinstance(action, PlayJackSwapAction):
        return (action.source, action.target)
    return ()


def _try_apply_action(engine: GameEngine, state: GameState, action: Action) -> Optional[GameState]:
    try:
        return engine_rules.apply_action(state, action, engine.cards_by_id)
    except ValueError:
        return None


def _is_capture(before: GameState, after: GameState, action: Action) -> bool:
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


def _enters_safe_zone(before: GameState, after: GameState, pawns: tuple[PawnRef, ...]) -> bool:
    for pawn in pawns:
        before_pos = get_pawn_position(before, pawn)
        after_pos = get_pawn_position(after, pawn)
        if before_pos.kind != PositionKind.SAFE and after_pos.kind == PositionKind.SAFE:
            return True
    return False
