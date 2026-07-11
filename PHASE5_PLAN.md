# Raspbotv2 Treasure Hunt — Phase 5 Plan: Learning Agent

**Date:** 2026-07-10  
**Status:** Planning  
**Depends on:** Phase 2 (Memory), Phase 3 (Story)

---

## Goal

Give Ringo the ability to **learn and adapt** to Sienna over time — adjusting difficulty, tracking her developmental progress, learning her preferences without being told, and growing the experience as she grows. Ringo becomes a companion that *evolves with her*.

---

## What Learning Enables

| Dimension | Without Learning | With Learning |
|-----------|-----------------|---------------|
| Difficulty | Same every time | Gradually harder puzzles as she masters easier ones |
| Vocabulary | Fixed simple | Introduces new words as she demonstrates understanding |
| Hunt complexity | Single object | Multi-step hunts, riddle chains, counting challenges |
| Engagement | Generic fun | Knows what makes *her* laugh, what themes she picks most |
| Duration | Fixed 15 min | Adapts based on attention patterns (shorter if distracted) |
| Praise style | Generic "Yay!" | Knows she prefers "You're so smart!" vs "Great teamwork!" |

---

## Architecture

```
         Orchestrator Agent
               │
    ┌──────────┼─────────────┐
    │          │             │
 Learning   Memory       Story
 Plugin     Plugin       Plugin
    │          │             │
    ▼          ▼             ▼
 ┌──────────────────────────────┐
 │      Sienna's Profile        │
 │  (Azure AI Search + local)   │
 │                              │
 │  • Skill levels              │
 │  • Vocabulary tier           │
 │  • Favourite themes          │
 │  • Engagement patterns       │
 │  • Session history stats     │
 └──────────────────────────────┘
```

---

## Sienna's Profile Model

A structured representation of what Ringo has learned about Sienna:

```python
@dataclass
class SiennaProfile:
    # Skill Levels (0.0 to 1.0)
    colour_recognition: float = 0.5      # Can she identify colours?
    spatial_reasoning: float = 0.3       # Understands left/right/near/far?
    counting: float = 0.4               # Can count objects?
    riddle_solving: float = 0.3         # Gets simple riddles?
    vocabulary_tier: int = 1            # 1=basic, 2=intermediate, 3=advanced
    
    # Preferences (learned over time)
    favourite_themes: list[str] = field(default_factory=list)  # ["pirate", "space"]
    favourite_colours: list[str] = field(default_factory=list) # ["purple", "blue"]
    favourite_characters: list[str] = field(default_factory=list)
    preferred_praise_style: str = "enthusiastic"  # or "gentle", "silly"
    
    # Engagement Metrics
    avg_session_duration_min: float = 10.0
    avg_turns_per_session: int = 15
    attention_drop_off_min: float = 12.0  # When she typically loses interest
    sessions_completed: int = 0
    treasures_found: int = 0
    
    # Difficulty Progression
    current_difficulty: int = 1          # 1-5 scale
    consecutive_successes: int = 0       # Bump difficulty after 3
    consecutive_struggles: int = 0       # Lower difficulty after 2
```

---

## Components to Build

### 1. Profile Manager (`agents/profile_manager.py`)

Manages Sienna's profile — loads, updates, and persists:

| Method | Description |
|--------|-------------|
| `load_profile()` | Load from local JSON + Azure AI Search |
| `save_profile()` | Persist updated profile |
| `update_skill(skill, outcome)` | Adjust skill level based on success/failure |
| `record_preference(category, value)` | Learn a new preference |
| `record_session_stats(duration, turns, found)` | Update engagement metrics |
| `get_difficulty_recommendation()` | Suggest difficulty for next interaction |

### 2. Difficulty Adapter (`agents/difficulty_adapter.py`)

Adjusts the treasure hunt complexity based on profile:

| Difficulty | Riddles | Clues Given | Hunt Steps | Vocabulary |
|-----------|---------|-------------|------------|-----------|
| 1 (Beginner) | None | Direct ("It's on the couch") | 1 object | Very simple |
| 2 (Easy) | Optional simple | Descriptive ("It's near something soft") | 1-2 objects | Simple |
| 3 (Medium) | Simple riddles | Indirect ("Where do we sit to watch TV?") | 2-3 steps | Introduces new words |
| 4 (Hard) | Multi-line riddles | Abstract ("Something warm and cosy") | 3-4 steps | Richer vocabulary |
| 5 (Expert) | Chains of riddles | Cryptic ("The treasure is where stories live") | Multi-room quest | Age-advanced |

