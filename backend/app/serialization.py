from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Optional

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
from brandi_dog.engine.board import simulate_entry_from_base, simulate_step_move, track_occupant
from brandi_dog.engine.cards import Card, Rank, render_card
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    Position,
    PositionKind,
    RoundStage,
    base_position,
    Team,
    active_swap_player,
    get_pawn_position,
    hand_of,
    player_pawns,
    set_pawn_position,
)


PLAYER_COLOR = {
    PlayerId.A1: "#d9443f",
    PlayerId.B1: "#239a59",
    PlayerId.A2: "#315fcb",
    PlayerId.B2: "#d4ae1f",
}


def active_player(state: GameState) -> Optional[PlayerId]:
    if state.round_stage == RoundStage.GAME_OVER:
        return None
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def serialize_game(
    engine: GameEngine,
    state: Optional[GameState],
    legal: Iterable[Action],
    viewer: Optional[PlayerId],
) -> Optional[dict[str, Any]]:
    if state is None:
        return None

    active = active_player(state)
    return {
        "phase": state.round_stage.value,
        "dealRoundIndex": state.deal_round_index,
        "activeDealSize": state.active_deal_size,
        "roundStarter": state.round_starter.name,
        "playCurrent": state.play_current.name,
        "activePlayer": None if active is None else active.name,
        "winner": None if state.winner is None else state.winner.value,
        "players": [_player_payload(player) for player in PlayerId],
        "pawns": serialize_pawns(state),
        "hands": _hands_payload(engine, state, viewer),
        "discardCount": len(state.discard_pile),
        "drawCount": len(state.draw_pile),
        "legalActions": [serialize_action(idx, action, engine.cards_by_id, state) for idx, action in enumerate(legal)],
    }


def _player_payload(player: PlayerId) -> dict[str, Any]:
    return {
        "id": player.name,
        "index": int(player),
        "team": "A" if player in (PlayerId.A1, PlayerId.A2) else "B",
        "color": PLAYER_COLOR[player],
    }


def _hands_payload(engine: GameEngine, state: GameState, viewer: Optional[PlayerId]) -> dict[str, Any]:
    hands: dict[str, Any] = {}
    for player in PlayerId:
        cards = hand_of(state, player)
        hands[player.name] = {
            "count": len(cards),
            "cards": [_card_payload(engine.cards_by_id[card_id]) for card_id in cards] if viewer == player else None,
        }
    return hands


def _card_payload(card: Card) -> dict[str, Any]:
    return {
        "id": card.card_id,
        "rank": card.rank.value,
        "label": render_card(card.rank),
        "asset": _card_asset_name(card),
    }


def _card_asset_name(card: Card) -> str:
    if card.rank == Rank.JOKER:
        return "joker.png"

    suit = ("C", "D", "S", "H")[card.card_id % 4]
    return f"{suit}{card.rank.value}.png"


def serialize_pawns(state: GameState) -> list[dict[str, Any]]:
    return [_pawn_payload(state, pawn) for player in PlayerId for pawn in player_pawns(player)]


def _pawn_payload(state: GameState, pawn: PawnRef) -> dict[str, Any]:
    position = get_pawn_position(state, pawn)
    return {
        "id": f"{pawn.owner.name}-{pawn.number}",
        "owner": pawn.owner.name,
        "number": pawn.number,
        "color": PLAYER_COLOR[pawn.owner],
        "position": _position_payload(position),
    }


def _position_payload(position: Position) -> dict[str, Any]:
    return {"kind": position.kind.value, "index": position.index}


