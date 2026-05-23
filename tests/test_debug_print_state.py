from __future__ import annotations

from brandi_dog.engine.cards import render_card
from brandi_dog.engine.state import PlayerId, Position, PositionKind, get_pawn_position, player_pawns

from .helpers import make_engine


def _format_position(position: Position) -> str:
    if position.kind == PositionKind.BASE:
        return "BASE"
    if position.kind == PositionKind.TRACK:
        return f"TRACK({position.index})"
    if position.kind == PositionKind.SAFE:
        return f"SAFE({position.index})"
    return f"UNKNOWN({position.kind})"


def _print_hands(engine, state) -> None:
    for player in PlayerId:
        hand = state.hands[int(player)]
        rendered = ", ".join(f"{card_id}:{render_card(engine.cards_by_id[card_id].rank)}" for card_id in hand) or "-"
        print(f"{player.name} hand -> [{rendered}]")


def _print_board(state) -> None:
    for player in PlayerId:
        pawns = []
        for pawn in player_pawns(player):
            position = get_pawn_position(state, pawn)
            pawns.append(f"P{pawn.number}={_format_position(position)}")
        print(f"{player.name} pawns -> {', '.join(pawns)}")


def test_print_hands_and_board_state() -> None:
    engine = make_engine(seed=7)
    state = engine.reset()

    print("=== HANDS ===")
    _print_hands(engine, state)
    print("\n=== BOARD ===")
    _print_board(state)
