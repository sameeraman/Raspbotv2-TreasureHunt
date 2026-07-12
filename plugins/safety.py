"""Safety plugin — session limits and obstacle checks."""

import time

from hardware.ultrasonic import UltrasonicSensor
from utils import setup_logger

logger = setup_logger("ringo.safety")


class SafetyPlugin:
    """Plugin for safety checks and session management."""

    def __init__(self, ultrasonic: UltrasonicSensor, max_session_minutes: int = 15):
        self.ultrasonic = ultrasonic
        self.max_session_minutes = max_session_minutes
        self._session_start: float | None = None

    # ── Non-tool helpers called directly by main.py ───────────────────────────

    def start_session(self):
        self._session_start = time.time()
        logger.info(f"Play session started (max {self.max_session_minutes} min)")

    def get_elapsed_minutes(self) -> float:
        if not self._session_start:
            return 0.0
        return (time.time() - self._session_start) / 60.0

    def is_session_expired(self) -> bool:
        expired = self.get_elapsed_minutes() >= self.max_session_minutes
        if expired:
            logger.info("Session time limit reached!")
        return expired

    # ── Tool implementations (invoked by the orchestrator) ────────────────────

    def check_safety(self) -> str:
        issues = []
        elapsed = self.get_elapsed_minutes()
        remaining = self.max_session_minutes - elapsed
        if remaining <= 0:
            issues.append("TIME_UP: The play session is over! Time for a break.")
        elif remaining <= 2:
            issues.append(f"ALMOST_DONE: Only {remaining:.0f} minutes left to play!")
        if self.ultrasonic.is_obstacle_ahead():
            issues.append("OBSTACLE: Something is blocking the path ahead.")
        if not issues:
            return f"All clear! We have about {remaining:.0f} minutes of play time left."
        return " | ".join(issues)

    def get_time_remaining(self) -> str:
        remaining = self.max_session_minutes - self.get_elapsed_minutes()
        if remaining <= 0:
            return "Our play time is up! We should take a break."
        return f"We have about {remaining:.0f} minutes left to play!"

    # ── Responses API tool definitions ────────────────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list[dict]:
        return [
            {
                "type": "function",
                "name": "check_safety",
                "description": "Check if it's safe to continue playing — looks at time and obstacles.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            {
                "type": "function",
                "name": "get_time_remaining",
                "description": "Check how many minutes of play time are left in this session.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        ]
