"""Memory plugin — persistent memory using Azure AI Search as a vector store."""

import uuid
from datetime import datetime, timezone

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

from services.embedding import EmbeddingService
from utils import setup_logger

logger = setup_logger("ringo.memory")


class MemoryPlugin:
    """Plugin for persistent memory via Azure AI Search."""

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
        self._session_id = session_id

    # ── Tool implementations ──────────────────────────────────────────────────

    async def remember(
        self,
        content: str,
        category: str,
        importance: int = 3,
        tags: str = "",
    ) -> str:
        vector = await self.embedding_service.embed(content)
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
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
        logger.info(f"Stored memory [{category}]: '{content[:60]}' (importance={importance})")
        return f"Got it! I'll remember that: {content[:50]}"

    async def recall(self, query: str, top_k: int = 3) -> str:
        top_k = max(1, min(5, top_k))
        query_vector = await self.embedding_service.embed(query)
        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )
        results = self._client.search(
            search_text=None,
            vector_queries=[vector_query],
            top=top_k,
            select=["content", "category", "importance", "tags"],
        )
        memories = [r for r in results]
        if not memories:
            logger.info(f"No memories found for: '{query}'")
            return "I don't remember anything about that yet — this might be our first time!"
        text = "\n".join(f"- [{m['category']}] {m['content']}" for m in memories)
        logger.info(f"Recalled {len(memories)} memories for: '{query}'")
        return f"Here's what I remember:\n{text}"

    async def recall_favourites(self) -> str:
        results = self._client.search(
            search_text="*",
            filter="category eq 'favourite'",
            top=10,
            order_by=["importance desc"],
            select=["content", "tags"],
        )
        favourites = [r["content"] for r in results]
        if not favourites:
            return "I haven't learned Sienna's favourites yet — I'll remember them as we play!"
        text = "\n".join(f"- {f}" for f in favourites)
        logger.info(f"Recalled {len(favourites)} favourites")
        return f"Sienna's favourites:\n{text}"

    async def recall_recent_adventures(self, max_results: int = 3) -> str:
        max_results = max(1, min(5, max_results))
        results = self._client.search(
            search_text="*",
            filter="category eq 'treasure_found' or category eq 'story_moment'",
            top=max_results,
            order_by=["timestamp desc"],
            select=["content", "category", "timestamp"],
        )
        adventures = [r["content"] for r in results]
        if not adventures:
            return "This is our first adventure together! How exciting!"
        text = "\n".join(f"- {a}" for a in adventures)
        logger.info(f"Recalled {len(adventures)} recent adventures")
        return f"Our recent adventures:\n{text}"

    async def get_session_context(self) -> str:
        """Build the memory section for the system prompt at session start."""
        parts = []
        fav = await self.recall_favourites()
        if "haven't learned" not in fav:
            parts.append(fav)
        recent = await self.recall_recent_adventures(max_results=3)
        if "first adventure" not in recent:
            parts.append(recent)
        return "\n\n".join(parts)

    # ── Responses API tool definitions ────────────────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list[dict]:
        return [
            {
                "type": "function",
                "name": "remember",
                "description": (
                    "Store a memory about something important that happened, "
                    "something Sienna likes, or a place where treasure was found."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "What to remember, e.g. 'Sienna found her red teddy near the couch'",
                        },
                        "category": {
                            "type": "string",
                            "enum": ["treasure_found", "favourite", "hint_pattern", "story_moment", "preference"],
                            "description": "Category of the memory",
                        },
                        "importance": {
                            "type": "integer",
                            "description": "Importance 1 (minor) to 5 (critical)",
                            "minimum": 1, "maximum": 5,
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags e.g. 'teddy,red,couch'",
                        },
                    },
                    "required": ["content", "category"],
                },
            },
            {
                "type": "function",
                "name": "recall",
                "description": (
                    "Search memories for information relevant to what's happening now. "
                    "Use to remember past adventures, favourites, or where treasures were found."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "How many memories to retrieve (1-5)",
                            "minimum": 1, "maximum": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "type": "function",
                "name": "recall_favourites",
                "description": "Remember Sienna's favourite things — colours, toys, characters, activities.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            {
                "type": "function",
                "name": "recall_recent_adventures",
                "description": "Remember what happened in recent treasure hunt sessions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "How many recent memories to get (1-5)",
                            "minimum": 1, "maximum": 5,
                        }
                    },
                    "required": [],
                },
            },
        ]
