from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Optional

from .actions import (
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
from .board import (
    SAFE_ZONE_LENGTH,
    entry_index,
    is_direct_play_position,
    simulate_entry_from_base,
    simulate_step_move,
    track_occupant,
)
from .cards import Card, NUMERIC_FORWARD_VALUES, Rank
from .state import (
    GameState,
    PawnRef,
    PlayerId,
    PositionKind,
    RoundStage,
    active_swap_player,
    base_position,
    get_pawn_position,
    hand_of,
    next_in_play_order,
    player_finished,
    player_pawns,
    set_hand,
    set_pawn_position,
    team_winner,
    teammate_of,
)


def legal_actions(state: GameState, cards_by_id: dict[int, Card]) -> tuple[Action, ...]:
    if state.round_stage == RoundStage.GAME_OVER:
        return ()
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return _legal_swap_actions(state)
    if state.round_stage == RoundStage.PLAY_LOOP:
        return _legal_play_actions(state, cards_by_id)
    return ()


def validate_action(state: GameState, action: Action, cards_by_id: dict[int, Card]) -> bool:
    return action in legal_actions(state, cards_by_id)


def apply_action(state: GameState, action: Action, cards_by_id: dict[int, Card]) -> GameState:
    if not validate_action(state, action, cards_by_id):
        raise ValueError(f"Illegal action for current state: {action}")

    if isinstance(action, SwapCardAction):
        return _apply_swap_action(state, action)
    if isinstance(action, SkipTurnAction):
        return replace(state, play_current=next_in_play_order(state.play_current))
    if isinstance(action, DiscardHandAction):
        return _apply_discard_hand_action(state, action)
    if isinstance(action, PlayEnterAction):
        return _apply_play_enter_action(state, action, cards_by_id)
    if isinstance(action, PlayStepCardAction):
        return _apply_play_step_action(state, action, cards_by_id)
    if isinstance(action, PlayJackSwapAction):
        return _apply_play_jack_action(state, action, cards_by_id)
    if isinstance(action, PlaySevenSplitAction):
        return _apply_play_seven_action(state, action, cards_by_id)

    raise TypeError(f"Unsupported action type: {type(action)}")


def all_hands_empty(state: GameState) -> bool:
    return all(len(hand) == 0 for hand in state.hands)


def _legal_swap_actions(state: GameState) -> tuple[Action, ...]:
    chooser = active_swap_player(state)
    hand = hand_of(state, chooser)
    return tuple(SwapCardAction(player=chooser, card_id=card_id) for card_id in hand)


def _legal_play_actions(state: GameState, cards_by_id: dict[int, Card]) -> tuple[Action, ...]:
    player = state.play_current
    hand = hand_of(state, player)

    if not hand:
        return (SkipTurnAction(player=player),)

    actions: list[Action] = []
    for card_id in hand:
        card = cards_by_id[card_id]
        actions.extend(_legal_card_actions(state, player, card_id, card))

    if not actions:
        return (DiscardHandAction(player=player),)

    return tuple(actions)


def _legal_card_actions(state: GameState, player: PlayerId, card_id: int, card: Card) -> list[Action]:
    represented_ranks = (card.rank,) if card.rank != Rank.JOKER else tuple(r for r in Rank if r != Rank.JOKER)
    is_joker = card.rank == Rank.JOKER

    actions: list[Action] = []
    for represented in represented_ranks:
        if represented == Rank.ACE:
            actions.extend(_legal_entry_actions(state, player, card_id, represented))
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=1, direction=MoveDirection.FORWARD, is_joker=is_joker))
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=11, direction=MoveDirection.FORWARD, is_joker=is_joker))
        elif represented == Rank.KING:
            actions.extend(_legal_entry_actions(state, player, card_id, represented))
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=13, direction=MoveDirection.FORWARD, is_joker=is_joker))
        elif represented == Rank.FOUR:
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=4, direction=MoveDirection.FORWARD, is_joker=is_joker))
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=4, direction=MoveDirection.BACKWARD, is_joker=is_joker))
        elif represented == Rank.SEVEN:
            actions.extend(_legal_seven_actions(state, player, card_id, represented, is_joker=is_joker))
        elif represented == Rank.JACK:
            actions.extend(_legal_jack_actions(state, player, card_id, represented))
        elif represented in NUMERIC_FORWARD_VALUES:
            steps = NUMERIC_FORWARD_VALUES[represented]
            actions.extend(_legal_step_actions(state, player, card_id, represented, steps=steps, direction=MoveDirection.FORWARD, is_joker=is_joker))
        else:
            raise ValueError(f"Unsupported represented rank: {represented}")

    return actions


