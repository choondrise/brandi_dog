from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brandi_dog.agents.heuristic_agent import HeuristicAgent
from brandi_dog.engine.actions import (
    Action,
    DiscardHandAction,
    MoveDirection,
    PlayEnterAction,
    PlayJackSwapAction,
    PlaySevenSplitAction,
    PlayStepCardAction,
    SkipTurnAction,
    SwapCardAction,
)
from brandi_dog.engine.cards import Card, render_card
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PawnRef,
    PlayerId,
    PositionKind,
    RoundStage,
    active_swap_player,
    get_pawn_position,
    hand_of,
    player_pawns,
)


ENTRY_OWNER_BY_INDEX: dict[int, PlayerId] = {
    0: PlayerId.A1,
    16: PlayerId.B1,
    32: PlayerId.A2,
    48: PlayerId.B2,
}

SAFE_COORDS: dict[PlayerId, tuple[tuple[int, int], ...]] = {
    PlayerId.A1: ((1, 3), (2, 4), (3, 5), (4, 6)),
    PlayerId.B1: ((1, 13), (2, 12), (3, 11), (4, 10)),
    PlayerId.A2: ((15, 13), (14, 12), (13, 11), (12, 10)),
    PlayerId.B2: ((15, 3), (14, 4), (13, 5), (12, 6)),
}

PLAYER_COLORS: dict[PlayerId, str] = {
    PlayerId.A1: "#D6433B",
    PlayerId.B1: "#2FA44F",
    PlayerId.A2: "#345CC8",
    PlayerId.B2: "#D8B216",
}


