"""RGB LED light bar control for Raspbotv2."""

import time

try:
    from Raspbot_Lib import Raspbot
except ImportError:
    Raspbot = None

from utils import setup_logger

logger = setup_logger("ringo.lights")


class LightController:
    """Controls the RGB LED light bar for visual feedback."""

    def __init__(self):
        if Raspbot:
            self.bot = Raspbot()
        else:
            self.bot = None
            logger.warning("Raspbot_Lib not available — lights will be simulated")

    def set_color(self, r: int, g: int, b: int):
        """Set all LEDs to a specific RGB colour."""
        r, g, b = min(r, 255), min(g, 255), min(b, 255)
        logger.debug(f"Lights set to RGB({r},{g},{b})")
        if self.bot:
            self.bot.Ctrl_WQ2812_brightness_ALL(r, g, b)

    def off(self):
        """Turn off all LEDs."""
        if self.bot:
            self.bot.Ctrl_WQ2812_ALL(0, 7)
        logger.debug("Lights off")

    def thinking(self):
        """Blue pulsing — robot is thinking."""
        self.set_color(0, 80, 255)

    def listening(self):
        """Green — robot is listening."""
        self.set_color(0, 255, 80)

    def speaking(self):
        """Warm yellow — robot is speaking."""
        self.set_color(255, 200, 0)

    def found_treasure(self):
        """Rainbow celebration flash."""
        colors = [
            (255, 0, 0), (255, 127, 0), (255, 255, 0),
            (0, 255, 0), (0, 0, 255), (148, 0, 211),
        ]
        for r, g, b in colors:
            self.set_color(r, g, b)
            time.sleep(0.2)
        self.set_color(255, 215, 0)  # Gold

    def searching(self):
        """Soft blue — robot is exploring."""
        self.set_color(0, 150, 255)

    def idle(self):
        """Dim white — robot is idle/waiting."""
        self.set_color(30, 30, 30)
