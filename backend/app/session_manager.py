from __future__ import annotations

import asyncio
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import HTTPException, WebSocket

from brandi_dog.engine.actions import SwapCardAction
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PlayerId, RoundStage

from .bots import BOT_LEVELS, build_bot
from .schemas import LobbyPlayer, PublicSession, SeatInfo
from .serialization import action_key, active_player, describe_action, serialize_action, serialize_game, serialize_pawns


SEAT_ORDER = (PlayerId.A1, PlayerId.B1, PlayerId.A2, PlayerId.B2)


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
    websockets: set[WebSocket] = field(default_factory=set)


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
            self._advance_bots_locked(session, events)
        await self._broadcast(session)
        return session, events

    async def apply_action(self, game_id: str, token: str, action_id: Optional[int], selected_action_key: Optional[str]) -> tuple[GameSession, list[dict[str, Any]]]:
        session = self._get(game_id)
        async with session.lock:
            self._ensure_playing(session)
            player = self._require_player(session, token)
            actor = active_player(session.state)
            if actor is None:
                raise HTTPException(status_code=409, detail="Game is over")
            if player.seat != actor:
                raise HTTPException(status_code=403, detail="It is not your turn")
            legal = session.engine.legal_actions(session.state)
            action = self._select_legal_action(legal, action_id, selected_action_key)
            events: list[dict[str, Any]] = []
            self._apply_action_locked(session, action, events)
            self._advance_bots_locked(session, events)
        await self._broadcast(session)
        return session, events

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

    async def connect_ws(self, game_id: str, websocket: WebSocket) -> GameSession:
        session = self._get(game_id)
        await websocket.accept()
        session.websockets.add(websocket)
        return session

    async def disconnect_ws(self, session: GameSession, websocket: WebSocket) -> None:
        session.websockets.discard(websocket)

    async def send_ws_state(self, session: GameSession, websocket: WebSocket, token: Optional[str]) -> None:
        await websocket.send_json(self.game_payload(session, token))

    def _advance_bots_locked(self, session: GameSession, events: Optional[list[dict[str, Any]]] = None) -> None:
        assert session.engine is not None
        assert session.state is not None
        guard = 0
        while session.state.round_stage != RoundStage.GAME_OVER and guard < 200:
            actor = active_player(session.state)
            if actor is None or actor not in session.bot_agents:
                break
            action = session.bot_agents[actor].select_action(session.engine, session.state)
            self._apply_action_locked(session, action, events)
            guard += 1
        if session.state.round_stage == RoundStage.GAME_OVER:
            session.phase = "FINISHED"

    def _apply_action_locked(self, session: GameSession, action, events: Optional[list[dict[str, Any]]] = None) -> None:
        assert session.engine is not None
        assert session.state is not None
        before_state = session.state
        before_pawns = serialize_pawns(before_state)
        session.state = session.engine.step(session.state, action)
        if events is not None and not isinstance(action, SwapCardAction):
            after_pawns = serialize_pawns(session.state)
            events.append(self._turn_event(session, action, before_pawns, after_pawns))

    def _turn_event(self, session: GameSession, action, before_pawns: list[dict[str, Any]], after_pawns: list[dict[str, Any]]) -> dict[str, Any]:
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
            card = serialize_action(0, action, session.engine.cards_by_id).get("card")
        return {
            "id": secrets.token_hex(6),
            "actor": None if actor is None else actor.name,
            "actorName": actor_name,
            "isBot": actor in session.bot_agents if actor is not None else False,
            "type": type(action).__name__,
            "label": describe_action(action, session.engine.cards_by_id),
            "card": card,
            "affectedPawns": affected,
            "pawnsBefore": before_pawns,
            "pawnsAfter": after_pawns,
        }

    def _display_name(self, session: GameSession, seat: PlayerId) -> str:
        human = next((player for player in session.players.values() if player.seat == seat), None)
        if human is not None:
            return human.name
        return seat.name

    async def _broadcast(self, session: GameSession) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(session.websockets):
            try:
                await websocket.send_json({"type": "refresh"})
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            session.websockets.discard(websocket)

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
