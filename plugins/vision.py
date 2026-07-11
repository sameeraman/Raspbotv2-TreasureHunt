"""Vision plugin — uses GPT-5.4 to understand camera frames."""

from typing import Annotated, Callable
from semantic_kernel.functions import kernel_function

from openai import AzureOpenAI

from hardware.camera import Camera
from utils import setup_logger

logger = setup_logger("ringo.vision")


class VisionPlugin:
    """Semantic Kernel plugin for camera-based scene understanding."""

    def __init__(self, camera: Camera, endpoint: str, token_provider: Callable[[], str],
                 deployment: str, api_version: str):
        self.camera = camera
        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        self.deployment = deployment

    @kernel_function(
        name="look_around",
        description="Take a photo and describe what the robot sees in front of it.",
    )
    def look_around(self) -> Annotated[str, "Description of what the camera sees"]:
        """Capture a frame and describe the scene."""
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "I couldn't see anything — the camera might be blocked."

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Ringo, a friendly robot helping a 6-year-old girl named Sienna "
                        "find hidden treasures around the house. Describe what you see in simple, "
                        "fun language a 6-year-old would understand. Focus on colours, shapes, "
                        "and recognizable objects (toys, furniture, etc.). Keep it to 2-3 sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What do you see right now?"},
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
            max_completion_tokens=200,
        )

        description = response.choices[0].message.content
        logger.info(f"Vision: {description}")
        return description

    @kernel_function(
        name="search_for_object",
        description="Look at the camera and check if a specific object or item is visible.",
    )
    def search_for_object(
        self,
        target: Annotated[str, "The object to search for, e.g. 'red teddy bear'"],
    ) -> Annotated[str, "Whether the object was found and where it appears"]:
        """Check if a specific target object is visible in the current frame."""
        image_b64 = self.camera.capture_as_base64()
        if not image_b64:
            return "I can't see right now — my camera might be blocked!"

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Ringo, a treasure-hunting robot helping 6-year-old Sienna. "
                        "Look at this image and determine if you can see the target object. "
                        "Reply in a fun way for a child. If you see it, say where in the image "
                        "(left, right, center, far away, close). If not, say you don't see it yet "
                        "and suggest a direction to try. Keep it to 2-3 short sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Can you see a '{target}' in this image?"},
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
            max_completion_tokens=200,
        )

        result = response.choices[0].message.content
        logger.info(f"Search for '{target}': {result}")
        return result
