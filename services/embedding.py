"""Azure OpenAI Embedding service for memory vector search."""

from typing import Callable

from openai import AzureOpenAI

from utils import setup_logger

logger = setup_logger("ringo.embedding")


class EmbeddingService:
    """Generates text embeddings using Azure OpenAI text-embedding-3-small."""

    def __init__(self, endpoint: str, token_provider: Callable[[], str],
                 deployment: str, api_version: str):
        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        self.deployment = deployment
        self.dimensions = 1536

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text string."""
        response = self.client.embeddings.create(
            input=text,
            model=self.deployment,
        )
        vector = response.data[0].embedding
        logger.debug(f"Embedded text ({len(text)} chars) → {len(vector)}-dim vector")
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single API call."""
        if not texts:
            return []

        response = self.client.embeddings.create(
            input=texts,
            model=self.deployment,
        )
        vectors = [item.embedding for item in response.data]
        logger.debug(f"Batch embedded {len(texts)} texts")
        return vectors
