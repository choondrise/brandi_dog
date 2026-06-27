from __future__ import annotations

from typing import Dict, Optional, List

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    host_name: str = Field(default="Host", max_length=32)


class JoinSessionRequest(BaseModel):
    player_name: str = Field(default="Player", max_length=32)
    preferred_seat: Optional[str] = None


class SeatRequest(BaseModel):
    token: str
    seat: Optional[str] = None


class BotRequest(BaseModel):
    token: str
    seat: str
    level: str


class StartRequest(BaseModel):
    token: str


class SevenSplitMoveRequest(BaseModel):
    pawn_id: str
    steps: int
    prefer_safe_entry: bool = True


class ActionRequest(BaseModel):
    token: str
    action_id: Optional[int] = None
    action_key: Optional[str] = None
    card_id: Optional[int] = None
    represented_rank: Optional[str] = None
    seven_moves: Optional[List[SevenSplitMoveRequest]] = None


class ApiError(BaseModel):
    detail: str


class SessionCreated(BaseModel):
    game_id: str
    host_token: str
    player_token: str


class JoinResponse(BaseModel):
    game_id: str
    player_token: str
    seat: Optional[str]


class HealthResponse(BaseModel):
    ok: bool = True


class LobbyPlayer(BaseModel):
    name: str
    token_hint: str
    seat: Optional[str]
    is_host: bool


class SeatInfo(BaseModel):
    seat: str
    team: str
    occupant: str
    human_name: Optional[str] = None
    bot_level: str


class PublicSession(BaseModel):
    game_id: str
    phase: str
    host_joined: bool
    seats: Dict[str, SeatInfo]
    players: Dict[str, LobbyPlayer]
    host_token_hint: str
