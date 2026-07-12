#!/usr/bin/env python3
"""Raspbotv2 Treasure Hunt — Main entry point.

This is the main loop that ties everything together:
1. Wait for wake word "Ringo"
2. Start a treasure hunt session (with memory context)
3. Listen → Think → Speak → Act loop (with auto-memory)
4. End session when time is up or Sienna says bye
"""

import asyncio
import contextlib
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time

from config import load_config
from hardware.wake_word import create_wake_word_listener, _WAKE_COMMAND_NAMES
from hardware.motor import MotorController
from hardware.camera import Camera
from hardware.ultrasonic import UltrasonicSensor
from hardware.lights import LightController
from hardware.lcd import LCDDisplay
from speech.stt import SpeechToText
from speech.tts import TextToSpeech
from services.embedding import EmbeddingService
from plugins.vision import VisionPlugin
from plugins.movement import MovementPlugin
from plugins.safety import SafetyPlugin
from plugins.memory import MemoryPlugin
from agents.orchestrator import RingoOrchestrator
from agents.memory_manager import MemoryManager
from utils import setup_logger

logger = setup_logger("ringo.main")


class TreasureHuntApp:
    """Main application class for the Ringo Treasure Hunt."""

    def __init__(self):
        self.config = load_config()
        self._running = False
        # Initialised here so _on_wake_command is safe even before run() is called
        self._session_active = False
        self._interrupt_requested = False

        # Create token provider from service principal
        token_provider = self.config.service_principal.get_token_provider()

        # Hardware
        self.motor = MotorController(max_speed=self.config.safety.max_motor_speed)
        self.camera = Camera(
            index=self.config.hardware.camera_index,
            width=self.config.hardware.camera_width,
            height=self.config.hardware.camera_height,
        )
        self.ultrasonic = UltrasonicSensor(
            stop_distance_mm=self.config.safety.obstacle_stop_distance_mm,
        )
        self.lights = LightController()
        self.lcd = LCDDisplay()

        # Wake word: hardware serial or Porcupine (set WAKE_WORD_ENGINE in .env)
        self.wake_word = create_wake_word_listener(
            on_command=self._on_wake_command
        )

        # Speech — instantiated lazily per session (no cloud connection at startup)
        self._speech_credential = self.config.service_principal.get_credential()
        self.stt = SpeechToText(
            speech_region=self.config.azure_speech.region,
            credential=self._speech_credential,
            resource_id=self.config.azure_speech.resource_id,
        )
        self.tts = TextToSpeech(
            speech_region=self.config.azure_speech.region,
            credential=self._speech_credential,
            resource_id=self.config.azure_speech.resource_id,
        )

        # Services
        self.embedding_service = EmbeddingService(
            endpoint=self.config.azure_openai.endpoint,
            token_provider=token_provider,
            deployment=self.config.azure_openai.embedding_deployment,
            api_version=self.config.azure_openai.api_version,
        )

        # Plugins
        self.vision_plugin = VisionPlugin(
            camera=self.camera,
            endpoint=self.config.azure_openai.endpoint,
            token_provider=token_provider,
            deployment=self.config.azure_openai.vision_deployment,
            api_version=self.config.azure_openai.api_version,
        )
        self.movement_plugin = MovementPlugin(
            motor=self.motor,
            ultrasonic=self.ultrasonic,
        )
        self.safety_plugin = SafetyPlugin(
            ultrasonic=self.ultrasonic,
            max_session_minutes=self.config.safety.max_session_minutes,
        )

        # Memory plugin (Phase 2)
        self.memory_plugin: MemoryPlugin | None = None
        self.memory_manager: MemoryManager | None = None
        if self.config.azure_search.endpoint and self.config.azure_search.key:
            self.memory_plugin = MemoryPlugin(
                search_endpoint=self.config.azure_search.endpoint,
                search_key=self.config.azure_search.key,
                index_name=self.config.azure_search.index_name,
                embedding_service=self.embedding_service,
            )
            self.memory_manager = MemoryManager(self.memory_plugin)
            logger.info("Memory system enabled (Azure AI Search)")
        else:
            logger.info("Memory system disabled (no Azure Search config)")

        # Orchestrator
        self.orchestrator = RingoOrchestrator(
            openai_config=self.config.azure_openai,
            token_provider=token_provider,
            vision_plugin=self.vision_plugin,
            movement_plugin=self.movement_plugin,
            safety_plugin=self.safety_plugin,
            memory_plugin=self.memory_plugin,
        )

    async def run(self):
        """Main application loop."""
        self._running = True
        self._session_active = False
        self._interrupt_requested = False

        # ── Wire Python logger → web dashboard WebSocket ─────────────────────
        import web.server as _web
        _web._event_loop = asyncio.get_event_loop()
        logging.getLogger("ringo").addHandler(_web._ws_log_handler)

        # Share hardware with the embedded web dashboard so it never tries to
        # open /dev/video0 (or motors/lights) a second time in the same process.
        _web._motor = self.motor
        _web._lights = self.lights
        _web._ultra = self.ultrasonic
        _web._camera = self.camera
        _web._tts = self.tts
        _web._hw_ready = True

        # ── Start web dashboard in background (port 8080) ─────────────────────
        def _start_uvicorn():
            import uvicorn
            uvicorn.run(_web.app, host="0.0.0.0", port=8080, log_level="warning")
        _web_thread = threading.Thread(target=_start_uvicorn, daemon=True)
        _web_thread.start()
        logger.info("Web dashboard started on http://0.0.0.0:8080")
        logger.info("=" * 50)
        logger.info("  🤖 Ringo Treasure Hunt — Starting up!")
        logger.info("=" * 50)

        # Set ALSA audio levels before hardware init
        self._set_audio_levels()

        # Initialize hardware
        self.camera.open()
        self.wake_word.start()
        self.lights.idle()
        self.lcd.set_state("idle")
        self.lcd.start()

        logger.info("Waiting for wake word 'Hey Ringo'...")
        logger.info("(Press Ctrl+C to quit)")

        try:
            while self._running:
                await self._wait_and_play()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self._cleanup()

    def _on_wake_command(self, command: str):
        """Called by WakeWordListener for every recognised voice command.

        During an active session the wake word acts as an interrupt —
        Ringo stops speaking and listens fresh.
        """
        if command in _WAKE_COMMAND_NAMES and self._session_active:
            logger.info("Wake word interrupt detected mid-session")
            self._interrupt_requested = True
            # Stop any in-progress TTS immediately
            try:
                self.tts.stop_speaking()
            except Exception:
                pass

    async def _ai_call(self, coro):
        """Run an AI coroutine while blinking the thinking light every 0.5 s.

        Bright blue ↔ very dim blue gives clear visual feedback of cloud latency.
        Sets LCD state to 'thinking' for the duration.
        """
        self.lcd.set_state("thinking")

        async def _blink():
            bright = True
            while True:
                if bright:
                    self.lights.set_color(0, 80, 255)
                else:
                    self.lights.set_color(5, 5, 25)
                bright = not bright
                await asyncio.sleep(0.5)

        blink = asyncio.create_task(_blink())
        try:
            return await coro
        finally:
            blink.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await blink

    async def _run_chat_session(self) -> bool:
        """Casual chat mode after wake word.

        Returns True if Sienna requests a treasure hunt, False to end the interaction.
        Automatically proposes closing after 5 minutes with no hunt request.
        """
        CHAT_MAX_SECS = 5 * 60

        logger.info("Starting chat session")
        self._session_active = True
        self._interrupt_requested = False
        self.lights.listening()
        self.lcd.set_state("listening")

        self.orchestrator.switch_to_chat_mode()

        # Greet Sienna
        try:
            greeting = await self._ai_call(self.orchestrator.start_chat())
        except Exception as e:
            logger.error(f"Chat greeting failed: {e}")
            self._session_active = False
            return False

        self.lights.speaking()
        self.lcd.set_state("speaking")
        self.tts.speak(self._process_response(greeting))
        self.lights.listening()
        self.lcd.set_state("listening")

        chat_start = time.time()
        timeout_offered = False

        while self._running:
            elapsed = time.time() - chat_start

            # 5-minute timeout — offer to wrap up or start a hunt
            if elapsed >= CHAT_MAX_SECS and not timeout_offered:
                timeout_offered = True
                logger.info("Chat timeout reached — proposing to close")
                try:
                    close_msg = await self._ai_call(self.orchestrator.propose_close())
                except Exception as e:
                    logger.error(f"Propose close failed: {e}")
                    break
                self.lights.speaking()
                self.lcd.set_state("speaking")
                self.tts.speak(self._process_response(close_msg))
                self.lights.listening()
                self.lcd.set_state("listening")

            # Wake word interrupt mid-chat
            if self._interrupt_requested:
                self._interrupt_requested = False
                self.tts.speak("I'm here!")
                self.lights.listening()

            # Listen
            user_text = self.stt.listen(timeout_seconds=15)

            if self._interrupt_requested:
                self._interrupt_requested = False
                if user_text is None:
                    self.tts.speak("Yes? I'm here!")
                    continue

            if user_text is None:
                if timeout_offered:
                    # No response after timeout warning — end quietly
                    break
                await asyncio.sleep(0.5)
                continue

            if self._is_goodbye(user_text):
                try:
                    farewell = await self._ai_call(self.orchestrator.chat(user_text))
                    farewell = farewell.removeprefix("HUNT:").strip()
                    self.lights.speaking()
                    self.tts.speak(self._process_response(farewell))
                except Exception as e:
                    logger.error(f"Farewell response failed: {e}")
                break

            # Get Ringo's response
            try:
                response = await self._ai_call(self.orchestrator.chat(user_text))
            except Exception as e:
                logger.error(f"Chat response failed: {e}")
                self.lights.listening()
                self.lcd.set_state("listening")
                continue

            # HUNT: prefix signals Sienna asked for a treasure hunt
            hunt_requested = response.startswith("HUNT:")
            clean = response.removeprefix("HUNT:").strip()

            if clean:
                self.lights.speaking()
                self.lcd.set_state("speaking")
                self.tts.speak(self._process_response(clean))
                self.lights.listening()
                self.lcd.set_state("listening")

            if hunt_requested:
                logger.info("Treasure hunt requested — transitioning to hunt mode")
                self._session_active = False
                return True

        self._session_active = False
        self.lights.idle()
        self.lcd.set_state("idle")
        return False

    async def _wait_and_play(self):
        """Wait for wake word, then run chat → optional treasure hunt."""
        # Wait for wake word
        while self._running:
            if self.wake_word.is_triggered():
                break
            await asyncio.sleep(0.1)

        if not self._running:
            return

        # Play dog bark as acknowledgement
        bark_path = os.path.join(os.path.dirname(__file__), "dog-bark.wav")
        speaker = os.getenv("SPEAKER_DEVICE", "plughw:3,0")
        try:
            subprocess.Popen(
                ["aplay", "-D", speaker, bark_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning(f"Could not play dog bark: {e}")

        # Brief pause so bark finishes before Ringo speaks
        await asyncio.sleep(0.8)

        # Chat mode first; transitions to hunt only if Sienna asks
        hunt_requested = await self._run_chat_session()
        if hunt_requested and self._running:
            await self._run_hunt_session()

        # Drain any stale wake word trigger that fired during the session
        # and add a cooldown so STT isn't immediately reopened.
        self.wake_word.is_triggered()
        await asyncio.sleep(3)

    async def _run_hunt_session(self):
        """Run one treasure hunt play session."""
        logger.info("🎮 New treasure hunt session starting!")
        self._session_active = True
        self._interrupt_requested = False
        self.lights.listening()
        self.lcd.set_state("listening")
        self.safety_plugin.start_session()

        # Initialize memory for this session
        memory_context = ""
        if self.memory_manager:
            self.memory_manager.start_session()
            memory_context = await self.memory_manager.get_greeting_context()
            if memory_context:
                logger.info("Memory context loaded for greeting")

        self.orchestrator.reset_history(memory_context=memory_context)

        # Greet Sienna (with memory context if available)
        greeting = await self._ai_call(self.orchestrator.start_treasure_hunt(memory_context=memory_context))
        self.lights.speaking()
        self.lcd.set_state("speaking")
        self.tts.speak(self._process_response(greeting))
        self.lights.listening()
        self.lcd.set_state("listening")

        # Main conversation loop
        while self._running:
            # Check session time
            if self.safety_plugin.is_session_expired():
                await self._end_session()
                break

            # Wake word interrupt: Ringo was mid-conversation and user said wake word
            if self._interrupt_requested:
                self._interrupt_requested = False
                logger.info("Session interrupted by wake word — resuming listening")
                self.lights.listening()
                self.tts.speak("I'm listening!")

            # Listen for Sienna's voice
            self.lights.listening()
            user_text = self.stt.listen(timeout_seconds=15)

            # Re-check interrupt in case it fired during the STT window
            if self._interrupt_requested:
                self._interrupt_requested = False
                logger.info("Wake word fired during STT — treating as fresh input signal")
                # user_text may already contain what was said after the wake word,
                # or it may be None — either way continue to the next loop iteration
                if user_text is None:
                    self.tts.speak("Yes? I'm listening!")
                    continue

            if user_text is None:
                # No speech detected — wait for next wake word or retry
                logger.info("No speech detected, waiting...")
                await asyncio.sleep(1)
                continue

            # Check for goodbye phrases
            if self._is_goodbye(user_text):
                await self._end_session()
                break

            # Process through the orchestrator
            response = await self._ai_call(self.orchestrator.chat(user_text))

            # Auto-observe for memory (Phase 2)
            if self.memory_manager:
                await self.memory_manager.observe_exchange(user_text, response)

            # Speak the response — may be interrupted by wake word
            self.lights.speaking()
            self.lcd.set_state("speaking")
            self.tts.speak(self._process_response(response))
            self.lights.listening()
            self.lcd.set_state("listening")

        self._session_active = False
        self.lights.idle()
        self.lcd.set_state("idle")

    async def _end_session(self):
        """End the current play session gracefully."""
        logger.info("🏁 Ending treasure hunt session")
        self._session_active = False

        # Store session summary in memory
        if self.memory_manager:
            await self.memory_manager.end_session_summary()

        goodbye = await self._ai_call(self.orchestrator.end_session())
        self.lights.speaking()
        self.tts.speak_excited(self._process_response(goodbye))
        self.lights.found_treasure()  # Celebration lights
        self.motor.nod()

    def _is_goodbye(self, text: str) -> bool:
        """Check if the user said goodbye."""
        goodbye_phrases = [
            "bye", "goodbye", "see you", "stop", "that's enough",
            "i'm done", "no more", "finish", "end", "quit",
        ]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in goodbye_phrases)

    def _play_bark(self):
        """Play dog-bark.wav non-blocking."""
        bark_path = os.path.join(os.path.dirname(__file__), "dog-bark.wav")
        speaker = os.getenv("SPEAKER_DEVICE", "plughw:3,0")
        try:
            subprocess.Popen(
                ["aplay", "-D", speaker, bark_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.6)
        except Exception as e:
            logger.warning(f"Could not play bark: {e}")

    def _wag_lights(self):
        """Quick warm orange flash — tail-wagging visual."""
        for _ in range(3):
            self.lights.set_color(255, 140, 0)
            time.sleep(0.12)
            self.lights.set_color(10, 10, 10)
            time.sleep(0.12)
        self.lights.speaking()  # restore

    def _process_response(self, text: str) -> str:
        """Pre-process AI response before TTS.

        [BARK]   → play bark WAV, strip tag.
        *action* → trigger physical action where possible, strip tag.
        Returns clean text safe to pass to TTS.
        """
        # Handle [BARK]
        if "[BARK]" in text:
            text = text.replace("[BARK]", "").strip()
            self._play_bark()

        # Handle *action* stage directions
        def _do_action(match):
            action = match.group(1).lower()
            if any(k in action for k in ("tilt", "tilts", "tilting")):
                threading.Thread(target=self.motor.shake_head, daemon=True).start()
            elif any(k in action for k in ("wag", "tail", "wiggl")):
                threading.Thread(target=self._wag_lights, daemon=True).start()
            elif any(k in action for k in ("nod", "nods")):
                threading.Thread(target=self.motor.nod, daemon=True).start()
            # sniff, whimper, yawn, etc. — just strip
            return ""

        text = re.sub(r'\*([^*\n]{1,40})\*', _do_action, text)
        text = re.sub(r' {2,}', ' ', text).strip()
        return text

    def _set_audio_levels(self):
        """Set ALSA speaker and microphone levels from environment variables.

        Configure in .env:
            SPEAKER_VOLUME=90   # 0-100 — sets Master volume on the ALSA card
            MIC_VOLUME=80       # 0-100 — sets Capture volume on the ALSA card
            ALSA_CARD=1         # card index if not the system default (e.g. USB audio)
        """
        card_flag = []
        card = os.getenv("ALSA_CARD", "").strip()
        if card:
            card_flag = ["-c", card]

        speaker_vol = os.getenv("SPEAKER_VOLUME", "").strip()
        if speaker_vol:
            # USB audio cards use different control names than built-in cards.
            # Try in priority order until one succeeds.
            for ctrl in ("PCM", "Speaker", "Headphone", "Master"):
                try:
                    r = subprocess.run(
                        ["amixer", *card_flag, "-q", "sset", ctrl, f"{speaker_vol}%"],
                        timeout=3, capture_output=True,
                    )
                    if r.returncode == 0:
                        logger.info(f"Speaker ({ctrl}) volume set to {speaker_vol}%")
                        break
                except Exception:
                    continue
            else:
                logger.warning(
                    "Speaker volume: no working ALSA control found. "
                    f"Run 'amixer -c {os.getenv('ALSA_CARD','0')} scontrols' to list available controls."
                )

        mic_vol = os.getenv("MIC_VOLUME", "").strip()
        if mic_vol:
            for ctrl in ("Mic", "Microphone", "Capture", "Mic Capture Volume"):
                try:
                    r = subprocess.run(
                        ["amixer", *card_flag, "-q", "sset", ctrl, f"{mic_vol}%"],
                        timeout=3, capture_output=True,
                    )
                    if r.returncode == 0:
                        logger.info(f"Mic ({ctrl}) volume set to {mic_vol}%")
                        break
                except Exception:
                    continue
            else:
                logger.warning(
                    "Mic volume: no working ALSA control found. "
                    f"Run 'amixer -c {os.getenv('ALSA_CARD','0')} scontrols' to list available controls."
                )

    def _cleanup(self):
        """Clean shutdown of all hardware."""
        logger.info("Cleaning up...")
        self.lcd.stop()
        self.wake_word.stop()
        self.camera.close()
        self.motor.stop()
        self.motor.reset_servos()
        self.lights.off()
        logger.info("Goodbye! 👋")


def main():
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Raspbotv2 Treasure Hunt")
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start the web dashboard instead of the voice-driven loop. "
             "Open http://localhost:8080 to control the robot.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Web dashboard bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Web dashboard port (default: 8080)")
    args = parser.parse_args()

    if args.web:
        import uvicorn
        print(f"🌐  Starting Ringo web dashboard on http://{args.host}:{args.port}")
        print(f"    Dashboard:   http://localhost:{args.port}/")
        print(f"    Remote ctrl: http://localhost:{args.port}/control")
        uvicorn.run("web.server:app", host=args.host, port=args.port, log_level="warning")
        return

    app = TreasureHuntApp()

    # Handle SIGTERM gracefully
    def handle_signal(sig, frame):
        app._running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    asyncio.run(app.run())


if __name__ == "__main__":
    main()
