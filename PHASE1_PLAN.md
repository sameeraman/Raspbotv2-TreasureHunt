# Raspbotv2 Treasure Hunt — Phase 1 Plan (Retrospective)

**Date:** 2026-07-09  
**Status:** ✅ Complete  
**Duration:** Single session (~25 minutes)

---

## Goal

Build a working treasure hunt robot agent that Sienna (age 6) can interact with by voice. Say "Ringo" to wake it, tell it what to find, and it explores using camera + movement while chatting back in a playful, child-friendly way.

---

## Discovery — What I Started With

### Source Material Reviewed

| File | What I Learned |
|------|---------------|
| `raspbotv2-specifications.md` | Hardware: Orange Pi 5 Pro, Mecanum wheels, 1MP USB camera with 2DOF PTZ, ultrasonic sensor, RGB light bar, AI voice module, TT motors (max 255 speed), servos, buzzer. Battery gives ~2 hours. |
| `raspbotv2-project_info.md` | Architecture vision (multi-agent with Semantic Kernel), model choices (GPT-5.4-mini orchestrator, o3 planner, GPT-5.4 vision), treasure hunt concept, target folder name `Raspbotv2-TreasureHunt`. |
| `raspbotv2-project_requirements.md` | Wake word is "Ringo", OLED shows system stats. |
| `RaspbotV2-Code/` — existing source | Full codebase for the stock robot. Key files studied below. |

### Existing Code Deep Dive

| File | What It Provided |
|------|-----------------|
| `Raspbot_Lib.py` (Python driver) | I2C address `0x2B`, motor control (`Ctrl_Car`, `Ctrl_Muto`), servo control (`Ctrl_Servo`), RGB LEDs (`Ctrl_WQ2812_*`), ultrasonic sensor read (registers `0x1A`/`0x1B`), buzzer, infrared. This is the foundational hardware API. |
| `McLumk_Wheel_Sports.py` | Mecanum kinematics — `set_deflection(speed, angle)` decomposes velocity into 4 wheel speeds. Forward=90°, Back=270°, Left=180°, Right=0°. Rotation uses inverted diagonal wheels. |
| `Car_base_control.py` | High-level wrappers — `Car_Forword()`, `Car_back()`, servo nod/shake head, ultrasonic distance read, RGB control, camera photo capture. All built on `McLumk_Wheel_Sports`. |
| `Car_decision_agent.py` | Stock agent uses Qwen VL models (Chinese). Two-tier architecture: decision agent parses commands → execution agent runs them. Output is JSON `{function: [...], response: "..."}`. |
| `mic_serial.py` | Wake word protocol: serial bytes `AA 55 [01-06] 00 FB` = wake word detected. Background thread reads serial port continuously. |
| `Intelligent agent prompt words.md` | Full function catalog for the stock agent — movement, RGB, servo, vision tracking, obstacle avoidance. All function signatures documented. |

### Key Design Decisions Made (10 questions asked)

See `PROJECT_DECISIONS.md` for the full log. Summary:
1. `.env` placeholders (no Azure provisioning yet)
2. Hardware wake-word + Azure Speech STT/TTS
3. English only
4. Start simple, expand later
5. Free-roaming, no physical markers
6. Low speed + 15-min session limit
7. Any object Sienna describes
8. "Ringo" personality — playful robot friend
9. 15-minute max sessions
10. Semantic Kernel Python SDK

---

## Architecture Designed

