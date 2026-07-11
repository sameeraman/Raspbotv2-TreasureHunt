"""Azure Text-to-Speech for Ringo's voice output."""

from typing import Optional

import azure.cognitiveservices.speech as speechsdk
from azure.identity import ClientSecretCredential

from utils import setup_logger

logger = setup_logger("ringo.tts")

# A friendly, child-appropriate voice
DEFAULT_VOICE = "en-AU-WilliamNeural"

_SPEECH_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class TextToSpeech:
    """Speaks text aloud using Azure Speech TTS."""

    def __init__(self, speech_region: str, voice_name: str = DEFAULT_VOICE,
                 speech_key: str = "",
                 credential: Optional[ClientSecretCredential] = None,
                 resource_id: str = ""):
        import os
        self.speech_region = speech_region
        self.voice_name = voice_name
        self.speech_key = speech_key
        self.credential = credential
        self.resource_id = resource_id
        self._synthesizer = None
        # SSML volume: 0-100 integer string, or named level
        # (silent / x-soft / soft / medium / loud / x-loud).
        # Set TTS_VOLUME in .env to override.  Default 90 is noticeably
        # louder than the SDK default ("medium" ≈ 50).
        self.volume: str = os.getenv("TTS_VOLUME", "90")

    def _get_synthesizer(self) -> speechsdk.SpeechSynthesizer:
        if not self._synthesizer:
            if self.credential:
                raw_token = self.credential.get_token(_SPEECH_TOKEN_SCOPE).token
                auth_token = f"aad#{self.resource_id}#{raw_token}"
                config = speechsdk.SpeechConfig(auth_token=auth_token, region=self.speech_region)
                logger.debug("Speech config using Entra ID token auth")
            else:
                config = speechsdk.SpeechConfig(
                    subscription=self.speech_key, region=self.speech_region
                )
                logger.debug("Speech config using key auth")
            config.speech_synthesis_voice_name = self.voice_name

            import os
            speaker_device = os.getenv("SPEAKER_DEVICE", "").strip()
            if speaker_device:
                logger.debug(f"Using explicit speaker device: {speaker_device}")
                audio_config = speechsdk.audio.AudioOutputConfig(device_name=speaker_device)
            else:
                audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

            self._synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=config,
                audio_config=audio_config,
            )
        return self._synthesizer

    def speak(self, text: str):
        """Speak the given text aloud with child-friendly pacing."""
        logger.info(f"Speaking: '{text[:80]}...' " if len(text) > 80 else f"Speaking: '{text}'")

        # Wrap in SSML for rate/volume control
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-AU">
            <voice name="{self.voice_name}">
                <prosody rate="-10%" pitch="+5%" volume="{self.volume}">
                    {text}
                </prosody>
            </voice>
        </speak>
        """

        synthesizer = self._get_synthesizer()
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.debug("Speech synthesis completed")
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            logger.error(f"Speech synthesis canceled: {cancellation.reason}")
            if cancellation.error_details:
                logger.error(f"Error: {cancellation.error_details}")

    def stop_speaking(self):
        """Interrupt any in-progress speech immediately."""
        if self._synthesizer:
            try:
                self._synthesizer.stop_speaking_async().get()
                logger.debug("TTS interrupted")
            except Exception as e:
                logger.warning(f"stop_speaking error: {e}")

    def speak_excited(self, text: str):
        """Speak with extra enthusiasm (for celebrations)."""
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-AU">
            <voice name="{self.voice_name}">
                <prosody rate="+5%" pitch="+15%" volume="{self.volume}">
                    {text}
                </prosody>
            </voice>
        </speak>
        """
        synthesizer = self._get_synthesizer()
        synthesizer.speak_ssml_async(ssml).get()
