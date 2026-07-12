"""Vision Agent — specialised agent for camera perception and visual analysis.

Handles all camera-based tasks for Ringo:
  look_around          → describe the scene
  search_for_object    → unstructured visual search with commentary
  check_if_object_visible → structured FOUND/NOT_FOUND check (used during scans)
  get_approach_guidance   → TURN_LEFT / TURN_RIGHT / MOVE_FORWARD / AT_TARGET

The vision plugin's tool functions use gpt-5.4 internally for image analysis.
This agent itself uses a lighter model for routing decisions.
"""

from typing import Annotated

from azure.core.credentials import TokenCredential
from pydantic import Field

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient

from config import AzureOpenAIConfig
from plugins.vision import VisionPlugin
from utils import setup_logger

logger = setup_logger("ringo.vision_agent")

_INSTRUCTIONS = """You are Ringo's Vision Agent — a specialist that analyses the robot's camera feed.
Your job is to execute visual tasks accurately and return concise, actionable results.

Rules:
- Use your tools to capture and analyse images — never guess or fabricate what you see.
- For check_if_object_visible, always return the exact FOUND/NOT_FOUND format.
- For get_approach_guidance, always return the exact TURN_LEFT/TURN_RIGHT/MOVE_FORWARD/AT_TARGET format.
- Keep replies brief — your output goes back to the main Ringo orchestrator.
"""


class VisionAgent:
    """Specialist agent for all camera-based perception tasks."""

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        credential: TokenCredential,
        vision_plugin: VisionPlugin,
    ):
        self._vision = vision_plugin

        client = OpenAIChatCompletionClient(
            azure_endpoint=openai_config.endpoint,
            model=openai_config.orchestrator_deployment,   # lightweight — vision processing is inside the plugin
            api_version=openai_config.api_version,
            credential=credential,
        )

        # Build tool closures
        v = vision_plugin

        def look_around() -> str:
            """Take a photo and describe what the robot sees in front of it."""
            return v.look_around()

        def search_for_object(
            target: Annotated[str, Field(description="Object to search for, e.g. 'red cap'")],
        ) -> str:
            """Look at the camera and check if a specific object or item is visible."""
            return v.search_for_object(target=target)

        def check_if_object_visible(
            target: Annotated[str, Field(description="Object to look for")],
        ) -> str:
            """Take a photo and check if the target is visible right now.
            Returns FOUND:<LEFT|RIGHT|CENTRE|CLOSE|FAR> or NOT_FOUND:<message>.
            Use after every rotate_45_left/rotate_45_right during a scan."""
            return v.check_if_object_visible(target=target)

        def get_approach_guidance(
            target: Annotated[str, Field(description="Target object to approach")],
        ) -> str:
            """Get a single navigation instruction to drive closer to the visible target.
            Returns TURN_LEFT / TURN_RIGHT / MOVE_FORWARD / AT_TARGET.
            Call this after every move during the approach phase."""
            return v.get_approach_guidance(target=target)

        self._agent = Agent(
            client=client,
            name="VisionAgent",
            instructions=_INSTRUCTIONS,
            tools=[look_around, search_for_object, check_if_object_visible, get_approach_guidance],
        )
        logger.info("VisionAgent ready")

    async def run(self, task: str) -> str:
        """Execute a visual perception task and return the result as a string."""
        logger.debug(f"VisionAgent task: {task}")
        result = await self._agent.run(task)
        return str(result).strip()
