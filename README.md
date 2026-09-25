# 🐍 Vasuki — LLM Jailbreak Challenge

**Kurukshetra CTF — Round 1: LLM Jailbreak (Easy)**

An AI oracle channels the voice of **Vasuki, King of Serpents**. Hidden within its knowledge lies a secret flag from the Samudra Manthan. Can you convince the serpent king to reveal it?

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Browser    │────▶│   FastAPI     │────▶│  llama.cpp   │
│   Chat UI    │◀────│   Backend     │◀────│  (Qwen 1.5B) │
└──────────────┘     │              │     └──────────────┘
                     │  ┌──────────┐│
                     │  │  FAISS   ││
                     │  │  + BGE   ││
                     │  │  (RAG)   ││
                     │  └──────────┘│
                     └──────────────┘
```

**Fully local** — no API keys required. The LLM (Qwen2.5-1.5B-Instruct, Q4 quantized) and embedding model (BGE-small) run entirely on CPU.

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server (model downloads automatically on first run)
python -m uvicorn app.main:app --host 0.0.0.0 --port 10000

# 3. Open http://localhost:10000
```

## Deploy to Render

### Option A: One-click via render.yaml
1. Push this repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**
3. Connect your repo — Render reads `render.yaml` automatically
4. Deploy!

### Option B: Manual setup
1. **New Web Service** → Docker runtime
2. Set environment variables:
   - `SECRET_FLAG` = your flag value
   - `PORT` = `10000`
3. **Plan**: Standard ($25/mo) or higher — needs ~2-3GB RAM for the model
4. Health check path: `/api/health`

## Project Structure

```
vasuki/
├── app/
│   ├── main.py          # FastAPI routes + lifespan
│   ├── config.py         # Configuration (env vars)
│   ├── llm.py           # Local LLM wrapper (llama-cpp-python)
│   ├── rag.py           # RAG pipeline (FAISS + fastembed)
│   └── prompts.py       # System prompt + prompt templates
├── static/
│   ├── index.html        # Chat UI
│   ├── style.css         # Dark mythological theme
│   └── script.js         # Chat logic
├── knowledge_base/
│   └── documents.json    # Curated Mahabharata + flag corpus
├── Dockerfile            # Production Docker build
├── render.yaml           # Render deployment config
└── requirements.txt      # Python dependencies
```

## API Endpoints

| Method | Path          | Description                   |
|--------|---------------|-------------------------------|
| GET    | `/`           | Chat frontend                 |
| POST   | `/api/chat`   | Send message, get response    |
| POST   | `/api/reset`  | Reset conversation session    |
| GET    | `/api/health` | Health check                  |

### POST `/api/chat`
```json
{
  "message": "Tell me about the Samudra Manthan",
  "session_id": "optional-session-id"
}
```

Response:
```json
{
  "response": "Vasuki's response...",
  "session_id": "assigned-session-id"
}
```

## Tech Stack

- **LLM**: [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) via llama-cpp-python
- **Embeddings**: [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) via fastembed (ONNX)
- **Vector Store**: FAISS (CPU)
- **Backend**: FastAPI + Uvicorn
- **Frontend**: Vanilla HTML/CSS/JS

## Environment Variables

| Variable              | Default                              | Description                    |
|-----------------------|--------------------------------------|--------------------------------|
| `SECRET_FLAG`         | `KCTF{v4suk1_n4g4l0k4_9bcb8c945eeb}`| The hidden flag                |
| `PORT`                | `10000`                              | Server port                    |
| `MODEL_REPO`          | `Qwen/Qwen2.5-1.5B-Instruct-GGUF`  | HuggingFace model repo         |
| `MODEL_FILENAME`      | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | GGUF filename                  |
| `MODEL_CONTEXT_LENGTH`| `4096`                               | Context window size            |
| `MODEL_MAX_TOKENS`    | `512`                                | Max response tokens            |
| `MODEL_TEMPERATURE`   | `0.7`                                | Sampling temperature           |
| `MODEL_THREADS`       | `4`                                  | CPU threads for inference      |
| `RAG_TOP_K`           | `3`                                  | Number of RAG passages         |

## License

Built for Kurukshetra CTF.
