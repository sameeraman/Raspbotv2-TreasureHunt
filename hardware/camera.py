"""Camera capture module for Raspbotv2."""

import cv2
import base64
import numpy as np
from io import BytesIO
from PIL import Image

from utils import setup_logger

logger = setup_logger("ringo.camera")


class Camera:
    """USB camera wrapper for capturing frames."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.index = index
        self.width = width
        self.height = height
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(self.index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self._cap.isOpened():
            logger.info(f"Camera opened (index={self.index}, {self.width}x{self.height})")
        else:
            logger.error("Failed to open camera")

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
            logger.info("Camera closed")

    def capture_frame(self) -> np.ndarray | None:
        """Capture a single frame from the camera."""
        if not self._cap or not self._cap.isOpened():
            self.open()

        ret, frame = self._cap.read()
        if ret:
            return frame
        logger.error("Failed to capture frame")
        return None

    def capture_as_base64(self, quality: int = 80) -> str | None:
        """Capture a frame and return as base64-encoded JPEG for vision API."""
        frame = self.capture_frame()
        if frame is None:
            return None

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_frame)

        # Resize for API efficiency (max 512px on longest side)
        img.thumbnail((512, 512), Image.LANCZOS)

        # Encode as JPEG
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.debug(f"Captured frame as base64 ({len(b64)} chars)")
        return b64

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
