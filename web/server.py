"""FastAPI web dashboard for Ringo Treasure Hunt.

Provides:
  - Real-time log stream via WebSocket (/ws/logs)
  - Live camera feed via WebSocket (/ws/camera)
  - Sensor readings via WebSocket (/ws/sensors)
  - Session management REST API
  - Manual robot control REST API
"""

import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC = Path(__file__).parent / "static"

# ─── WebSocket connection pool ────────────────────────────────────────────────

class WSPool:
    """Manages a pool of WebSocket connections and broadcasts to all."""

    def __init__(self):
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, data: dict):
        dead: Set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    @property
    def count(self) -> int:
        return len(self._clients)


log_pool = WSPool()
sensor_pool = WSPool()
camera_pool = WSPool()

# ─── Log capture ──────────────────────────────────────────────────────────────

_log_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_event_loop: Optional[asyncio.AbstractEventLoop] = None


class WebSocketLogHandler(logging.Handler):
    """Captures log records and feeds them into the async queue."""

    def emit(self, record: logging.LogRecord):
        if _event_loop and not _event_loop.is_closed():
            entry = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "logger": record.name.replace("ringo.", ""),
                "message": self.format(record),
            }
            asyncio.run_coroutine_threadsafe(
                _safe_enqueue(entry), _event_loop
            )


async def _safe_enqueue(entry: dict):
    try:
        _log_queue.put_nowait(entry)
    except asyncio.QueueFull:
        pass  # Drop oldest by discarding new


_ws_log_handler = WebSocketLogHandler()
_ws_log_handler.setFormatter(logging.Formatter("%(message)s"))

# ─── Shared hardware (lazy-initialised once) ──────────────────────────────────

_hw_ready = False
_motor = None
_lights = None
_ultra = None
_camera = None
_tts = None
_pending_stop: asyncio.Task | None = None
_light_state = "idle"

# Current audio levels — initialised from .env, adjustable via /api/audio
_current_speaker_vol: int = int(os.getenv("SPEAKER_VOLUME") or "95")
_current_mic_vol: int = int(os.getenv("MIC_VOLUME") or "85")
_current_tts_vol: int = int(os.getenv("TTS_VOLUME") or "90")


def _ensure_hardware():
    global _hw_ready, _motor, _lights, _ultra, _camera
    if _hw_ready:
        return
    try:
        from config import load_config
        from hardware.camera import Camera
        from hardware.lights import LightController
        from hardware.motor import MotorController
        from hardware.ultrasonic import UltrasonicSensor
        cfg = load_config()
        _motor = MotorController(max_speed=cfg.safety.max_motor_speed)
        _lights = LightController()
        _ultra = UltrasonicSensor(stop_distance_mm=cfg.safety.obstacle_stop_distance_mm)
        _camera = Camera(
            index=cfg.hardware.camera_index,
            width=cfg.hardware.camera_width,
            height=cfg.hardware.camera_height,
        )
        _camera.open()
        _hw_ready = True
    except Exception as e:
        logging.getLogger("ringo.web").error(f"Hardware init error: {e}")


# ─── Session state ────────────────────────────────────────────────────────────

class _Session:
    active: bool = False
    start_time: Optional[datetime] = None
    task: Optional[asyncio.Task] = None
    stop_event: Optional[asyncio.Event] = None

    @property
    def elapsed_seconds(self) -> int:
        if self.start_time:
            return int((datetime.now() - self.start_time).total_seconds())
        return 0


_session = _Session()

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Ringo Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.on_event("startup")
async def _startup():
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    # Attach WebSocket log handler to root logger
    root = logging.getLogger()
    root.addHandler(_ws_log_handler)
    # Initialise hardware
    _ensure_hardware()
    # Start background broadcasting tasks
    asyncio.create_task(_pump_logs())
    asyncio.create_task(_pump_sensors())
    asyncio.create_task(_pump_camera())
    logging.getLogger("ringo.web").info(
        "🌐 Ringo web dashboard started — http://0.0.0.0:8080"
    )


# ─── Background pump tasks ────────────────────────────────────────────────────

async def _pump_logs():
    while True:
        entry = await _log_queue.get()
        await log_pool.broadcast(entry)


