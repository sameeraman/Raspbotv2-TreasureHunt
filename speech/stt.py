"""Azure Speech-to-Text for capturing Sienna's voice input."""

from typing import Optional

import azure.cognitiveservices.speech as speechsdk
from azure.identity import ClientSecretCredential

from utils import setup_logger

logger = setup_logger("ringo.stt")

_SPEECH_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class SpeechToText:
    """Records audio from microphone and transcribes using Azure Speech."""

    def __init__(self, speech_region: str,
                 speech_key: str = "",
                 credential: Optional[ClientSecretCredential] = None,
                 resource_id: str = ""):
        self.speech_region = speech_region
        self.speech_key = speech_key
        self.credential = credential
        self.resource_id = resource_id
        self._speech_config = None

    def _get_config(self) -> speechsdk.SpeechConfig:
        if not self._speech_config:
            if self.credential:
                raw_token = self.credential.get_token(_SPEECH_TOKEN_SCOPE).token
                auth_token = f"aad#{self.resource_id}#{raw_token}"
                self._speech_config = speechsdk.SpeechConfig(
                    auth_token=auth_token, region=self.speech_region
                )
                logger.debug("Speech config using Entra ID token auth")
            else:
                self._speech_config = speechsdk.SpeechConfig(
                    subscription=self.speech_key, region=self.speech_region
                )
                logger.debug("Speech config using key auth")
            self._speech_config.speech_recognition_language = "en-AU"
        return self._speech_config

    def listen(self, timeout_seconds: int = 10) -> str | None:
        """Listen for speech and return the transcribed text.

        Returns None if no speech was detected or recognition failed.
        """
        logger.info("Listening for speech...")
        config = self._get_config()

        # Use the default microphone
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=config,
            audio_config=audio_config,
        )

        # Single-shot recognition with timeout
        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = result.text.strip()
            logger.info(f"Recognized: '{text}'")
            return text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.info("No speech detected")
            return None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            logger.error(f"Speech recognition canceled: {cancellation.reason}")
            if cancellation.error_details:
                logger.error(f"Error details: {cancellation.error_details}")
            return None

        return None
