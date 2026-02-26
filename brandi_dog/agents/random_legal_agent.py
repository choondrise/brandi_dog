from __future__ import annotations

import random
from typing import Optional

from brandi_dog.engine.actions import Action
from brandi_dog.engine.engine import GameEngine
from brandi_dog.engine.state import GameState


class RandomLegalAgent:
    def __init__(self, seed: Optional[int] = None, rng: Optional[random.Random] = None):
        if rng is not None and seed is not None:
            raise ValueError("Provide either seed or rng, not both")
        self.rng = rng if rng is not None else random.Random(seed)

    def select_action(self, engine: GameEngine, state: GameState) -> Action:
        legal = engine.legal_actions(state)
        if not legal:
            raise RuntimeError("No legal actions available")
        return self.rng.choice(legal)
