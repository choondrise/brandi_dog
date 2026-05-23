from __future__ import annotations

from dataclasses import dataclass

from brandi_dog.engine.actions import DiscardHandAction, SkipTurnAction
from brandi_dog.engine.board import MAIN_TRACK_LENGTH
from brandi_dog.engine.state import GameState, PlayerId, Position, PositionKind, Team, team_of, teammate_of

from .config import RewardWeights


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    win_loss: float = 0.0
    team_progress: float = 0.0
    partner_progress: float = 0.0
    opponent_progress: float = 0.0
    safe_entry: float = 0.0
    capture: float = 0.0
    discard: float = 0.0
    sent_back: float = 0.0


class ShapedReward:
    """Configurable team-based shaped reward for policy-gradient fine-tuning."""

    def __init__(self, weights: RewardWeights | None = None, **overrides):
        if weights is None:
            weights = RewardWeights()
        if overrides:
            values = {**weights.__dict__, **overrides}
            weights = RewardWeights(**values)
        self.weights = weights

    def score_transition(self, before: GameState, after: GameState, trained_team: Team, trained_player: PlayerId | None = None, action=None) -> RewardBreakdown:
        win_loss = 0.0
        if after.winner is not None:
            win_loss = self.weights.win_reward if after.winner == trained_team else self.weights.loss_penalty

        enemy_team = Team.B if trained_team == Team.A else Team.A
        team_delta_raw = self._team_progress(after, trained_team) - self._team_progress(before, trained_team)
        enemy_delta_raw = self._team_progress(after, enemy_team) - self._team_progress(before, enemy_team)
        partner_delta_raw = 0.0
        if trained_player is not None:
            partner = teammate_of(trained_player)
            partner_delta_raw = self._player_progress(after, partner) - self._player_progress(before, partner)

        team_progress = team_delta_raw * self.weights.team_progress_scale
        partner_progress = partner_delta_raw * self.weights.partner_progress_scale
        opponent_progress = enemy_delta_raw * self.weights.opponent_progress_scale

        safe_entry = self._safe_entries(before, after, trained_team) * self.weights.safe_entry_reward
        capture = self._captures(before, after, trained_team) * self.weights.capture_reward
        sent_back = self._sent_back(before, after, trained_team) * self.weights.sent_back_penalty
        discard = self.weights.discard_penalty if isinstance(action, (DiscardHandAction, SkipTurnAction)) else 0.0

        total = win_loss + team_progress + partner_progress + opponent_progress + safe_entry + capture + discard + sent_back
        return RewardBreakdown(
            total=total,
            win_loss=win_loss,
            team_progress=team_progress,
            partner_progress=partner_progress,
            opponent_progress=opponent_progress,
            safe_entry=safe_entry,
            capture=capture,
            discard=discard,
            sent_back=sent_back,
        )

    def terminal_score(self, state: GameState, trained_team: Team) -> float:
        if state.winner == trained_team:
            return self.weights.win_reward
        if state.winner is not None:
            return self.weights.loss_penalty
        enemy_team = Team.B if trained_team == Team.A else Team.A
        return (self._team_progress(state, trained_team) - self._team_progress(state, enemy_team)) * self.weights.terminal_progress_scale

    def _team_progress(self, state: GameState, team: Team) -> float:
        total = 0.0
        for index, position in enumerate(state.pawn_positions):
            if team_of(PlayerId(index // 4)) == team:
                total += self._progress(position)
        return total

    def _player_progress(self, state: GameState, player: PlayerId) -> float:
        start = int(player) * 4
        return sum(self._progress(position) for position in state.pawn_positions[start : start + 4])

    def _progress(self, position: Position) -> float:
        if position.kind == PositionKind.BASE:
            return 0.0
        if position.kind == PositionKind.TRACK:
            return 0.25 + (0.0 if position.index is None else float(position.index) / float(MAIN_TRACK_LENGTH))
        if position.kind == PositionKind.SAFE:
            return 1.0 + (0.0 if position.index is None else float(position.index + 1) / 4.0)
        return 0.0

    def _safe_entries(self, before: GameState, after: GameState, team: Team) -> int:
        count = 0
        for index, (before_pos, after_pos) in enumerate(zip(before.pawn_positions, after.pawn_positions)):
            if team_of(PlayerId(index // 4)) == team and before_pos.kind != PositionKind.SAFE and after_pos.kind == PositionKind.SAFE:
                count += 1
        return count

    def _captures(self, before: GameState, after: GameState, team: Team) -> int:
        count = 0
        for index, (before_pos, after_pos) in enumerate(zip(before.pawn_positions, after.pawn_positions)):
            if team_of(PlayerId(index // 4)) != team and before_pos.kind != PositionKind.BASE and after_pos.kind == PositionKind.BASE:
                count += 1
        return count

    def _sent_back(self, before: GameState, after: GameState, team: Team) -> int:
        count = 0
        for index, (before_pos, after_pos) in enumerate(zip(before.pawn_positions, after.pawn_positions)):
            if team_of(PlayerId(index // 4)) == team and before_pos.kind != PositionKind.BASE and after_pos.kind == PositionKind.BASE:
                count += 1
        return count
