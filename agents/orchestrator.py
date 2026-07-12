"""Ringo orchestrator — Azure OpenAI Responses API with local tool execution.

Uses the Responses API (requires api_version >= 2025-03-01-preview) for:
  - Stateful multi-turn conversation via previous_response_id
  - Automatic tool calling with local execution loop
  - Persistent system instructions per conversation mode

RBAC: existing service principal with Cognitive Services User role is sufficient.
Token scope: https://cognitiveservices.azure.com/.default  (unchanged)
"""

import asyncio
import inspect
import json
from typing import Callable

from openai import AsyncAzureOpenAI

from config import AzureOpenAIConfig
from agents.prompts import RINGO_SYSTEM_PROMPT, RINGO_SYSTEM_PROMPT_WITH_MEMORY
from plugins.vision import VisionPlugin
from plugins.movement import MovementPlugin
from plugins.safety import SafetyPlugin
from plugins.memory import MemoryPlugin
from utils import setup_logger

logger = setup_logger("ringo.orchestrator")

# Maximum tool-call rounds per turn (prevents infinite loops)
_MAX_TOOL_ROUNDS = 15


class RingoOrchestrator:
    """Coordinates Ringo's behaviour via the Azure OpenAI Responses API."""

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        token_provider: Callable[[], str],
        vision_plugin: VisionPlugin,
        movement_plugin: MovementPlugin,
        safety_plugin: SafetyPlugin,
        memory_plugin: MemoryPlugin | None = None,
    ):
        self.deployment = openai_config.orchestrator_deployment
        self.vision   = vision_plugin
        self.movement = movement_plugin
        self.safety   = safety_plugin
        self.memory   = memory_plugin

        # Async OpenAI client (Responses API is natively async here)
        self._client = AsyncAzureOpenAI(
            azure_endpoint=openai_config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=openai_config.api_version,  # >= 2025-03-01-preview required
        )

        # Conversation state — server-side thread tracked by response ID
        self._previous_response_id: str | None = None
        self._system_prompt: str = RINGO_SYSTEM_PROMPT

        # Collect all tool definitions from plugins
        self._tools: list[dict] = (
            VisionPlugin.get_tool_definitions()
            + MovementPlugin.get_tool_definitions()
            + SafetyPlugin.get_tool_definitions()
            + (MemoryPlugin.get_tool_definitions() if memory_plugin else [])
        )

        # Map tool names → callables
        m, v, s = movement_plugin, vision_plugin, safety_plugin
        self._executors: dict[str, Callable] = {
            # vision
            "look_around":            lambda a: v.look_around(),
            "search_for_object":      lambda a: v.search_for_object(target=a["target"]),
            "check_if_object_visible":lambda a: v.check_if_object_visible(target=a["target"]),
            "get_approach_guidance":  lambda a: v.get_approach_guidance(target=a["target"]),
            # movement
            "move_forward":        lambda a: m.move_forward(duration=a.get("duration", 1.0)),
            "move_backward":       lambda a: m.move_backward(duration=a.get("duration", 1.0)),
            "turn_left":           lambda a: m.turn_left(duration=a.get("duration", 0.8)),
            "turn_right":          lambda a: m.turn_right(duration=a.get("duration", 0.8)),
            "strafe_left":         lambda a: m.strafe_left(duration=a.get("duration", 1.0)),
            "strafe_right":        lambda a: m.strafe_right(duration=a.get("duration", 1.0)),
            "stop":                lambda a: m.stop(),
            "nod_yes":             lambda a: m.nod_yes(),
            "shake_head_no":       lambda a: m.shake_head_no(),
            "look_around_gesture": lambda a: m.look_around_gesture(),
            "rotate_45_left":      lambda a: m.rotate_45_left(),
            "rotate_45_right":     lambda a: m.rotate_45_right(),
            # safety
            "check_safety":      lambda a: s.check_safety(),
            "get_time_remaining":lambda a: s.get_time_remaining(),
        }
        if memory_plugin:
            mp = memory_plugin
            self._executors.update({
                "remember":               lambda a: mp.remember(**a),
                "recall":                 lambda a: mp.recall(**a),
                "recall_favourites":      lambda a: mp.recall_favourites(),
                "recall_recent_adventures":lambda a: mp.recall_recent_adventures(
                    max_results=a.get("max_results", 3)
                ),
            })

        logger.info(
            "RingoOrchestrator ready (Responses API, %d tools, memory=%s)",
            len(self._tools), memory_plugin is not None,
        )

    # ── Core inference ────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> str:
        """Send a user message and return Ringo's text reply.

        Runs a tool-execution loop internally: the model may call any number of
        tools before producing its final text response.
        """
        logger.info(f"Sienna says: '{user_message}'")

        response = await self._client.responses.create(
            model=self.deployment,
            input=user_message,
            instructions=self._system_prompt,
            tools=self._tools,
            previous_response_id=self._previous_response_id,
        )

        # Tool-execution loop
        for _round in range(_MAX_TOOL_ROUNDS):
            tool_calls = [
                item for item in response.output
                if item.type == "function_call"
            ]
            if not tool_calls:
                break

            tool_outputs = []
            for call in tool_calls:
                output = await self._execute_tool(call.name, call.arguments)
                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": output,
                })

            response = await self._client.responses.create(
                model=self.deployment,
                input=tool_outputs,
                previous_response_id=response.id,
            )

        self._previous_response_id = response.id

        # Extract text from the response
        parts: list[str] = []
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    text = getattr(content, "text", None)
                    if text:
                        parts.append(text)

        reply = " ".join(parts).strip() or "Woof! *tilts head*"
        logger.info(f"Ringo says: '{reply[:120]}'")
        return reply

    async def _execute_tool(self, name: str, arguments_json: str) -> str:
        """Execute a named tool and return its string result."""
        try:
            args = json.loads(arguments_json) if arguments_json else {}
            executor = self._executors.get(name)
            if not executor:
                logger.warning(f"Unknown tool called: {name}")
                return f"Unknown tool: {name}"
            result = executor(args)
            if inspect.isawaitable(result):
                result = await result
            output = str(result)
            logger.info(f"Tool '{name}' → {output[:100]}")
            return output
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}", exc_info=True)
            return f"Tool error: {e}"

    # ── Conversation management ───────────────────────────────────────────────

    def reset_history(self, memory_context: str = ""):
        """Start a fresh conversation (clears server-side thread)."""
        self._previous_response_id = None
        if memory_context:
            self._system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
        else:
            self._system_prompt = RINGO_SYSTEM_PROMPT
        logger.info("Conversation history reset")

    def switch_to_chat_mode(self):
        """Switch to casual chat mode (also resets thread)."""
        from agents.prompts import RINGO_CHAT_SYSTEM_PROMPT
        self._system_prompt = RINGO_CHAT_SYSTEM_PROMPT
        self._previous_response_id = None
        logger.info("Switched to chat mode")

    def switch_to_hunt_mode(self, memory_context: str = ""):
        """Switch to treasure-hunt mode (also resets thread)."""
        if memory_context:
            self._system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
        else:
            self._system_prompt = RINGO_SYSTEM_PROMPT
        self._previous_response_id = None
        logger.info("Switched to hunt mode")

    # ── Convenience wrappers ──────────────────────────────────────────────────

    async def start_chat(self) -> str:
        from agents.prompts import CHAT_GREETING_PROMPT
        return await self.chat(CHAT_GREETING_PROMPT)

    async def propose_close(self) -> str:
        from agents.prompts import CHAT_TIMEOUT_PROMPT
        return await self.chat(CHAT_TIMEOUT_PROMPT)

    async def start_treasure_hunt(self, memory_context: str = "") -> str:
        if memory_context:
            self._system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
        from agents.prompts import TREASURE_HUNT_START_PROMPT
        return await self.chat(TREASURE_HUNT_START_PROMPT)

    async def end_session(self) -> str:
        from agents.prompts import SESSION_END_PROMPT
        return await self.chat(SESSION_END_PROMPT)
