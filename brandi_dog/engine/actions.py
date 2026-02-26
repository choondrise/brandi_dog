from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union

from .cards import Rank
from .state import PawnRef, PlayerId


class MoveDirection(Enum):
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"


@dataclass(frozen=True)
class SwapCardAction:
    player: PlayerId
    card_id: int


@dataclass(frozen=True)
class PlayStepCardAction:
    player: PlayerId
    card_id: int
    represented_rank: Rank
    pawn: PawnRef
    steps: int
    direction: MoveDirection


@dataclass(frozen=True)
class PlayEnterAction:
    player: PlayerId
    card_id: int
    represented_rank: Rank
    pawn: PawnRef


@dataclass(frozen=True)
class SevenSubMove:
    pawn: PawnRef
    steps: int


@dataclass(frozen=True)
class PlaySevenSplitAction:
    player: PlayerId
    card_id: int
    represented_rank: Rank
    moves: tuple[SevenSubMove, ...]


@dataclass(frozen=True)
class PlayJackSwapAction:
    player: PlayerId
    card_id: int
    represented_rank: Rank
    source: PawnRef
    target: PawnRef


@dataclass(frozen=True)
class DiscardHandAction:
    player: PlayerId


@dataclass(frozen=True)
class SkipTurnAction:
    player: PlayerId


Action = Union[
    SwapCardAction,
    PlayStepCardAction,
    PlayEnterAction,
    PlaySevenSplitAction,
    PlayJackSwapAction,
    DiscardHandAction,
    SkipTurnAction,
]
