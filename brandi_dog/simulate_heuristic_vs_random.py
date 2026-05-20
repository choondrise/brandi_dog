from __future__ import annotations

import argparse

from brandi_dog.agents.heuristic_agent import HeuristicAgent
from brandi_dog.agents.random_legal_agent import RandomLegalAgent
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import (
    GameState,
    PlayerId,
    PositionKind,
    RoundStage,
    Team,
    TEAM_PLAYERS,
    active_swap_player,
    get_pawn_position,
    player_pawns,
)


def _current_actor(state: GameState) -> PlayerId:
    if state.round_stage == RoundStage.TEAM_SWAPS:
        return active_swap_player(state)
    return state.play_current


def _team_safe_count(state: GameState, team: Team) -> int:
    total = 0
    for player in TEAM_PLAYERS[team]:
        for pawn in player_pawns(player):
            if get_pawn_position(state, pawn).kind == PositionKind.SAFE:
                total += 1
    return total


def _play_single_game(game_seed: int, max_turns: int) -> GameState:
    engine = GameEngine(seed=game_seed)
    agents = {
        PlayerId.A1: HeuristicAgent(seed=game_seed * 17 + 1),
        PlayerId.A2: HeuristicAgent(seed=game_seed * 17 + 2),
        PlayerId.B1: HeuristicAgent(seed=game_seed * 17 + 3),
        PlayerId.B2: HeuristicAgent(seed=game_seed * 17 + 4),
    }

    state = engine.reset()
    turns = 0

    while state.round_stage != RoundStage.GAME_OVER:
        if turns >= max_turns:
            # raise RuntimeError(f"Game exceeded max_turns={max_turns} (seed={game_seed})")
            return state
        actor = _current_actor(state)
        action = agents[actor].select_action(engine, state)
        state = engine.step(state, action)
        turns += 1

    return state


def run_simulation(games: int, seed: int, max_turns: int) -> None:
    total_team_a = 0
    total_team_b = 0

    print("Seat assignment: Team A (A1,A2) = heuristic, Team B (B1,B2) = random", flush=True)

    for game_idx in range(1, games + 1):
        game_seed = seed + game_idx - 1
        final_state = _play_single_game(game_seed=game_seed, max_turns=max_turns)

        team_a_safe = _team_safe_count(final_state, Team.A)
        team_b_safe = _team_safe_count(final_state, Team.B)

        total_team_a += team_a_safe
        total_team_b += team_b_safe

        print(f"Game {game_idx}: {team_a_safe}-{team_b_safe}", flush=True)

    print("\nTotals", flush=True)
    print(f"Team A safe pawns total: {total_team_a}", flush=True)
    print(f"Team B safe pawns total: {total_team_b}", flush=True)
    # print(f"Combined total: {total_team_a + total_team_b}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate games between 2 heuristic agents (Team A) and 2 random agents (Team B).",
    )
    parser.add_argument("--games", type=int, default=10, help="Number of games to simulate.")
    parser.add_argument("--seed", type=int, default=1, help="Base seed for deterministic simulation.")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=1000,
        help="Safety cap for turns per game.",
    )
    args = parser.parse_args()

    run_simulation(games=args.games, seed=args.seed, max_turns=args.max_turns)


if __name__ == "__main__":
    main()