```
     "Ringo!" (wake word)
           │
    ┌──────▼───────┐
    │  Wake Word   │  Hardware serial → byte protocol parser
    └──────┬───────┘
           │ triggered
    ┌──────▼───────┐
    │  Azure STT   │  Microphone → Azure Speech → text
    └──────┬───────┘
           │ text
    ┌──────▼───────────────────────────┐
    │  Semantic Kernel Orchestrator    │
    │  (GPT-5.4-mini)                  │
    │                                  │
    │  Plugins (auto function-calling) │
    │  ├── VisionPlugin                │
    │  │   └── look_around()           │ Camera → base64 → GPT-5.4
    │  │   └── search_for_object()     │ "Can you see X?" → GPT-5.4
    │  ├── MovementPlugin              │
    │  │   └── move_forward/back/L/R() │ Speed-capped Mecanum control
    │  │   └── turn_left/right()       │ Rotation
    │  │   └── nod_yes/shake_head()    │ PTZ servo gestures
    │  │   └── look_around_gesture()   │ Slow camera pan
    │  └── SafetyPlugin               │
    │      └── check_safety()          │ Obstacle + time check
    │      └── get_time_remaining()    │ Session countdown
    └──────┬───────────────────────────┘
           │ response text
    ┌──────▼───────┐
    │  Azure TTS   │  SSML with -10% rate, +5% pitch (child-friendly)
    └──────────────┘
```

---

## Implementation Order

This is the sequence I followed when building the code:

### Step 1: Project Scaffolding
- Created `Raspbotv2-TreasureHunt/` directory
- Created subdirectories: `agents/`, `plugins/`, `hardware/`, `speech/`, `utils/`
- Created `__init__.py` for each package
- Created `.env.example` with all required placeholders
- Created `requirements.txt` with pinned dependencies

### Step 2: Config & Utilities
- **`config.py`** — Dataclass-based config loaded from `.env` via `python-dotenv`. Four config groups: `AzureOpenAIConfig`, `AzureSpeechConfig`, `SafetyConfig`, `HardwareConfig`.
- **`utils/__init__.py`** — Centralized logger setup with `[HH:MM:SS] name LEVEL: message` format.

### Step 3: Hardware Abstraction Layer
Built bottom-up from the existing `Raspbot_Lib` and `McLumk_Wheel_Sports`:

| File | Based On | Key Design Choice |
|------|----------|-------------------|
| `hardware/motor.py` | `McLumk_Wheel_Sports.py` + `Car_base_control.py` | Added `_clamp_speed()` that enforces `max_speed=75` on every command. Ported the Mecanum kinematics. Added `nod()`, `shake_head()`, `look_around()` servo gestures. |
| `hardware/camera.py` | `Car_base_control.py` `take_photo_agent()` | Returns base64 JPEG directly (for GPT-5.4 vision API). Thumbnails to 512px to save API tokens. |
| `hardware/ultrasonic.py` | `Car_base_control.py` `Get_dis_obstacle()` | Simplified to `get_distance_mm()` and `is_obstacle_ahead()`. Toggle sensor on/off per read. |
| `hardware/lights.py` | `Raspbot_Lib.py` RGB functions | Semantic methods: `thinking()` = blue, `listening()` = green, `speaking()` = yellow, `found_treasure()` = rainbow flash. |
| `hardware/wake_word.py` | `mic_serial.py` | Same byte protocol (AA 55 01-06 00 FB). Added thread-safe `is_triggered()` with auto-reset and `wait_for_wake_word(timeout)`. |

**Critical design:** All hardware modules have a simulation fallback — if `Raspbot_Lib` isn't importable (i.e., running on a dev machine, not the Orange Pi), they log instead of crashing. This enables testing the full flow on a laptop.

### Step 4: Speech Layer
| File | Purpose | Details |
|------|---------|---------|
| `speech/stt.py` | Azure Speech-to-Text | Uses `en-AU` locale, single-shot recognition via default microphone. Returns `str | None`. |
| `speech/tts.py` | Azure Text-to-Speech | Uses `en-AU-WilliamNeural` voice. SSML wrapper with `-10% rate` and `+5% pitch` for child-friendly pacing. Added `speak_excited()` variant with `+15% pitch` for celebrations. |

### Step 5: Semantic Kernel Plugins
Three plugins exposing robot capabilities as SK kernel functions:

| Plugin | Functions | How Orchestrator Uses Them |
|--------|-----------|---------------------------|
| `VisionPlugin` | `look_around()`, `search_for_object(target)` | Camera capture → base64 → GPT-5.4 multimodal API. System prompts tuned for child-friendly 2-3 sentence descriptions. |
| `MovementPlugin` | `move_forward/backward(duration)`, `turn_left/right(duration)`, `strafe_left/right(duration)`, `stop()`, `nod_yes()`, `shake_head_no()`, `look_around_gesture()` | Durations clamped (0.5-3.0s). Forward movement checks ultrasonic first. |
| `SafetyPlugin` | `check_safety()`, `get_time_remaining()` | Combined obstacle + timer check. Returns human-readable status. |