Progression rules:
- 3 consecutive successes → difficulty + 1
- 2 consecutive struggles → difficulty - 1
- Never go below 1 or above current_age_appropriate_max

### 3. Engagement Monitor (`agents/engagement_monitor.py`)

Detects Sienna's engagement level during a session:

```python
class EngagementMonitor:
    def assess(self, response_time: float, response_length: int, 
               content: str) -> EngagementLevel:
        """Assess engagement from response patterns.
        
        Signals of low engagement:
        - Long pauses before responding
        - Very short responses ("yeah", "ok", "dunno")
        - Off-topic responses
        - Repeated "I don't know"
        
        Signals of high engagement:
        - Quick responses
        - Detailed descriptions
        - Asking questions back
        - Excitement words ("wow!", "cool!", "let's go!")
        """
        ...
```

When engagement drops, Ringo can:
- Switch to a more exciting activity
- Offer a simpler challenge
- Suggest a break
- Change the story theme

### 4. Vocabulary Tracker (`agents/vocabulary_tracker.py`)

Tracks words Sienna uses and understands:

```python
class VocabularyTracker:
    def record_word_used(self, word: str):
        """Sienna used this word — she probably knows it."""
        ...
    
    def record_word_understood(self, word: str):
        """Sienna responded correctly to this word."""
        ...
    
    def suggest_new_word(self) -> str | None:
        """Suggest a word slightly above her current level to introduce."""
        ...
    
    def get_vocabulary_tier(self) -> int:
        """Assess overall vocabulary level (1-3)."""
        ...
```

### 5. Learning Plugin (`plugins/learning.py`)

Semantic Kernel plugin:

| Function | Description |
|----------|-------------|
| `get_difficulty_settings()` | Returns current difficulty parameters for the orchestrator |
| `assess_response(sienna_text, expected_skill)` | Evaluate if she got it right/wrong |
| `suggest_vocabulary_word()` | Get a word to teach during this session |
| `get_engagement_status()` | Current engagement assessment |
| `get_session_adaptation()` | Recommendations for current session (simpler/harder/change topic) |

### 6. Parent Dashboard (optional, stretch goal)

A simple local web page showing:
- Sienna's skill levels over time
- Session history
- Favourite themes
- Vocabulary growth
- Suggestions for parents

---

## Implementation Tasks

### Profile System
- [ ] Create `agents/profile_manager.py` — profile CRUD with JSON + Azure Search persistence
- [ ] Create `data/default_profile.json` — initial profile for Sienna
- [ ] Create skill level update algorithm (Elo-like scoring)
- [ ] Add profile fields to Azure AI Search index (or separate local JSON)

### Difficulty & Adaptation
- [ ] Create `agents/difficulty_adapter.py` — 5-level difficulty system
- [ ] Define difficulty parameters (riddle complexity, clue directness, vocab tier)
- [ ] Implement progression rules (3 successes up, 2 struggles down)
- [ ] Create `agents/engagement_monitor.py` — response pattern analysis

### Vocabulary
- [ ] Create `agents/vocabulary_tracker.py` — word frequency tracking
- [ ] Create `data/vocabulary_tiers.json` — age-appropriate word lists (tier 1-3)
- [ ] Implement word introduction strategy (1 new word per session max)

### Learning Plugin
- [ ] Create `plugins/learning.py` — SK plugin with 5 functions
- [ ] Wire into orchestrator — inject difficulty settings into prompt
- [ ] Post-session profile update logic

### Integration
- [ ] Update `agents/orchestrator.py` — use difficulty/engagement in decision-making
- [ ] Update `agents/prompts.py` — add adaptive sections
- [ ] Update `main.py` — load profile at start, save at end
- [ ] Connect to Story Plugin (Phase 3) — theme selection influenced by favourites
- [ ] Connect to Memory Plugin (Phase 2) — skill observations stored as memories

### Testing
- [ ] Test difficulty progression over simulated 10 sessions
- [ ] Test engagement detection accuracy
- [ ] Test vocabulary tier assignment
- [ ] Verify profile persists correctly across reboots
- [ ] Playtest with age-appropriate difficulty calibration

