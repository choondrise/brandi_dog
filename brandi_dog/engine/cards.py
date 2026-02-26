from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Rank(Enum):
    ACE = "A"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    JOKER = "JK"


NON_JOKER_RANKS: tuple[Rank, ...] = (
    Rank.ACE,
    Rank.TWO,
    Rank.THREE,
    Rank.FOUR,
    Rank.FIVE,
    Rank.SIX,
    Rank.SEVEN,
    Rank.EIGHT,
    Rank.NINE,
    Rank.TEN,
    Rank.JACK,
    Rank.QUEEN,
    Rank.KING,
)


NUMERIC_FORWARD_VALUES: dict[Rank, int] = {
    Rank.TWO: 2,
    Rank.THREE: 3,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.QUEEN: 12,
    Rank.KING: 13,
}


@dataclass(frozen=True)
class Card:
    card_id: int
    rank: Rank


def build_deck() -> tuple[Card, ...]:
    cards: list[Card] = []
    next_id = 0
    for rank in NON_JOKER_RANKS:
        for _ in range(8):
            cards.append(Card(card_id=next_id, rank=rank))
            next_id += 1
    for _ in range(6):
        cards.append(Card(card_id=next_id, rank=Rank.JOKER))
        next_id += 1
    return tuple(cards)


def card_map(cards: tuple[Card, ...]) -> dict[int, Card]:
    return {card.card_id: card for card in cards}


def render_card(rank: Rank) -> str:
    return rank.value
