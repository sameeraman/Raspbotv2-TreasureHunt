"""Ringo orchestrator — Microsoft Agent Framework, multi-agent architecture.

Architecture
────────────
  RingoAgent  (this file)
  │  ask_vision_agent(task)     ──►  VisionAgent
  │  ask_navigation_agent(task) ──►  NavigationAgent
  │  ask_memory_agent(task)     ──►  MemoryAgent   (optional)
  │  check_safety()             ──►  direct (no sub-agent, no AI needed)
  │  get_time_remaining()       ──►  direct

  Every agent runs locally on the Orange Pi.
  Only LLM inference crosses the network to Azure OpenAI.

Adding a new agent
  1. Create agents/<domain>_agent.py  →  class <Domain>Agent with .run(task)
  2. Add an ask_<domain>_agent tool closure in _build_tools()
  3. Update the orchestrator system prompt to mention the new capability

Azure auth: ClientSecretCredential — no new RBAC needed.
"""

from typing import Annotated

from azure.core.credentials import TokenCredential
from pydantic import Field

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from config import AzureOpenAIConfig
from agents.prompts import (
    RINGO_SYSTEM_PROMPT, RINGO_SYSTEM_PROMPT_WITH_MEMORY,
    RINGO_CHAT_SYSTEM_PROMPT,
    CHAT_GREETING_PROMPT, CHAT_TIMEOUT_PROMPT,
    TREASURE_HUNT_START_PROMPT, SESSION_END_PROMPT,
)
from agents.vision_agent      import VisionAgent
from agents.navigation_agent  import NavigationAgent
from agents.memory_agent      import MemoryAgent
from agents.planner_agent     import PlannerAgent
from plugins.vision    import VisionPlugin
from plugins.movement  import MovementPlugin
from plugins.safety    import SafetyPlugin
from plugins.memory    import MemoryPlugin
from utils import setup_logger

logger = setup_logger("ringo.orchestrator")