def serialize_action(action_id: int, action: Action, cards_by_id: dict[int, Card], state: Optional[GameState] = None) -> dict[str, Any]:
    payload = {
        "id": action_id,
        "key": action_key(action),
        "type": type(action).__name__,
        "player": getattr(action, "player", None).name,
        "label": describe_action(action, cards_by_id),
        "representedRank": None,
        "pawns": [],
        "moves": [],
        "steps": None,
        "direction": None,
        "preferSafeEntry": None,
        "preview": action_preview(state, action) if state is not None else empty_preview(),
    }
    card_id = getattr(action, "card_id", None)
    if card_id is not None:
        payload["card"] = _card_payload(cards_by_id[card_id])
    represented_rank = getattr(action, "represented_rank", None)
    if represented_rank is not None:
        payload["representedRank"] = represented_rank.value
    if isinstance(action, PlayEnterAction):
        payload["pawns"] = [_pawn_ref_payload(action.pawn)]
    elif isinstance(action, PlayStepCardAction):
        payload["pawns"] = [_pawn_ref_payload(action.pawn)]
        payload["steps"] = action.steps
        payload["direction"] = action.direction.value
        payload["preferSafeEntry"] = action.prefer_safe_entry
    elif isinstance(action, PlayJackSwapAction):
        payload["pawns"] = [_pawn_ref_payload(action.source), _pawn_ref_payload(action.target)]
    elif isinstance(action, PlaySevenSplitAction):
        payload["pawns"] = [_pawn_ref_payload(move.pawn) for move in action.moves]
        payload["moves"] = [
            {
                "pawn": _pawn_ref_payload(move.pawn),
                "steps": move.steps,
                "preferSafeEntry": move.prefer_safe_entry,
            }
            for move in action.moves
        ]
    return payload


def empty_preview() -> dict[str, Any]:
    return {"positions": [], "capturePawnIds": [], "valid": True}


def action_preview(state: Optional[GameState], action: Action) -> dict[str, Any]:
    if state is None:
        return empty_preview()
    if isinstance(action, PlayEnterAction):
        path = simulate_entry_from_base(state, action.pawn)
        if path is None:
            return {"positions": [], "capturePawnIds": [], "valid": False}
        return {"positions": [_preview_position_payload(path.end, action.pawn.owner)], "capturePawnIds": [], "valid": True}
    if isinstance(action, PlayStepCardAction):
        path = simulate_step_move(
            state,
            action.pawn,
            direction=action.direction,
            steps=action.steps,
            prefer_safe_entry=action.prefer_safe_entry,
        )
        if path is None:
            return {"positions": [], "capturePawnIds": [], "valid": False}
        return {
            "positions": [_preview_position_payload(position, action.pawn.owner) for position in path.counted_positions],
            "capturePawnIds": _landing_capture_ids(state, action.pawn, path.end),
            "valid": True,
        }
    if isinstance(action, PlaySevenSplitAction):
        return seven_preview(state, action)
    return empty_preview()


def seven_preview(state: GameState, action: PlaySevenSplitAction) -> dict[str, Any]:
    preview_state = state
    positions: list[dict[str, Any]] = []
    capture_ids: list[str] = []
    for move in action.moves:
        path = simulate_step_move(
            preview_state,
            move.pawn,
            direction=MoveDirection.FORWARD,
            steps=move.steps,
            prefer_safe_entry=move.prefer_safe_entry,
        )
        if path is None:
            return {"positions": _unique_positions(positions), "capturePawnIds": _unique(capture_ids), "valid": False}
        positions.extend(_preview_position_payload(position, move.pawn.owner) for position in path.counted_positions)
        before = preview_state
        preview_state = _apply_preview_move(
            preview_state,
            move.pawn,
            path.end,
            path.traversed_open_track_indices,
            pass_capture=True,
        )
        capture_ids.extend(_captured_pawn_ids(before, preview_state, move.pawn))
    return {"positions": _unique_positions(positions), "capturePawnIds": _unique(capture_ids), "valid": True}


def _apply_preview_move(
    state: GameState,
    pawn: PawnRef,
    end: Position,
    traversed_open_track_indices: tuple[int, ...],
    pass_capture: bool,
) -> GameState:
    updated = state
    if pass_capture:
        for track_index in traversed_open_track_indices:
            victim = track_occupant(updated, track_index, ignore=[pawn])
            if victim is not None:
                updated = set_pawn_position(updated, victim, base_position())
    updated = set_pawn_position(updated, pawn, end)
    if end.kind == PositionKind.TRACK and end.index is not None:
        victim = track_occupant(updated, end.index, ignore=[pawn])
        if victim is not None:
            updated = set_pawn_position(updated, victim, base_position())
    return updated


def _landing_capture_ids(state: GameState, pawn: PawnRef, end: Position) -> list[str]:
    if end.kind != PositionKind.TRACK or end.index is None:
        return []
    victim = track_occupant(state, end.index, ignore=[pawn])
    return [] if victim is None else [_pawn_ref_payload(victim)["id"]]


