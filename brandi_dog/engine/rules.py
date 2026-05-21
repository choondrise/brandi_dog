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
    MAIN_TRACK_LENGTH,
    SAFE_ZONE_LENGTH,
    entry_index,
    is_direct_play_position,
    SimulatedPath,
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
    pawn_safe_entry_ready,
    next_in_play_order,
    player_finished,
    player_pawns,
    set_hand,
    set_pawn_position,
    set_pawn_safe_entry_ready,
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

    non_joker_ranks_in_hand = {
        cards_by_id[card_id].rank
        for card_id in hand
        if cards_by_id[card_id].rank != Rank.JOKER
    }

    actions: list[Action] = []
    for card_id in hand:
        card = cards_by_id[card_id]
        actions.extend(_legal_card_actions(state, player, card_id, card, non_joker_ranks_in_hand))

    if not actions:
        return (DiscardHandAction(player=player),)

    return tuple(actions)


def _legal_card_actions(
    state: GameState,
    player: PlayerId,
    card_id: int,
    card: Card,
    non_joker_ranks_in_hand: set[Rank],
) -> list[Action]:
    represented_ranks = _represented_ranks_for_card(card.rank, non_joker_ranks_in_hand)
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


def _represented_ranks_for_card(card_rank: Rank, non_joker_ranks_in_hand: set[Rank]) -> tuple[Rank, ...]:
    if card_rank != Rank.JOKER:
        return (card_rank,)
    return tuple(rank for rank in Rank if rank != Rank.JOKER and rank not in non_joker_ranks_in_hand)


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
    for pawn in player_pawns(owner):
        if simulate_entry_from_base(state, pawn) is None:
            continue
        return [
            PlayEnterAction(
                player=player,
                card_id=card_id,
                represented_rank=represented_rank,
                pawn=pawn,
            )
        ]
    return []


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
        for prefer_safe_entry, path in _step_path_candidates(state, pawn, direction=direction, steps=steps):
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
                    prefer_safe_entry=prefer_safe_entry,
                )
            )
    return actions


def _step_path_candidates(
    state: GameState,
    pawn: PawnRef,
    direction: MoveDirection,
    steps: int,
) -> tuple[tuple[bool, SimulatedPath], ...]:
    if direction == MoveDirection.BACKWARD:
        path = simulate_step_move(state, pawn, direction=direction, steps=steps, prefer_safe_entry=True)
        if path is None:
            return ()
        return ((True, path),)

    preferred = simulate_step_move(state, pawn, direction=direction, steps=steps, prefer_safe_entry=True)
    non_entering = simulate_step_move(state, pawn, direction=direction, steps=steps, prefer_safe_entry=False)

    candidates: list[tuple[bool, SimulatedPath]] = []
    if preferred is not None:
        candidates.append((True, preferred))

    if non_entering is not None:
        duplicate = preferred is not None and non_entering == preferred
        if not duplicate:
            candidates.append((False, non_entering))

    return tuple(candidates)


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
    pawns = tuple(
        pawn
        for owner in owners
        for pawn in player_pawns(owner)
        if get_pawn_position(state, pawn).kind != PositionKind.BASE
    )
    actions: list[Action] = []

    for allocation in _seven_step_allocations(len(pawns), total=7):
        raw_moves = [
            SevenSubMove(pawn=pawn, steps=steps)
            for pawn, steps in zip(pawns, allocation)
            if steps > 0
        ]
        if not raw_moves:
            continue

        ordered_moves = tuple(
            sorted(
                raw_moves,
                key=lambda move: (_pawn_progress_for_seven_order(state, move.pawn), -int(move.pawn.owner), -move.pawn.number),
                reverse=True,
            )
        )
        actions.extend(
            _seven_actions_for_ordered_allocation(
                state=state,
                player=player,
                card_id=card_id,
                represented_rank=represented_rank,
                is_joker=is_joker,
                ordered_moves=ordered_moves,
            )
        )

    return actions


