from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - depends on optional training dependency
    torch = None
    nn = None


if nn is not None:
    class RankingScorer(nn.Module):
        """Small MLP that scores one state-action pair with a scalar."""

        def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim + action_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, 1),
            )

        def forward(self, state_features, action_features):
            if state_features.dim() == 1:
                state_features = state_features.unsqueeze(0).expand(action_features.shape[0], -1)
            inputs = torch.cat([state_features, action_features], dim=-1)
            return self.net(inputs).squeeze(-1)
else:
    class RankingScorer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch is required for RankingScorer. Install torch to train models.")
