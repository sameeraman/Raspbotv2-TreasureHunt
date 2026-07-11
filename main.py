#!/usr/bin/env python3
"""Raspbotv2 Treasure Hunt — Main entry point.

This is the main loop that ties everything together:
1. Wait for wake word "Ringo"
2. Start a treasure hunt session (with memory context)
3. Listen → Think → Speak → Act loop (with auto-memory)
4. End session when time is up or Sienna says bye
"""

import asyncio
import signal
import sys

from config import load_config
from hardware.wake_word import create_wake_word_listener
from hardware.motor import MotorController
from hardware.camera import Camera
from hardware.ultrasonic import UltrasonicSensor
from hardware.lights import LightController
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
        logger.info("=" * 50)
        logger.info("  🤖 Ringo Treasure Hunt — Starting up!")
        logger.info("=" * 50)

        # Initialize hardware
        self.camera.open()
        self.wake_word.start()
        self.lights.idle()

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
        if command == "wake_word" and self._session_active:
            logger.info("Wake word interrupt detected mid-session")
            self._interrupt_requested = True
            # Stop any in-progress TTS immediately
            try:
                self.tts.stop_speaking()
            except Exception:
                pass

    async def _wait_and_play(self):
        """Wait for wake word, then run one treasure hunt session."""
        # Wait for "Ringo" wake word
        while self._running:
            if self.wake_word.is_triggered():
                break
            await asyncio.sleep(0.1)

        if not self._running:
            return

        # Start a new session
        await self._run_session()

    async def _run_session(self):
        """Run one treasure hunt play session."""
        logger.info("🎮 New treasure hunt session starting!")
        self._session_active = True
        self._interrupt_requested = False
        self.lights.listening()
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
        greeting = await self.orchestrator.start_treasure_hunt(memory_context=memory_context)
        self.lights.speaking()
        self.tts.speak(greeting)
        self.lights.listening()

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
            self.lights.thinking()
            response = await self.orchestrator.chat(user_text)

            # Auto-observe for memory (Phase 2)
            if self.memory_manager:
                await self.memory_manager.observe_exchange(user_text, response)

            # Speak the response — may be interrupted by wake word
            self.lights.speaking()
            self.tts.speak(response)

        self._session_active = False
        self.lights.idle()

    async def _end_session(self):
        """End the current play session gracefully."""
        logger.info("🏁 Ending treasure hunt session")
        self._session_active = False

        # Store session summary in memory
        if self.memory_manager:
            await self.memory_manager.end_session_summary()

        goodbye = await self.orchestrator.end_session()
        self.lights.speaking()
        self.tts.speak_excited(goodbye)
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

    def _cleanup(self):
        """Clean shutdown of all hardware."""
        logger.info("Cleaning up...")
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