def _captured_pawn_ids(before: GameState, after: GameState, moving_pawn: PawnRef) -> list[str]:
    captured: list[str] = []
    for player in PlayerId:
        for pawn in player_pawns(player):
            if pawn == moving_pawn:
                continue
            before_pos = get_pawn_position(before, pawn)
            after_pos = get_pawn_position(after, pawn)
            if before_pos.kind != PositionKind.BASE and after_pos.kind == PositionKind.BASE:
                captured.append(_pawn_ref_payload(pawn)["id"])
    return captured


def _preview_position_payload(position: Position, owner: PlayerId) -> dict[str, Any]:
    payload = {"kind": position.kind.value, "index": position.index}
    if position.kind == PositionKind.SAFE:
        payload["owner"] = owner.name
    return payload


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _unique_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for position in positions:
        key = (position.get("kind"), position.get("owner"), position.get("index"))
        if key in seen:
            continue
        seen.add(key)
        result.append(position)
    return result


def action_key(action: Action) -> str:
    parts = [type(action).__name__, _enum_name(getattr(action, "player", None))]
    card_id = getattr(action, "card_id", None)
    if card_id is not None:
        parts.extend(["card", str(card_id)])
    represented_rank = getattr(action, "represented_rank", None)
    if represented_rank is not None:
        parts.extend(["rank", _enum_name(represented_rank)])
    if isinstance(action, PlayEnterAction):
        parts.extend(["pawn", _pawn_key(action.pawn)])
    elif isinstance(action, PlayStepCardAction):
        parts.extend([
            "pawn",
            _pawn_key(action.pawn),
            "steps",
            str(action.steps),
            "direction",
            action.direction.value,
            "safe",
            "1" if action.prefer_safe_entry else "0",
        ])
    elif isinstance(action, PlayJackSwapAction):
        parts.extend(["source", _pawn_key(action.source), "target", _pawn_key(action.target)])
    elif isinstance(action, PlaySevenSplitAction):
        for move in action.moves:
            parts.extend(["move", _pawn_key(move.pawn), str(move.steps), "1" if move.prefer_safe_entry else "0"])
    return "|".join(parts)


def _pawn_key(pawn: PawnRef) -> str:
    return f"{pawn.owner.name}.{pawn.number}"


def _enum_name(value: Any) -> str:
    return value.name if hasattr(value, "name") else str(value)


def _pawn_ref_payload(pawn: PawnRef) -> dict[str, Any]:
    return {"id": f"{pawn.owner.name}-{pawn.number}", "owner": pawn.owner.name, "number": pawn.number}


def describe_action(action: Action, cards_by_id: dict[int, Card]) -> str:
    if isinstance(action, SwapCardAction):
        return f"Swap {render_card(cards_by_id[action.card_id].rank)} with teammate"
    if isinstance(action, PlayEnterAction):
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} to enter {_pawn_descriptor(action.pawn)}"
    if isinstance(action, PlayStepCardAction):
        direction = "+" if action.direction == MoveDirection.FORWARD else "-"
        suffix = "" if action.prefer_safe_entry else " on track"
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} move {_pawn_descriptor(action.pawn)} {direction}{action.steps}{suffix}"
    if isinstance(action, PlayJackSwapAction):
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} swap {_pawn_descriptor(action.source)} with {_pawn_descriptor(action.target)}"
    if isinstance(action, PlaySevenSplitAction):
        moves = ", ".join(f"{_pawn_descriptor(move.pawn)}+{move.steps}" for move in action.moves)
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} split [{moves}]"
    if isinstance(action, DiscardHandAction):
        return "Discard hand"
    if isinstance(action, SkipTurnAction):
        return "Skip turn"
    return repr(action)


def _pawn_descriptor(pawn: PawnRef) -> str:
    return f"{pawn.owner.name}.{pawn.number + 1}"


def _card_descriptor(card_id: int, represented_rank: Rank, cards_by_id: dict[int, Card]) -> str:
    actual = render_card(cards_by_id[card_id].rank)
    represented = render_card(represented_rank)
    if actual == represented:
        return actual
    return f"{actual} as {represented}"
