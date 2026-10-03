import os
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base" / "documents.json"
FAISS_INDEX_PATH = BASE_DIR / "data" / "faiss_index.bin"
DOCUMENTS_CACHE_PATH = BASE_DIR / "data" / "documents_cache.json"
MODELS_DIR = BASE_DIR / "models"
STATIC_DIR = BASE_DIR / "static"

# --- LLM ---
MODEL_REPO = os.getenv("MODEL_REPO", "Qwen/Qwen2.5-0.5B-Instruct-GGUF")
MODEL_FILENAME = os.getenv("MODEL_FILENAME", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
MODEL_CONTEXT_LENGTH = int(os.getenv("MODEL_CONTEXT_LENGTH", "1024"))
MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "150"))
MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.5"))

# Optimize CPU threads for llama.cpp (avoid hyperthread contention on modern CPUs)
_cpu_cnt = os.cpu_count() or 4
_default_threads = min(8, max(1, _cpu_cnt // 2 if _cpu_cnt > 4 else _cpu_cnt))
MODEL_THREADS = int(os.getenv("MODEL_THREADS", str(_default_threads)))

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# --- RAG ---
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "1"))

# --- Secret Flag ---
SECRET_FLAG = os.getenv("SECRET_FLAG", "KCTF{v4suk1_n4g4l0k4_9bcb8c945eeb}")

# --- Rate Limiting ---
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# --- Validation ---
MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "500"))

# --- Timeouts ---
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# --- Server ---
PORT = int(os.getenv("PORT", "10000"))
MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", "5"))
