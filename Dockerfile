FROM python:3.11-slim

# Install build dependencies for llama-cpp-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the GGUF model at build time (cached in Docker layer)
RUN python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download( \
    repo_id='Qwen/Qwen2.5-0.5B-Instruct-GGUF', \
    filename='qwen2.5-0.5b-instruct-q4_k_m.gguf', \
    local_dir='/app/models' \
)"

# Pre-download the embedding model at build time
RUN python -c "\
from fastembed import TextEmbedding; \
TextEmbedding('BAAI/bge-small-en-v1.5')"

# Copy application code
COPY . .

# Build the FAISS index at build time
RUN python -c "\
import sys; sys.path.insert(0, '/app'); \
from app.rag import rag; \
rag.initialize(); \
print('FAISS index built successfully')"

# Expose port (Render uses PORT env var, default 10000)
EXPOSE 10000

# Run the server
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
