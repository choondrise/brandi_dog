from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    ActionRequest,
    BotRequest,
    CreateSessionRequest,
    HealthResponse,
    JoinResponse,
    JoinSessionRequest,
    SeatRequest,
    SessionCreated,
    StartRequest,
)
from .session_manager import SessionManager


app = FastAPI(title="Brandi Dog Online API")
manager = SessionManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/sessions", response_model=SessionCreated)
async def create_session(request: CreateSessionRequest) -> SessionCreated:
    session, player_token = await manager.create_session(request.host_name)
    return SessionCreated(game_id=session.game_id, host_token=session.host_token, player_token=player_token)


@app.post("/api/sessions/{game_id}/join", response_model=JoinResponse)
async def join_session(game_id: str, request: JoinSessionRequest) -> JoinResponse:
    session, token = await manager.join_session(game_id, request.player_name, request.preferred_seat)
    seat = session.players[token].seat
    return JoinResponse(game_id=session.game_id, player_token=token, seat=None if seat is None else seat.name)


@app.get("/api/sessions/{game_id}")
def get_session(game_id: str, token: Optional[str] = None):
    session = manager._get(game_id)
    return manager.game_payload(session, token)


@app.post("/api/sessions/{game_id}/seat")
async def set_seat(game_id: str, request: SeatRequest):
    session = await manager.set_seat(game_id, request.token, request.seat)
    return manager.game_payload(session, request.token)


@app.post("/api/sessions/{game_id}/bot")
async def set_bot(game_id: str, request: BotRequest):
    session = await manager.set_bot(game_id, request.token, request.seat, request.level)
    return manager.game_payload(session, request.token)


@app.post("/api/sessions/{game_id}/start")
async def start_game(game_id: str, request: StartRequest):
    session, events = await manager.start(game_id, request.token)
    return manager.game_payload(session, request.token, events)


@app.post("/api/sessions/{game_id}/action")
async def apply_action(game_id: str, request: ActionRequest):
    session, events = await manager.apply_action(game_id, request.token, request.action_id, request.action_key)
    return manager.game_payload(session, request.token, events)


@app.websocket("/ws/{game_id}")
async def websocket_updates(websocket: WebSocket, game_id: str, token: Optional[str] = None):
    session = await manager.connect_ws(game_id, websocket, token)
    try:
        await manager.send_ws_state(session, websocket, token)
        while True:
            await websocket.receive_text()
            await manager.send_ws_state(session, websocket, token)
    except WebSocketDisconnect:
        await manager.disconnect_ws(session, websocket)
