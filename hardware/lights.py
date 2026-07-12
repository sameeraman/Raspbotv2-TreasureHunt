"""RGB LED light bar control for Raspbotv2."""

import time

try:
    from Raspbot_Lib import Raspbot, LightShow
except ImportError:
    Raspbot = None
    LightShow = None

from utils import setup_logger

logger = setup_logger("ringo.lights")

_NUM_LEDS = 14   # Raspbot V2 LED count


class LightController:
    """Controls the RGB LED light bar for visual feedback."""

    def __init__(self):
        if Raspbot:
            self.bot = Raspbot()
        else:
            self.bot = None
            logger.warning("Raspbot_Lib not available — lights will be simulated")

        # LightShow wraps the same hardware; used for multi-LED effects.
        self._ls = LightShow() if LightShow else None

    # ── Solid states ───────────────────────────────────────────────────────────

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
        """Blue — robot is processing / waiting for AI."""
        self.set_color(0, 80, 255)

    def listening(self):
        """Green — robot is listening."""
        self.set_color(0, 255, 80)

    def speaking(self):
        """Warm yellow — robot is speaking."""
        self.set_color(255, 200, 0)

    def searching(self):
        """Soft blue — robot is exploring."""
        self.set_color(0, 150, 255)

    def idle(self):
        """Dim white — robot is idle/waiting."""
        self.set_color(30, 30, 30)

    # ── Animated states ────────────────────────────────────────────────────────

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

    # ── Light effects (blocking — run for `duration` seconds) ─────────────────

    def effect_gradient(self, duration: float = 5, speed: float = 0.02):
        """Smooth colour sweep across the bar."""
        if self._ls:
            logger.debug(f"effect_gradient duration={duration}s speed={speed}")
            self._ls.execute_effect('gradient', duration, speed, 0)

    def effect_flowing(self, duration: float = 5, speed: float = 0.01):
        """Coloured band flowing along the strip."""
        if self._ls:
            logger.debug(f"effect_flowing duration={duration}s speed={speed}")
            self._ls.execute_effect('river', duration, speed, 0)

    def effect_running(self, duration: float = 5, speed: float = 0.1):
        """Random-colour segments chasing each other."""
        if self._ls:
            logger.debug(f"effect_running duration={duration}s speed={speed}")
            self._ls.execute_effect('random_running', duration, speed, 0)

    def effect_sparkling(self, duration: float = 5, speed: float = 0.1):
        """Random LEDs twinkle like stars."""
        if self._ls:
            logger.debug(f"effect_sparkling duration={duration}s speed={speed}")
            self._ls.execute_effect('starlight', duration, speed, 0)

    def effect_breathing(self, duration: float = 5, speed: float = 0.01,
                         color: int = 0):
        """Single colour pulses slowly in and out.

        color: 0=red  1=green  2=blue  3=yellow  4=purple  5=cyan  6=white
        """
        if self._ls:
            logger.debug(f"effect_breathing color={color} duration={duration}s")
            self._ls.execute_effect('breathing', duration, speed, color)

    def effect_knight_rider(self, duration: float = 8, speed: float = 0.06):
        """Classic KITT scanner — red head + trail sweeps back and forth."""
        if not self.bot:
            return
        logger.debug(f"effect_knight_rider duration={duration}s speed={speed}")

        TRAIL = 2
        end_time = time.time() + duration
        pos = 0
        direction = 1

        while time.time() < end_time:
            self.bot.Ctrl_WQ2812_ALL(0, 0)               # clear strip
            for t in range(TRAIL + 1):
                led = pos - t * direction
                if 0 <= led < _NUM_LEDS:
                    self.bot.Ctrl_WQ2812_Alone(led, 1, 0) # red
            time.sleep(speed)

            pos += direction
            if pos >= _NUM_LEDS:
                pos = _NUM_LEDS - 1
                direction = -1
            elif pos < 0:
                pos = 0
                direction = 1

        self.bot.Ctrl_WQ2812_ALL(0, 0)