class RingoOrchestrator:
    """Coordinates Ringo's behaviour via specialist sub-agents.

    Conversation history is managed inside the Agent instance.
    Call reset_history() or switch_to_*_mode() to start a fresh conversation.
    """

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        credential: TokenCredential,
        vision_plugin:   VisionPlugin,
        movement_plugin: MovementPlugin,
        safety_plugin:   SafetyPlugin,
        memory_plugin:   MemoryPlugin | None = None,
    ):
        self._openai_config = openai_config
        self._credential    = credential
        self._safety        = safety_plugin
        self._memory_plugin = memory_plugin

        # Shared chat client for the orchestrator
        self._chat_client = OpenAIChatClient(
            azure_endpoint=openai_config.endpoint,
            model=openai_config.orchestrator_deployment,
            api_version=openai_config.api_version,   # >= 2025-03-01-preview
            credential=credential,
        )

        # Specialist sub-agents (created once, reused across sessions)
        self._vision_agent   = VisionAgent(openai_config, credential, vision_plugin)
        self._nav_agent      = NavigationAgent(openai_config, credential, movement_plugin)
        self._planner_agent  = PlannerAgent(openai_config, credential)
        self._mem_agent      = MemoryAgent(openai_config, credential, memory_plugin) \
                              if memory_plugin else None

        self._system_prompt: str = RINGO_SYSTEM_PROMPT
        self._agent: Agent | None = None
        self._create_agent()

        logger.info(
            "RingoOrchestrator ready (vision=%s navigation=%s planner=%s memory=%s)",
            self._vision_agent is not None,
            self._nav_agent is not None,
            self._planner_agent is not None,
            self._mem_agent is not None,
        )

    # ── Agent lifecycle ───────────────────────────────────────────────────────

    def _create_agent(self):
        """Instantiate a fresh RingoAgent with current instructions."""
        self._agent = Agent(
            client=self._chat_client,
            name="Ringo",
            instructions=self._system_prompt,
            tools=self._build_tools(),
        )

    def _build_tools(self) -> list:
        """Return the orchestrator-level tool functions.

        Each tool delegates to a specialist sub-agent via its .run(task) method.
        Safety tools stay direct — they're simple function calls, no AI needed.
        """
        va      = self._vision_agent
        nav     = self._nav_agent
        planner = self._planner_agent
        mem     = self._mem_agent
        s       = self._safety

        async def ask_planner_agent(
            task: Annotated[str, Field(
                description="Full description of the treasure hunt task including: "
                            "what Sienna wants to find, any size/colour/location hints she gave. "
                            "Example: 'Find a red cap — Sienna says it might be near her bedroom'"
            )],
        ) -> str:
            """Ask the Planner Agent (o3) to create a detailed search-and-approach plan.
            Call this FIRST whenever Sienna specifies what to find, before any physical search.
            The plan will tell you exactly how to use the vision and navigation agents
            to find the object efficiently and safely."""
            logger.debug(f"→ PlannerAgent: {task}")
            result = await planner.run(task)
            logger.debug(f"← PlannerAgent: {result[:120]}")
            return result

        async def ask_vision_agent(
            task: Annotated[str, Field(
                description="Natural-language description of the visual task to perform. "
                            "Examples: 'look around and describe the scene', "
                            "'check if the red cap is visible', "
                            "'get approach guidance for the blue ball'"
            )],
        ) -> str:
            """Delegate a visual perception task to the Vision Agent.
            Use for: looking around, searching for objects, scan checks, approach guidance.
            The Vision Agent has access to the camera and specialist vision tools."""
            logger.debug(f"→ VisionAgent: {task}")
            result = await va.run(task)
            logger.debug(f"← VisionAgent: {result[:80]}")
            return result

        async def ask_navigation_agent(
            task: Annotated[str, Field(
                description="Natural-language description of the movement to perform. "
                            "Examples: 'move forward 1 second', "
                            "'rotate 45 degrees left', "
                            "'turn right to face the object'"
            )],
        ) -> str:
            """Delegate a movement or positioning task to the Navigation Agent.
            Use for: moving forward/backward, turning, strafing, scanning rotations, gestures.
            The Navigation Agent controls the motors with built-in obstacle checking."""
            logger.debug(f"→ NavigationAgent: {task}")
            result = await nav.run(task)
            logger.debug(f"← NavigationAgent: {result[:80]}")
            return result

        def check_safety() -> str:
            """Check if it's safe to continue playing — time remaining and obstacles."""
            return s.check_safety()

        def get_time_remaining() -> str:
            """Check how many minutes of play time are left in this session."""
            return s.get_time_remaining()

        tools = [ask_planner_agent, ask_vision_agent, ask_navigation_agent, check_safety, get_time_remaining]

        if mem:
            async def ask_memory_agent(
                task: Annotated[str, Field(
                    description="Natural-language description of the memory task. "
                                "Examples: 'remember that Sienna found the teddy near the couch', "
                                "'recall where we found treasures before', "
                                "'what are Sienna's favourite things?'"
                )],
            ) -> str:
                """Delegate a memory task to the Memory Agent.
                Use for: storing new memories, recalling past adventures, finding favourites.
                The Memory Agent uses Azure AI Search with semantic vector search."""
                logger.debug(f"→ MemoryAgent: {task}")
                result = await mem.run(task)
                logger.debug(f"← MemoryAgent: {result[:80]}")
                return result

            tools.append(ask_memory_agent)

        return tools

    # ── Core inference ────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> str:
        """Send a user message and return Ringo's text reply.

        The Agent handles its own tool-execution loop. Tool calls delegate
        to sub-agents, which in turn call their local plugin functions.
        """
        logger.info(f"Sienna says: '{user_message[:100]}'")
        result = await self._agent.run(user_message)
        reply = str(result).strip() or "Woof! *tilts head*"
        logger.info(f"Ringo says: '{reply[:120]}'")
        return reply

    # ── Conversation management ───────────────────────────────────────────────

    def reset_history(self, memory_context: str = ""):
        """Start a fresh conversation by creating a new Agent instance."""
        self._system_prompt = (
            RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(memory_context=memory_context)
            if memory_context else RINGO_SYSTEM_PROMPT
        )
        self._create_agent()
        logger.info("Conversation reset")

    def switch_to_chat_mode(self):
        """Switch to casual chat mode with a fresh conversation."""
        self._system_prompt = RINGO_CHAT_SYSTEM_PROMPT
        self._create_agent()
        logger.info("Switched to chat mode")

    def switch_to_hunt_mode(self, memory_context: str = ""):
        """Switch to treasure-hunt mode with a fresh conversation."""
        self._system_prompt = (
            RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(memory_context=memory_context)
            if memory_context else RINGO_SYSTEM_PROMPT
        )
        self._create_agent()
        logger.info("Switched to hunt mode")

    # ── Convenience wrappers ──────────────────────────────────────────────────

    async def start_chat(self) -> str:
        return await self.chat(CHAT_GREETING_PROMPT)

    async def propose_close(self) -> str:
        return await self.chat(CHAT_TIMEOUT_PROMPT)

    async def start_treasure_hunt(self, memory_context: str = "") -> str:
        if memory_context:
            self._system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
            self._create_agent()
        return await self.chat(TREASURE_HUNT_START_PROMPT)

    async def end_session(self) -> str:
        return await self.chat(SESSION_END_PROMPT)
