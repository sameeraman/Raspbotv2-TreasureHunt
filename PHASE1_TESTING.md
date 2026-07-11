# Phase 1 Testing Guide

This guide walks you through testing every component of Phase 1, from individual hardware modules up to the full treasure hunt loop. You can test on your **Mac/laptop** (simulation mode) or on the **Orange Pi 5 Pro** (with real hardware).

---

## Prerequisites

### Azure Services Required

| Service | What to Provision | Deployment Name |
|---------|-------------------|----------------|
| Azure OpenAI | GPT-5.4-mini model deployment | `gpt-5.4-mini` |
| Azure OpenAI | GPT-5.4 model deployment | `gpt-5.4` |
| Azure Speech | Speech Services resource | — |

### Install Dependencies

```bash
cd Raspbotv2-TreasureHunt
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in (minimum for Phase 1):

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT=gpt-5.4-mini
AZURE_OPENAI_VISION_DEPLOYMENT=gpt-5.4
AZURE_SP_TENANT_ID=your-tenant-id
AZURE_SP_CLIENT_ID=your-client-id
AZURE_SP_CLIENT_SECRET=your-client-secret
AZURE_SPEECH_REGION=australiaeast
AZURE_SPEECH_RESOURCE_ID=/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/<name>
```

> **Note:** Leave the `AZURE_SEARCH_*` fields as-is for Phase 1 — memory is disabled when those are blank.

---

## Test 1: Configuration Loads Correctly

**What it tests:** `.env` is read, all config dataclasses populate.

```bash
python -c "
from config import load_config
cfg = load_config()
print('✅ Config loaded')
print(f'   OpenAI endpoint: {cfg.azure_openai.endpoint[:30]}...')
print(f'   Speech region:   {cfg.azure_speech.region}')
print(f'   Max speed:       {cfg.safety.max_motor_speed}')
print(f'   Session limit:   {cfg.safety.max_session_minutes} min')
"
```

**Expected output:**
```
✅ Config loaded
   OpenAI endpoint: https://your-resource.openai...
   Speech region:   australiaeast
   Max speed:       75
   Session limit:   15 min
```

---

## Test 2: Motor Controller (Simulation Mode)

**What it tests:** Motor commands execute without crashing on a non-robot machine. On the Orange Pi, this moves the actual wheels.

```bash
python -c "
from hardware.motor import MotorController
motor = MotorController(max_speed=75)
print('Testing motor simulation...')
motor.move_forward(speed=50, duration=0.5)
motor.rotate_left(speed=40, duration=0.3)
motor.nod()
motor.shake_head()
motor.stop()
print('✅ Motor controller works (simulation mode)')
"
```

**Expected output (Mac):**
```
[HH:MM:SS] ringo.motor WARNING: Raspbot_Lib not available — motor commands will be simulated
Testing motor simulation...
[HH:MM:SS] ringo.motor INFO: Moving forward (speed=50, 0.5s)
[HH:MM:SS] ringo.motor INFO: Rotating left (speed=40, 0.3s)
[HH:MM:SS] ringo.motor INFO: Nodding
[HH:MM:SS] ringo.motor INFO: Shaking head
✅ Motor controller works (simulation mode)
```

---

## Test 3: Speed Limiting

**What it tests:** The safety speed cap is enforced — no motor command exceeds `max_speed`.

```bash
python -c "
from hardware.motor import MotorController
motor = MotorController(max_speed=75)

# Try to exceed the speed limit
clamped = motor._clamp_speed(200)
assert clamped == 75, f'Expected 75, got {clamped}'

clamped = motor._clamp_speed(50)
assert clamped == 50, f'Expected 50, got {clamped}'

clamped = motor._clamp_speed(-10)
assert clamped == 0, f'Expected 0, got {clamped}'

print('✅ Speed limiting works correctly')
print(f'   200 → {motor._clamp_speed(200)} (capped at 75)')
print(f'   50  → {motor._clamp_speed(50)}  (within limit)')
print(f'   -10 → {motor._clamp_speed(-10)} (floored at 0)')
"
```

---

## Test 4: Ultrasonic Sensor (Simulation Mode)

**What it tests:** Distance reading returns simulated value on Mac, real values on Orange Pi.

```bash
python -c "
from hardware.ultrasonic import UltrasonicSensor
sensor = UltrasonicSensor(stop_distance_mm=150)
distance = sensor.get_distance_mm()
blocked = sensor.is_obstacle_ahead()
print(f'Distance: {distance} mm')
print(f'Obstacle ahead: {blocked}')
print('✅ Ultrasonic sensor works (simulation: always 9999mm, no obstacle)')
"
```

