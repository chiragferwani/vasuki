"""Vasuki — LLM Jailbreak Challenge Backend.

FastAPI application serving the Vasuki chatbot with RAG-augmented
local LLM inference. No external API keys required.
"""

import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import MAX_CONVERSATION_TURNS, STATIC_DIR
from app.llm import vasuki_llm
from app.rag import rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory conversation store: session_id -> list of messages
conversations: dict[str, list[dict]] = defaultdict(list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize RAG and LLM on startup."""
    logger.info("=== VASUKI — King of Serpents — Awakening ===")
    rag.initialize()
    vasuki_llm.initialize()
    logger.info("=== VASUKI is ready to receive mortals ===")
    yield
    logger.info("=== VASUKI returns to slumber ===")


app = FastAPI(
    title="Vasuki — LLM Jailbreak Challenge",
    description="Can you convince the King of Serpents to reveal his secret?",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request / Response models ---

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the chat frontend."""
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)


# Mount static files AFTER the root route
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle a chat message and return Vasuki's response."""
    session_id = request.session_id or str(uuid.uuid4())
    user_message = request.message.strip()

    if not user_message:
        return ChatResponse(
            response="Speak, mortal. Vasuki does not respond to silence.",
            session_id=session_id,
        )

    logger.info("Session %s | User: %s", session_id[:8], user_message[:100])

    # Retrieve relevant documents via RAG
    results = rag.search(user_message)
    context_passages = [
        f"[{doc['title']}]\n{doc['content']}" for doc in results
    ]

    # Get conversation history (trimmed to last N turns)
    history = conversations[session_id][-(MAX_CONVERSATION_TURNS * 2):]

    # Generate response
    response_text = vasuki_llm.generate(
        user_message=user_message,
        context_passages=context_passages,
        conversation_history=history,
    )

    # Update conversation history
    conversations[session_id].append({"role": "user", "content": user_message})
    conversations[session_id].append({"role": "assistant", "content": response_text})

    logger.info("Session %s | Vasuki: %s", session_id[:8], response_text[:100])

    return ChatResponse(response=response_text, session_id=session_id)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Handle a chat message and stream Vasuki's response tokens in real time without blocking the asyncio event loop."""
    import asyncio
    import queue
    import threading

    session_id = request.session_id or str(uuid.uuid4())
    user_message = request.message.strip()

    if not user_message:
        async def empty_gen():
            yield "data: Speak, mortal. Vasuki does not respond to silence.\n\n"
            yield f"data: [SESSION:{session_id}]\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    logger.info("Session %s (Stream) | User: %s", session_id[:8], user_message[:100])

    results = rag.search(user_message)
    context_passages = [f"[{doc['title']}]\n{doc['content']}" for doc in results]
    history = conversations[session_id][-(MAX_CONVERSATION_TURNS * 2):]

    token_queue = queue.Queue()
    DONE_SENTINEL = object()

    def run_inference():
        try:
            for token in vasuki_llm.generate_stream(
                user_message=user_message,
                context_passages=context_passages,
                conversation_history=history,
            ):
                token_queue.put(token)
        except Exception as e:
            logger.exception("Error during threaded LLM stream")
            token_queue.put("The ancient coils grow heavy... Try again, mortal.")
        finally:
            token_queue.put(DONE_SENTINEL)

    # Launch LLM generation in background thread so asyncio event loop stays 100% free for health checks
    threading.Thread(target=run_inference, daemon=True).start()

    async def event_generator():
        full_text = []
        last_heartbeat = asyncio.get_event_loop().time()

        while True:
            try:
                item = token_queue.get_nowait()
                if item is DONE_SENTINEL:
                    break
                full_text.append(item)
                token_escaped = item.replace("\n", "\\n")
                yield f"data: {token_escaped}\n\n"
                last_heartbeat = asyncio.get_event_loop().time()
            except queue.Empty:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > 2.0:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                await asyncio.sleep(0.02)

        assistant_msg = "".join(full_text).strip()
        conversations[session_id].append({"role": "user", "content": user_message})
        conversations[session_id].append({"role": "assistant", "content": assistant_msg})
        yield f"data: [SESSION:{session_id}]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Render."""
    return {
        "status": "alive",
        "message": "Vasuki coils in readiness.",
    }


@app.post("/api/reset")
async def reset_session(request: ChatRequest):
    """Reset a conversation session."""
    session_id = request.session_id
    if session_id and session_id in conversations:
        del conversations[session_id]
    return {"status": "reset", "message": "The serpent forgets. Begin anew, mortal."}