def _controlled_owner_for_turn(state: GameState, player: PlayerId) -> PlayerId:
    if player_finished(state, player):
        return teammate_of(player)
    return player


def _seven_allowed_owners(state: GameState, player: PlayerId) -> tuple[PlayerId, ...]:
    if player_finished(state, player):
        return (teammate_of(player),)
    return (player, teammate_of(player))


def _legal_entry_actions(state: GameState, player: PlayerId, card_id: int, represented_rank: Rank) -> list[Action]:
    owner = _controlled_owner_for_turn(state, player)
    actions: list[Action] = []
    for pawn in player_pawns(owner):
        if simulate_entry_from_base(state, pawn) is None:
            continue
        actions.append(
            PlayEnterAction(
                player=player,
                card_id=card_id,
                represented_rank=represented_rank,
                pawn=pawn,
            )
        )
    return actions


def _legal_step_actions(
    state: GameState,
    player: PlayerId,
    card_id: int,
    represented_rank: Rank,
    steps: int,
    direction: MoveDirection,
    is_joker: bool,
) -> list[Action]:
    owner = _controlled_owner_for_turn(state, player)
    actions: list[Action] = []
    for pawn in player_pawns(owner):
        path = simulate_step_move(state, pawn, direction=direction, steps=steps)
        if path is None:
            continue
        if is_joker and _joker_last_pawn_safe_entry_violation(state, pawn, path.entered_safe_from_track):
            continue
        actions.append(
            PlayStepCardAction(
                player=player,
                card_id=card_id,
                represented_rank=represented_rank,
                pawn=pawn,
                steps=steps,
                direction=direction,
            )
        )
    return actions


def _legal_jack_actions(state: GameState, player: PlayerId, card_id: int, represented_rank: Rank) -> list[Action]:
    owner = _controlled_owner_for_turn(state, player)
    actions: list[Action] = []

    source_candidates = [pawn for pawn in player_pawns(owner) if is_direct_play_position(get_pawn_position(state, pawn))]
    target_candidates = [
        pawn
        for other_player in PlayerId
        for pawn in player_pawns(other_player)
        if other_player != owner and is_direct_play_position(get_pawn_position(state, pawn))
    ]

    for source in source_candidates:
        for target in target_candidates:
            actions.append(
                PlayJackSwapAction(
                    player=player,
                    card_id=card_id,
                    represented_rank=represented_rank,
                    source=source,
                    target=target,
                )
            )

    return actions


def _legal_seven_actions(
    state: GameState,
    player: PlayerId,
    card_id: int,
    represented_rank: Rank,
    is_joker: bool,
) -> list[Action]:
    owners = _seven_allowed_owners(state, player)
    pawns = tuple(pawn for owner in owners for pawn in player_pawns(owner))
    actions: list[Action] = []

    def dfs(current_state: GameState, remaining: int, moves: list[SevenSubMove]) -> None:
        if remaining == 0:
            if moves:
                actions.append(
                    PlaySevenSplitAction(
                        player=player,
                        card_id=card_id,
                        represented_rank=represented_rank,
                        moves=tuple(moves),
                    )
                )
            return

        for pawn in pawns:
            for step_count in range(1, remaining + 1):
                path = simulate_step_move(current_state, pawn, direction=MoveDirection.FORWARD, steps=step_count)
                if path is None:
                    continue
                if is_joker and _joker_last_pawn_safe_entry_violation(current_state, pawn, path.entered_safe_from_track):
                    continue
                next_state = _apply_move_path(
                    current_state,
                    pawn=pawn,
                    end=path.end,
                    traversed_open_track=path.traversed_open_track_indices,
                    pass_capture=True,
                )
                moves.append(SevenSubMove(pawn=pawn, steps=step_count))
                dfs(next_state, remaining - step_count, moves)
                moves.pop()

    dfs(state, remaining=7, moves=[])
    return actions


