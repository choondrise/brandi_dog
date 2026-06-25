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
from brandi_dog.engine.cards import Card, Rank, render_card
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    Position,
    PositionKind,
    RoundStage,
    Team,
    active_swap_player,
    get_pawn_position,
    hand_of,
    player_pawns,
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
        "pawns": [_pawn_payload(state, pawn) for player in PlayerId for pawn in player_pawns(player)],
        "hands": _hands_payload(engine, state, viewer),
        "discardCount": len(state.discard_pile),
        "drawCount": len(state.draw_pile),
        "legalActions": [serialize_action(idx, action, engine.cards_by_id) for idx, action in enumerate(legal)],
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


def serialize_action(action_id: int, action: Action, cards_by_id: dict[int, Card]) -> dict[str, Any]:
    payload = {
        "id": action_id,
        "type": type(action).__name__,
        "player": getattr(action, "player", None).name,
        "label": describe_action(action, cards_by_id),
        "representedRank": None,
        "pawns": [],
        "moves": [],
        "steps": None,
        "direction": None,
        "preferSafeEntry": None,
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


def _pawn_ref_payload(pawn: PawnRef) -> dict[str, Any]:
    return {"id": f"{pawn.owner.name}-{pawn.number}", "owner": pawn.owner.name, "number": pawn.number}


def describe_action(action: Action, cards_by_id: dict[int, Card]) -> str:
    if isinstance(action, SwapCardAction):
        return f"Swap {render_card(cards_by_id[action.card_id].rank)} with teammate"
    if isinstance(action, PlayEnterAction):
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} to enter {action.pawn.owner.name}.{action.pawn.number}"
    if isinstance(action, PlayStepCardAction):
        direction = "+" if action.direction == MoveDirection.FORWARD else "-"
        suffix = "" if action.prefer_safe_entry else " on track"
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} move {action.pawn.owner.name}.{action.pawn.number} {direction}{action.steps}{suffix}"
    if isinstance(action, PlayJackSwapAction):
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} swap {action.source.owner.name}.{action.source.number} with {action.target.owner.name}.{action.target.number}"
    if isinstance(action, PlaySevenSplitAction):
        moves = ", ".join(f"{move.pawn.owner.name}.{move.pawn.number}+{move.steps}" for move in action.moves)
        return f"Play {_card_descriptor(action.card_id, action.represented_rank, cards_by_id)} split [{moves}]"
    if isinstance(action, DiscardHandAction):
        return "Discard hand"
    if isinstance(action, SkipTurnAction):
        return "Skip turn"
    return repr(action)


def _card_descriptor(card_id: int, represented_rank: Rank, cards_by_id: dict[int, Card]) -> str:
    actual = render_card(cards_by_id[card_id].rank)
    represented = render_card(represented_rank)
    if actual == represented:
        return actual
    return f"{actual} as {represented}"