async def _pump_sensors():
    while True:
        try:
            if sensor_pool.count:
                data = {
                    "distance_mm": _ultra.get_distance_mm() if _ultra else 9999,
                    "obstacle": _ultra.is_obstacle_ahead() if _ultra else False,
                    "light_state": _light_state,
                }
                await sensor_pool.broadcast(data)
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def _pump_camera():
    while True:
        try:
            if camera_pool.count and _camera:
                b64 = await asyncio.to_thread(_camera.capture_as_base64)
                if b64:
                    await camera_pool.broadcast({"frame": b64})
        except Exception:
            pass
        await asyncio.sleep(0.25)  # ~4 fps


# ─── Page routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def page_dashboard():
    return (STATIC / "index.html").read_text()


@app.get("/control", response_class=HTMLResponse)
async def page_control():
    return (STATIC / "control.html").read_text()


# ─── Status API ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return {
        "session_active": _session.active,
        "elapsed_seconds": _session.elapsed_seconds,
        "light_state": _light_state,
        "hw_ready": _hw_ready,
    }


# ─── Session API ──────────────────────────────────────────────────────────────

@app.post("/api/session/start")
async def api_session_start():
    if _session.active:
        return {"ok": False, "reason": "Session already active"}
    _session.active = True
    _session.start_time = datetime.now()
    _session.stop_event = asyncio.Event()
    _session.task = asyncio.create_task(_run_session())
    logging.getLogger("ringo.web").info("▶ Session started from web UI")
    return {"ok": True}


@app.post("/api/session/stop")
async def api_session_stop():
    _stop_session("web UI stop request")
    return {"ok": True}


# ─── Emergency stop ───────────────────────────────────────────────────────────

@app.post("/api/emergency-stop")
async def api_emergency_stop():
    global _light_state, _pending_stop
    if _pending_stop and not _pending_stop.done():
        _pending_stop.cancel()
        _pending_stop = None
    if _motor:
        _motor.stop()
    if _lights:
        _lights.off()
        _light_state = "off"
    _stop_session("EMERGENCY STOP")
    logging.getLogger("ringo.web").warning("🛑 EMERGENCY STOP activated")
    return {"ok": True}


# ─── Movement API ─────────────────────────────────────────────────────────────

class MoveRequest(BaseModel):
    direction: str
    duration: float = 0.5
    speed: int = 50


async def _schedule_stop(delay: float):
    """Asyncio-native guaranteed motor stop after `delay` seconds.

    Using asyncio.sleep (not time.sleep in a thread) means the stop fires
    precisely on the event loop and cannot race with another command's stop.
    """
    await asyncio.sleep(delay)
    if _motor:
        _motor.stop()
        logging.getLogger("ringo.web").debug(f"Motor auto-stop after {delay:.2f}s")


@app.post("/api/move")
async def api_move(req: MoveRequest):
    global _pending_stop

    if not _motor:
        return {"ok": False, "reason": "Hardware not ready"}

    log = logging.getLogger("ringo.web")
    speed = max(10, min(100, req.speed))
    dur   = max(0.1, min(3.0, req.duration))
    d     = req.direction

    # Cancel any previous timed stop so it cannot fire while a new command runs
    if _pending_stop and not _pending_stop.done():
        _pending_stop.cancel()
        _pending_stop = None

    if d in ("forward", "backward", "strafe_left", "strafe_right",
             "rotate_left", "rotate_right"):
        if d == "forward" and _ultra and _ultra.is_obstacle_ahead():
            log.warning("⚠ Obstacle ahead — forward blocked")
            return {"ok": False, "reason": "Obstacle detected"}
        _motor.start_drive(d, speed)
        _pending_stop = asyncio.create_task(_schedule_stop(dur))
        log.info(f"Move {d} {dur}s @ {speed}%")

    elif d == "stop":
        # _pending_stop already cancelled above; hard-stop immediately
        _motor.stop()
        log.info("■ Stop")

    elif d == "nod":
        await asyncio.to_thread(_motor.nod)
        log.info("↕ Nod")

    elif d == "shake":
        await asyncio.to_thread(_motor.shake_head)
        log.info("↔ Shake head")

    else:
        return {"ok": False, "reason": f"Unknown direction: {d}"}

    return {"ok": True}


# ─── Lights API ───────────────────────────────────────────────────────────────

