"""Wake word detection via the hardware voice module serial interface.

The voice module sends a specific byte sequence (AA 55 01-06 00 FB)
when the wake word "Ringo" is detected.
"""

import serial
import threading
import time

from utils import setup_logger

logger = setup_logger("ringo.wakeword")


class WakeWordListener:
    """Listens for the hardware wake-word trigger on the serial port."""

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._ser = None
        self._running = False
        self._triggered = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        """Open serial port and begin listening in a background thread."""
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

    def stop(self):
        """Stop the listener and close the serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._ser and self._ser.is_open:
            self._ser.close()
        logger.info("Wake word listener stopped")

    def is_triggered(self) -> bool:
        """Check if the wake word was detected (and reset the flag)."""
        with self._lock:
            if self._triggered:
                self._triggered = False
                return True
            return False

    def wait_for_wake_word(self, timeout: float | None = None) -> bool:
        """Block until wake word is detected or timeout expires."""
        start = time.time()
        while True:
            if self.is_triggered():
                logger.info("Wake word 'Ringo' detected!")
                return True
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)

    def _listen_loop(self):
        """Background thread: parse the serial protocol for wake word trigger."""
        step = 1
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(0.5)
                continue
            try:
                data = self._ser.read(1)
                if not data:
                    continue
                byte_val = data[0]

                if byte_val == 0xAA and step == 1:
                    step = 2
                elif byte_val == 0x55 and step == 2:
                    step = 3
                elif byte_val in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06) and step == 3:
                    step = 4
                elif byte_val == 0x00 and step == 4:
                    step = 5
                elif byte_val == 0xFB and step == 5:
                    with self._lock:
                        self._triggered = True
                    step = 1
                else:
                    step = 1

            except Exception as e:
                logger.error(f"Serial read error: {e}")
                time.sleep(0.5)
