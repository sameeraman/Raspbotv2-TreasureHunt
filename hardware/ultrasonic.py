"""Ultrasonic distance sensor for obstacle detection."""

import time

try:
    from Raspbot_Lib import Raspbot
except ImportError:
    Raspbot = None

from utils import setup_logger

logger = setup_logger("ringo.ultrasonic")


class UltrasonicSensor:
    """Wrapper for the onboard ultrasonic distance sensor."""

    def __init__(self, stop_distance_mm: int = 150):
        self.stop_distance_mm = stop_distance_mm
        if Raspbot:
            self.bot = Raspbot()
        else:
            self.bot = None
            logger.warning("Raspbot_Lib not available — ultrasonic will return simulated values")

    def get_distance_mm(self) -> int:
        """Read distance to nearest obstacle in millimeters."""
        if not self.bot:
            return 9999  # Simulated: no obstacle

        self.bot.Ctrl_Ulatist_Switch(1)
        time.sleep(0.15)

        distance = 9999
        for _ in range(3):
            try:
                high = self.bot.read_data_array(0x1B, 1)[0]
                low = self.bot.read_data_array(0x1A, 1)[0]
                distance = (high << 8) | low
            except (TypeError, IndexError):
                pass
            time.sleep(0.05)

        self.bot.Ctrl_Ulatist_Switch(0)
        logger.debug(f"Ultrasonic distance: {distance} mm")
        return distance

    def is_obstacle_ahead(self) -> bool:
        """Check if an obstacle is within the stop distance."""
        dist = self.get_distance_mm()
        blocked = dist < self.stop_distance_mm
        if blocked:
            logger.warning(f"Obstacle detected at {dist} mm (threshold: {self.stop_distance_mm} mm)")
        return blocked
