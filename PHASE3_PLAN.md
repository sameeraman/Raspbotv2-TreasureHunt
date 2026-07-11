# Raspbotv2 Treasure Hunt — Phase 3 Plan: Story Agent

**Date:** 2026-07-10  
**Status:** Planning  
**Depends on:** Phase 2 (Memory Agent)

---

## Goal

Give Ringo the ability to **generate and narrate themed treasure hunt adventures** — turning each session into a mini story with characters, missions, and a narrative arc. Instead of just "find the teddy", Ringo says *"Captain Sparkle the mermaid lost her treasure map! We need to find the pieces before the silly octopus gets them!"*

---

## Why This Matters for a 6-Year-Old

- Stories create **engagement** — Sienna isn't just finding objects, she's on a quest
- Narrative structure gives **natural pacing** — beginning, middle, end
- Characters create **emotional investment** — she's helping someone
- Themes can be **rotated** so it never feels repetitive
- The Memory Agent (Phase 2) feeds in past favourites to personalise stories

---

## Architecture

```
         Orchestrator Agent
               │
         ┌─────┴──────┐
         │             │
   Story Plugin    Memory Plugin (Phase 2)
         │             │
    ┌────┴────┐    ┌───┴───┐
    │         │    │       │
 Generate  Progress  Recall favourites
 Story     Tracker   & past stories
    │         │
 o3   Session
 (creative  State
  planning)
```

---

## Story Structure

Each treasure hunt session follows a 3-act structure:

### Act 1: The Hook (Session Start)
- Ringo introduces a character who needs help
- A theme is established (pirate, space, fairy tale, jungle, etc.)
- The "treasure" is framed within the story context

### Act 2: The Quest (Main Play Loop)  
- Each movement/discovery is narrated as part of the adventure
- Mini-challenges or riddles between locations
- Encouragement framed as story progress ("The map says we're getting closer!")

### Act 3: The Celebration (Treasure Found / Session End)
- Finding the treasure resolves the story
- The character thanks Sienna
- A teaser for next time ("I wonder what adventure awaits tomorrow...")

---

## Components to Build

### 1. Story Plugin (`plugins/story.py`)

Semantic Kernel plugin with these functions:

| Function | Description | When Called |
|----------|-------------|-------------|
| `generate_adventure(target_object, favourites)` | Creates a themed story arc for this session | At session start, after Sienna names the treasure |
| `narrate_progress(event, story_context)` | Generates story-appropriate narration for events | During exploration (found clue, hit obstacle, etc.) |
| `generate_riddle(hint)` | Creates a simple riddle/clue appropriate for age 6 | When giving directional hints |
| `celebrate_discovery(object_found, story_context)` | Story-appropriate celebration | When treasure is found |
| `generate_farewell(story_summary)` | Wrap up the story with a teaser | At session end |

### 2. Story Themes Library (`agents/story_themes.py`)

Pre-defined theme templates that o3 can build on:

```python
THEMES = [
    {
        "name": "Pirate Adventure",
        "character": "Captain Sparkle",
        "setting": "a magical pirate ship",
        "quest_verb": "find the lost treasure",
        "villain": "the silly octopus",
        "reward": "a chest of golden stars",
    },
    {
        "name": "Space Explorer",
        "character": "Astro the friendly alien",
        "setting": "a sparkly spaceship",
        "quest_verb": "collect the missing moon crystals",
        "villain": "the grumpy space cloud",
        "reward": "a ride through the rainbow nebula",
    },
    # ... 8-10 themes total
]
```

Themes rotate and are influenced by Memory Agent recall of Sienna's favourites.

### 3. Story State Tracker (`agents/story_state.py`)

Tracks narrative progress within a session:

```python
@dataclass
class StoryState:
    theme: dict                    # Active theme
    act: int                       # 1, 2, or 3
    clues_given: int              # How many hints/clues so far
    discoveries: list[str]        # What's been found/seen
    character_name: str           # The story character
    target_object: str            # What Sienna is looking for
    narrative_summary: str        # Running summary for context
```

### 4. Updated Orchestrator Integration

The orchestrator prompt gets a `## Current Story` section injected:

```
## Current Story
Theme: Pirate Adventure
Character: Captain Sparkle needs your help!
Quest: Find the lost treasure map (Sienna's red teddy bear)
Progress: Act 2 — We've found 1 clue so far
Story so far: Captain Sparkle told us the treasure is somewhere warm and cosy...

When responding, stay in character with the story. Frame movements and 
discoveries as part of the adventure.
```