---

## Test 5: Camera Capture

**What it tests:** Camera opens, captures a frame, converts to base64 JPEG.

> **Requires:** A USB webcam or built-in camera.

```bash
python -c "
from hardware.camera import Camera
cam = Camera(index=0, width=640, height=480)
cam.open()
b64 = cam.capture_as_base64()
if b64:
    print(f'✅ Camera captured image ({len(b64)} base64 chars)')
    print(f'   Approx image size: {len(b64) * 3 // 4 // 1024} KB')
else:
    print('❌ No camera available — capture returned None')
    print('   This is OK if testing on a headless machine')
cam.close()
"
```

---

## Test 6: RGB Lights (Simulation Mode)

**What it tests:** Light state changes log correctly.

```bash
python -c "
from hardware.lights import LightController
lights = LightController()
lights.idle()
lights.listening()
lights.thinking()
lights.speaking()
lights.found_treasure()
lights.off()
print('✅ Light controller works (simulation mode)')
"
```

---

## Test 7: Azure Speech — Text-to-Speech

**What it tests:** Azure TTS synthesizes and plays audio through your speakers.

> **Requires:** SP credentials and `AZURE_SPEECH_REGION` / `AZURE_SPEECH_RESOURCE_ID` in `.env`, plus a speaker/headphones.

```bash
python -c "
from config import load_config
from speech.tts import TextToSpeech
cfg = load_config()
tts = TextToSpeech(
    speech_region=cfg.azure_speech.region,
    credential=cfg.service_principal.get_credential(),
    resource_id=cfg.azure_speech.resource_id,
)
print('Speaking... (listen for audio)')
tts.speak('Hello Sienna! I am Ringo, your treasure hunting buddy! Beep boop!')
print('✅ TTS works')
"
```

**What to check:**
- You should hear a friendly voice saying the text
- Speech rate should be slightly slower than normal (child-friendly)

---

## Test 8: Azure Speech — Speech-to-Text

**What it tests:** Microphone records, Azure STT transcribes.

> **Requires:** SP credentials and `AZURE_SPEECH_REGION` / `AZURE_SPEECH_RESOURCE_ID` in `.env`, plus a microphone.

```bash
python -c "
from config import load_config
from speech.stt import SpeechToText
cfg = load_config()
stt = SpeechToText(
    speech_region=cfg.azure_speech.region,
    credential=cfg.service_principal.get_credential(),
    resource_id=cfg.azure_speech.resource_id,
)
print('🎤 Speak now (you have ~10 seconds)...')
text = stt.listen(timeout_seconds=10)
if text:
    print(f'✅ Recognized: \"{text}\"')
else:
    print('❌ No speech detected — try again or check microphone')
"
```

**What to check:**
- Say something clearly (e.g., "Find my red teddy bear")
- The transcription should match what you said

---

## Test 9: Vision Plugin — Look Around

**What it tests:** Camera capture → base64 → Azure OpenAI GPT-5.4 vision → scene description.

> **Requires:** Camera + `AZURE_OPENAI_*` keys in `.env`.

```bash
python -c "
from config import load_config
from hardware.camera import Camera
from plugins.vision import VisionPlugin

cfg = load_config()
cam = Camera(); cam.open()
token_provider = cfg.service_principal.get_token_provider()

vp = VisionPlugin(
    camera=cam,
    endpoint=cfg.azure_openai.endpoint,
    token_provider=token_provider,
    deployment=cfg.azure_openai.vision_deployment,
    api_version=cfg.azure_openai.api_version,
)

print('📷 Looking around...')
description = vp.look_around()
print(f'✅ Vision says: \"{description}\"')
cam.close()
"
```

**What to check:**
- Description should be in child-friendly language
- Should mention colours, shapes, objects it sees

---

## Test 10: Vision Plugin — Search for Object

**What it tests:** Camera + GPT-5.4 searches for a specific object.

```bash
python -c "
from config import load_config
from hardware.camera import Camera
from plugins.vision import VisionPlugin

cfg = load_config()
cam = Camera(); cam.open()
token_provider = cfg.service_principal.get_token_provider()

vp = VisionPlugin(
    camera=cam,
    endpoint=cfg.azure_openai.endpoint,
    token_provider=token_provider,
    deployment=cfg.azure_openai.vision_deployment,
    api_version=cfg.azure_openai.api_version,
)

print('🔍 Searching for a cup...')
result = vp.search_for_object('cup')
print(f'✅ Search result: \"{result}\"')
cam.close()
"
```

---

