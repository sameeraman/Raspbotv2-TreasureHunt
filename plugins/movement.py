"""Movement plugin — exposes motor actions to the Semantic Kernel agent."""

from typing import Annotated
from semantic_kernel.functions import kernel_function

from hardware.motor import MotorController
from hardware.ultrasonic import UltrasonicSensor
from utils import setup_logger

logger = setup_logger("ringo.movement")


class MovementPlugin:
    """Semantic Kernel plugin for robot movement with safety checks."""

    def __init__(self, motor: MotorController, ultrasonic: UltrasonicSensor):
        self.motor = motor
        self.ultrasonic = ultrasonic

    def _check_obstacle(self) -> str | None:
        """Returns a warning string if obstacle is ahead, else None."""
        if self.ultrasonic.is_obstacle_ahead():
            self.motor.stop()
            return "Oops! Something is in my way. I better not go that direction!"
        return None

    @kernel_function(
        name="move_forward",
        description="Move the robot forward for a short distance. Use when exploring or approaching something.",
    )
    def move_forward(
        self,
        duration: Annotated[float, "How many seconds to move (0.5 to 3.0)"] = 1.0,
    ) -> Annotated[str, "Result of the movement"]:
        duration = max(0.5, min(duration, 3.0))
        obstacle = self._check_obstacle()
        if obstacle:
            return obstacle
        self.motor.move_forward(speed=50, duration=duration)
        return f"I moved forward for {duration} seconds!"

    @kernel_function(
        name="move_backward",
        description="Move the robot backward. Use to back away from something.",
    )
    def move_backward(
        self,
        duration: Annotated[float, "How many seconds to move (0.5 to 2.0)"] = 1.0,
    ) -> Annotated[str, "Result of the movement"]:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_backward(speed=50, duration=duration)
        return f"I backed up for {duration} seconds!"

    @kernel_function(
        name="turn_left",
        description="Rotate the robot to the left to look in a different direction.",
    )
    def turn_left(
        self,
        duration: Annotated[float, "How long to turn (0.3 to 2.0 seconds)"] = 0.8,
    ) -> Annotated[str, "Result of the turn"]:
        duration = max(0.3, min(duration, 2.0))
        self.motor.rotate_left(speed=45, duration=duration)
        return "I turned to the left!"

    @kernel_function(
        name="turn_right",
        description="Rotate the robot to the right to look in a different direction.",
    )
    def turn_right(
        self,
        duration: Annotated[float, "How long to turn (0.3 to 2.0 seconds)"] = 0.8,
    ) -> Annotated[str, "Result of the turn"]:
        duration = max(0.3, min(duration, 2.0))
        self.motor.rotate_right(speed=45, duration=duration)
        return "I turned to the right!"

    @kernel_function(
        name="strafe_left",
        description="Slide sideways to the left without turning.",
    )
    def strafe_left(
        self,
        duration: Annotated[float, "How long to strafe (0.5 to 2.0)"] = 1.0,
    ) -> Annotated[str, "Result of the movement"]:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_left(speed=45, duration=duration)
        return "I slid to the left!"

    @kernel_function(
        name="strafe_right",
        description="Slide sideways to the right without turning.",
    )
    def strafe_right(
        self,
        duration: Annotated[float, "How long to strafe (0.5 to 2.0)"] = 1.0,
    ) -> Annotated[str, "Result of the movement"]:
        duration = max(0.5, min(duration, 2.0))
        self.motor.move_right(speed=45, duration=duration)
        return "I slid to the right!"

    @kernel_function(
        name="stop",
        description="Stop all movement immediately.",
    )
    def stop(self) -> Annotated[str, "Confirmation"]:
        self.motor.stop()
        return "I stopped!"

    @kernel_function(
        name="nod_yes",
        description="Nod the camera up and down (to say yes or show excitement).",
    )
    def nod_yes(self) -> Annotated[str, "Confirmation"]:
        self.motor.nod()
        return "I nodded yes!"

    @kernel_function(
        name="shake_head_no",
        description="Shake the camera side to side (to say no or show uncertainty).",
    )
    def shake_head_no(self) -> Annotated[str, "Confirmation"]:
        self.motor.shake_head()
        return "I shook my head!"

    @kernel_function(
        name="look_around_gesture",
        description="Pan the camera left and right slowly, as if searching for something.",
    )
    def look_around_gesture(self) -> Annotated[str, "Confirmation"]:
        self.motor.look_around()
        return "I looked around!"
