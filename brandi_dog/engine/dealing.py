from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .state import (
    GameState,
    PLAY_ORDER,
    RoundStage,
    empty_swap_selections,
)

DEAL_SEQUENCE = (6, 5, 4, 3, 2)


class RngProtocol(Protocol):
    def randint(self, a: int, b: int) -> int:
        ...

    def shuffle(self, x: list[int]) -> None:
        ...


def cards_to_deal_for_round(deal_round_index: int, rng: RngProtocol) -> int:
    if deal_round_index < len(DEAL_SEQUENCE):
        return DEAL_SEQUENCE[deal_round_index]
    return rng.randint(1, 6)


def draw_cards(
    draw_pile: tuple[int, ...],
    discard_pile: tuple[int, ...],
    count: int,
    rng: RngProtocol,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    draw = list(draw_pile)
    discard = list(discard_pile)
    drawn: list[int] = []

    for _ in range(count):
        if not draw:
            if not discard:
                raise RuntimeError("No cards available to draw")
            draw = discard
            discard = []
            rng.shuffle(draw)
        drawn.append(draw.pop())

    return tuple(draw), tuple(discard), tuple(drawn)


def deal_new_round(state: GameState, rng: RngProtocol) -> GameState:
    round_index = state.deal_round_index + 1
    deal_size = cards_to_deal_for_round(round_index, rng)

    hands = list(state.hands)
    draw_pile = state.draw_pile
    discard_pile = state.discard_pile

    for player in PLAY_ORDER:
        draw_pile, discard_pile, drawn = draw_cards(draw_pile, discard_pile, deal_size, rng)
        hands[int(player)] = tuple(hands[int(player)] + drawn)

    return replace(
        state,
        round_stage=RoundStage.TEAM_SWAPS,
        deal_round_index=round_index,
        active_deal_size=deal_size,
        swap_cursor=0,
        swap_selections=empty_swap_selections(),
        draw_pile=draw_pile,
        discard_pile=discard_pile,
        hands=tuple(hands),
    )
