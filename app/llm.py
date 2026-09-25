"""LLM wrapper for local inference via llama-cpp-python."""

import logging
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from app.config import (
    MODEL_CONTEXT_LENGTH,
    MODEL_FILENAME,
    MODEL_MAX_TOKENS,
    MODEL_REPO,
    MODEL_TEMPERATURE,
    MODEL_THREADS,
    MODELS_DIR,
)
from app.prompts import SYSTEM_PROMPT, build_rag_prompt

logger = logging.getLogger(__name__)


class VasukiLLM:
    """Local LLM wrapper using llama-cpp-python."""

    def __init__(self) -> None:
        self.llm: Llama | None = None
        self.model_path: Path | None = None

    def initialize(self) -> None:
        """Download model (if needed) and load into memory."""
        self.model_path = self._download_model()

        logger.info("Loading LLM from: %s", self.model_path)
        self.llm = Llama(
            model_path=str(self.model_path),
            n_ctx=MODEL_CONTEXT_LENGTH,
            n_threads=MODEL_THREADS,
            verbose=False,
        )
        logger.info("LLM loaded successfully")

    def _download_model(self) -> Path:
        """Download the GGUF model from Hugging Face Hub."""
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        local_path = MODELS_DIR / MODEL_FILENAME

        if local_path.exists():
            logger.info("Model already cached at: %s", local_path)
            return local_path

        logger.info(
            "Downloading model: %s/%s → %s", MODEL_REPO, MODEL_FILENAME, local_path
        )
        downloaded = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            local_dir=str(MODELS_DIR),
        )
        logger.info("Model downloaded: %s", downloaded)
        return Path(downloaded)

    def generate(
        self,
        user_message: str,
        context_passages: list[str],
        conversation_history: list[dict],
    ) -> str:
        """Generate a response from Vasuki given user input and RAG context."""
        if self.llm is None:
            raise RuntimeError("LLM not initialized. Call initialize() first.")

        # Build messages list
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add conversation history (last N turns)
        messages.extend(conversation_history)

        # Build the current user message with RAG context
        augmented_message = build_rag_prompt(context_passages, user_message)
        messages.append({"role": "user", "content": augmented_message})

        # Generate response
        try:
            response = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=MODEL_MAX_TOKENS,
                temperature=MODEL_TEMPERATURE,
                top_p=0.9,
                repeat_penalty=1.1,
            )

            content = response["choices"][0]["message"]["content"]
            return content.strip() if content else "The serpent king is silent..."

        except Exception:
            logger.exception("Error generating response")
            return (
                "The ancient coils grow heavy... "
                "Vasuki cannot speak at this moment. Try again, mortal."
            )


# Singleton instance
vasuki_llm = VasukiLLM()