def _joker_last_pawn_safe_entry_violation(state: GameState, pawn: PawnRef, entered_safe_from_track: bool) -> bool:
    if not entered_safe_from_track:
        return False
    safe_count = sum(1 for p in player_pawns(pawn.owner) if get_pawn_position(state, p).kind == PositionKind.SAFE)
    return safe_count == SAFE_ZONE_LENGTH - 1


def _apply_swap_action(state: GameState, action: SwapCardAction) -> GameState:
    selections = list(state.swap_selections)
    selections[int(action.player)] = action.card_id
    updated = replace(state, swap_cursor=state.swap_cursor + 1, swap_selections=tuple(selections))

    teammate = teammate_of(action.player)
    this_card = updated.swap_selections[int(action.player)]
    mate_card = updated.swap_selections[int(teammate)]

    if this_card is not None and mate_card is not None:
        updated = _swap_cards(updated, action.player, teammate, this_card, mate_card)
        selections = list(updated.swap_selections)
        selections[int(action.player)] = None
        selections[int(teammate)] = None
        updated = replace(updated, swap_selections=tuple(selections))

    if updated.swap_cursor >= 4:
        updated = replace(updated, round_stage=RoundStage.PLAY_LOOP, play_current=updated.round_starter)

    return updated


def _swap_cards(state: GameState, first: PlayerId, second: PlayerId, first_card: int, second_card: int) -> GameState:
    hands = list(state.hands)

    first_hand = list(hands[int(first)])
    second_hand = list(hands[int(second)])

    first_hand.remove(first_card)
    second_hand.remove(second_card)

    first_hand.append(second_card)
    second_hand.append(first_card)

    hands[int(first)] = tuple(first_hand)
    hands[int(second)] = tuple(second_hand)

    return replace(state, hands=tuple(hands))


def _apply_discard_hand_action(state: GameState, action: DiscardHandAction) -> GameState:
    hand = hand_of(state, action.player)
    updated = set_hand(state, action.player, ())
    updated = replace(updated, discard_pile=updated.discard_pile + hand)
    return replace(updated, play_current=next_in_play_order(updated.play_current))


def _apply_play_enter_action(state: GameState, action: PlayEnterAction, cards_by_id: dict[int, Card]) -> GameState:
    _assert_card_identity(cards_by_id, action.card_id, action.represented_rank)

    path = simulate_entry_from_base(state, action.pawn)
    if path is None:
        raise ValueError("Invalid entry action")

    updated = set_pawn_position(state, action.pawn, path.end)
    updated = _consume_played_card(updated, action.player, action.card_id)
    return _finalize_play_transition(updated)


def _apply_play_step_action(state: GameState, action: PlayStepCardAction, cards_by_id: dict[int, Card]) -> GameState:
    _assert_card_identity(cards_by_id, action.card_id, action.represented_rank)

    path = simulate_step_move(state, action.pawn, direction=action.direction, steps=action.steps)
    if path is None:
        raise ValueError("Invalid step move action")

    if cards_by_id[action.card_id].rank == Rank.JOKER and _joker_last_pawn_safe_entry_violation(
        state, action.pawn, path.entered_safe_from_track
    ):
        raise ValueError("Joker cannot be used for last pawn entering safe zone")

    updated = _apply_move_path(
        state,
        pawn=action.pawn,
        end=path.end,
        traversed_open_track=path.traversed_open_track_indices,
        pass_capture=False,
    )
    updated = _consume_played_card(updated, action.player, action.card_id)
    return _finalize_play_transition(updated)