def _seven_step_allocations(num_pawns: int, total: int) -> tuple[tuple[int, ...], ...]:
    if num_pawns <= 0:
        return ()
    allocations: list[tuple[int, ...]] = []

    def build(index: int, remaining: int, current: list[int]) -> None:
        if index == num_pawns - 1:
            allocations.append(tuple(current + [remaining]))
            return
        for steps in range(remaining + 1):
            current.append(steps)
            build(index + 1, remaining - steps, current)
            current.pop()

    build(0, total, [])
    return tuple(allocations)


def _seven_actions_for_ordered_allocation(
    state: GameState,
    player: PlayerId,
    card_id: int,
    represented_rank: Rank,
    is_joker: bool,
    ordered_moves: tuple[SevenSubMove, ...],
) -> list[Action]:
    actions: list[Action] = []

    def build(current_state: GameState, index: int, moves: list[SevenSubMove]) -> None:
        if index >= len(ordered_moves):
            actions.append(
                PlaySevenSplitAction(
                    player=player,
                    card_id=card_id,
                    represented_rank=represented_rank,
                    moves=tuple(moves),
                )
            )
            return

        move = ordered_moves[index]
        for prefer_safe_entry, path in _step_path_candidates(
            current_state,
            move.pawn,
            direction=MoveDirection.FORWARD,
            steps=move.steps,
        ):
            if is_joker and _joker_last_pawn_safe_entry_violation(current_state, move.pawn, path.entered_safe_from_track):
                continue
            next_state = _apply_move_path(
                current_state,
                pawn=move.pawn,
                end=path.end,
                traversed_open_track=path.traversed_open_track_indices,
                crossed_own_entry_from_behind=path.crossed_own_entry_from_behind,
                pass_capture=True,
            )
            moves.append(SevenSubMove(pawn=move.pawn, steps=move.steps, prefer_safe_entry=prefer_safe_entry))
            build(next_state, index + 1, moves)
            moves.pop()

    build(state, 0, [])
    return actions


def _pawn_progress_for_seven_order(state: GameState, pawn: PawnRef) -> int:
    position = get_pawn_position(state, pawn)
    if position.kind == PositionKind.SAFE and position.index is not None:
        return MAIN_TRACK_LENGTH + position.index + 1
    if position.kind == PositionKind.TRACK and position.index is not None:
        progress = 1 + ((position.index - entry_index(pawn.owner)) % MAIN_TRACK_LENGTH)
        if pawn_safe_entry_ready(state, pawn):
            progress += MAIN_TRACK_LENGTH
        return progress
    return -1


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
    updated = set_pawn_safe_entry_ready(updated, action.pawn, False)
    updated = _consume_played_card(updated, action.player, action.card_id)
    return _finalize_play_transition(updated)


def _apply_play_step_action(state: GameState, action: PlayStepCardAction, cards_by_id: dict[int, Card]) -> GameState:
    _assert_card_identity(cards_by_id, action.card_id, action.represented_rank)

    path = simulate_step_move(
        state,
        action.pawn,
        direction=action.direction,
        steps=action.steps,
        prefer_safe_entry=action.prefer_safe_entry,
    )
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
        crossed_own_entry_from_behind=path.crossed_own_entry_from_behind,
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

        path = simulate_step_move(
            updated,
            move.pawn,
            direction=MoveDirection.FORWARD,
            steps=move.steps,
            prefer_safe_entry=move.prefer_safe_entry,
        )
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
            crossed_own_entry_from_behind=path.crossed_own_entry_from_behind,
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
    crossed_own_entry_from_behind: bool,
    pass_capture: bool,
) -> GameState:
    updated = state

    if pass_capture:
        for track_index in traversed_open_track:
            victim = track_occupant(updated, track_index, ignore=[pawn])
            if victim is not None:
                updated = set_pawn_position(updated, victim, base_position())
                updated = set_pawn_safe_entry_ready(updated, victim, False)

    updated = set_pawn_position(updated, pawn, end)
    if crossed_own_entry_from_behind:
        updated = set_pawn_safe_entry_ready(updated, pawn, True)

    if end.kind == PositionKind.TRACK and end.index is not None:
        victim = track_occupant(updated, end.index, ignore=[pawn])
        if victim is not None:
            updated = set_pawn_position(updated, victim, base_position())
            updated = set_pawn_safe_entry_ready(updated, victim, False)

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