class LightRequest(BaseModel):
    state: str


@app.post("/api/lights")
async def api_lights(req: LightRequest):
    global _light_state
    if not _lights:
        return {"ok": False, "reason": "Hardware not ready"}

    _state_map = {
        "idle": lambda: _lights.set_color(40, 40, 60),
        "listening": _lights.listening,
        "thinking": _lights.thinking,
        "speaking": _lights.speaking,
        "treasure": _lights.found_treasure,
        "off": _lights.off,
    }
    fn = _state_map.get(req.state)
    if not fn:
        return {"ok": False, "reason": f"Unknown state: {req.state}"}

    fn()
    _light_state = req.state
    logging.getLogger("ringo.web").info(f"💡 Lights → {req.state}")
    return {"ok": True}


# ─── Audio API ────────────────────────────────────────────────────────────────

class AudioRequest(BaseModel):
    speaker_volume: int | None = None
    mic_volume: int | None = None
    tts_volume: int | None = None


@app.get("/api/audio")
async def api_audio_status():
    """Return current audio levels."""
    return {
        "speaker_volume": _current_speaker_vol,
        "mic_volume": _current_mic_vol,
        "tts_volume": _current_tts_vol,
    }


@app.post("/api/audio")
async def api_audio(req: AudioRequest):
    global _current_speaker_vol, _current_mic_vol, _current_tts_vol

    card = os.getenv("ALSA_CARD", "").strip()
    card_flag = ["-c", card] if card else []
    log = logging.getLogger("ringo.web")

    if req.speaker_volume is not None:
        vol = max(0, min(100, req.speaker_volume))
        for ctrl in ("PCM", "Speaker", "Headphone", "Master"):
            try:
                r = subprocess.run(
                    ["amixer", *card_flag, "-q", "sset", ctrl, f"{vol}%"],
                    timeout=3, capture_output=True,
                )
                if r.returncode == 0:
                    _current_speaker_vol = vol
                    log.info(f"🔊 Speaker ({ctrl}) volume → {vol}%")
                    break
            except Exception:
                continue
        else:
            log.warning(
                f"Speaker: no ALSA control found (tried PCM, Speaker, Headphone, Master). "
                f"Run 'amixer -c {card or '0'} scontrols' to list available controls."
            )
            _current_speaker_vol = vol

    if req.mic_volume is not None:
        vol = max(0, min(100, req.mic_volume))
        for ctrl in ("Mic", "Microphone", "Capture", "Mic Capture Volume"):
            try:
                r = subprocess.run(
                    ["amixer", *card_flag, "-q", "sset", ctrl, f"{vol}%"],
                    timeout=3, capture_output=True,
                )
                if r.returncode == 0:
                    _current_mic_vol = vol
                    log.info(f"🎤 Mic ({ctrl}) volume → {vol}%")
                    break
            except Exception:
                continue
        else:
            log.warning(
                f"Mic: no ALSA control found (tried Mic, Microphone, Capture). "
                f"Run 'amixer -c {card or '0'} scontrols' to list available controls."
            )
            _current_mic_vol = vol

    if req.tts_volume is not None:
        vol = max(0, min(100, req.tts_volume))
        _current_tts_vol = vol
        if _tts:
            _tts.volume = str(vol)
        log.info(f"🗣 TTS volume → {vol}%")

    return {
        "ok": True,
        "speaker_volume": _current_speaker_vol,
        "mic_volume": _current_mic_vol,
        "tts_volume": _current_tts_vol,
    }


# ─── Chat API (send text to active session) ───────────────────────────────────

class ChatRequest(BaseModel):
    message: str


_chat_queue: asyncio.Queue = asyncio.Queue(maxsize=10)


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    if not _session.active:
        return {"ok": False, "reason": "No active session"}
    try:
        _chat_queue.put_nowait(req.message)
        logging.getLogger("ringo.web").info(f"💬 Web chat: {req.message}")
        return {"ok": True}
    except asyncio.QueueFull:
        return {"ok": False, "reason": "Chat queue full — try again"}


# ─── WebSocket endpoints ──────────────────────────────────────────────────────

@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await log_pool.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
    except (WebSocketDisconnect, Exception):
        log_pool.disconnect(ws)