class TkBoardRenderer:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._tk = None
        self.root = None
        self.canvas = None
        self._width = 900
        self._height = 1000
        self._cx = self._width / 2
        self._cy = self._height / 2
        self._track_radius = 330
        self._hole_radius = 12
        self._safe_step = 45
        self._base_step = 40

        self._track_coords = [self._track_coord(i) for i in range(64)]
        self._safe_coords = {player: self._safe_coords_for_player(player) for player in PlayerId}
        self._base_coords = {player: self._base_coords_for_player(player) for player in PlayerId}

        if not enabled:
            return

        try:
            import tkinter as tk
        except Exception as exc:
            print(f"GUI disabled: tkinter not available ({exc}).")
            self.enabled = False
            return

        self._tk = tk
        try:
            self.root = tk.Tk()
        except Exception as exc:
            print(f"GUI disabled: unable to open a display ({exc}).")
            self.enabled = False
            return
        # self.root.title("Brandi Dog Board")
        self.canvas = tk.Canvas(self.root, width=self._width, height=self._height, bg="#E6E6E6", highlightthickness=0)
        self.canvas.pack()
        self._draw_static_board()
        self.refresh()

    def _angle_for_index(self, index: int) -> float:
        return math.radians(-90 + (index * 360.0 / 64.0))

    def _player_entry_angle(self, player: PlayerId) -> float:
        return self._angle_for_index(ENTRY_OWNER_BY_INDEX_INV[player])

    def _track_coord(self, index: int) -> tuple[float, float]:
        angle = self._angle_for_index(index)
        return (
            self._cx + (self._track_radius * math.cos(angle)),
            self._cy + (self._track_radius * math.sin(angle)),
        )

    def _safe_coords_for_player(self, player: PlayerId) -> tuple[tuple[float, float], ...]:
        angle = self._player_entry_angle(player)
        ux = math.cos(angle)
        uy = math.sin(angle)
        coords: list[tuple[float, float]] = []
        for idx in range(4):
            radius = self._track_radius - ((idx + 1) * self._safe_step)
            coords.append((self._cx + (radius * ux), self._cy + (radius * uy)))
        return tuple(coords)

    def _base_coords_for_player(self, player: PlayerId) -> tuple[tuple[float, float], ...]:
        angle = self._player_entry_angle(player)
        ux = math.cos(angle)
        uy = math.sin(angle)
        tx = -uy
        ty = ux
        center_x = self._cx + ((self._track_radius + 85) * ux)
        center_y = self._cy + ((self._track_radius + 85) * uy)
        coords: list[tuple[float, float]] = []
        for i in range(4):
            offset = (i - 1.5) * self._base_step
            coords.append((center_x + (offset * tx), center_y + (offset * ty)))
        return tuple(coords)

    def _draw_circle(self, x: float, y: float, radius: float, fill: str, outline: str, width: int = 2) -> None:
        assert self.canvas is not None
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline=outline, width=width)

    def _draw_static_board(self) -> None:
        if not self.enabled or self.canvas is None:
            return

        c = self.canvas
        c.delete("all")

        # Board body (octagon) + center well.
        board_radius = 400
        points: list[float] = []
        for i in range(8):
            ang = math.radians(22.5 + (i * 45))
            points.extend([self._cx + (board_radius * math.cos(ang)), self._cy + (board_radius * math.sin(ang))])
        c.create_polygon(points, fill="#E6C49A", outline="#B9946D", width=5)
        c.create_oval(self._cx - 155, self._cy - 155, self._cx + 155, self._cy + 155, fill="#F3F3F3", outline="#D7D7D7", width=3)

        # Main track sockets.
        for idx, (x, y) in enumerate(self._track_coords):
            owner = ENTRY_OWNER_BY_INDEX.get(idx)
            if owner is None:
                self._draw_circle(x, y, self._hole_radius, fill="#DAB892", outline="#C7A07A", width=2)
            else:
                self._draw_circle(x, y, self._hole_radius, fill="#F8E9D6", outline=PLAYER_COLORS[owner], width=3)

        # Safe lanes.
        for player, coords in self._safe_coords.items():
            color = PLAYER_COLORS[player]
            for x, y in coords:
                self._draw_circle(x, y, self._hole_radius, fill="#F8E9D6", outline=color, width=3)

        # Base sockets + labels.
        for player, coords in self._base_coords.items():
            color = PLAYER_COLORS[player]
            for x, y in coords:
                self._draw_circle(x, y, self._hole_radius + 2, fill="#F8E9D6", outline=color, width=3)
            lx, ly = coords[0]
            c.create_text(lx - 28, ly, text=player.name, fill=color, font=("Helvetica", 11, "bold"), anchor="e")

        c.create_text(
            self._cx,
            self._cy,
            text="Brandi Dog",
            fill="#397B42",
            font=("Helvetica", 18, "bold"),
        )

    def _pawn_position(self, state: GameState, pawn: PawnRef) -> tuple[float, float]:
        position = get_pawn_position(state, pawn)
        if position.kind == PositionKind.TRACK and position.index is not None:
            return self._track_coords[position.index]
        if position.kind == PositionKind.SAFE and position.index is not None:
            return self._safe_coords[pawn.owner][position.index]
        return self._base_coords[pawn.owner][pawn.number]

    def render(self, state: GameState, actor: PlayerId, turn_index: int, human_player: PlayerId) -> None:
        if not self.enabled or self.canvas is None:
            return

        self._draw_static_board()

        for pawn in _all_pawns():
            x, y = self._pawn_position(state, pawn)
            color = PLAYER_COLORS[pawn.owner]
            self._draw_circle(x, y, self._hole_radius + 2, fill=color, outline="#2A2A2A", width=2)
            self.canvas.create_text(x, y + 1, text=str(pawn.number), fill="#FFFFFF", font=("Helvetica", 8, "bold"))

        self.canvas.create_text(
            self._cx,
            20,
            text=(
                f"Turn {turn_index} | Stage: {state.round_stage.value} | "
                f"Round #{state.deal_round_index} | Actor: {actor.name} | You: {human_player.name}"
            ),
            fill="#222222",
            font=("Helvetica", 12, "bold"),
        )
        self.refresh()

    def refresh(self) -> None:
        if not self.enabled or self.root is None:
            return
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            self.enabled = False

    def close(self) -> None:
        if not self.enabled or self.root is None:
            return
        try:
            self.root.destroy()
        except Exception:
            pass


ENTRY_OWNER_BY_INDEX_INV: dict[PlayerId, int] = {owner: index for index, owner in ENTRY_OWNER_BY_INDEX.items()}


def _pawn_code(pawn: PawnRef) -> str:
    return f"{pawn.owner.name}{pawn.number}"


def _track_coord(index: int) -> tuple[int, int]:
    if 0 <= index <= 16:
        return 0, index
    if 17 <= index <= 32:
        return index - 16, 16
    if 33 <= index <= 48:
        return 16, 48 - index
    if 49 <= index <= 63:
        return 64 - index, 0
    raise ValueError(f"Track index out of range: {index}")


def _all_pawns() -> Iterable[PawnRef]:
    for player in PlayerId:
        yield from player_pawns(player)


