# 🤖 Ringo — Treasure Hunt Robot

A treasure hunt activity agent for the RaspbotV2, designed for Sienna (age 6).  
Ringo is a friendly robot that helps find hidden "treasures" around the house using voice, vision, and movement.

## How It Works

1. **Say "Ringo"** — the wake word activates the robot
2. **Ringo greets Sienna** and asks what treasure to find
3. **Sienna gives hints** — "Find my red teddy bear!" or "It's near the blue chair"
4. **Ringo explores** — moves around, uses camera + AI vision to search
5. **Celebrates** when the treasure is found! 🎉

## Quick Start (on Orange Pi 5 Pro)

```bash
# 1. Copy this folder to the Orange Pi
scp -r Raspbotv2-TreasureHunt/ orangepi@<ip>:~/

# 2. SSH into the Orange Pi
ssh orangepi@<ip>

# 3. Install dependencies
cd ~/Raspbotv2-TreasureHunt
pip install -r requirements.txt

# 4. Copy and fill in your Azure credentials
cp .env.example .env
nano .env  # Fill in your keys

# 5. Run!
python main.py
```

## Architecture

```
     "Ringo!" (wake word)
           │
    ┌──────▼───────┐
    │  Wake Word   │  Hardware serial module
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Azure STT   │  Listens to Sienna
    └──────┬───────┘
           │ text
    ┌──────▼───────────────────┐
    │  Semantic Kernel Agent   │
    │  (GPT-5.4-mini)          │
    │  ├── Vision Plugin       │  Camera + GPT-5.4
    │  ├── Movement Plugin     │  Motors (speed-limited)
    │  └── Safety Plugin       │  Obstacles + timer
    └──────┬───────────────────┘
           │ response
    ┌──────▼───────┐
    │  Azure TTS   │  Speaks to Sienna
    └──────────────┘
```

## Safety Features

- **Speed limited** to 30% (safe around children)
- **Ultrasonic obstacle detection** — stops at 15cm
- **15-minute session limit** — suggests breaks
- **Gentle language** — never scary or complex

## Project Structure

```
Raspbotv2-TreasureHunt/
├── main.py              # Entry point
├── config.py            # Environment/settings loader
├── .env.example         # Template for Azure keys
├── requirements.txt     # Python dependencies
├── agents/
│   ├── orchestrator.py  # Semantic Kernel orchestrator
│   └── prompts.py       # Ringo's personality prompts
├── plugins/
│   ├── vision.py        # Camera + GPT-5.4 scene understanding
│   ├── movement.py      # Motor actions as SK functions
│   └── safety.py        # Session timer + obstacle checks
├── hardware/
│   ├── motor.py         # Mecanum wheel controller
│   ├── camera.py        # USB camera capture
│   ├── ultrasonic.py    # Distance sensor
│   ├── lights.py        # RGB LED feedback
│   └── wake_word.py     # Serial wake-word listener
└── speech/
    ├── stt.py           # Azure Speech-to-Text
    └── tts.py           # Azure Text-to-Speech
```

## Azure Services Required

| Service | Purpose | Deployment Name |
|---------|---------|----------------|
| Azure OpenAI | Orchestrator agent | `gpt-5.4-mini` |
| Azure OpenAI | Vision understanding | `gpt-5.4` |
| Azure Speech | Speech-to-Text | — |
| Azure Speech | Text-to-Speech | — |

## Future Phases

- **Phase 2**: Memory Agent (Azure AI Search + embeddings) — remembers past adventures
- **Phase 3**: Story Agent — generates themed treasure hunt narratives
- **Phase 4**: Advanced navigation with spatial awareness
- **Phase 5**: Learning Agent — adapts to Sienna's interests and level

## License

Personal project — built with ❤️ for Sienna.
