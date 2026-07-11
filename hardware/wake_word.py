"""Wake word detection via Yahboom voice modules.

Two serial protocols are supported:

BINARY (original Raspbot V2 built-in module):
    Module sends: AA 55 [CMD_ID_1] [CMD_ID_2] FB
    CMD_ID_1 = 0x00 for all Ringo commands; CMD_ID_2 identifies the phrase

ASCII (CSK4002 / CI1302 standalone module - Voice-interaction-module repo):
    Module sends ASCII strings:  $BXXX#
    $B000# = wake word ("Hi Yahboom")
    $B095#-$B104# = custom command slots A-J (user-programmable phrases)

The listener auto-detects the protocol from the incoming bytes.

Custom command workflow to get "Hey Ringo":
  1. Buy or use the CSK4002/CI1302 module
  2. Program "Hey Ringo" into Custom A slot ($B095#) via Yahboom web platform
  3. Add "$B095#" to _WAKE_CODES below (already done)

Prerequisites:
    sudo usermod -aG dialout $USER   # access to /dev/ttyUSB0
"""

import serial
import threading
import time
from typing import Optional, Callable

from utils import setup_logger

logger = setup_logger("ringo.wakeword")

# Binary protocol: 4th byte value → command name
# Values come from the Yahboom configuration tool (semantic tag + offset).
# Extend this dict as you add more programmed commands.
_BINARY_COMMANDS = {
    0x5D: "garbage_sorting",
    0x5E: "what_garbage",
    0x5F: "hi_ringo",       # wake word
    0x60: "hello_ringo",    # wake word
    0x61: "ringo",          # wake word
    0x62: "command_four",
}

# The 4th-byte values that should trigger the wake-word
_BINARY_WAKE_BYTES = {0x5F, 0x60, 0x61}  # Hi Ringo / Hello Ringo / Ringo

# Command *names* that count as a wake word — used by the app for interrupt detection.
# Combines binary protocol names + the ASCII protocol's "wake_word" ($B000#).
_WAKE_COMMAND_NAMES: frozenset[str] = frozenset(
    {_BINARY_COMMANDS[b] for b in _BINARY_WAKE_BYTES if b in _BINARY_COMMANDS}
    | {"wake_word"}
)


def create_wake_word_listener(on_command=None):
    """Factory that returns the configured WakeWordListener.

    on_command: optional callback for all voice commands (not just wake word).
    """
    import os
    return WakeWordListener(
        port=os.getenv("VOICE_MODULE_PORT", "/dev/ttyUSB0"),
        baudrate=int(os.getenv("VOICE_MODULE_BAUD", "115200")),
        on_command=on_command,
    )


class WakeWordListener:
    """Wake-word listener supporting both Yahboom binary and ASCII serial protocols.

    Binary protocol (built-in Raspbot V2 module):
        Detects  AA 55 [CMD_ID_1] [CMD_ID_2] FB  byte sequences.

    ASCII protocol (CSK4002 / CI1302 standalone module):
        Detects  $BXXX#  strings.  _WAKE_CODES controls which trigger the
        wake word; on_command receives ALL commands for local offline control.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200,
                 on_command: Optional[Callable[[str], None]] = None):
        self.port = port
        self.baudrate = baudrate
        self._on_command = on_command
        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._triggered = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        try:
            self._ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=1)
            self._running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            logger.info(f"Wake word listener started on {self.port}")
        except Exception as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            logger.error("Run: sudo usermod -aG dialout $USER  then re-login")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._ser and self._ser.is_open:
            self._ser.close()
        logger.info("Wake word listener stopped")

    def is_triggered(self) -> bool:
        with self._lock:
            if self._triggered:
                self._triggered = False
                return True
            return False

    def wait_for_wake_word(self, timeout: float | None = None) -> bool:
        start = time.time()
        while True:
            if self.is_triggered():
                logger.info("Wake word detected!")
                return True
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # Internal auto-detecting listener loop
    # ------------------------------------------------------------------
    def _listen_loop(self):
        """Read bytes, auto-detect protocol, fire callbacks."""
        buffer = b""
        step = 1   # binary state machine step
        cmd_id_1 = 0
        cmd_id_2 = 0

        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(0.5)
                continue
            try:
                data = self._ser.read(1)
                if not data:
                    time.sleep(0.05)
                    continue

                b = data[0]

                # ASCII protocol: collect bytes between '$' and '#'
                if buffer or b == ord('$'):
                    buffer += data
                    if b == ord('#'):
                        token = buffer.decode("ascii", errors="ignore").strip()
                        buffer = b""
                        self._handle_ascii_command(token)
                    elif len(buffer) > 8:
                        buffer = b""  # discard garbage
                    continue

                # Binary protocol state machine: AA 55 [CMD_ID_1] [CMD_ID_2] FB
                # byte 3 = CMD_ID_1 (0x00 for all Ringo commands)
                # byte 4 = CMD_ID_2 (identifies the specific phrase)
                if b == 0xAA and step == 1:
                    step = 2
                elif b == 0x55 and step == 2:
                    step = 3
                elif step == 3:
                    cmd_id_1 = b
                    step = 4
                elif step == 4:
                    cmd_id_2 = b
                    step = 5
                elif b == 0xFB and step == 5:
                    cmd_name = _BINARY_COMMANDS.get(cmd_id_2, f"cmd_0x{cmd_id_1:02X}_{cmd_id_2:02X}")
                    is_wake = cmd_id_2 in _BINARY_WAKE_BYTES
                    logger.info(
                        f"Voice command: '{cmd_name}' (CMD_ID_1=0x{cmd_id_1:02X} CMD_ID_2=0x{cmd_id_2:02X}) wake={is_wake}"
                    )
                    if is_wake:
                        with self._lock:
                            self._triggered = True
                    if self._on_command:
                        self._on_command(cmd_name)
                    step = 1
                else:
                    step = 1
                time.sleep(0.05)

            except Exception as e:
                logger.error(f"Serial read error: {e}")
                time.sleep(0.5)

    def _handle_ascii_command(self, token: str):
        # ASCII protocol is for CSK4002/CI1302 standalone modules
        ascii_names = {
            "$B000#": "wake_word", "$B095#": "hi_ringo",
            "$B096#": "hello_ringo", "$B097#": "ringo",
        }
        ascii_wake = {"$B000#", "$B095#", "$B096#", "$B097#"}
        name = ascii_names.get(token, token)
        logger.info(f"ASCII voice command: {token} → {name}")
        if self._on_command:
            self._on_command(name)
        if token in ascii_wake:
            logger.info(f"Wake word triggered by {token}")
            with self._lock:
                self._triggered = True