### 5. Riddle Generator Prompt

Simple riddles appropriate for a 6-year-old:

```
Generate a simple riddle for a 6-year-old. The answer relates to: {hint}.
Rules:
- Maximum 2 lines
- Use rhyming if possible
- Must be solvable by a 6-year-old
- Be playful and fun
Example: "I'm soft and red, I sit on your bed. What am I?" (teddy bear)
```

---

## Implementation Tasks

### Story Engine
- [ ] Create `agents/story_themes.py` — 10 pre-defined story themes
- [ ] Create `agents/story_state.py` — session narrative state tracker
- [ ] Create `plugins/story.py` — SK plugin with 5 functions (uses o3 for generation)

### Integration
- [ ] Update `agents/orchestrator.py` — inject story context into system prompt
- [ ] Update `agents/prompts.py` — add story-mode prompt template
- [ ] Update `main.py` — trigger story generation after Sienna names the treasure
- [ ] Wire Memory Plugin recall → Story Plugin (favourite themes, past characters)

### Memory Hooks (requires Phase 2)
- [ ] Store completed story summaries as memories (`category: "story_moment"`)
- [ ] Recall past themes to avoid repetition
- [ ] Recall favourite characters to bring them back in future sessions

### Testing
- [ ] Test story generation with various target objects
- [ ] Test riddle quality for age-appropriateness
- [ ] Test narrative flow across a full session (acts 1→2→3)
- [ ] Verify story context doesn't bloat the orchestrator token usage

---

## New File Structure (additions in Phase 3)

```
Raspbotv2-TreasureHunt/
├── ...existing files...
├── agents/
│   ├── ...existing...
│   ├── story_themes.py        # Pre-defined adventure themes
│   └── story_state.py         # Narrative progress tracker
└── plugins/
    ├── ...existing...
    └── story.py               # Story generation SK plugin (uses o3)
```

---

## Example Session Flow

```
[Act 1 — The Hook]
Sienna: "Find my purple unicorn!"
Ringo: "Ooh! Captain Sparkle just sent me a message — she says a magical 
        purple unicorn escaped from Rainbow Castle! It's hiding somewhere 
        in your house. Let's be unicorn rescuers! 🦄 Do you know which 
        room it might be in?"

[Act 2 — The Quest]
Sienna: "Maybe the living room?"
Ringo: "Great idea! Captain Sparkle says unicorns love cosy places. 
        Let me zoom to the living room! Vroom!" *moves forward*
Ringo: "Hmm, I see the couch and some cushions... Here's a riddle from 
        Captain Sparkle: 'I'm soft and tall, I lean on the wall. 
        Look behind me!' Should I check behind the cushions?"

[Act 3 — Celebration]
Ringo: "WAIT! I see something purple! Is that your unicorn?! 
        YAY! We rescued the unicorn! Captain Sparkle is SO happy — 
        she says you're the best unicorn rescuer ever! 🎉 
        Next time, maybe we'll help Astro the alien find his lost stars!"
```

---

## Model Usage

| Component | Model | Reason |
|-----------|-------|--------|
| Story arc generation | o3 | Creative planning, structured output |
| In-session narration | GPT-5.4-mini (orchestrator) | Fast, stays in conversation flow |
| Riddle generation | GPT-5.4-mini | Simple, low-latency |

---

## Estimated Effort

| Task | Time |
|------|------|
| Story themes library | 1 hour |
| Story state tracker | 1 hour |
| Story plugin (o3) | 3 hours |
| Orchestrator integration | 2 hours |
| Memory hooks | 1 hour |
| Testing & tuning prompts | 3 hours |
| **Total** | **~11 hours** |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Stories too complex for age 6 | Strict prompt constraints (2-sentence max, simple words) |
| o3 latency for story generation | Generate full arc at start, narrate in-line with fast model |
| Token bloat from story context | Keep injected context under 200 tokens |
| Repetitive themes | Rotate themes + memory of past themes used |
| Scary story elements | Explicit prompt rule: "Never include anything scary, sad, or negative" |

---

## Success Criteria

Phase 3 is complete when:
1. ✅ Each session has a unique themed story arc
2. ✅ Ringo narrates discoveries as part of the story
3. ✅ Simple riddles/clues are age-appropriate and fun
4. ✅ Story celebrates the discovery with narrative closure
5. ✅ Past stories are remembered and not repeated
6. ✅ Sienna's favourites influence theme selection
