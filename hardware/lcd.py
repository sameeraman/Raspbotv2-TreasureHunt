"""OLED display driver for Raspbot V2.

Uses luma.oled (SBC-agnostic — works on Orange Pi, Raspberry Pi, and any Linux SBC).

Install on the robot:
    pip install luma.oled Pillow psutil

Display: 128×32 SSD1306 on I2C (address 0x3C or 0x3D).
Shows robot state / CPU / RAM / battery, refreshing every 2 s.

Diagnostics if the display doesn't appear:
    i2cdetect -y 1          # should show 3c or 3d
    pip install luma.oled   # make sure the library is installed
"""

import glob
import os
import threading
import time
from typing import Optional

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from utils import setup_logger

logger = setup_logger("ringo.lcd")

_I2C_BUS_CANDIDATES = [1, 0, 7, 8]
_I2C_ADDRESSES      = [0x3C, 0x3D]


class LCDDisplay:
    """128×32 SSD1306 OLED — shows robot state / CPU / RAM / battery."""

    def __init__(self):
        self._device = None
        self._state  = "idle"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._init_display()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_display(self):
        try:
            from luma.oled.device import ssd1306        # type: ignore
            from luma.core.interface.serial import i2c  # type: ignore
            from luma.core.render import canvas          # type: ignore

            for bus in _I2C_BUS_CANDIDATES:
                for addr in _I2C_ADDRESSES:
                    try:
                        serial = i2c(port=bus, address=addr)
                        device = ssd1306(serial)

                        # Smoke-test: verify rendering actually works
                        with canvas(device) as draw:
                            draw.text((0, 0), "Ringo!", fill="white")

                        self._device = device
                        logger.info(
                            f"OLED initialised (luma.oled, I2C bus={bus} addr=0x{addr:02X})"
                        )
                        return
                    except Exception as e:
                        logger.warning(f"OLED: bus={bus} addr=0x{addr:02X} failed: {e}")
                        continue

            logger.warning(
                "OLED: SSD1306 not found — check warnings above for the specific error."
            )

        except ImportError as e:
            logger.warning(
                "OLED: luma.oled not installed. Run: pip install luma.oled"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        """Update the robot state label shown on the display."""
        with self._lock:
            self._state = state

    def start(self):
        """Start the 2-second background refresh loop."""
        if self._device is None:
            logger.debug("OLED unavailable — display loop not started")
            return
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        logger.info("LCD refresh loop started")

    def stop(self):
        """Stop the loop and blank the display."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        try:
            if self._device:
                self._device.cleanup()
        except Exception:
            pass
        logger.info("LCD stopped")

    # ── Stats helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _cpu() -> str:
        if _HAS_PSUTIL:
            return f"{psutil.cpu_percent(interval=None):.0f}%"
        try:
            with open("/proc/loadavg") as f:
                return f"ld {f.read().split()[0]}"
        except Exception:
            return "--"

    @staticmethod
    def _ram() -> str:
        if _HAS_PSUTIL:
            m = psutil.virtual_memory()
            return f"{m.percent:.0f}% {m.used >> 20}MB"
        return "--"

    @staticmethod
    def _battery() -> str:
        for cap in glob.glob("/sys/class/power_supply/*/capacity"):
            try:
                with open(cap) as f:
                    return f"{f.read().strip()}%"
            except Exception:
                pass
        try:
            from Raspbot_Lib import Raspbot  # type: ignore
            bot = Raspbot()
            hi = bot.read_data_array(0x1c, 1)[0]
            lo = bot.read_data_array(0x1d, 1)[0]
            mv = (hi << 8) | lo
            if 4000 < mv < 12000:
                pct = max(0, min(100, (mv - 6000) * 100 // 2400))
                return f"{pct}% {mv / 1000:.1f}V"
        except Exception:
            pass
        return "--"

    # ── Refresh loop ──────────────────────────────────────────────────────────

    def _update_loop(self):
        try:
            from luma.core.render import canvas  # type: ignore
            from PIL import ImageFont
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
        except ImportError:
            return

        while self._running:
            try:
                with self._lock:
                    state = self._state

                cpu = self._cpu()
                ram = self._ram()
                bat = self._battery()

                with canvas(self._device) as draw:
                    draw.text((0,  0), f"[{state}]", fill="white", font=font)
                    draw.text((0,  8), f"CPU:{cpu}",  fill="white", font=font)
                    draw.text((0, 16), f"RAM:{ram}",  fill="white", font=font)
                    draw.text((0, 24), f"BAT:{bat}",  fill="white", font=font)

            except Exception as e:
                logger.error(f"LCD update error: {e}")

            time.sleep(2)


import glob
import os
import threading
import time
from typing import Optional

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False