@app.websocket("/ws/sensors")
async def ws_sensors(ws: WebSocket):
    await sensor_pool.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
    except (WebSocketDisconnect, Exception):
        sensor_pool.disconnect(ws)


@app.websocket("/ws/camera")
async def ws_camera(ws: WebSocket):
    await camera_pool.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
    except (WebSocketDisconnect, Exception):
        camera_pool.disconnect(ws)


# ─── Session runner ───────────────────────────────────────────────────────────

def _stop_session(reason: str):
    if _session.stop_event:
        _session.stop_event.set()
    _session.active = False
    _session.start_time = None
    if _motor:
        _motor.stop()


async def _run_session():
    """Run the full Ringo treasure hunt session (voice + AI loop)."""
    log = logging.getLogger("ringo.session")
    try:
        from config import load_config
        from services.embedding import EmbeddingService
        from plugins.vision import VisionPlugin
        from plugins.movement import MovementPlugin
        from plugins.safety import SafetyPlugin
        from plugins.memory import MemoryPlugin
        from agents.orchestrator import RingoOrchestrator
        from agents.memory_manager import MemoryManager
        from speech.stt import SpeechToText
        from speech.tts import TextToSpeech

        cfg = load_config()
        token_provider = cfg.service_principal.get_token_provider()
        credential = cfg.service_principal.get_credential()

        emb = EmbeddingService(
            cfg.azure_openai.endpoint, token_provider,
            cfg.azure_openai.embedding_deployment, cfg.azure_openai.api_version,
        )
        vp = VisionPlugin(
            _camera, cfg.azure_openai.endpoint, token_provider,
            cfg.azure_openai.vision_deployment, cfg.azure_openai.api_version,
        )
        mp = MovementPlugin(_motor, _ultra)
        sp = SafetyPlugin(_ultra, cfg.safety.max_session_minutes)

        mem_plugin = None
        mgr = None
        if cfg.azure_search.endpoint and cfg.azure_search.key:
            mem_plugin = MemoryPlugin(
                cfg.azure_search.endpoint, cfg.azure_search.key,
                cfg.azure_search.index_name, emb,
            )
            mgr = MemoryManager(mem_plugin)

        orch = RingoOrchestrator(
            openai_config=cfg.azure_openai,
            token_provider=token_provider,
            vision_plugin=vp,
            movement_plugin=mp,
            safety_plugin=sp,
            memory_plugin=mem_plugin,
        )
        stt = SpeechToText(
            speech_region=cfg.azure_speech.region,
            credential=credential,
            resource_id=cfg.azure_speech.resource_id,
        )
        tts = TextToSpeech(
            speech_region=cfg.azure_speech.region,
            credential=credential,
            resource_id=cfg.azure_speech.resource_id,
        )

        if mgr:
            mgr.start_session()
            memory_context = await mgr.get_greeting_context()
        else:
            memory_context = ""

        sp.start_session()
        greeting = await orch.start_treasure_hunt(memory_context=memory_context)
        log.info(f"Ringo: {greeting}")
        await asyncio.to_thread(tts.speak, greeting)

        while _session.active and not _session.stop_event.is_set():
            if sp.is_session_expired():
                log.info("Session time limit reached")
                break

            # Check web chat queue first (non-blocking)
            text = None
            try:
                text = _chat_queue.get_nowait()
                log.info(f"[web] {text}")
            except asyncio.QueueEmpty:
                pass

            # Fall back to voice
            if text is None:
                text = await asyncio.to_thread(stt.listen, 8)

            if not text:
                continue

            log.info(f"Sienna: {text}")
            if any(w in text.lower() for w in ["goodbye", "bye", "stop", "exit"]):
                break

            response = await orch.chat(text)
            log.info(f"Ringo: {response}")
            if mgr:
                await mgr.observe_exchange(text, response)
            await asyncio.to_thread(tts.speak, response)

        farewell = await orch.end_session()
        log.info(f"Ringo: {farewell}")
        await asyncio.to_thread(tts.speak, farewell)

        if mgr:
            await mgr.end_session_summary()

    except asyncio.CancelledError:
        log.info("Session cancelled")
    except Exception as e:
        log.error(f"Session error: {e}", exc_info=True)
    finally:
        _stop_session("session completed")
        log.info("Session ended")
