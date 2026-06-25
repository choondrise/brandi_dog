# Brandi Dog Web App

The online app is split from the current game engine:

- `backend/`: FastAPI session server.
- `frontend/`: mobile-first Vite client.
- `brandi_dog/`: existing engine and agents, imported but not modified by the web layer.

## Local Development

Terminal 1:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Create a game, copy the six-character game ID, and join from another browser/device on the same network.

## Current Scope

Sessions are in-memory and no stats are recorded. The server is authoritative: clients submit an action index from the current legal action list, and the backend applies it through the existing engine.
