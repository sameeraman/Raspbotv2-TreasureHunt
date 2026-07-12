"""Memory Agent — specialised agent for persistent memory via Azure AI Search.

Handles all memory operations:
  remember              → store a new memory
  recall                → semantic vector search
  recall_favourites     → Sienna's favourite things
  recall_recent_adventures → recent treasure hunt sessions
"""

from typing import Annotated

from azure.core.credentials import TokenCredential
from pydantic import Field

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from config import AzureOpenAIConfig
from plugins.memory import MemoryPlugin
from utils import setup_logger

logger = setup_logger("ringo.memory_agent")

_INSTRUCTIONS = """You are Ringo's Memory Agent — a specialist for storing and retrieving memories.
Use your tools to save important events and recall relevant past experiences.

Rules:
- Store memories with accurate categories and meaningful content.
- When recalling, search for what is most useful for the current situation.
- Keep replies brief — your output goes back to the main Ringo orchestrator.
"""


class MemoryAgent:
    """Specialist agent for all memory storage and retrieval tasks."""

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        credential: TokenCredential,
        memory_plugin: MemoryPlugin,
    ):
        mp = memory_plugin

        client = OpenAIChatClient(
            azure_endpoint=openai_config.endpoint,
            model=openai_config.orchestrator_deployment,
            api_version=openai_config.api_version,
            credential=credential,
        )

        async def remember(
            content: Annotated[str, Field(description="What to remember")],
            category: Annotated[str, Field(
                description="Category: treasure_found / favourite / hint_pattern / story_moment / preference",
            )],
            importance: Annotated[int, Field(description="Importance 1–5", ge=1, le=5)] = 3,
            tags: Annotated[str, Field(description="Comma-separated tags")] = "",
        ) -> str:
            """Store a memory about something important that happened,
            something Sienna likes, or a place where treasure was found."""
            return await mp.remember(content=content, category=category,
                                     importance=importance, tags=tags)

        async def recall(
            query: Annotated[str, Field(description="What to search for in memories")],
            top_k: Annotated[int, Field(description="Number of memories to retrieve (1–5)", ge=1, le=5)] = 3,
        ) -> str:
            """Search memories for information relevant to the current situation.
            Use for past adventures, favourite things, or treasure locations."""
            return await mp.recall(query=query, top_k=top_k)

        async def recall_favourites() -> str:
            """Retrieve Sienna's known favourite things — colours, toys, characters, activities."""
            return await mp.recall_favourites()

        async def recall_recent_adventures(
            max_results: Annotated[int, Field(description="How many recent adventures (1–5)", ge=1, le=5)] = 3,
        ) -> str:
            """Retrieve what happened in recent treasure hunt sessions."""
            return await mp.recall_recent_adventures(max_results=max_results)

        self._agent = Agent(
            client=client,
            name="MemoryAgent",
            instructions=_INSTRUCTIONS,
            tools=[remember, recall, recall_favourites, recall_recent_adventures],
        )
        logger.info("MemoryAgent ready")

    async def run(self, task: str) -> str:
        """Execute a memory task and return the result as a string."""
        logger.debug(f"MemoryAgent task: {task}")
        result = await self._agent.run(task)
        return str(result).strip()
