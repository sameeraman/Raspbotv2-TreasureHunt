# Raspbotv2 Treasure Hunt — Project Decisions

**Date:** 2026-07-09  
**Target User:** Sienna (6 years old)  
**Hardware:** RaspbotV2 on Orange Pi 5 Pro (Linux 6.1.43, Python 3.11)

---

## Decision Log

### 1. Azure Services Setup
**Decision:** Set up code with `.env` placeholders — provision later.

All Azure endpoints and keys will be read from a `.env` file. Services needed:
- Azure OpenAI (GPT-5.4, GPT-5.4-mini, o3, text-embedding-3-small)
- Azure AI Search (for Memory Agent vector store — Phase 2)
- Azure Speech Services (STT/TTS)

---

### 2. Speech / Voice Approach
**Decision:** Hardware module for wake-word + Azure Speech for conversation STT/TTS.

- The onboard voice module detects the wake word **"Ringo"** via serial protocol.
- Once woken, the system uses the Orange Pi's microphone to record Sienna's speech.
- Azure Speech-to-Text transcribes her words.
- Azure Text-to-Speech generates Ringo's spoken responses.

---

### 3. Language
**Decision:** English only.

All prompts, responses, and TTS output will be in English, appropriate for a 6-year-old's vocabulary.

---

### 4. Implementation Scope (Phase 1)
**Decision:** Start simple — voice + vision + basic movement, then expand.

Phase 1 includes:
- Wake-word detection → voice conversation loop
- Camera vision (GPT-5.4 scene understanding)
- Basic Mecanum wheel movement
- Simple treasure hunt game flow

Future phases will add Memory Agent, full Story Agent, advanced navigation, etc.

---

### 5. Treasure Hunt Mechanism
**Decision:** Free-roaming indoors — no physical markers needed.

The robot relies on:
- Sienna's verbal hints ("it's near the blue chair")
- Camera + GPT-5.4 vision to identify objects and colours
- No ArUco/QR codes required

---

### 6. Safety Constraints
**Decision:** Low speed limits + max roam time.

- **Max motor speed:** 30% (≈75/255)
- **Ultrasonic obstacle stop distance:** 15 cm
- **Max session duration:** 15 minutes (then robot suggests a break)
- Parent-supervised play sessions

---

### 7. Treasure Items
**Decision:** Any toy/household object she describes.

The vision system uses GPT-5.4 to understand natural language descriptions (e.g., "find the red teddy", "look for my blue cup") rather than being limited to a fixed object list.

---

### 8. Robot Personality
**Decision:** "Ringo" — a helpful robot friend with a playful personality.

- Speaks in short, enthusiastic sentences suitable for a 6-year-old
- Uses simple vocabulary and encouraging tone
- Celebrates discoveries ("Yay! I think I found it!")
- Asks playful clarifying questions ("Hmm, is it something big or small?")

---

### 9. Max Session Duration
**Decision:** 15 minutes.

After 15 minutes, the robot says something like: "Wow, what an adventure! Let's take a break and play again later!"

---

### 10. Orchestration Framework
**Decision:** Semantic Kernel (Python SDK).

The agent orchestration will use Microsoft's Semantic Kernel Python SDK, which provides:
- Plugin/function calling
- Agent abstractions
- Azure OpenAI integration
- Extensibility for future agents

---

## Architecture Summary (Phase 1)

```
         Sienna speaks
              │
    ┌─────────▼──────────┐
    │  Wake Word Module   │  (Hardware serial — "Ringo")
    │  (mic_serial.py)    │
    └─────────┬──────────┘
              │ triggered
    ┌─────────▼──────────┐
    │  Azure Speech STT   │  (Records → transcribes)
    └─────────┬──────────┘
              │ text
    ┌─────────▼──────────┐
    │  Orchestrator Agent │  (GPT-5.4-mini via Semantic Kernel)
    │  ├─ Vision Plugin   │  (GPT-5.4 — camera frame analysis)
    │  ├─ Movement Plugin │  (Motor control — speed-limited)
    │  └─ Safety Plugin   │  (Obstacle check, speed cap, timer)
    └─────────┬──────────┘
              │ response text
    ┌─────────▼──────────┐
    │  Azure Speech TTS   │  (Speaks back to Sienna)
    └─────────────────────┘
```

---

## File Structure (Planned)

```
Raspbotv2-TreasureHunt/
├── PROJECT_DECISIONS.md
├── README.md
├── .env.example
├── requirements.txt
├── main.py                  # Entry point
├── config.py                # Settings & env loading
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py      # Main SK orchestrator agent
│   └── prompts.py           # System prompts for Ringo
├── plugins/
│   ├── __init__.py
│   ├── vision.py            # Camera + GPT-5.4 vision
│   ├── movement.py          # Motor control (speed-limited)
│   └── safety.py            # Obstacle detection, session timer
├── hardware/
│   ├── __init__.py
│   ├── wake_word.py         # Serial wake-word listener
│   ├── motor.py             # Mecanum wheel wrapper
│   ├── camera.py            # Camera capture
│   ├── ultrasonic.py        # Distance sensor
│   └── lights.py            # RGB LED control
├── speech/
│   ├── __init__.py
│   ├── stt.py               # Azure Speech-to-Text
│   └── tts.py               # Azure Text-to-Speech
└── utils/
    ├── __init__.py
    └── logger.py            # Logging utilities
```
