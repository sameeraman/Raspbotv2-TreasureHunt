"""Navigation Agent — specialised agent for robot movement and positioning.

Handles all motor-control tasks:
  move_forward / move_backward / strafe_left / strafe_right
  turn_left / turn_right
  rotate_45_left / rotate_45_right  (for systematic scanning)
  stop / nod_yes / shake_head_no / look_around_gesture

Safety checks (obstacle detection) are enforced inside MovementPlugin.
"""

from typing import Annotated

from azure.core.credentials import TokenCredential
from pydantic import Field

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from config import AzureOpenAIConfig
from plugins.movement import MovementPlugin
from utils import setup_logger

logger = setup_logger("ringo.navigation_agent")

_INSTRUCTIONS = """You are Ringo's Navigation Agent — a specialist that controls the robot's movement.
Execute the requested movement task using your tools, then report what you did.

Rules:
- Use small movements — the robot is in a house with a child.
- The tools enforce obstacle checks automatically; report if blocked.
- If asked to scan, rotate_45_left then report the result.
- Keep replies brief — your output goes back to the main Ringo orchestrator.
"""


class NavigationAgent:
    """Specialist agent for all motor movement and positioning tasks."""

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        credential: TokenCredential,
        movement_plugin: MovementPlugin,
    ):
        m = movement_plugin

        client = OpenAIChatClient(
            azure_endpoint=openai_config.endpoint,
            model=openai_config.orchestrator_deployment,
            api_version=openai_config.api_version,
            credential=credential,
        )

        def move_forward(
            duration: Annotated[float, Field(description="Seconds (0.5–3.0)", ge=0.5, le=3.0)] = 1.0,
        ) -> str:
            """Move the robot forward. Checks for obstacles first."""
            return m.move_forward(duration=duration)

        def move_backward(
            duration: Annotated[float, Field(description="Seconds (0.5–2.0)", ge=0.5, le=2.0)] = 1.0,
        ) -> str:
            """Move the robot backward."""
            return m.move_backward(duration=duration)

        def turn_left(
            duration: Annotated[float, Field(description="Seconds (0.3–2.0)", ge=0.3, le=2.0)] = 0.8,
        ) -> str:
            """Rotate the robot to the left."""
            return m.turn_left(duration=duration)

        def turn_right(
            duration: Annotated[float, Field(description="Seconds (0.3–2.0)", ge=0.3, le=2.0)] = 0.8,
        ) -> str:
            """Rotate the robot to the right."""
            return m.turn_right(duration=duration)

        def strafe_left(
            duration: Annotated[float, Field(description="Seconds (0.5–2.0)", ge=0.5, le=2.0)] = 1.0,
        ) -> str:
            """Slide sideways to the left without turning."""
            return m.strafe_left(duration=duration)

        def strafe_right(
            duration: Annotated[float, Field(description="Seconds (0.5–2.0)", ge=0.5, le=2.0)] = 1.0,
        ) -> str:
            """Slide sideways to the right without turning."""
            return m.strafe_right(duration=duration)

        def stop() -> str:
            """Stop all movement immediately."""
            return m.stop()

        def nod_yes() -> str:
            """Nod the camera up and down (yes / excitement)."""
            return m.nod_yes()

        def shake_head_no() -> str:
            """Shake the camera side to side (no / uncertainty)."""
            return m.shake_head_no()

        def look_around_gesture() -> str:
            """Pan the camera left and right slowly, as if searching."""
            return m.look_around_gesture()

        def rotate_45_left() -> str:
            """Rotate approximately 45 degrees to the left.
            Used for systematic 360° scanning — repeat up to 8 times for a full circle."""
            return m.rotate_45_left()

        def rotate_45_right() -> str:
            """Rotate approximately 45 degrees to the right.
            Used for systematic 360° scanning — repeat up to 8 times for a full circle."""
            return m.rotate_45_right()

        self._agent = Agent(
            client=client,
            name="NavigationAgent",
            instructions=_INSTRUCTIONS,
            tools=[
                move_forward, move_backward, turn_left, turn_right,
                strafe_left, strafe_right, stop,
                nod_yes, shake_head_no, look_around_gesture,
                rotate_45_left, rotate_45_right,
            ],
        )
        logger.info("NavigationAgent ready")

    async def run(self, task: str) -> str:
        """Execute a movement task and return the result as a string."""
        logger.debug(f"NavigationAgent task: {task}")
        result = await self._agent.run(task)
        return str(result).strip()
