# Brandi Dog Online Backend

FastAPI wrapper around the existing `brandi_dog` engine. The backend does not modify core game rules; it keeps session state, seats, bots, and HTTP/WebSocket transport in `backend/app`.

## Run

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..
backend/.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

API health check:

```bash
curl http://localhost:8000/api/health
```

## Bot Mapping

- `Idiot`: `RandomLegalAgent`
- `Easy`: `HeuristicAgent`
- `Medium`: `DeepLearningAgent` using the RL checkpoint under `brandi_dog/agents/reinforcement_learning/checkpoints/agent_0/checkpoint_agent_0_final.pt`
- `Hard`: `ImperfectInformationMonteCarloAgent`
- `Cheater`: `MonteCarloAgent`

Sessions are in memory. Restarting the backend clears active games.

## Human Dataset Collection

The backend can append human decisions as raw JSONL samples compatible with the existing supervised-learning encoders. Collection is disabled by default. When enabled, rows are written directly to disk and are not kept in RAM.

Environment variables:

```bash
BRANDI_COLLECT_HUMAN_DATASET=1
BRANDI_DATASET_DIR=/app/data
# optional explicit paths
BRANDI_TURN_DATASET_PATH=/app/data/human_turn_decisions.jsonl
BRANDI_SWAP_DATASET_PATH=/app/data/human_swap_decisions.jsonl
BRANDI_DATASET_CANDIDATE_ALTERNATIVES=10
```

Files:

- `human_turn_decisions.jsonl`: PLAY_LOOP decisions, using the same raw sample builder as the existing imitation/ranking dataset pipeline.
- `human_swap_decisions.jsonl`: TEAM_SWAPS decisions, same top-level JSONL shape in a separate file for a future swap model.

Status check:

```bash
curl http://localhost:8000/api/dataset/status
```

Encode turn samples later with:

```bash
python -m brandi_dog.agents.supervised_learning.encoders encode \
  --encoder v2 \
  --input /app/data/human_turn_decisions.jsonl \
  --output /app/data/human_turn_decisions_encoded_v2.jsonl

python -m brandi_dog.agents.supervised_learning.encoders to-pt \
  --input /app/data/human_turn_decisions_encoded_v2.jsonl \
  --output /app/data/human_turn_decisions_encoded_v2.pt
```
