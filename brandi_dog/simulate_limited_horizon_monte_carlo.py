from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brandi_dog.agents import HeuristicAgent, LimitedHorizonMonteCarloAgent, RandomLegalAgent, AdvancedHeuristicAgent
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    TEAM_PLAYERS,
    GameState,
    PlayerId,
    PositionKind,
    RoundStage,
    Team,
    active_swap_player,
    get_pawn_position,
    player_pawns,
)


def _current_actor(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def _team_safe_count(state: GameState, team: Team) -> int:
    return sum(
        1
        for player in TEAM_PLAYERS[team]
        for pawn in player_pawns(player)
        if get_pawn_position(state, pawn).kind == PositionKind.SAFE
    )


def _make_baseline(kind: str, seed: int):
    if kind == "random":
        return RandomLegalAgent(seed=seed)
    if kind == "heuristic":
        return AdvancedHeuristicAgent(seed=seed)
    raise ValueError(f"Unsupported baseline: {kind}")


def _play_single_game(game_seed: int, max_turns: int, baseline: str) -> GameState:
    engine = GameEngine(seed=game_seed)
    agents = {
        PlayerId.A1: LimitedHorizonMonteCarloAgent(seed=game_seed * 17 + 1, top_k=3, rollouts_per_action=2, rollout_policy="heuristic"),
        PlayerId.A2: LimitedHorizonMonteCarloAgent(seed=game_seed * 17 + 2, top_k=3, rollouts_per_action=2, rollout_policy="heuristic"),
        PlayerId.B1: _make_baseline(baseline, game_seed * 17 + 3),
        PlayerId.B2: _make_baseline(baseline, game_seed * 17 + 4),
    }
    state = engine.reset()
    turns = 0
    while state.round_stage != RoundStage.GAME_OVER and turns < max_turns:
        actor = _current_actor(state)
        action = agents[actor].select_action(engine, state)
        state = engine.step(state, action)
        turns += 1
    return state


def run_simulation(games: int, seed: int, max_turns: int, baseline: str) -> None:
    print(f"Team A: LimitedHorizonMonteCarloAgent | Team B: {baseline}", flush=True)
    total_a = 0
    total_b = 0
    for game_index in range(games):
        final_state = _play_single_game(seed + game_index, max_turns, baseline)
        team_a_safe = _team_safe_count(final_state, Team.A)
        team_b_safe = _team_safe_count(final_state, Team.B)
        total_a += team_a_safe
        total_b += team_b_safe
        winner = final_state.winner.value if final_state.winner is not None else "none"
        print(f"Game {game_index + 1}: safe={team_a_safe}-{team_b_safe}, winner={winner}", flush=True)
    print("Totals", flush=True)
    print(f"Team A safe pawns total: {total_a}", flush=True)
    print(f"Team B safe pawns total: {total_b}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare LimitedHorizonMonteCarloAgent against a baseline.")
    parser.add_argument("--baseline", choices=("random", "heuristic"), default="heuristic")
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=100)
    args = parser.parse_args()
    run_simulation(args.games, args.seed, args.max_turns, args.baseline)


if __name__ == "__main__":
    main()