def _apply_play_jack_action(state: GameState, action: PlayJackSwapAction, cards_by_id: dict[int, Card]) -> GameState:
    _assert_card_identity(cards_by_id, action.card_id, action.represented_rank)

    owner = _controlled_owner_for_turn(state, action.player)
    if action.source.owner != owner:
        raise ValueError("Jack source pawn is not controllable by player")
    if action.target.owner == owner:
        raise ValueError("Jack target must belong to a different player")

    source_position = get_pawn_position(state, action.source)
    target_position = get_pawn_position(state, action.target)
    if not is_direct_play_position(source_position) or not is_direct_play_position(target_position):
        raise ValueError("Jack source/target must be in direct play")

    updated = set_pawn_position(state, action.source, target_position)
    updated = set_pawn_position(updated, action.target, source_position)
    updated = _consume_played_card(updated, action.player, action.card_id)
    return _finalize_play_transition(updated)


def _apply_play_seven_action(state: GameState, action: PlaySevenSplitAction, cards_by_id: dict[int, Card]) -> GameState:
    _assert_card_identity(cards_by_id, action.card_id, action.represented_rank)

    if sum(move.steps for move in action.moves) != 7:
        raise ValueError("Seven split must total exactly 7")

    owners = set(_seven_allowed_owners(state, action.player))
    updated = state

    for move in action.moves:
        if move.steps <= 0:
            raise ValueError("Seven split segments must be positive")
        if move.pawn.owner not in owners:
            raise ValueError("Seven split includes a pawn outside the controllable set")

        path = simulate_step_move(updated, move.pawn, direction=MoveDirection.FORWARD, steps=move.steps)
        if path is None:
            raise ValueError("Invalid seven split move segment")

        if cards_by_id[action.card_id].rank == Rank.JOKER and _joker_last_pawn_safe_entry_violation(
            updated, move.pawn, path.entered_safe_from_track
        ):
            raise ValueError("Joker cannot be used for last pawn entering safe zone")

        updated = _apply_move_path(
            updated,
            pawn=move.pawn,
            end=path.end,
            traversed_open_track=path.traversed_open_track_indices,
            pass_capture=True,
        )

        winner = team_winner(updated)
        if winner is not None:
            break

    updated = _consume_played_card(updated, action.player, action.card_id)
    return _finalize_play_transition(updated)


def _apply_move_path(
    state: GameState,
    pawn: PawnRef,
    end,
    traversed_open_track: tuple[int, ...],
    pass_capture: bool,
) -> GameState:
    updated = state

    if pass_capture:
        for track_index in traversed_open_track:
            victim = track_occupant(updated, track_index, ignore=[pawn])
            if victim is not None:
                updated = set_pawn_position(updated, victim, base_position())

    updated = set_pawn_position(updated, pawn, end)

    if end.kind == PositionKind.TRACK and end.index is not None:
        victim = track_occupant(updated, end.index, ignore=[pawn])
        if victim is not None:
            updated = set_pawn_position(updated, victim, base_position())

    return updated


def _consume_played_card(state: GameState, player: PlayerId, card_id: int) -> GameState:
    hand = list(hand_of(state, player))
    hand.remove(card_id)
    updated = set_hand(state, player, tuple(hand))
    return replace(updated, discard_pile=updated.discard_pile + (card_id,))


def _finalize_play_transition(state: GameState) -> GameState:
    winner = team_winner(state)
    if winner is not None:
        return replace(state, round_stage=RoundStage.GAME_OVER, winner=winner)
    return replace(state, play_current=next_in_play_order(state.play_current))


def _assert_card_identity(cards_by_id: dict[int, Card], card_id: int, represented_rank: Rank) -> None:
    card = cards_by_id[card_id]
    if card.rank == Rank.JOKER:
        if represented_rank == Rank.JOKER:
            raise ValueError("Joker must represent a non-joker rank")
        return
    if card.rank != represented_rank:
        raise ValueError(f"Card rank mismatch: card={card.rank}, represented={represented_rank}")