def _format_hand(state: GameState, player: PlayerId, cards_by_id: dict[int, Card]) -> str:
    cards = hand_of(state, player)
    if not cards:
        return "-"
    return ", ".join(f"{card_id}:{render_card(cards_by_id[card_id].rank)}" for card_id in cards)


def _board_grid(state: GameState) -> list[list[str]]:
    grid = [["   " for _ in range(17)] for _ in range(17)]

    for idx in range(64):
        row, col = _track_coord(idx)
        owner = ENTRY_OWNER_BY_INDEX.get(idx)
        if owner is None:
            grid[row][col] = " . "
        else:
            grid[row][col] = f"E{owner.name}"

    for player, coords in SAFE_COORDS.items():
        marker = f"S{player.name}"
        for row, col in coords:
            grid[row][col] = marker

    for pawn in _all_pawns():
        position = get_pawn_position(state, pawn)
        if position.kind == PositionKind.TRACK and position.index is not None:
            row, col = _track_coord(position.index)
            grid[row][col] = _pawn_code(pawn)
        elif position.kind == PositionKind.SAFE and position.index is not None:
            row, col = SAFE_COORDS[pawn.owner][position.index]
            grid[row][col] = _pawn_code(pawn)

    return grid


def _print_board(state: GameState) -> None:
    print("\n=== BOARD ===")
    for row in _board_grid(state):
        print(" ".join(f"{cell:>3}" for cell in row))

    print("\nBase pawns:")
    for player in PlayerId:
        in_base: list[str] = []
        for pawn in player_pawns(player):
            if get_pawn_position(state, pawn).kind == PositionKind.BASE:
                in_base.append(str(pawn.number))
        print(f"  {player.name}: {', '.join(in_base) if in_base else '-'}")


def _card_descriptor(card_id: int, represented_rank, cards_by_id: dict[int, Card]) -> str:
    actual_rank = cards_by_id[card_id].rank
    actual = render_card(actual_rank)
    represented = render_card(represented_rank)
    if represented == actual:
        return f"{card_id}:{actual}"
    return f"{card_id}:{actual} as {represented}"


def _describe_action(action: Action, cards_by_id: dict[int, Card]) -> str:
    if isinstance(action, SwapCardAction):
        rank = render_card(cards_by_id[action.card_id].rank)
        return f"Swap card {action.card_id}:{rank} with teammate"

    if isinstance(action, PlayEnterAction):
        card_desc = _card_descriptor(action.card_id, action.represented_rank, cards_by_id)
        return f"Play {card_desc} to enter pawn {action.pawn.owner.name}.{action.pawn.number}"

    if isinstance(action, PlayStepCardAction):
        card_desc = _card_descriptor(action.card_id, action.represented_rank, cards_by_id)
        sign = "+" if action.direction == MoveDirection.FORWARD else "-"
        detail = (
            f"Play {card_desc} move pawn {action.pawn.owner.name}.{action.pawn.number} "
            f"{sign}{action.steps}"
        )
        if action.direction == MoveDirection.FORWARD and not action.prefer_safe_entry:
            detail += " (continue on track)"
        return detail

    if isinstance(action, PlayJackSwapAction):
        card_desc = _card_descriptor(action.card_id, action.represented_rank, cards_by_id)
        source = f"{action.source.owner.name}.{action.source.number}"
        target = f"{action.target.owner.name}.{action.target.number}"
        return f"Play {card_desc} swap {source} <-> {target}"

    if isinstance(action, PlaySevenSplitAction):
        card_desc = _card_descriptor(action.card_id, action.represented_rank, cards_by_id)
        segments = ", ".join(
            (
                f"{move.pawn.owner.name}.{move.pawn.number}+{move.steps}"
                if move.prefer_safe_entry
                else f"{move.pawn.owner.name}.{move.pawn.number}+{move.steps}(track)"
            )
            for move in action.moves
        )
        return f"Play {card_desc} split as [{segments}]"

    if isinstance(action, DiscardHandAction):
        return "Discard current hand (no legal play)"

    if isinstance(action, SkipTurnAction):
        return "Skip turn (empty hand)"

    return repr(action)


