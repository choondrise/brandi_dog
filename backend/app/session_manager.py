from __future__ import annotations

import asyncio
import logging
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import HTTPException, WebSocket

from brandi_dog.engine.actions import PlaySevenSplitAction, SevenSubMove, SkipTurnAction, SwapCardAction
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PawnRef, PlayerId, RoundStage

from .bots import BOT_LEVELS, build_bot
from brandi_dog.engine.cards import Rank
from brandi_dog.engine import rules as engine_rules

from .schemas import LobbyPlayer, PublicSession, SeatInfo, SevenSplitMoveRequest
from .serialization import action_key, active_player, describe_action, serialize_action, serialize_game, serialize_pawns, seven_preview


SEAT_ORDER = (PlayerId.A1, PlayerId.B1, PlayerId.A2, PlayerId.B2)
logger = logging.getLogger(__name__)


@dataclass
class HumanPlayer:
    name: str
    token: str
    seat: Optional[PlayerId] = None
    is_host: bool = False


@dataclass
class GameSession:
    game_id: str
    host_token: str
    engine: Optional[GameEngine] = None
    state: Optional[GameState] = None
    phase: str = "LOBBY"
    players: Dict[str, HumanPlayer] = field(default_factory=dict)
    bot_levels: Dict[PlayerId, str] = field(default_factory=lambda: {seat: "Easy" for seat in SEAT_ORDER})
    bot_agents: Dict[PlayerId, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    websockets: dict[WebSocket, Optional[str]] = field(default_factory=dict)


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, GameSession] = {}

    async def create_session(self, host_name: str) -> tuple[GameSession, str]:
        game_id = self._new_game_id()
        host_token = self._new_token()
        player_token = self._new_token()
        session = GameSession(game_id=game_id, host_token=host_token)
        session.players[player_token] = HumanPlayer(name=host_name or "Host", token=player_token, is_host=True)
        self.sessions[game_id] = session
        await self._broadcast(session)
        return session, player_token

    async def join_session(self, game_id: str, name: str, preferred_seat: Optional[str]) -> tuple[GameSession, str]:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_lobby(session)
            token = self._new_token()
            seat = self._parse_optional_seat(preferred_seat)
            if seat is not None and self._seat_occupied_by_human(session, seat):
                seat = None
            if seat is None:
                seat = self._first_open_seat(session)
            session.players[token] = HumanPlayer(name=name or "Player", token=token, seat=seat)
        await self._broadcast(session)
        return session, token

    async def set_seat(self, game_id: str, token: str, seat_name: Optional[str]) -> GameSession:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_lobby(session)
            player = self._require_player(session, token)
            seat = self._parse_optional_seat(seat_name)
            if seat is not None and self._seat_occupied_by_human(session, seat, except_token=token):
                raise HTTPException(status_code=409, detail="Seat is already taken")
            player.seat = seat
        await self._broadcast(session)
        return session

    async def set_bot(self, game_id: str, token: str, seat_name: str, level: str) -> GameSession:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_host(session, token)
            self._ensure_lobby(session)
            seat = self._parse_seat(seat_name)
            normalized = self._normalize_bot(level)
            session.bot_levels[seat] = normalized
        await self._broadcast(session)
        return session

    async def start(self, game_id: str, token: str) -> tuple[GameSession, list[dict[str, Any]]]:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_host(session, token)
            self._ensure_lobby(session)
            if not any(player.seat is not None for player in session.players.values()):
                raise HTTPException(status_code=409, detail="At least one human must take a seat before starting")
            session.engine = GameEngine(seed=secrets.randbelow(1_000_000_000))
            session.state = session.engine.reset()
            session.bot_agents = {}
            for seat in SEAT_ORDER:
                if not self._seat_occupied_by_human(session, seat):
                    session.bot_agents[seat] = build_bot(session.bot_levels[seat], seed=secrets.randbelow(1_000_000_000))
            session.phase = "PLAYING"
            events: list[dict[str, Any]] = []
            pause_for_swap = self._advance_automatic_locked(session, events)
        await self._broadcast(session, events)
        if pause_for_swap:
            self._schedule_automatic_after_swap_overlay(session)
        return session, events

    async def apply_action(
        self,
        game_id: str,
        token: str,
        action_id: Optional[int],
        selected_action_key: Optional[str],
        card_id: Optional[int] = None,
        represented_rank: Optional[str] = None,
        seven_moves: Optional[list[SevenSplitMoveRequest]] = None,
    ) -> tuple[GameSession, list[dict[str, Any]]]:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_playing(session)
            player = self._require_player(session, token)
            actor = active_player(session.state)
            if actor is None:
                raise HTTPException(status_code=409, detail="Game is over")
            if player.seat != actor:
                raise HTTPException(status_code=403, detail="It is not your turn")
            events: list[dict[str, Any]] = []
            if seven_moves is not None:
                action = self._build_custom_seven_action(actor, card_id, represented_rank, seven_moves)
                self._apply_custom_seven_locked(session, action, events)
            else:
                legal = session.engine.legal_actions(session.state)
                action = self._select_legal_action(legal, action_id, selected_action_key)
                self._apply_action_locked(session, action, events)
            pause_for_swap = self._advance_automatic_locked(session, events)
        await self._broadcast(session, events)
        if pause_for_swap:
            self._schedule_automatic_after_swap_overlay(session)
        return session, events

    async def preview_seven(
        self,
        game_id: str,
        token: str,
        card_id: Optional[int],
        represented_rank: Optional[str],
        seven_moves: list[SevenSplitMoveRequest],
    ) -> dict[str, Any]:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_playing(session)
            assert session.state is not None
            player = self._require_player(session, token)
            actor = active_player(session.state)
            if actor is None:
                raise HTTPException(status_code=409, detail="Game is over")
            if player.seat != actor:
                raise HTTPException(status_code=403, detail="It is not your turn")
            action = self._build_custom_seven_action(actor, card_id, represented_rank, seven_moves)
            return seven_preview(session.state, action)

    def _build_custom_seven_action(
        self,
        actor: PlayerId,
        card_id: Optional[int],
        represented_rank: Optional[str],
        moves: list[SevenSplitMoveRequest],
    ) -> PlaySevenSplitAction:
        if card_id is None:
            raise HTTPException(status_code=400, detail="Seven split card is required")
        if not moves:
            raise HTTPException(status_code=400, detail="Seven split moves are required")
        try:
            rank = Rank(represented_rank or "7")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid represented rank for seven split") from exc
        if rank != Rank.SEVEN:
            raise HTTPException(status_code=400, detail="Custom split must play the card as 7")
        return PlaySevenSplitAction(
            player=actor,
            card_id=card_id,
            represented_rank=rank,
            moves=tuple(
                SevenSubMove(
                    pawn=self._parse_pawn_id(move.pawn_id),
                    steps=move.steps,
                    prefer_safe_entry=move.prefer_safe_entry,
                )
                for move in moves
            ),
        )

    def _parse_pawn_id(self, raw: str) -> PawnRef:
        try:
            owner_name, number_raw = raw.split("-", 1)
            owner = PlayerId[owner_name]
            number = int(number_raw)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail="Invalid pawn id") from exc
        if number < 0 or number > 3:
            raise HTTPException(status_code=400, detail="Invalid pawn id")
        return PawnRef(owner=owner, number=number)

    def _select_legal_action(self, legal, action_id: Optional[int], selected_action_key: Optional[str]):
        if selected_action_key:
            for candidate in legal:
                if action_key(candidate) == selected_action_key:
                    return candidate
            raise HTTPException(status_code=409, detail="Selected move is no longer legal. Refresh and choose again.")
        if action_id is None or action_id < 0 or action_id >= len(legal):
            raise HTTPException(status_code=400, detail="Invalid action")
        return legal[action_id]

    def public_session(self, session: GameSession) -> PublicSession:
        return PublicSession(
            game_id=session.game_id,
            phase=session.phase,
            host_joined=any(player.is_host for player in session.players.values()),
            seats={seat.name: self._seat_info(session, seat) for seat in SEAT_ORDER},
            players={
                token: LobbyPlayer(
                    name=player.name,
                    token_hint=self._hint(token),
                    seat=None if player.seat is None else player.seat.name,
                    is_host=player.is_host,
                )
                for token, player in session.players.items()
            },
            host_token_hint=self._hint(session.host_token),
        )

    def game_payload(self, session: GameSession, token: Optional[str], events: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        viewer = None
        if token and token in session.players:
            viewer = session.players[token].seat
        legal = ()
        if session.engine is not None and session.state is not None and viewer == active_player(session.state):
            legal = session.engine.legal_actions(session.state)
        return {
            "session": self.public_session(session).model_dump(),
            "game": serialize_game(session.engine, session.state, legal, viewer) if session.engine is not None else None,
            "viewerSeat": None if viewer is None else viewer.name,
            "isHost": token == session.host_token or (token in session.players and session.players[token].is_host),
            "events": events or [],
        }

    async def connect_ws(self, game_id: str, websocket: WebSocket, token: Optional[str]) -> GameSession:
        session = self._get(game_id)
        await websocket.accept()
        session.websockets[websocket] = token
        return session

    async def disconnect_ws(self, session: GameSession, websocket: WebSocket) -> None:
        session.websockets.pop(websocket, None)

    async def send_ws_state(self, session: GameSession, websocket: WebSocket, token: Optional[str]) -> None:
        await websocket.send_json(self.game_payload(session, token))

    def _advance_automatic_locked(self, session: GameSession, events: Optional[list[dict[str, Any]]] = None) -> bool:
        assert session.engine is not None
        assert session.state is not None
        guard = 0
        while session.state.round_stage != RoundStage.GAME_OVER and guard < 200:
            actor = active_player(session.state)
            if actor is None:
                break
            legal = session.engine.legal_actions(session.state)
            if not legal:
                break
            if actor in session.bot_agents:
                action = self._select_bot_action_locked(session, actor, legal)
            elif len(legal) == 1 and isinstance(legal[0], SkipTurnAction):
                action = legal[0]
            else:
                break
            completed_swap = self._apply_action_locked(session, action, events)
            guard += 1
            if completed_swap:
                return True
        if session.state.round_stage == RoundStage.GAME_OVER:
            session.phase = "FINISHED"
        return False

    def _select_bot_action_locked(self, session: GameSession, actor: PlayerId, legal):
        assert session.engine is not None
        assert session.state is not None
        legal_by_key = {action_key(action): action for action in legal}
        try:
            selected = session.bot_agents[actor].select_action(session.engine, session.state)
            selected_key = action_key(selected)
            if selected_key not in legal_by_key:
                raise ValueError(f"Bot {actor.name} selected an illegal action: {selected_key}")
            return legal_by_key[selected_key]
        except Exception:
            logger.exception("Bot %s failed to select a legal action; falling back to a random legal action", actor.name)
            return legal[secrets.randbelow(len(legal))]

    def _apply_action_locked(self, session: GameSession, action, events: Optional[list[dict[str, Any]]] = None) -> bool:
        assert session.engine is not None
        assert session.state is not None
        before_state = session.state
        before_pawns = serialize_pawns(before_state)
        session.state = session.engine.step(session.state, action)
        completed_swap = isinstance(action, SwapCardAction) and session.state.hands != before_state.hands
        if events is not None and not isinstance(action, SwapCardAction):
            after_pawns = serialize_pawns(session.state)
            events.append(self._turn_event(session, action, before_state, before_pawns, after_pawns))
        return completed_swap

    def _schedule_automatic_after_swap_overlay(self, session: GameSession) -> None:
        asyncio.create_task(self._continue_automatic_after_swap_overlay(session))

    async def _continue_automatic_after_swap_overlay(self, session: GameSession) -> None:
        await asyncio.sleep(2.1)
        events: list[dict[str, Any]] = []
        async with session.lock:
            if session.phase not in {"PLAYING", "FINISHED"} or session.engine is None or session.state is None:
                return
            pause_for_swap = self._advance_automatic_locked(session, events)
        await self._broadcast(session, events)
        if pause_for_swap:
            self._schedule_automatic_after_swap_overlay(session)

    def _apply_custom_seven_locked(self, session: GameSession, action: PlaySevenSplitAction, events: list[dict[str, Any]]) -> None:
        assert session.engine is not None
        assert session.state is not None
        before_state = session.state
        before_pawns = serialize_pawns(before_state)
        try:
            session.state = engine_rules._apply_play_seven_action(session.state, action, session.engine.cards_by_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        after_pawns = serialize_pawns(session.state)
        events.append(self._turn_event(session, action, before_state, before_pawns, after_pawns))
        if session.state.round_stage == RoundStage.GAME_OVER:
            session.phase = "FINISHED"

    def _turn_event(self, session: GameSession, action, before_state: GameState, before_pawns: list[dict[str, Any]], after_pawns: list[dict[str, Any]]) -> dict[str, Any]:
        assert session.engine is not None
        actor = getattr(action, "player", None)
        actor_name = self._display_name(session, actor) if actor is not None else "Game"
        before_by_id = {pawn["id"]: pawn for pawn in before_pawns}
        affected = [
            pawn["id"]
            for pawn in after_pawns
            if before_by_id.get(pawn["id"], {}).get("position") != pawn["position"]
        ]
        card_id = getattr(action, "card_id", None)
        card = None
        if card_id is not None:
            card = serialize_action(0, action, session.engine.cards_by_id, before_state).get("card")
        return {
            "id": secrets.token_hex(6),
            "actor": None if actor is None else actor.name,
            "actorName": actor_name,
            "isBot": actor in session.bot_agents if actor is not None else False,
            "type": type(action).__name__,
            "label": describe_action(action, session.engine.cards_by_id),
            "card": card,
            "action": serialize_action(0, action, session.engine.cards_by_id, before_state),
            "affectedPawns": affected,
            "pawnsBefore": before_pawns,
            "pawnsAfter": after_pawns,
        }

    def _display_name(self, session: GameSession, seat: PlayerId) -> str:
        human = next((player for player in session.players.values() if player.seat == seat), None)
        if human is not None:
            return human.name
        return seat.name

    async def _broadcast(self, session: GameSession, events: Optional[list[dict[str, Any]]] = None) -> None:
        disconnected: list[WebSocket] = []
        for websocket, token in list(session.websockets.items()):
            try:
                if events:
                    await websocket.send_json(self.game_payload(session, token, events))
                else:
                    await websocket.send_json({"type": "refresh"})
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            session.websockets.pop(websocket, None)

    def _get(self, game_id: str) -> GameSession:
        session = self.sessions.get(game_id.upper())
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown game id")
        return session

    def _new_game_id(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            game_id = "".join(secrets.choice(alphabet) for _ in range(6))
            if game_id not in self.sessions:
                return game_id

    def _new_token(self) -> str:
        return secrets.token_urlsafe(24)

    def _ensure_lobby(self, session: GameSession) -> None:
        if session.phase != "LOBBY":
            raise HTTPException(status_code=409, detail="Session is no longer in the lobby")

    def _ensure_playing(self, session: GameSession) -> None:
        if session.phase not in {"PLAYING", "FINISHED"} or session.engine is None or session.state is None:
            raise HTTPException(status_code=409, detail="Game has not started")

    def _ensure_host(self, session: GameSession, token: str) -> None:
        if token == session.host_token:
            return
        player = session.players.get(token)
        if player is None or not player.is_host:
            raise HTTPException(status_code=403, detail="Only the host can do that")

    def _require_player(self, session: GameSession, token: str) -> HumanPlayer:
        player = session.players.get(token)
        if player is None:
            raise HTTPException(status_code=403, detail="Unknown player token")
        return player

    def _parse_seat(self, raw: str) -> PlayerId:
        try:
            return PlayerId[raw.upper()]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail="Seat must be A1, B1, A2, or B2") from exc

    def _parse_optional_seat(self, raw: Optional[str]) -> Optional[PlayerId]:
        if raw is None or raw == "":
            return None
        return self._parse_seat(raw)

    def _first_open_seat(self, session: GameSession) -> Optional[PlayerId]:
        for seat in SEAT_ORDER:
            if not self._seat_occupied_by_human(session, seat):
                return seat
        return None

    def _seat_occupied_by_human(self, session: GameSession, seat: PlayerId, except_token: Optional[str] = None) -> bool:
        return any(player.seat == seat and token != except_token for token, player in session.players.items())

    def _seat_info(self, session: GameSession, seat: PlayerId) -> SeatInfo:
        human = next((player for player in session.players.values() if player.seat == seat), None)
        return SeatInfo(
            seat=seat.name,
            team="A" if seat in (PlayerId.A1, PlayerId.A2) else "B",
            occupant="human" if human is not None else "bot",
            human_name=None if human is None else human.name,
            bot_level=session.bot_levels[seat],
        )

    def _normalize_bot(self, level: str) -> str:
        for known in BOT_LEVELS:
            if known.lower() == level.lower():
                return known
        raise HTTPException(status_code=400, detail=f"Bot level must be one of: {', '.join(BOT_LEVELS)}")

    def _hint(self, token: str) -> str:
        return token[:6]
