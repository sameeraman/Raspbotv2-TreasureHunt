"""Vision plugin — GPT-4o vision calls for scene understanding."""

from typing import Callable

from openai import AzureOpenAI

from hardware.camera import Camera
from utils import setup_logger

logger = setup_logger("ringo.vision")


class VisionPlugin:
    """Plugin for camera-based scene understanding via Azure OpenAI Vision."""

    def __init__(self, camera: Camera, endpoint: str, token_provider: Callable[[], str],
                 deployment: str, api_version: str):
        self.camera = camera
        # Vision inference still uses chat completions (synchronous, called as a tool)
        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        self.deployment = deployment

    def _vision_call(self, system: str, user_text: str, image_b64: str,
                     max_tokens: int = 200) -> str:
        """Shared helper for all vision inference calls."""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            max_completion_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    # ── Tool implementations ──────────────────────────────────────────────────

    def look_around(self) -> str:
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "I couldn't see anything — the camera might be blocked."
        result = self._vision_call(
            system=(
                "You are Ringo, a friendly robot puppy helping 6-year-old Sienna find "
                "hidden treasures. Describe what you see in simple, fun language. "
                "Focus on colours, shapes, and recognizable objects. 2-3 sentences max."
            ),
            user_text="What do you see right now?",
            image_b64=image_b64,
        )
        logger.info(f"Vision: {result}")
        return result

    def search_for_object(self, target: str) -> str:
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "I can't see right now — my camera might be blocked!"
        result = self._vision_call(
            system=(
                "You are Ringo, a treasure-hunting robot puppy helping 6-year-old Sienna. "
                "Look at this image and determine if you can see the target object. "
                "Reply in a fun way. If you see it, say where (left, right, center, far, close). "
                "If not, say you don't see it and suggest a direction. 2-3 short sentences."
            ),
            user_text=f"Can you see a '{target}' in this image?",
            image_b64=image_b64,
        )
        logger.info(f"Search for '{target}': {result}")
        return result

    def check_if_object_visible(self, target: str) -> str:
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "NOT_FOUND: Camera error — I can't see right now!"
        result = self._vision_call(
            system=(
                "You are a precise vision system for a treasure-hunting robot.\n"
                "Examine the image and respond in EXACTLY this format:\n"
                "  If the target IS visible: FOUND:<POSITION> — <short note>\n"
                "  If NOT visible:           NOT_FOUND: <fun one-liner for a 6-year-old>\n"
                "POSITION must be one of: LEFT, RIGHT, CENTRE, CLOSE (very near), FAR\n"
                "Examples:\n"
                "  FOUND:LEFT — red cap is on the left edge of the frame\n"
                "  FOUND:CLOSE — the cap fills most of the frame, very close\n"
                "  NOT_FOUND: Sniff sniff, I don't see it here!"
            ),
            user_text=f"Can you see a '{target}'?",
            image_b64=image_b64,
            max_tokens=80,
        )
        result = result.strip()
        logger.info(f"check_if_object_visible '{target}': {result}")
        return result

    def get_approach_guidance(self, target: str) -> str:
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "MOVE_FORWARD: can't see — keep going"
        result = self._vision_call(
            system=(
                "You are a navigation assistant for a small robot approaching a target.\n"
                "Reply with EXACTLY one line in this format:\n"
                "  TURN_LEFT: <reason under 10 words>\n"
                "  TURN_RIGHT: <reason under 10 words>\n"
                "  MOVE_FORWARD: <reason under 10 words>\n"
                "  AT_TARGET: <confirm the object is very close and centred>\n"
                "Choose AT_TARGET only when the object is close and fills the centre of the frame."
            ),
            user_text=f"I'm approaching the '{target}'. How should I move?",
            image_b64=image_b64,
            max_tokens=60,
        )
        result = result.strip()
        logger.info(f"get_approach_guidance '{target}': {result}")
        return result

    # ── Responses API tool definitions ────────────────────────────────────────

    @staticmethod
    def get_tool_definitions() -> list[dict]:
        return [
            {
                "type": "function",
                "name": "look_around",
                "description": "Take a photo and describe what the robot sees in front of it.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            {
                "type": "function",
                "name": "search_for_object",
                "description": "Look at the camera and check if a specific object or item is visible.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "The object to search for, e.g. 'red teddy bear'",
                        }
                    },
                    "required": ["target"],
                },
            },
            {
                "type": "function",
                "name": "check_if_object_visible",
                "description": (
                    "Take a photo and check if the target object is visible right now. "
                    "Returns FOUND:<position> or NOT_FOUND:<message>. "
                    "Use after every rotate_45_left/rotate_45_right during a scan."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "The object to look for, e.g. 'red cap'",
                        }
                    },
                    "required": ["target"],
                },
            },
            {
                "type": "function",
                "name": "get_approach_guidance",
                "description": (
                    "After spotting the target, take a photo and get a single navigation "
                    "instruction (TURN_LEFT / TURN_RIGHT / MOVE_FORWARD / AT_TARGET) to "
                    "drive closer. Call this after every move during the approach phase."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "The target object you are driving toward",
                        }
                    },
                    "required": ["target"],
                },
            },
        ]