def _current_actor(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def _prompt_human_action(legal: tuple[Action, ...], cards_by_id: dict[int, Card]) -> Action:
    print("\nYour legal actions:")
    for idx, action in enumerate(legal, start=1):
        print(f"  {idx}. {_describe_action(action, cards_by_id)}")

    while True:
        raw = input("Choose action number (or 'q' to quit): ").strip().lower()
        if raw in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if not raw.isdigit():
            print("Invalid input. Enter a number.")
            continue
        choice = int(raw)
        if choice < 1 or choice > len(legal):
            print(f"Choice out of range. Enter 1..{len(legal)}.")
            continue
        return legal[choice - 1]


def run_game(
    seed: Optional[int],
    human_player: PlayerId,
    max_turns: int = 5000,
    use_gui: bool = True,
    text_board: bool = False,
    bot_agent: str = "smart",
) -> None:
    engine = GameEngine(seed=seed)
    bots: Dict[PlayerId, object] = {}
    for player in PlayerId:
        if player == human_player:
            continue
        bot_seed = None if seed is None else (seed * 17 + int(player))
        if bot_agent == "smart":
            bots[player] = HeuristicAgent(seed=bot_seed)
        else:
            from brandi_dog.agents.random_legal_agent import RandomLegalAgent

            bots[player] = RandomLegalAgent(seed=bot_seed)

    renderer = TkBoardRenderer(enabled=use_gui)
    state = engine.reset()
    turn_index = 1

    print(f"Human player: {human_player.name}")
    print(f"Bot agent: {bot_agent}")
    if renderer.enabled:
        print("GUI board window enabled.")
    else:
        print("GUI board window disabled.")
    if text_board or not renderer.enabled:
        print("Legend: E* = entry fields, S* = safe slots, A1/B1/A2/B2# = pawn")

    try:
        while state.round_stage != RoundStage.GAME_OVER and turn_index <= max_turns:
            actor = _current_actor(state)
            print("\n" + "=" * 72)
            print(
                f"Turn {turn_index} | Stage: {state.round_stage.value} | "
                f"Round #{state.deal_round_index} | Actor: {actor.name}"
            )

            renderer.render(state, actor=actor, turn_index=turn_index, human_player=human_player)
            if text_board or not renderer.enabled:
                _print_board(state)

            print("\nHands:")
            for player in PlayerId:
                prefix = "YOU" if player == human_player else "BOT"
                hand_text = _format_hand(state, player, engine.cards_by_id)
                print(f"  {prefix} {player.name}: {hand_text}")

            options = engine.legal_actions(state)
            if not options:
                raise RuntimeError("No legal actions available for current actor")

            if actor == human_player:
                renderer.refresh()
                action = _prompt_human_action(options, engine.cards_by_id)
            else:
                action = bots[actor].select_action(engine, state)
                print(f"\n{actor.name} chooses: {_describe_action(action, engine.cards_by_id)}")

            state = engine.step(state, action)
            renderer.refresh()
            turn_index += 1
    except KeyboardInterrupt:
        print("\nGame stopped by user.")
        renderer.close()
        return

    print("\n" + "=" * 72)
    actor = _current_actor(state)
    renderer.render(state, actor=actor, turn_index=turn_index, human_player=human_player)
    if text_board or not renderer.enabled:
        _print_board(state)
    if state.winner is None:
        print("Stopped without a winner.")
    else:
        print(f"Winner: Team {state.winner.value}")
    renderer.close()


def _parse_player(raw: str) -> PlayerId:
    upper = raw.upper()
    try:
        return PlayerId[upper]
    except KeyError as exc:
        valid = ", ".join(player.name for player in PlayerId)
        raise argparse.ArgumentTypeError(f"Invalid player '{raw}'. Use one of: {valid}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Brandi Dog as one human against three random agents.")
    parser.add_argument("--seed", type=int, default=7, help="Seed for deterministic shuffle and bot choices.")
    parser.add_argument(
        "--human",
        type=_parse_player,
        default=PlayerId.A1,
        help="Human player seat: A1, B1, A2, or B2.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=5000,
        help="Safety guard to stop extremely long games.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable Tkinter board window and use terminal output only.",
    )
    parser.add_argument(
        "--text-board",
        action="store_true",
        help="Also print ASCII board in terminal on each turn.",
    )
    parser.add_argument(
        "--bot-agent",
        choices=("smart", "random"),
        default="smart",
        help="Bot policy to use for non-human players.",
    )
    args = parser.parse_args()

    run_game(
        seed=args.seed,
        human_player=args.human,
        max_turns=args.max_turns,
        use_gui=not args.no_gui,
        text_board=args.text_board,
        bot_agent=args.bot_agent,
    )


if __name__ == "__main__":
    main()
