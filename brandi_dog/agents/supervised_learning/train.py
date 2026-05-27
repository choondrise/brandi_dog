from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Iterable, Optional

from .model import RankingScorer, torch


def train_ranking_model(
    dataset_path: str,
    output_path: str,
    epochs: int = 3,
    learning_rate: float = 1e-3,
    hidden_dim: int = 128,
    device: str = "auto",
    seed: int = 0,
    shuffle: bool = True,
    initial_model_path: Optional[str] = None,
    l2_anchor_weight: float = 0.0,
) -> None:
    """Train a softmax ranking model over each decision's candidate actions."""

    if torch is None:
        raise ImportError("PyTorch is required for training. Install torch to use this module.")

    train_device = _select_device(device)
    torch.manual_seed(seed)
    random.seed(seed)

    dataset = _load_grouped_pt_dataset(dataset_path)
    candidate_features = dataset["candidate_features"]
    target_indices = dataset["target_indices"]
    if not candidate_features:
        raise ValueError("Dataset contains no samples")

    feature_dim = int(dataset.get("feature_dim") or candidate_features[0].shape[1])
    initial_checkpoint = _load_initial_checkpoint(initial_model_path, feature_dim) if initial_model_path else None
    if initial_checkpoint is not None:
        hidden_dim = int(initial_checkpoint.get("hidden_dim", hidden_dim))

    model = RankingScorer(state_dim=0, action_dim=feature_dim, hidden_dim=hidden_dim).to(train_device)
    anchor_state = None
    if initial_checkpoint is not None:
        model.load_state_dict(initial_checkpoint["model_state"])
        anchor_state = {key: value.detach().clone().to(train_device) for key, value in model.named_parameters()}
        print(f"Loaded initial model: {initial_model_path}", flush=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss()
    empty_state = torch.empty(0, dtype=torch.float32, device=train_device)
    indices = list(range(len(candidate_features)))

    print(f"Training samples: {len(candidate_features)}", flush=True)
    print(f"Feature dim: {feature_dim}", flush=True)
    print(f"Device: {train_device}", flush=True)
    print(f"Hidden dim: {hidden_dim}", flush=True)
    if l2_anchor_weight > 0.0:
        print(f"L2 anchor weight: {l2_anchor_weight}", flush=True)

    for epoch in range(epochs):
        if shuffle:
            random.shuffle(indices)
        total_loss = 0.0
        correct = 0
        heuristic_top3_correct = 0
        for sample_index in indices:
            action_tensor = candidate_features[sample_index].to(train_device)
            target = target_indices[sample_index].view(1).to(train_device)
            scores = model(empty_state, action_tensor).unsqueeze(0)
            loss = loss_fn(scores, target)
            if anchor_state is not None and l2_anchor_weight > 0.0:
                loss = loss + l2_anchor_weight * _anchor_l2_penalty(model, anchor_state)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += float(loss.detach().cpu())
            predicted_index = int(scores.argmax(dim=1).detach().cpu()[0])
            if predicted_index == int(target.detach().cpu()[0]):
                correct += 1
            if predicted_index < min(3, action_tensor.shape[0]):
                heuristic_top3_correct += 1

        avg_loss = total_loss / len(indices)
        accuracy = correct / len(indices)
        heuristic_top3_accuracy = heuristic_top3_correct / len(indices)
        print(
            f"epoch={epoch + 1} loss={avg_loss:.6f} accuracy={accuracy:.4f} "
            f"heuristic_top3={heuristic_top3_accuracy:.4f}",
            flush=True,
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "state_dim": 0,
            "action_dim": feature_dim,
            "hidden_dim": hidden_dim,
            "format": "grouped_ranking_finetuned_scorer" if initial_model_path else "grouped_ranking_v1_scorer",
            "initial_model_path": initial_model_path,
        },
        output_path,
    )
    print(f"Saved model: {output_path}", flush=True)


def _load_initial_checkpoint(initial_model_path: Optional[str], feature_dim: int) -> Optional[dict]:
    if not initial_model_path:
        return None
    checkpoint = torch.load(initial_model_path, map_location="cpu")
    required = {"model_state", "action_dim"}
    missing = required.difference(checkpoint)
    if missing:
        raise ValueError(f"Initial model checkpoint is missing keys: {sorted(missing)}")
    checkpoint_dim = int(checkpoint["action_dim"])
    if checkpoint_dim != feature_dim:
        raise ValueError(
            f"Feature dimension mismatch: dataset has {feature_dim}, initial model expects {checkpoint_dim}. "
            "Use the same encoder version for dataset and checkpoint."
        )
    return checkpoint


def _anchor_l2_penalty(model, anchor_state: dict) -> object:
    penalty = None
    for key, current in model.named_parameters():
        term = torch.mean((current - anchor_state[key]) ** 2)
        penalty = term if penalty is None else penalty + term
    if penalty is None:
        return torch.tensor(0.0, device=next(model.parameters()).device)
    return penalty


def _load_grouped_pt_dataset(dataset_path: str) -> dict:
    if torch is None:
        raise ImportError("PyTorch is required for training. Install torch to use this module.")
    dataset = torch.load(dataset_path, map_location="cpu")
    required = {"candidate_features", "target_indices", "feature_dim"}
    missing = required.difference(dataset)
    if missing:
        raise ValueError(f"Unsupported dataset format; missing keys: {sorted(missing)}")
    return dataset


def _select_device(device: str):
    if torch is None:
        raise ImportError("PyTorch is required for training. Install torch to use this module.")
    if device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    requested = torch.device(device)
    if requested.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is False")
    return requested


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Train a supervised action-ranking model from encoded .pt samples.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, ...")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-shuffle", action="store_true")
    parser.add_argument("--initial-model-path", help="Optional existing .pt checkpoint to fine-tune instead of training from scratch.")
    parser.add_argument("--l2-anchor-weight", type=float, default=0.0, help="Small penalty that keeps fine-tuning weights near the initial checkpoint.")
    args = parser.parse_args(argv)
    train_ranking_model(
        args.dataset,
        args.output,
        epochs=args.epochs,
        learning_rate=args.lr,
        hidden_dim=args.hidden_dim,
        device=args.device,
        seed=args.seed,
        shuffle=not args.no_shuffle,
        initial_model_path=args.initial_model_path,
        l2_anchor_weight=args.l2_anchor_weight,
    )


if __name__ == "__main__":
    main()