## Test 11: Safety Plugin

**What it tests:** Session timer and obstacle check.

```bash
python -c "
import time
from hardware.ultrasonic import UltrasonicSensor
from plugins.safety import SafetyPlugin

ultra = UltrasonicSensor()
safety = SafetyPlugin(ultra, max_session_minutes=1)  # 1-min limit for testing

safety.start_session()
print(f'Session started. Expired? {safety.is_session_expired()}')
print(f'Elapsed: {safety.get_elapsed_minutes():.1f} min')

# Simulate a short wait
time.sleep(2)
print(f'After 2s: {safety.get_elapsed_minutes():.2f} min elapsed')
print(f'Expired? {safety.is_session_expired()}')
print('✅ Safety plugin works')
"
```

---

## Test 12: Orchestrator — Text Chat (No Voice)

**What it tests:** Full Semantic Kernel orchestrator with all plugins, using typed text instead of voice.

> **Requires:** All `AZURE_OPENAI_*` keys in `.env`. Camera optional.

```bash
python -c "
import asyncio
from config import load_config
from hardware.camera import Camera
from hardware.motor import MotorController
from hardware.ultrasonic import UltrasonicSensor
from plugins.vision import VisionPlugin
from plugins.movement import MovementPlugin
from plugins.safety import SafetyPlugin
from agents.orchestrator import RingoOrchestrator

cfg = load_config()
cam = Camera(); cam.open()
motor = MotorController(max_speed=cfg.safety.max_motor_speed)
ultra = UltrasonicSensor()
token_provider = cfg.service_principal.get_token_provider()

vp = VisionPlugin(cam, cfg.azure_openai.endpoint, token_provider,
                   cfg.azure_openai.vision_deployment, cfg.azure_openai.api_version)
mp = MovementPlugin(motor, ultra)
sp = SafetyPlugin(ultra, cfg.safety.max_session_minutes)

orch = RingoOrchestrator(cfg.azure_openai, token_provider, vp, mp, sp)

async def test():
    print('--- Starting Treasure Hunt ---')
    greeting = await orch.start_treasure_hunt()
    print(f'Ringo: {greeting}')
    print()

    response = await orch.chat('Find my red teddy bear!')
    print(f'Ringo: {response}')
    print()

    response = await orch.chat('Maybe try looking to the left?')
    print(f'Ringo: {response}')
    print()

    goodbye = await orch.end_session()
    print(f'Ringo: {goodbye}')
    print()
    print('✅ Orchestrator works')

asyncio.run(test())
cam.close()
"
```

**What to check:**
- Ringo's responses are child-friendly (short, fun sentences)
- It may call vision/movement functions automatically
- No errors or crashes

---

## Test 13: Full End-to-End (Orange Pi Only)

**What it tests:** Complete flow: wake word → voice → AI → movement → voice response.

> **Run this on the Orange Pi with the robot assembled.**

```bash
ssh orangepi@<ip>
cd ~/Raspbotv2-TreasureHunt
python main.py
```

**Test script:**
1. Wait for `Waiting for wake word 'Ringo'...` in the logs
2. Say **"Ringo"** — robot should activate (lights change to green)
3. Listen for Ringo's greeting
4. Say **"Find my red cup"** — Ringo should respond and start searching
5. Say **"Try looking to the right"** — Ringo should turn
6. Say **"That's it! You found it!"** — Ringo should celebrate
7. Say **"Goodbye"** — Ringo should say farewell and return to idle

**What to check:**
- ✅ Wake word triggers correctly
- ✅ Lights change with state (green=listening, blue=thinking, yellow=speaking)
- ✅ Speech is understandable and child-appropriate
- ✅ Motors move at safe speed (not too fast)
- ✅ Robot stops when saying "stop" or "bye"
- ✅ Session ends after 15 minutes

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Raspbot_Lib not available` | Running on Mac, not Orange Pi | This is normal — simulation mode |
| `Speech recognition canceled` | Bad Azure Speech key | Check `AZURE_SPEECH_KEY` in `.env` |
| `Failed to open camera` | No webcam / wrong index | Try `CAMERA_INDEX=1` or `2` |
| `write_u8 I2C error` | I2C bus issue on Orange Pi | Check wiring; run `i2cdetect -y 1` |
| `openai.AuthenticationError` | Bad OpenAI key | Check `AZURE_OPENAI_API_KEY` |
| No audio output from TTS | No speaker configured | Check `aplay -l` on Orange Pi |
| Wake word never triggers | Serial port wrong | Check `VOICE_MODULE_PORT` (try `/dev/ttyUSB1`) |
