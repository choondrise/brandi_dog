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
