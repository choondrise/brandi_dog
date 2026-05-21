from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Protocol

from brandi_dog.engine.actions import Action
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState, PlayerId


class AgentProtocol(Protocol):
    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        ...


AgentsByPlayer = Mapping[PlayerId, AgentProtocol]


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    num_games: int
    seed: int
    agents_by_player: AgentsByPlayer
    output_path: Optional[Path] = None
    max_turns: Optional[int] = None
    team_a_label: str = "Team A"
    team_b_label: str = "Team B"
    print_progress: bool = True
