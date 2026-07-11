"""Orchestrator agent — the main Semantic Kernel agent powering Ringo."""

from typing import Callable

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory

from config import AzureOpenAIConfig
from agents.prompts import RINGO_SYSTEM_PROMPT, RINGO_SYSTEM_PROMPT_WITH_MEMORY
from plugins.vision import VisionPlugin
from plugins.movement import MovementPlugin
from plugins.safety import SafetyPlugin
from plugins.memory import MemoryPlugin
from utils import setup_logger

logger = setup_logger("ringo.orchestrator")


class RingoOrchestrator:
    """Main orchestrator that coordinates Ringo's behavior via Semantic Kernel."""

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        token_provider: Callable[[], str],
        vision_plugin: VisionPlugin,
        movement_plugin: MovementPlugin,
        safety_plugin: SafetyPlugin,
        memory_plugin: MemoryPlugin | None = None,
    ):
        self.openai_config = openai_config
        self.memory_plugin = memory_plugin
        self.kernel = Kernel()
        self.chat_history = ChatHistory(system_message=RINGO_SYSTEM_PROMPT)

        # Register the Azure OpenAI chat service using token-based auth
        self.kernel.add_service(
            AzureChatCompletion(
                service_id="orchestrator",
                deployment_name=openai_config.orchestrator_deployment,
                endpoint=openai_config.endpoint,
                ad_token_provider=token_provider,
                api_version=openai_config.api_version,
            )
        )

        # Register plugins
        self.kernel.add_plugin(vision_plugin, plugin_name="vision")
        self.kernel.add_plugin(movement_plugin, plugin_name="movement")
        self.kernel.add_plugin(safety_plugin, plugin_name="safety")
        if memory_plugin:
            self.kernel.add_plugin(memory_plugin, plugin_name="memory")

        # Execution settings: allow the model to call functions automatically
        self.execution_settings = AzureChatPromptExecutionSettings(
            service_id="orchestrator",
            max_completion_tokens=300,
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                auto_invoke=True,
            ),
        )

        logger.info("Ringo orchestrator initialized (memory=%s)", memory_plugin is not None)

    async def chat(self, user_message: str) -> str:
        """Process a message from Sienna and return Ringo's response.

        The orchestrator may call vision, movement, safety, or memory plugins
        as needed before formulating a response.
        """
        logger.info(f"Sienna says: '{user_message}'")
        self.chat_history.add_user_message(user_message)

        chat_service = self.kernel.get_service("orchestrator")
        results = await chat_service.get_chat_message_contents(
            chat_history=self.chat_history,
            settings=self.execution_settings,
            kernel=self.kernel,
        )

        assistant_message = str(results[0])
        self.chat_history.add_assistant_message(assistant_message)
        logger.info(f"Ringo says: '{assistant_message}'")
        return assistant_message

    async def start_treasure_hunt(self, memory_context: str = "") -> str:
        """Generate the opening greeting for a new treasure hunt session.

        If memory_context is provided, it's injected into the system prompt
        so Ringo can reference past adventures in the greeting.
        """
        if memory_context:
            system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
            self.chat_history = ChatHistory(system_message=system_prompt)
            logger.info("Injected memory context into system prompt")

        from agents.prompts import TREASURE_HUNT_START_PROMPT
        return await self.chat(TREASURE_HUNT_START_PROMPT)

    async def end_session(self) -> str:
        """Generate a cheerful goodbye message."""
        from agents.prompts import SESSION_END_PROMPT
        return await self.chat(SESSION_END_PROMPT)

    def reset_history(self, memory_context: str = ""):
        """Clear conversation history for a fresh session.

        Optionally injects memory context into the new system prompt.
        """
        if memory_context:
            system_prompt = RINGO_SYSTEM_PROMPT_WITH_MEMORY.format(
                memory_context=memory_context
            )
        else:
            system_prompt = RINGO_SYSTEM_PROMPT

        self.chat_history = ChatHistory(system_message=system_prompt)
        logger.info("Chat history reset")

    def switch_to_chat_mode(self):
        """Switch system prompt to casual chat mode."""
        from agents.prompts import RINGO_CHAT_SYSTEM_PROMPT
        self.chat_history = ChatHistory(system_message=RINGO_CHAT_SYSTEM_PROMPT)
        logger.info("Switched to chat mode")

    async def start_chat(self) -> str:
        """Generate the wake-word greeting in casual chat mode."""
        from agents.prompts import CHAT_GREETING_PROMPT
        return await self.chat(CHAT_GREETING_PROMPT)

    async def propose_close(self) -> str:
        """Suggest wrapping up after 5 minutes of chat."""
        from agents.prompts import CHAT_TIMEOUT_PROMPT
        return await self.chat(CHAT_TIMEOUT_PROMPT)
