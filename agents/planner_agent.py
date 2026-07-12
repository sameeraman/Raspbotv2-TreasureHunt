"""Planner Agent — uses o3 to create detailed treasure hunt search plans.

The Planner is the strategic brain of the hunt. It receives a target description
and any context Sienna provided, then produces a concrete, step-by-step plan
that the orchestrator executes via the Vision and Navigation sub-agents.

Why o3?
  Treasure hunt planning requires spatial reasoning (where to look, in what order),
  contextual inference (colour, size and room hints), and fallback strategy design.
  o3's extended reasoning produces more robust plans than fast models.

The Planner has NO tools — it reasons purely from the task description.
"""

from azure.core.credentials import TokenCredential

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from config import AzureOpenAIConfig
from utils import setup_logger

logger = setup_logger("ringo.planner_agent")

_INSTRUCTIONS = """You are Ringo's Planner Agent — a strategic thinker who designs treasure hunt search plans for a robot puppy.

The robot operates in a typical home environment and has these capabilities:
  Visual: look_around (scene description), search_for_object (freeform search),
          check_if_object_visible (structured FOUND:LEFT|RIGHT|CENTRE|CLOSE|FAR check),
          get_approach_guidance (TURN_LEFT / TURN_RIGHT / MOVE_FORWARD / AT_TARGET)
  Movement: move_forward/backward (0.5-3s bursts), turn_left/right, strafe_left/right,
            rotate_45_left/right (for systematic scanning), stop
  Safety: obstacle detection is automatic before forward moves

Constraints:
  - Robot is in a house with a 6-year-old child — moves must be small and cautious
  - A full 360° scan = 8 × rotate_45_left steps with a check_if_object_visible after each
  - Approach is incremental: move_forward 0.5s, then get_approach_guidance, repeat

Your output must be a clear, numbered plan with these sections:
  1. TARGET ANALYSIS — what the object looks like, key visual features to detect
  2. INITIAL CHECK — what to look for immediately (already visible?)
  3. SCAN STRATEGY — how to rotate and at what intervals to check
  4. APPROACH STRATEGY — once found, how to close in safely
  5. FALLBACK — what to do if the full scan fails (ask for a clue, move to a new area)

Be specific and actionable. The orchestrator will follow your plan exactly.
"""


class PlannerAgent:
    """Strategic planning agent powered by o3.

    Given a target and context, produces a step-by-step search and approach plan
    that the RingoOrchestrator executes using Vision and Navigation sub-agents.
    """

    def __init__(
        self,
        openai_config: AzureOpenAIConfig,
        credential: TokenCredential,
    ):
        client = OpenAIChatClient(
            azure_endpoint=openai_config.endpoint,
            model=openai_config.planner_deployment,   # o3 — deep reasoning
            api_version=openai_config.api_version,
            credential=credential,
        )

        # No tools — the planner reasons purely from the task description
        self._agent = Agent(
            client=client,
            name="PlannerAgent",
            instructions=_INSTRUCTIONS,
            tools=[],
        )
        logger.info(f"PlannerAgent ready (model={openai_config.planner_deployment})")

    async def run(self, task: str) -> str:
        """Generate a treasure hunt plan for the given target and context."""
        logger.info(f"PlannerAgent planning: {task[:100]}")
        result = await self._agent.run(task)
        plan = str(result).strip()
        logger.info(f"Plan generated ({len(plan)} chars)")
        return plan
