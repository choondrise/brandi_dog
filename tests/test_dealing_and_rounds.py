from __future__ import annotations

from dataclasses import replace

from brandi_dog.engine.actions import DiscardHandAction, SwapCardAction
from brandi_dog.engine.cards import Rank
from brandi_dog.engine.dealing import deal_new_round, draw_cards
from brandi_dog.engine.state import PlayerId, RoundStage, initial_hands

from .helpers import blank_state, make_engine, rank_card_id, with_player_hand


class FakeRng:
    def __init__(self, dice: list[int]):
        self._dice = list(dice)
        self.shuffle_calls = 0

    def randint(self, a: int, b: int) -> int:
        assert a == 1 and b == 6
        return self._dice.pop(0)

    def shuffle(self, x: list[int]) -> None:
        self.shuffle_calls += 1
        x.reverse()


def test_deal_schedule_switches_to_dice_rounds() -> None:
    engine = make_engine()
    rng = FakeRng(dice=[4, 6])

    state = blank_state(engine, stage=RoundStage.TEAM_SWAPS)
    state = replace(
        state,
        deal_round_index=-1,
        hands=initial_hands(),
        draw_pile=tuple(range(300)),
        discard_pile=(),
    )

    sizes: list[int] = []
    for _ in range(6):
        state = deal_new_round(state, rng)
        sizes.append(state.active_deal_size)
        state = replace(state, hands=initial_hands())

    assert sizes == [6, 5, 4, 3, 2, 4]


def test_draw_uses_existing_draw_pile_before_reshuffled_discard() -> None:
    rng = FakeRng(dice=[1])
    draw, discard, drawn = draw_cards(
        draw_pile=(1, 2),
        discard_pile=(3, 4, 5),
        count=4,
        rng=rng,
    )

    assert drawn == (2, 1, 3, 4)
    assert draw == (5,)
    assert discard == ()
    assert rng.shuffle_calls == 1


def test_round_starter_rotates_after_round_is_exhausted() -> None:
    engine = make_engine()
    two = rank_card_id(engine, Rank.TWO)

    state = blank_state(engine)
    state = replace(state, deal_round_index=0, round_starter=PlayerId.A1, play_current=PlayerId.A1)
    state = with_player_hand(state, PlayerId.A1, (two,))

    legal = engine.legal_actions(state)
    assert legal == (DiscardHandAction(player=PlayerId.A1),)

    next_state = engine.step(state, legal[0])
    assert next_state.round_starter == PlayerId.B1
    assert next_state.round_stage == RoundStage.TEAM_SWAPS


def test_swap_stage_requires_all_swaps_before_play_loop() -> None:
    engine = make_engine(seed=7)
    state = engine.reset()

    assert state.round_stage == RoundStage.TEAM_SWAPS

    expected_order = (PlayerId.A1, PlayerId.A2, PlayerId.B1, PlayerId.B2)
    for expected_player in expected_order:
        legal = engine.legal_actions(state)
        assert legal
        assert all(isinstance(action, SwapCardAction) and action.player == expected_player for action in legal)
        state = engine.step(state, legal[0])

    assert state.round_stage == RoundStage.PLAY_LOOP
    assert state.play_current == state.round_starter == PlayerId.A1
