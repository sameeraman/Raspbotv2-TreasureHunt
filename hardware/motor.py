"""Motor control wrapper with safety speed limiting for Raspbotv2.

Wraps the Mecanum wheel driver with a configurable max speed cap
to ensure safe operation around children.
"""

import time
import math

try:
    from Raspbot_Lib import Raspbot
except ImportError:
    Raspbot = None

from utils import setup_logger

logger = setup_logger("ringo.motor")


class MotorController:
    """Speed-limited Mecanum wheel controller."""

    def __init__(self, max_speed: int = 75):
        self.max_speed = min(max_speed, 255)
        if Raspbot:
            self.bot = Raspbot()
        else:
            self.bot = None
            logger.warning("Raspbot_Lib not available — motor commands will be simulated")

    def _clamp_speed(self, speed: int) -> int:
        return max(0, min(speed, self.max_speed))

    def _set_deflection(self, speed: int, deflection: int) -> tuple[int, int, int, int]:
        speed = self._clamp_speed(speed)
        rad = math.pi / 180
        vx = speed * math.cos(deflection * rad)
        vy = speed * math.sin(deflection * rad)
        l1 = int(vy + vx)
        l2 = int(vy - vx)
        r1 = int(vy - vx)
        r2 = int(vy + vx)
        return l1, l2, r1, r2

    def _drive(self, l1: int, l2: int, r1: int, r2: int):
        if self.bot:
            self.bot.Ctrl_Muto(0, l1)
            self.bot.Ctrl_Muto(1, l2)
            self.bot.Ctrl_Muto(2, r1)
            self.bot.Ctrl_Muto(3, r2)
        else:
            logger.debug(f"SIM motor: L1={l1} L2={l2} R1={r1} R2={r2}")

    def move_forward(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Moving forward (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 90)
        self._drive(l1, l2, r1, r2)
        time.sleep(duration)
        self.stop()

    def move_backward(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Moving backward (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 270)
        self._drive(l1, l2, r1, r2)
        time.sleep(duration)
        self.stop()

    def move_left(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Moving left (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 180)
        self._drive(l1, l2, r1, r2)
        time.sleep(duration)
        self.stop()

    def move_right(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Moving right (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 0)
        self._drive(l1, l2, r1, r2)
        time.sleep(duration)
        self.stop()

    def rotate_left(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Rotating left (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 180)
        if self.bot:
            self.bot.Ctrl_Muto(0, l1)
            self.bot.Ctrl_Muto(1, -l2)
            self.bot.Ctrl_Muto(2, r1)
            self.bot.Ctrl_Muto(3, abs(r2))
        time.sleep(duration)
        self.stop()

    def rotate_right(self, speed: int = 40, duration: float = 1.0):
        logger.info(f"Rotating right (speed={self._clamp_speed(speed)}, {duration}s)")
        l1, l2, r1, r2 = self._set_deflection(speed, 0)
        if self.bot:
            self.bot.Ctrl_Muto(0, l1)
            self.bot.Ctrl_Muto(1, abs(l2))
            self.bot.Ctrl_Muto(2, r1)
            self.bot.Ctrl_Muto(3, -r2)
        time.sleep(duration)
        self.stop()

    def stop(self):
        if self.bot:
            self.bot.Ctrl_Car(0, 0, 0)
            self.bot.Ctrl_Car(1, 0, 0)
            self.bot.Ctrl_Car(2, 0, 0)
            self.bot.Ctrl_Car(3, 0, 0)
        logger.debug("Motors stopped")

    def nod(self):
        """Camera PTZ nod gesture (yes)."""
        logger.info("Nodding")
        if self.bot:
            for _ in range(2):
                self.bot.Ctrl_Servo(2, 25)
                time.sleep(0.3)
                self.bot.Ctrl_Servo(2, 100)
                time.sleep(0.3)
            self.bot.Ctrl_Servo(2, 25)

    def shake_head(self):
        """Camera PTZ shake gesture (no/looking around)."""
        logger.info("Shaking head")
        if self.bot:
            for _ in range(2):
                self.bot.Ctrl_Servo(1, 60)
                time.sleep(0.3)
                self.bot.Ctrl_Servo(1, 120)
                time.sleep(0.3)
            self.bot.Ctrl_Servo(1, 90)

    def look_around(self):
        """Slowly pan camera left and right (searching gesture)."""
        logger.info("Looking around")
        if self.bot:
            self.bot.Ctrl_Servo(1, 45)
            time.sleep(0.8)
            self.bot.Ctrl_Servo(1, 135)
            time.sleep(0.8)
            self.bot.Ctrl_Servo(1, 90)
            time.sleep(0.4)

    def reset_servos(self):
        """Return camera to center position."""
        if self.bot:
            self.bot.Ctrl_Servo(1, 90)
            self.bot.Ctrl_Servo(2, 25)
