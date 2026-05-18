from __future__ import annotations

import random
from dataclasses import replace
from typing import Optional

from .actions import Action
from .cards import Card, build_deck, card_map
from .dealing import RngProtocol, deal_new_round
from .rules import all_hands_empty, apply_action, legal_actions
from .state import (
    GameState,
    PlayerId,
    RoundStage,
    empty_swap_selections,
    initial_hands,
    initial_pawn_positions,
    initial_pawn_safe_entry_ready,
    next_in_play_order,
)


class GameEngine:
    def __init__(self, seed: Optional[int] = None, rng: Optional[RngProtocol] = None):
        if rng is not None and seed is not None:
            raise ValueError("Provide either seed or rng, not both")
        self.rng: RngProtocol = rng if rng is not None else random.Random(seed)
        self.cards: tuple[Card, ...] = build_deck()
        self.cards_by_id: dict[int, Card] = card_map(self.cards)

    def reset(self) -> GameState:
        draw_pile = [card.card_id for card in self.cards]
        self.rng.shuffle(draw_pile)

        state = GameState(
            round_stage=RoundStage.TEAM_SWAPS,
            deal_round_index=-1,
            round_starter=PlayerId.A1,
            play_current=PlayerId.A1,
            swap_cursor=0,
            swap_selections=empty_swap_selections(),
            active_deal_size=0,
            hands=initial_hands(),
            pawn_positions=initial_pawn_positions(),
            pawn_safe_entry_ready=initial_pawn_safe_entry_ready(),
            draw_pile=tuple(draw_pile),
            discard_pile=(),
            winner=None,
        )
        return deal_new_round(state, self.rng)

    def legal_actions(self, state: GameState) -> tuple[Action, ...]:
        return legal_actions(state, self.cards_by_id)

    def step(self, state: GameState, action: Action) -> GameState:
        updated = apply_action(state, action, self.cards_by_id)

        if updated.round_stage == RoundStage.GAME_OVER:
            return updated

        if all_hands_empty(updated):
            next_starter = next_in_play_order(updated.round_starter)
            updated = replace(updated, round_starter=next_starter, play_current=next_starter)
            updated = deal_new_round(updated, self.rng)

        return updated
