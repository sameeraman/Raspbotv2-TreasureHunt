"""Wake word detection via the Yahboom AI voice module serial interface.

The module sends AA 55 [01-06] 00 FB when the wake word is spoken.
No Azure/cloud connection is made until after the wake word triggers.

Prerequisites on Orange Pi:
    sudo usermod -aG dialout $USER   # grant access to /dev/ttyUSB0
"""

import serial
import threading
import time
from typing import Optional

from utils import setup_logger

logger = setup_logger("ringo.wakeword")


class WakeWordListener:
    """Hardware wake-word listener using the Yahboom AI voice module serial protocol.

    Parses the byte sequence AA 55 [01-06] 00 FB emitted by the voice module.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._triggered = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        """Open serial port and start listening in a background thread."""
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1,
            )
            self._running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            logger.info(f"Wake word listener started on {self.port}")
        except Exception as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            logger.error("Run: sudo usermod -aG dialout $USER  then re-login")

    def stop(self):
        """Stop the listener and close the serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._ser and self._ser.is_open:
            self._ser.close()
        logger.info("Wake word listener stopped")

    def is_triggered(self) -> bool:
        """Return True (and reset) if the wake word was detected since last call."""
        with self._lock:
            if self._triggered:
                self._triggered = False
                return True
            return False

    def wait_for_wake_word(self, timeout: float | None = None) -> bool:
        """Block until wake word fires or timeout expires. Returns True on detection."""
        start = time.time()
        while True:
            if self.is_triggered():
                logger.info("Wake word detected!")
                return True
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)

    def _listen_loop(self):
        """Background thread: parse AA 55 [01-06] 00 FB byte sequence."""
        step = 1
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(0.5)
                continue
            try:
                data = self._ser.read(1)
                if not data:
                    time.sleep(0.1)
                    continue
                b = data[0]
                if b == 0xAA and step == 1:
                    step = 2
                elif b == 0x55 and step == 2:
                    step = 3
                elif b in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06) and step == 3:
                    step = 4
                elif b == 0x00 and step == 4:
                    step = 5
                elif b == 0xFB and step == 5:
                    with self._lock:
                        self._triggered = True
                    step = 1
                else:
                    step = 1
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Serial read error: {e}")
                time.sleep(0.5)

logger = setup_logger("ringo.wakeword")
