"""RAG pipeline: FAISS vector store + fastembed embeddings."""

import json
import logging

import faiss
import numpy as np
from fastembed import TextEmbedding

from app.config import (
    DOCUMENTS_CACHE_PATH,
    EMBEDDING_MODEL,
    FAISS_INDEX_PATH,
    KNOWLEDGE_BASE_PATH,
    RAG_TOP_K,
)

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Simple RAG pipeline using FAISS and fastembed."""

    def __init__(self) -> None:
        self.embedding_model: TextEmbedding | None = None
        self.index: faiss.IndexFlatIP | None = None
        self.documents: list[dict] = []

    def initialize(self) -> None:
        """Load or build the FAISS index and embedding model."""
        logger.info("Initializing RAG pipeline...")

        # Load embedding model
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        self.embedding_model = TextEmbedding(EMBEDDING_MODEL)

        # Load knowledge base documents
        logger.info("Loading knowledge base from: %s", KNOWLEDGE_BASE_PATH)
        with open(KNOWLEDGE_BASE_PATH) as f:
            self.documents = json.load(f)

        # Check for pre-built index
        if FAISS_INDEX_PATH.exists() and DOCUMENTS_CACHE_PATH.exists():
            logger.info("Loading pre-built FAISS index from: %s", FAISS_INDEX_PATH)
            self.index = faiss.read_index(str(FAISS_INDEX_PATH))
            logger.info("FAISS index loaded with %d vectors", self.index.ntotal)
        else:
            self._build_index()

        logger.info(
            "RAG pipeline ready — %d documents, %d vectors",
            len(self.documents),
            self.index.ntotal,
        )

    def _build_index(self) -> None:
        """Build and save the FAISS index."""
        logger.info("Building FAISS index from %d documents...", len(self.documents))

        # Prepare texts for embedding (combine title + content)
        texts = [
            f"{doc['title']}: {doc['content']}" for doc in self.documents
        ]

        # Generate embeddings
        embeddings = list(self.embedding_model.embed(texts))
        embeddings_np = np.array(embeddings, dtype=np.float32)

        # Normalize for cosine similarity (using inner product index)
        faiss.normalize_L2(embeddings_np)

        # Build index
        dimension = embeddings_np.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings_np)

        # Save index and documents cache
        FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(FAISS_INDEX_PATH))

        with open(DOCUMENTS_CACHE_PATH, "w") as f:
            json.dump(self.documents, f)

        logger.info("FAISS index saved to: %s", FAISS_INDEX_PATH)

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """Search for the most relevant documents given a query."""
        if self.index is None or self.embedding_model is None:
            raise RuntimeError("RAG pipeline not initialized. Call initialize() first.")

        k = top_k or RAG_TOP_K

        # Embed query
        query_embedding = list(self.embedding_model.embed([query]))
        query_np = np.array(query_embedding, dtype=np.float32)
        faiss.normalize_L2(query_np)

        # Search
        distances, indices = self.index.search(query_np, k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.documents):
                doc = self.documents[idx].copy()
                doc["score"] = float(distances[0][i])
                results.append(doc)

        return results


# Singleton instance
rag = RAGPipeline()
