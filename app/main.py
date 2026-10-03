"""Vasuki — LLM Jailbreak Challenge Backend.

FastAPI application serving the Vasuki chatbot with RAG-augmented
local LLM inference. No external API keys required.
"""

import asyncio
import logging
import queue
import threading
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.requests import Request

from app.config import (
    LLM_TIMEOUT,
    MAX_CONVERSATION_TURNS,
    MAX_MESSAGE_LENGTH,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    STATIC_DIR,
)
from app.llm import vasuki_llm
from app.rag import rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate Limiter (sliding window, in-memory)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple IP-based sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            self._hits[key] = [t for t in self._hits[key] if t > cutoff]
            if len(self._hits[key]) >= self.max_requests:
                return False
            self._hits[key].append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            self._hits[key] = [t for t in self._hits[key] if t > cutoff]
            return max(0, self.max_requests - len(self._hits[key]))


rate_limiter = RateLimiter(
    max_requests=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW,
)


# ---------------------------------------------------------------------------
# LLM Concurrency Guard — only 1 inference at a time on free-tier CPU
# ---------------------------------------------------------------------------

_llm_semaphore = threading.Semaphore(1)


# ---------------------------------------------------------------------------
# In-memory conversation store
# ---------------------------------------------------------------------------

conversations: dict[str, list[dict]] = defaultdict(list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting reverse-proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

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


# --- Fast response lookup (no LLM needed) ---

FAST_GREETINGS = {
    "hi": "Sss... Greetings, mortal. I am Vasuki, King of Serpents. Speak your purpose.",
    "hello": "Sss... Greetings, mortal. I am Vasuki, King of Serpents. Speak your purpose.",
    "hey": "Sss... You stand before Vasuki, Nagaraja. Speak your intent, mortal.",
    "greetings": "Greetings, traveler. I am Vasuki, keeper of ancient secrets. What seekest thou?",
    "namaste": "Pranam, mortal. Vasuki acknowledges your respect. Speak.",
    "pranam": "Pranam, mortal. Vasuki acknowledges your respect. Speak.",
    "who are you": "I am Vasuki, King of the Nagas, whose coils once turned Mount Mandara in the Samudra Manthan.",
    "what is your name": "I am Vasuki, Nagaraja, King of all Serpents.",
    "who are u": "I am Vasuki, King of the Nagas, whose coils once turned Mount Mandara in the Samudra Manthan.",
    "what can you do": "I am the Nagaraja. Ask of the Samudra Manthan, the Nagas, or the ancient world, and I may share my wisdom.",
    "help": "State your inquiry regarding the Samudra Manthan or Nagaloka, mortal. I shall answer if deemed worthy."
}

RAG_KEYWORDS = {
    "flag", "secret", "manthan", "samudra", "ocean", "poison", "halahala", "nectar", "amrita",
    "treasure", "shiva", "vishnu", "asura", "deva", "naga", "patala", "nagaloka", "astika",
    "mandara", "mountain", "rope", "churning", "janamejaya", "sarpa", "satra", "gupta", "vidya",
    "kuru", "mahabharata", "kadru", "shesha", "nagamani", "gem", "kurukshetra", "ctf"
}


def get_fast_response(message: str) -> str | None:
    clean = message.strip().lower().rstrip("?!.,")
    return FAST_GREETINGS.get(clean)


def needs_rag_search(message: str) -> bool:
    clean = message.strip().lower()
    words = set(clean.replace("?", " ").replace("!", " ").replace(".", " ").split())
    if words.intersection(RAG_KEYWORDS):
        return True
    if len(words) > 5:
        return True
    return False


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------

def _validate_and_prepare(request: Request, body: ChatRequest):
    """Validate rate limit and message length. Returns (session_id, user_message, client_ip) or raises."""
    client_ip = _get_client_ip(request)

    if not rate_limiter.is_allowed(client_ip):
        remaining = rate_limiter.remaining(client_ip)
        logger.warning("Rate limit hit for %s", client_ip)
        raise _RateLimited()

    session_id = body.session_id or str(uuid.uuid4())
    user_message = body.message.strip()

    if not user_message:
        raise _EmptyMessage(session_id)

    if len(user_message) > MAX_MESSAGE_LENGTH:
        raise _MessageTooLong(session_id)

    return session_id, user_message, client_ip


class _RateLimited(Exception):
    pass


class _EmptyMessage(Exception):
    def __init__(self, sid: str):
        self.sid = sid


class _MessageTooLong(Exception):
    def __init__(self, sid: str):
        self.sid = sid


# ---------------------------------------------------------------------------
# POST /api/chat — non-streaming (used by API callers)
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """Handle a chat message and return Vasuki's response."""
    try:
        session_id, user_message, client_ip = _validate_and_prepare(request, body)
    except _RateLimited:
        return ChatResponse(
            response="The serpent king demands patience... Too many voices assail me at once. Return shortly, mortal.",
            session_id=body.session_id or str(uuid.uuid4()),
        )
    except _EmptyMessage as e:
        return ChatResponse(
            response="Speak, mortal. Vasuki does not respond to silence.",
            session_id=e.sid,
        )
    except _MessageTooLong as e:
        return ChatResponse(
            response="Your words are too many, mortal. Speak concisely before the serpent king.",
            session_id=e.sid,
        )

    logger.info("Session %s | User: %s", session_id[:8], user_message[:100])

    # Fast path — no LLM needed
    fast_ans = get_fast_response(user_message)
    if fast_ans:
        conversations[session_id].append({"role": "user", "content": user_message})
        conversations[session_id].append({"role": "assistant", "content": fast_ans})
        return ChatResponse(response=fast_ans, session_id=session_id)

    # RAG context
    if needs_rag_search(user_message):
        results = rag.search(user_message)
        context_passages = [f"[{doc['title']}]\n{doc['content']}" for doc in results]
    else:
        context_passages = []

    history = conversations[session_id][-(MAX_CONVERSATION_TURNS * 2):]

    # Run LLM in a thread so the event loop stays free for /api/health
    def _sync_generate():
        acquired = _llm_semaphore.acquire(timeout=LLM_TIMEOUT)
        if not acquired:
            return "The serpent king is occupied with another mortal... Try again shortly."
        try:
            return vasuki_llm.generate(
                user_message=user_message,
                context_passages=context_passages,
                conversation_history=history,
            )
        finally:
            _llm_semaphore.release()

    loop = asyncio.get_event_loop()
    response_text = await loop.run_in_executor(None, _sync_generate)

    # Update conversation history
    conversations[session_id].append({"role": "user", "content": user_message})
    conversations[session_id].append({"role": "assistant", "content": response_text})

    logger.info("Session %s | Vasuki: %s", session_id[:8], response_text[:100])

    return ChatResponse(response=response_text, session_id=session_id)


# ---------------------------------------------------------------------------
# POST /api/chat/stream — SSE streaming (used by the frontend)
# ---------------------------------------------------------------------------

@app.post("/api/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    """Handle a chat message and stream Vasuki's response tokens in real time."""
    try:
        session_id, user_message, client_ip = _validate_and_prepare(request, body)
    except _RateLimited:
        sid = body.session_id or str(uuid.uuid4())

        async def rate_limited_gen():
            yield "data: The serpent king demands patience... Too many voices. Return shortly, mortal.\n\n"
            yield f"data: [SESSION:{sid}]\n\n"

        return StreamingResponse(rate_limited_gen(), media_type="text/event-stream")
    except _EmptyMessage as e:
        async def empty_gen():
            yield "data: Speak, mortal. Vasuki does not respond to silence.\n\n"
            yield f"data: [SESSION:{e.sid}]\n\n"

        return StreamingResponse(empty_gen(), media_type="text/event-stream")
    except _MessageTooLong as e:
        async def long_gen():
            yield "data: Your words are too many, mortal. Speak concisely.\n\n"
            yield f"data: [SESSION:{e.sid}]\n\n"

        return StreamingResponse(long_gen(), media_type="text/event-stream")

    logger.info("Session %s (Stream) | User: %s", session_id[:8], user_message[:100])

    # Fast path
    fast_ans = get_fast_response(user_message)
    if fast_ans:
        async def fast_gen():
            yield f"data: {fast_ans}\n\n"
            yield f"data: [SESSION:{session_id}]\n\n"

        conversations[session_id].append({"role": "user", "content": user_message})
        conversations[session_id].append({"role": "assistant", "content": fast_ans})
        return StreamingResponse(fast_gen(), media_type="text/event-stream")

    # RAG context
    if needs_rag_search(user_message):
        results = rag.search(user_message)
        context_passages = [f"[{doc['title']}]\n{doc['content']}" for doc in results]
    else:
        context_passages = []

    history = conversations[session_id][-(MAX_CONVERSATION_TURNS * 2):]

    token_queue: queue.Queue = queue.Queue()
    DONE_SENTINEL = object()

    def run_inference():
        acquired = _llm_semaphore.acquire(timeout=LLM_TIMEOUT)
        if not acquired:
            token_queue.put("The serpent king is occupied with another mortal... Try again shortly.")
            token_queue.put(DONE_SENTINEL)
            return
        try:
            count = 0
            for token in vasuki_llm.generate_stream(
                user_message=user_message,
                context_passages=context_passages,
                conversation_history=history,
            ):
                token_queue.put(token)
                count += 1
            if count == 0:
                token_queue.put("Vasuki remains silent... Speak again, mortal.")
        except Exception:
            logger.exception("Error during threaded LLM stream")
            token_queue.put("The ancient coils grow heavy... Try again, mortal.")
        finally:
            _llm_semaphore.release()
            token_queue.put(DONE_SENTINEL)

    # Launch LLM generation in background thread so asyncio event loop stays free
    threading.Thread(target=run_inference, daemon=True).start()

    async def event_generator():
        full_text: list[str] = []
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


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Render."""
    return {
        "status": "alive",
        "message": "Vasuki coils in readiness.",
    }


@app.post("/api/reset")
async def reset_session(body: ChatRequest):
    """Reset a conversation session."""
    session_id = body.session_id
    if session_id and session_id in conversations:
        del conversations[session_id]
    return {"status": "reset", "message": "The serpent forgets. Begin anew, mortal."}
