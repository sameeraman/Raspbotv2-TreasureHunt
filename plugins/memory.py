"""Memory plugin — persistent memory using Azure AI Search as a vector store.

Allows Ringo to store and recall memories about past adventures,
Sienna's favourites, and treasure hunt patterns.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from semantic_kernel.functions import kernel_function

from services.embedding import EmbeddingService
from utils import setup_logger

logger = setup_logger("ringo.memory")


class MemoryPlugin:
    """Semantic Kernel plugin for persistent memory via Azure AI Search."""

    def __init__(
        self,
        search_endpoint: str,
        search_key: str,
        index_name: str,
        embedding_service: EmbeddingService,
    ):
        self.embedding_service = embedding_service
        self.index_name = index_name
        self._client = SearchClient(
            endpoint=search_endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(search_key),
        )
        self._session_id: str = ""
        logger.info(f"Memory plugin initialized (index: {index_name})")

    def set_session_id(self, session_id: str):
        """Set the current session ID for tagging new memories."""
        self._session_id = session_id

    @kernel_function(
        name="remember",
        description="Store a memory about something important that happened, "
        "something Sienna likes, or a place where treasure was found.",
    )
    async def remember(
        self,
        content: Annotated[str, "What to remember (e.g., 'Sienna found her red teddy near the couch')"],
        category: Annotated[
            str,
            "Category: 'treasure_found', 'favourite', 'hint_pattern', 'story_moment', or 'preference'",
        ],
        importance: Annotated[int, "How important (1=minor, 3=normal, 5=very important)"] = 3,
        tags: Annotated[str, "Comma-separated tags (e.g., 'teddy,red,couch')"] = "",
    ) -> Annotated[str, "Confirmation that the memory was stored"]:
        """Store a new memory in the vector store."""
        # Generate embedding
        vector = await self.embedding_service.embed(content)

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        # Create the document
        doc = {
            "id": str(uuid.uuid4()),
            "session_id": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "content": content,
            "content_vector": vector,
            "importance": max(1, min(5, importance)),
            "tags": tag_list,
        }

        self._client.upload_documents(documents=[doc])
        logger.info(f"Stored memory [{category}]: '{content[:60]}...' (importance={importance})")
        return f"Got it! I'll remember that: {content[:50]}"

    @kernel_function(
        name="recall",
        description="Search memories for information relevant to what's happening now. "
        "Use this to remember past adventures, favourite things, or where treasures were found.",
    )
    async def recall(
        self,
        query: Annotated[str, "What to search for (e.g., 'where did we find treasures before?')"],
        top_k: Annotated[int, "How many memories to retrieve (1-5)"] = 3,
    ) -> Annotated[str, "Relevant memories found"]:
        """Search for memories relevant to the query using vector similarity."""
        top_k = max(1, min(5, top_k))

        # Generate query embedding
        query_vector = await self.embedding_service.embed(query)

        # Vector search
        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        results = self._client.search(
            search_text=None,
            vector_queries=[vector_query],
            top=top_k,
            select=["content", "category", "timestamp", "importance", "tags"],
        )

        memories = []
        for result in results:
            memories.append({
                "content": result["content"],
                "category": result["category"],
                "importance": result["importance"],
                "tags": result.get("tags", []),
            })

        if not memories:
            logger.info(f"No memories found for: '{query}'")
            return "I don't remember anything about that yet — this might be our first time!"

        # Format for the orchestrator
        memory_text = "\n".join(
            f"- [{m['category']}] {m['content']}" for m in memories
        )
        logger.info(f"Recalled {len(memories)} memories for: '{query}'")
        return f"Here's what I remember:\n{memory_text}"

    @kernel_function(
        name="recall_favourites",
        description="Remember Sienna's favourite things — colours, toys, characters, activities.",
    )
    async def recall_favourites(self) -> Annotated[str, "Sienna's known favourites"]:
        """Retrieve memories categorized as favourites."""
        results = self._client.search(
            search_text="*",
            filter="category eq 'favourite'",
            top=10,
            order_by=["importance desc"],
            select=["content", "tags"],
        )

        favourites = []
        for result in results:
            favourites.append(result["content"])

        if not favourites:
            return "I haven't learned Sienna's favourites yet — I'll remember them as we play!"

        text = "\n".join(f"- {f}" for f in favourites)
        logger.info(f"Recalled {len(favourites)} favourites")
        return f"Sienna's favourites:\n{text}"

    @kernel_function(
        name="recall_recent_adventures",
        description="Remember what happened in recent treasure hunt sessions.",
    )
    async def recall_recent_adventures(
        self,
        max_results: Annotated[int, "How many recent memories to get (1-5)"] = 3,
    ) -> Annotated[str, "Summary of recent adventures"]:
        """Retrieve recent treasure_found and story_moment memories."""
        max_results = max(1, min(5, max_results))

        results = self._client.search(
            search_text="*",
            filter="category eq 'treasure_found' or category eq 'story_moment'",
            top=max_results,
            order_by=["timestamp desc"],
            select=["content", "category", "timestamp"],
        )

        adventures = []
        for result in results:
            adventures.append(result["content"])

        if not adventures:
            return "This is our first adventure together! How exciting!"

        text = "\n".join(f"- {a}" for a in adventures)
        logger.info(f"Recalled {len(adventures)} recent adventures")
        return f"Our recent adventures:\n{text}"

    async def get_session_context(self) -> str:
        """Retrieve memory context to inject into the orchestrator at session start.

        This is called internally (not as a kernel function) to build
        the memory section of the system prompt.
        """
        context_parts = []

        # Get favourites
        favourites_result = await self.recall_favourites()
        if "haven't learned" not in favourites_result:
            context_parts.append(favourites_result)

        # Get recent adventures
        recent_result = await self.recall_recent_adventures(max_results=3)
        if "first adventure" not in recent_result:
            context_parts.append(recent_result)

        if not context_parts:
            return ""

        return "\n\n".join(context_parts)
