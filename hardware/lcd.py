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

            for bus in _I2C_BUS_CANDIDATES:
                for addr in _I2C_ADDRESSES:
                    try:
                        serial = i2c(port=bus, address=addr)
                        device = ssd1306(serial)
                        self._device = device
                        logger.info(
                            f"OLED initialised (luma.oled, I2C bus={bus} addr=0x{addr:02X})"
                        )
                        return
                    except Exception:
                        continue

            logger.warning(
                "OLED: SSD1306 not found on any I2C bus. "
                "Run 'i2cdetect -y 1' on the robot to check connections."
            )

        except ImportError:
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

from utils import setup_logger

logger = setup_logger("ringo.lcd")

# I2C bus candidates — tried in order until one responds (mirrors Yahboom logic)
_I2C_BUS_CANDIDATES = [1, 0, 7, 8]
_WIDTH, _HEIGHT = 128, 32   # SSD1306 128×32


class LCDDisplay:
    """128×32 SSD1306 OLED — shows robot state / CPU / RAM / battery."""

    def __init__(self):
        self._disp = None
        self._image = None
        self._draw = None
        self._font = None
        self._state = "idle"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._init_display()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_display(self):
        try:
            import Adafruit_SSD1306 as SSD           # type: ignore
            from PIL import Image, ImageDraw, ImageFont

            for bus in _I2C_BUS_CANDIDATES:
                try:
                    disp = SSD.SSD1306_128_32(rst=None, i2c_bus=bus, gpio=1)
                    disp.begin()
                    disp.clear()
                    disp.display()
                    self._disp = disp
                    logger.info(f"OLED initialised on I2C bus {bus}")
                    break
                except Exception:
                    continue

            if self._disp is None:
                logger.warning("OLED: no display found on any I2C bus (tried 1,0,7,8)")
                return

            self._image = Image.new("1", (_WIDTH, _HEIGHT))
            self._draw = ImageDraw.Draw(self._image)
            self._font = ImageFont.load_default()

        except ImportError as e:
            logger.warning(
                f"OLED: missing library ({e}). "
                "Run: pip install Adafruit-SSD1306 Pillow"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        """Update the robot state label shown on the display."""
        with self._lock:
            self._state = state

    def start(self):
        """Start the background 2-second refresh loop."""
        if self._disp is None:
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
            if self._disp and self._draw:
                self._draw.rectangle((0, 0, _WIDTH, _HEIGHT), outline=0, fill=0)
                self._disp.image(self._image)
                self._disp.display()
        except Exception:
            pass
        logger.info("LCD stopped")

    # ── Display primitives ────────────────────────────────────────────────────

    def _clear_buf(self):
        self._draw.rectangle((0, 0, _WIDTH, _HEIGHT), outline=0, fill=0)

    def _write_line(self, text: str, line: int):
        """Draw text on line 1-4 (each row is 8 px tall)."""
        y = 8 * (line - 1)
        self._draw.text((0, y), str(text)[:21], font=self._font, fill=255)

    def _flush(self):
        self._disp.image(self._image)
        self._disp.display()

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
        try:
            import subprocess
            out = subprocess.check_output(
                "free | awk 'NR==2{printf \"%d%% %dMB\","
                " 100*($2-$7)/$2, ($2-$7)/1024}'",
                shell=True,
            ).decode().strip()
            return out
        except Exception:
            return "--"

    @staticmethod
    def _battery() -> str:
        # 1. Linux power-supply subsystem (UPS hats, etc.)
        for cap in glob.glob("/sys/class/power_supply/*/capacity"):
            try:
                with open(cap) as f:
                    return f"{f.read().strip()}%"
            except Exception:
                pass

        # 2. Raspbot V2 chassis I2C — 0x1C (high) / 0x1D (low) = mV
        try:
            from Raspbot_Lib import Raspbot  # type: ignore
            bot = Raspbot()
            hi = bot.read_data_array(0x1c, 1)[0]
            lo = bot.read_data_array(0x1d, 1)[0]
            mv = (hi << 8) | lo
            if 4000 < mv < 12000:                      # sanity check
                pct = max(0, min(100, (mv - 6000) * 100 // 2400))
                return f"{pct}% {mv / 1000:.1f}V"
        except Exception:
            pass

        return "--"

    # ── Refresh loop ──────────────────────────────────────────────────────────

    def _update_loop(self):
        while self._running:
            try:
                with self._lock:
                    state = self._state

                cpu = self._cpu()
                ram = self._ram()
                bat = self._battery()

                self._clear_buf()
                self._write_line(f"[{state}]", 1)
                self._write_line(f"CPU:{cpu}", 2)
                self._write_line(f"RAM:{ram}", 3)
                self._write_line(f"BAT:{bat}", 4)
                self._flush()

            except Exception as e:
                logger.error(f"LCD update error: {e}")

            time.sleep(2)


try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from utils import setup_logger

logger = setup_logger("ringo.lcd")

_DEFAULT_OLED_PATHS = [
    "/home/orangepi/software/oled_yahboom",
    "/home/pi/software/oled_yahboom",
]


class LCDDisplay:
    """Drives the Yahboom OLED, refreshing every 2 seconds in a background thread."""

    def __init__(self):
        self._oled = None
        self._state = "idle"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._oled_lib_dir: str = ""
        self._init_oled()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_oled(self):
        env_path = os.getenv("OLED_LIB_PATH", "").strip()
        search = [env_path] if env_path else _DEFAULT_OLED_PATHS

        for path in search:
            if not os.path.isdir(path):
                continue
            try:
                if path not in sys.path:
                    sys.path.insert(0, path)
                from yahboom_oled import Yahboom_OLED  # type: ignore
                self._oled = Yahboom_OLED(debug=False)
                self._oled.init_oled_process()
                self._oled_lib_dir = path
                logger.info(f"OLED display initialised ({path})")
                return
            except Exception as e:
                logger.debug(f"OLED init failed at {path}: {e}")

        logger.warning(
            "OLED not found — set OLED_LIB_PATH in .env if the library is installed"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        """Update the robot state label shown on the display."""
        with self._lock:
            self._state = state

    def start(self):
        """Start the 2-second background refresh loop."""
        if self._oled is None:
            logger.debug("OLED unavailable — display loop not started")
            return
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        logger.info("LCD refresh loop started")

    def stop(self):
        """Stop the loop and restore Yahboom's default stats screen."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        # Restore the built-in Yahboom system stats display
        script = os.path.join(self._oled_lib_dir, "yahboom_oled.py")
        if os.path.exists(script):
            os.system(f"python3 {script} &")
        logger.info("LCD stopped")

    # ── Stats helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _cpu() -> str:
        if _HAS_PSUTIL:
            return f"{psutil.cpu_percent(interval=None):.0f}%"
        try:
            with open("/proc/loadavg") as f:
                return f"load {f.read().split()[0]}"
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
        # 1. Linux power-supply subsystem (UPS hats, etc.)
        for cap in glob.glob("/sys/class/power_supply/*/capacity"):
            try:
                with open(cap) as f:
                    return f"{f.read().strip()}%"
            except Exception:
                pass

        # 2. Raspbot chassis I2C: registers 0x1C (high) + 0x1D (low) = mV
        try:
            from Raspbot_Lib import Raspbot  # type: ignore
            bot = Raspbot()
            hi = bot.read_data_array(0x1c, 1)[0]
            lo = bot.read_data_array(0x1d, 1)[0]
            mv = (hi << 8) | lo
            if 4000 < mv < 12000:  # sanity check
                pct = max(0, min(100, (mv - 6000) * 100 // 2400))
                return f"{pct}% {mv / 1000:.1f}V"
        except Exception:
            pass

        return "--"

    # ── Refresh loop ──────────────────────────────────────────────────────────

    def _update_loop(self):
        while self._running:
            try:
                with self._lock:
                    state = self._state

                cpu = self._cpu()
                ram = self._ram()
                bat = self._battery()

                self._oled.clear()
                self._oled.add_line(f"Ringo [{state}]", 1)
                self._oled.add_line(f"CPU : {cpu}", 2)
                self._oled.add_line(f"RAM : {ram}", 3)
                self._oled.add_line(f"BAT : {bat}", 4)
                self._oled.refresh()
            except Exception as e:
                logger.error(f"LCD update error: {e}")

            time.sleep(2)