### Step 6: Orchestrator Agent
- **`agents/prompts.py`** — Ringo's system prompt defines personality (enthusiastic, simple vocabulary, sound effects), treasure hunt flow (5 steps), available actions, safety rules, and conversation style examples. Also includes `TREASURE_HUNT_START_PROMPT` and `SESSION_END_PROMPT`.
- **`agents/orchestrator.py`** — Wires up SK `Kernel` with `AzureChatCompletion`, registers all three plugins, uses `FunctionChoiceBehavior.Auto` so the model can call any plugin function as needed. Maintains `ChatHistory` across the session. Key methods: `chat()`, `start_treasure_hunt()`, `end_session()`, `reset_history()`.

### Step 7: Main Entry Point
- **`main.py`** — `TreasureHuntApp` class ties everything together in an async loop:
  1. Initialize all hardware + services
  2. `lights.idle()` — dim white while waiting
  3. Wait for wake word "Ringo"
  4. `start_treasure_hunt()` → greeting via TTS
  5. Loop: `lights.listening()` → STT → `lights.thinking()` → orchestrator → `lights.speaking()` → TTS
  6. Exit conditions: goodbye phrase detected OR session timer expired
  7. `end_session()` → celebration lights + farewell
  8. Return to waiting for wake word

- Graceful shutdown via `SIGTERM`/`SIGINT` handlers that stop motors, reset servos, turn off lights.

### Step 8: Documentation
- **`README.md`** — Quick start guide, architecture diagram, safety features, project structure, Azure services table, future phases list.
- **`PROJECT_DECISIONS.md`** — Full decision log from the 10 questions asked.

### Step 9: Validation
- Ran `ast.parse()` on all 15 Python files — all passed syntax check.
- Verified file structure matches the planned layout (23 files total).

---

## Files Produced

```
Raspbotv2-TreasureHunt/           23 files
├── .env.example                   Azure credentials template
├── requirements.txt               11 dependencies
├── config.py                      Dataclass config from .env
├── main.py                        Entry point — wake → listen → think → speak loop
├── PROJECT_DECISIONS.md           10 design decisions
├── README.md                      Setup guide & architecture
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py            SK kernel + chat history + 3 plugins
│   └── prompts.py                 Ringo personality + hunt prompts
├── plugins/
│   ├── __init__.py
│   ├── vision.py                  2 SK functions (look, search)
│   ├── movement.py                10 SK functions (move, turn, gesture)
│   └── safety.py                  2 SK functions (check, timer)
├── hardware/
│   ├── __init__.py
│   ├── motor.py                   Speed-capped Mecanum + PTZ servos
│   ├── camera.py                  USB capture → base64 JPEG
│   ├── ultrasonic.py              Distance sensor with threshold
│   ├── lights.py                  Semantic LED states (thinking, listening...)
│   └── wake_word.py               Serial protocol wake-word detector
├── speech/
│   ├── __init__.py
│   ├── stt.py                     Azure STT (en-AU, microphone)
│   └── tts.py                     Azure TTS (SSML, child-friendly pace)
└── utils/
    └── __init__.py                Logger setup
```

---

## What's NOT in Phase 1 (deferred)

| Feature | Deferred To | Reason |
|---------|-------------|--------|
| Memory / persistence | Phase 2 | Needs Azure AI Search provisioned |
| Story generation | Phase 3 | Needs memory context to be meaningful |
| Planner agent (o3) | Phase 3+ | Simple orchestrator is sufficient for now |
| Advanced navigation / mapping | Phase 4 | Needs spatial awareness + testing |
| Learning / adaptation | Phase 5 | Needs accumulated memory data |
| OLED display stats | Separate task | Orthogonal to treasure hunt |
| Buzzer sounds | Future | Nice-to-have, not core |