---

## New File Structure (additions in Phase 5)

```
Raspbotv2-TreasureHunt/
├── ...existing files...
├── agents/
│   ├── ...existing...
│   ├── profile_manager.py       # Sienna's profile CRUD
│   ├── difficulty_adapter.py    # 5-level difficulty system
│   ├── engagement_monitor.py    # Real-time engagement detection
│   └── vocabulary_tracker.py    # Word learning tracker
├── plugins/
│   ├── ...existing...
│   └── learning.py             # Adaptive learning SK plugin
└── data/
    ├── default_profile.json     # Initial profile template
    └── vocabulary_tiers.json    # Age-appropriate word lists
```

---

## Adaptation Examples

### Difficulty Progression Over Time

```
Session 1 (Difficulty 1):
  Ringo: "Find your red teddy! It's on the couch!"
  Sienna finds it quickly → SUCCESS
  
Session 4 (Difficulty 2):
  Ringo: "Find something soft and purple! It's near where you sleep."
  Sienna: "My bedroom!" → SUCCESS
  
Session 10 (Difficulty 3):
  Ringo: "Here's a riddle! I'm round and bouncy, I love to play,
          I live outside — where's my hiding bay?"
  Sienna: "My ball in the garden!" → SUCCESS
  
Session 20 (Difficulty 4):
  Ringo: "Captain Sparkle left 3 clues! First: find something that 
          tells time. Second: look behind it. Third: what colour 
          is the treasure?"
  Multi-step challenge → PARTIAL SUCCESS → stays at Difficulty 4
```

### Engagement Adaptation

```
[High engagement detected]
Sienna: "Ooh let's go! I think it's in the kitchen! Can you go fast?"
Ringo: Maintains current difficulty, adds bonus challenges

[Low engagement detected]  
Sienna: "ok" ... *long pause* ... "I dunno"
Ringo: "Hey, want to do something different? I could show you a magic 
        light show! Or we could find something super easy and fun?"
→ Drops difficulty, switches activity, or suggests break
```

### Vocabulary Teaching

```
[Sienna's level: Tier 1]
Ringo introduces: "magnificent" (replaces "really really good")

Ringo: "You found it! That was MAGNIFICENT! Can you say 'magnificent'? 
        It means super duper amazing!"
Sienna: "Mag-nif-i-cent!"
Ringo: "YES! You're magnificent! 🌟"

→ Stores: vocabulary_tracker.record_word_used("magnificent")
→ Next session: uses "magnificent" naturally to reinforce
```

---

## Estimated Effort

| Task | Time |
|------|------|
| Profile manager & data model | 3 hours |
| Difficulty adapter (5 levels) | 3 hours |
| Engagement monitor | 3 hours |
| Vocabulary tracker + word lists | 3 hours |
| Learning plugin | 2 hours |
| Orchestrator integration | 2 hours |
| Testing & calibration | 5 hours |
| Parent dashboard (stretch) | 4 hours |
| **Total** | **~25 hours** (21 without dashboard) |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Mis-calibrated difficulty | Start low, be conservative with increases; always offer "easier" option |
| Over-teaching feels annoying | Max 1 new word per session; vocabulary is optional/organic |
| Engagement detection false positives | Require 3+ signals before adapting; never abruptly change mid-story |
| Profile data loss | Dual storage (local JSON + Azure); backup on each session end |
| Growth too slow / too fast | Configurable progression rates in settings; parent can override |
| Child develops faster than model predicts | Regular profile review; model catches up within 2-3 sessions |

---

## Privacy Considerations

- All data about Sienna is stored **locally** (on the Orange Pi) + optionally in the family's own Azure tenant
- No data is shared with third parties
- Parent has full access to view/edit/delete the profile
- System is transparent: "Ringo remembers you like purple because you told me!"

---

## Success Criteria

Phase 5 is complete when:
1. ✅ Difficulty increases after consistent successes
2. ✅ Difficulty decreases when Sienna struggles
3. ✅ Ringo introduces 1 new vocabulary word per session naturally
4. ✅ Engagement drop triggers adaptation (simpler task or break suggestion)
5. ✅ Favourite themes influence story selection (without being asked)
6. ✅ Profile persists across sessions and reboots
7. ✅ Parent can view progress (at minimum via profile JSON)
