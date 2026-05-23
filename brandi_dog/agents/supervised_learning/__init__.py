"""Supervised imitation-learning utilities for Brändi Dog agents.

Generate raw JSONL samples:
    python -m brandi_dog.agents.supervised_learning.dataset_builder \
        --games 100 --seed 7 --candidate-alternatives 10 --append --output brandi_dog/agents/supervised_learning/data/imitation.jsonl

Generate in parallel:
    python -m brandi_dog.agents.supervised_learning.parallel_dataset_builder \
        --games 100 --workers 4 --seed 7 --candidate-alternatives 10 --append --output brandi_dog/agents/supervised_learning/data/imitation.jsonl

Encode raw samples for ranking with V1:
    python -m brandi_dog.agents.supervised_learning.encoders encode \
        --encoder v1 \
        --input brandi_dog/agents/supervised_learning/data/imitation.jsonl \
        --output brandi_dog/agents/supervised_learning/data/imitation_encoded.jsonl

Encode raw samples for ranking with perspective-normalized V2:
    python -m brandi_dog.agents.supervised_learning.encoders encode \
        --encoder v2 \
        --input brandi_dog/agents/supervised_learning/data/imitation.jsonl \
        --output brandi_dog/agents/supervised_learning/data/imitation_encoded_v2.jsonl

Inspect encoded samples:
    python -m brandi_dog.agents.supervised_learning.inspect_encoded_dataset \
        --input brandi_dog/agents/supervised_learning/data/imitation_encoded.jsonl

Convert encoded JSONL to PyTorch .pt:
    python -m brandi_dog.agents.supervised_learning.encoders to-pt \
        --input brandi_dog/agents/supervised_learning/data/imitation_encoded.jsonl \
        --output brandi_dog/agents/supervised_learning/data/imitation_encoded.pt
"""

__all__ = [
    "DatasetBuildConfig",
    "DatasetBuildResult",
    "EncodedSample",
    "ImitationDatasetBuilder",
    "PartialInformationEncoder",
    "PartialInfoPerspectiveEncoderV2",
    "DeepLearningAgent",
    "RankingModelAgent",
    "build_dataset",
    "encode_dataset",
    "encode_jsonl",
    "encoded_jsonl_to_pt",
]


def __getattr__(name: str):
    if name in {"DatasetBuildConfig", "DatasetBuildResult", "EncodedSample"}:
        from .dataset_types import DatasetBuildConfig, DatasetBuildResult, EncodedSample

        return {
            "DatasetBuildConfig": DatasetBuildConfig,
            "DatasetBuildResult": DatasetBuildResult,
            "EncodedSample": EncodedSample,
        }[name]
    if name in {"ImitationDatasetBuilder", "build_dataset"}:
        from .dataset_builder import ImitationDatasetBuilder, build_dataset

        return {"ImitationDatasetBuilder": ImitationDatasetBuilder, "build_dataset": build_dataset}[name]
    if name in {"DeepLearningAgent", "RankingModelAgent"}:
        from brandi_dog.agents.deep_learning_agent import DeepLearningAgent

        return DeepLearningAgent
    if name in {"PartialInformationEncoder", "PartialInfoPerspectiveEncoderV2", "encode_dataset", "encode_jsonl", "encoded_jsonl_to_pt"}:
        from .encoders import PartialInformationEncoder, PartialInfoPerspectiveEncoderV2, encode_dataset, encode_jsonl, encoded_jsonl_to_pt

        return {
            "PartialInformationEncoder": PartialInformationEncoder,
            "PartialInfoPerspectiveEncoderV2": PartialInfoPerspectiveEncoderV2,
            "encode_dataset": encode_dataset,
            "encode_jsonl": encode_jsonl,
            "encoded_jsonl_to_pt": encoded_jsonl_to_pt,
        }[name]
    raise AttributeError(name)
