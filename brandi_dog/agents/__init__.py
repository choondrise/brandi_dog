from .action_generation import AgentActionGenerationPolicy
from .advanced_heuristic_agent import AdvancedHeuristicAgent
from .heuristic_agent import HeuristicAgent
from .monte_carlo_agent import MonteCarloAgent
from .random_legal_agent import RandomLegalAgent

__all__ = [
    "AgentActionGenerationPolicy",
    "AdvancedHeuristicAgent",
    "HeuristicAgent",
    "MonteCarloAgent",
    "RandomLegalAgent",
    "DeepLearningAgent",
    "RankingModelAgent",
]


def __getattr__(name: str):
    if name in {"DeepLearningAgent", "RankingModelAgent"}:
        from .deep_learning_agent import DeepLearningAgent

        return DeepLearningAgent
    raise AttributeError(name)
