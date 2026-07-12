"""Movement plugin — motor actions for the Responses API agent."""

import os

from hardware.motor import MotorController
from hardware.ultrasonic import UltrasonicSensor
from utils import setup_logger

logger = setup_logger("ringo.movement")

# Duration (seconds) for a ~45-degree rotation at speed=45.
# Tune with TURN_45_SECS=0.35 in .env if the angle is off.
_TURN_45_SECS = float(os.getenv("TURN_45_SECS", "0.4"))


class MovementPlugin:
    """Plugin for robot movement with safety checks."""

    def __init__(self, motor: MotorController, ultrasonic: UltrasonicSensor):
        self.motor = motor
        self.ultrasonic = ultrasonic

    def _check_obstacle(self) -> str | None:
        if self.ultrasonic.is_obstacle_ahead():
            self.motor.stop()
            return "Oops! Something is in my way. I better not go that direction!"
        return None

    # ── Tool implementations ──────────────────────────────────────────────────

    def move_forward(self, duration: float = 1.0) -> str:
        duration = max(0.5, min(duration, 3.0))
        obstacle = self._check_obstacle()
        if obstacle:
            return obstacle
        self.motor.move_forward(speed=50, duration=duration)
        return f"I moved forward for {duration} seconds!"

    def move_backward(self, duration: float = 1.0) -> str:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_backward(speed=50, duration=duration)
        return f"I backed up for {duration} seconds!"

    def turn_left(self, duration: float = 0.8) -> str:
        duration = max(0.3, min(duration, 2.0))
        self.motor.rotate_left(speed=45, duration=duration)
        return "I turned to the left!"

    def turn_right(self, duration: float = 0.8) -> str:
        duration = max(0.3, min(duration, 2.0))
        self.motor.rotate_right(speed=45, duration=duration)
        return "I turned to the right!"

    def strafe_left(self, duration: float = 1.0) -> str:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_left(speed=45, duration=duration)
        return "I slid to the left!"

    def strafe_right(self, duration: float = 1.0) -> str:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_right(speed=45, duration=duration)
        return "I slid to the right!"

    def stop(self) -> str:
        self.motor.stop()
        return "I stopped!"

    def nod_yes(self) -> str:
        self.motor.nod()
        return "I nodded yes!"

    def shake_head_no(self) -> str:
        self.motor.shake_head()
        return "I shook my head!"

    def look_around_gesture(self) -> str:
        self.motor.look_around()
        return "I looked around!"

    def rotate_45_left(self) -> str:
        self.motor.rotate_left(speed=45, duration=_TURN_45_SECS)
        return "I turned 45 degrees to the left."

    def rotate_45_right(self) -> str:
        self.motor.rotate_right(speed=45, duration=_TURN_45_SECS)
        return "I turned 45 degrees to the right."

    # ── Responses API tool definitions ────────────────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list[dict]:
        def _fn(name, desc, props=None, required=None):
            return {
                "type": "function",
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props or {},
                    "required": required or [],
                },
            }

        _dur = lambda lo, hi: {
            "type": "number",
            "description": f"Seconds to move ({lo} to {hi})",
        }

        return [
            _fn("move_forward",  "Move the robot forward. Use when exploring or approaching something.",
                {"duration": _dur(0.5, 3.0)}),
            _fn("move_backward", "Move the robot backward. Use to back away from something.",
                {"duration": _dur(0.5, 2.0)}),
            _fn("turn_left",     "Rotate left to look in a different direction.",
                {"duration": _dur(0.3, 2.0)}),
            _fn("turn_right",    "Rotate right to look in a different direction.",
                {"duration": _dur(0.3, 2.0)}),
            _fn("strafe_left",   "Slide sideways left without turning.",
                {"duration": _dur(0.5, 2.0)}),
            _fn("strafe_right",  "Slide sideways right without turning.",
                {"duration": _dur(0.5, 2.0)}),
            _fn("stop",              "Stop all movement immediately."),
            _fn("nod_yes",           "Nod the camera up and down (yes / excitement)."),
            _fn("shake_head_no",     "Shake the camera side to side (no / uncertainty)."),
            _fn("look_around_gesture","Pan the camera left and right as if searching."),
            _fn("rotate_45_left",
                "Rotate ~45 degrees left. Use for systematic scanning — call up to 8 times for a full circle. "
                "Always call check_if_object_visible after each rotation."),
            _fn("rotate_45_right",
                "Rotate ~45 degrees right. Use for systematic scanning — call up to 8 times for a full circle. "
                "Always call check_if_object_visible after each rotation."),
        ]
