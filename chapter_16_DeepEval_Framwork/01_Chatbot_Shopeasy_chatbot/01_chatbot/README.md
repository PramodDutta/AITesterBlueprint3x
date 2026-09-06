# Subsystem A — ShopSphere E-commerce Chatbot

React (Vite) frontend + FastAPI backend + Groq LLM. The "app under test" for the DeepEval framework.

## Ports
| Service | Port |
|--------|------|
| FastAPI backend | 8201 |
| Vite dev server | 5173 |

## Run

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
export GROQ_API_KEY=gsk_...
uvicorn app:app --reload --port 8201

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## API
- `GET /health` — status + active model
- `POST /chat` — `{message, history?}` → `{reply, model, mode}`
