# Raspbotv2 Treasure Hunt — Phase 2 Plan: Memory Agent

**Date:** 2026-07-09 (planned) → 2026-07-10 (implemented)  
**Status:** ✅ Complete  
**Depends on:** Phase 1 (complete)

---

## Goal

Give Ringo **persistent memory** so it remembers past adventures, Sienna's favourite things, and previous treasure hunts. This makes each session feel continuous rather than starting fresh — Ringo becomes a companion that *knows* Sienna.

---

## What Memory Enables

| Scenario | Without Memory (Phase 1) | With Memory (Phase 2) |
|----------|--------------------------|----------------------|
| Greeting | "Hi! What should we find?" | "Hi Sienna! Last time we found your blue dinosaur — that was fun! What's today's treasure?" |
| Hints | Treats every hunt as new | "You usually hide things near the couch — should I check there first?" |
| Favourites | No context | "I know you love unicorns — is it something sparkly?" |
| Difficulty | Always same | Remembers what was easy/hard and adapts |

---

## Architecture

```
                    Orchestrator Agent
                          │
                    Memory Plugin (new)
                    ┌─────┴──────┐
                    │            │
              Store Memory   Recall Memory
                    │            │
              ┌─────▼────┐  ┌───▼────────┐
              │ Embedding │  │ Vector     │
              │ Model     │  │ Search     │
              │ (text-    │  │ (Azure AI  │
              │ embedding-│  │ Search)    │
              │ 3-small)  │  │            │
              └───────────┘  └────────────┘
```

---

## Components to Build

### 1. Azure AI Search Index Setup

**Index name:** `ringo-memory`  
**Fields:**

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string (key) | Unique memory ID |
| `session_id` | string | Which play session |
| `timestamp` | DateTimeOffset | When it happened |
| `category` | string | `treasure_found`, `favourite`, `hint_pattern`, `story_moment`, `preference` |
| `content` | string | Human-readable description |
| `content_vector` | Collection(Single) | Embedding of content (1536 dims) |
| `importance` | int32 | 1-5 scale (5 = very important) |
| `tags` | Collection(string) | Searchable tags (e.g., `["toy", "red", "teddy"]`) |

**Script:** `scripts/setup_search_index.py` — creates the index with vector config.

---

### 2. Memory Plugin (`plugins/memory.py`)

Semantic Kernel plugin with these functions:

| Function | Description | When Called |
|----------|-------------|-------------|
| `remember(content, category, importance)` | Store a new memory | After finding treasure, learning a preference |
| `recall(query, top_k=3)` | Search memories relevant to current context | At session start, when hunting, when stuck |
| `recall_favourites()` | Get Sienna's known favourite things | At greeting time |
| `recall_recent_adventures(days=7)` | What happened in recent sessions | At session start for continuity |

---

### 3. Memory Manager (`agents/memory_manager.py`)

A helper class (not a full agent yet) that handles:

- **Auto-store triggers:** Automatically stores memories when:
  - Treasure is found → `treasure_found`
  - Sienna mentions a favourite thing → `favourite`
  - A hint pattern works (e.g., "near the couch") → `hint_pattern`
  - Session ends → `story_moment` (summary of the adventure)

- **Auto-recall triggers:** Automatically queries memory when:
  - Session starts → injects context into orchestrator prompt
  - Sienna says "remember when..." → explicit recall
  - Robot is stuck / hunting → recall similar past hunts

---

### 4. Embedding Service (`services/embedding.py`)

Thin wrapper around Azure OpenAI embedding model:

```python
class EmbeddingService:
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text using text-embedding-3-small."""
        ...
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed multiple texts."""
        ...
```

---

### 5. Updated Orchestrator Prompt

Extend `RINGO_SYSTEM_PROMPT` with memory context injection:

```
## What You Remember About Sienna
{injected_memories}

Use these memories naturally in conversation — reference past adventures,
mention her favourites, and build on what you know about her.
Don't repeat memories verbatim — weave them in naturally.
```

---

### 6. Updated Config

New `.env` variables:
```
AZURE_SEARCH_ENDPOINT=https://...
AZURE_SEARCH_KEY=...
AZURE_SEARCH_INDEX=ringo-memory
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

---

## Implementation Tasks

### Setup (one-time)
- [ ] Create `scripts/setup_search_index.py` — provisions the AI Search index
- [ ] Add `azure-search-documents` to `requirements.txt`
- [ ] Add new config fields to `config.py`

### Core Memory
- [ ] Create `services/embedding.py` — embedding wrapper
- [ ] Create `plugins/memory.py` — SK plugin with store/recall functions
- [ ] Create `agents/memory_manager.py` — auto-trigger logic

### Integration
- [ ] Update `agents/orchestrator.py` — inject memory context at session start
- [ ] Update `agents/prompts.py` — add memory section to system prompt
- [ ] Update `main.py` — wire in memory manager, store on session end

### Testing
- [ ] Test index creation script
- [ ] Test store/recall roundtrip
- [ ] Test memory injection into orchestrator conversation
- [ ] Verify memories persist across sessions

---

## New File Structure (additions in Phase 2)

```
Raspbotv2-TreasureHunt/
├── ...existing files...
├── services/
│   ├── __init__.py
│   └── embedding.py          # Azure OpenAI embedding wrapper
├── plugins/
│   ├── ...existing...
│   └── memory.py             # Memory store/recall SK plugin
├── agents/
│   ├── ...existing...
│   └── memory_manager.py     # Auto-trigger memory store/recall
└── scripts/
    └── setup_search_index.py # One-time index provisioning
```

---

## Memory Lifecycle Example

```
SESSION 1:
  Sienna: "Find my red teddy bear!"
  Ringo: *searches, finds it near the couch*
  → STORE: {category: "treasure_found", content: "Found Sienna's red teddy bear near the couch", tags: ["teddy", "red", "couch"]}
  → STORE: {category: "favourite", content: "Sienna has a red teddy bear she loves", tags: ["teddy", "red"]}

SESSION 2:
  → RECALL at start: "Last time we found your red teddy bear near the couch!"
  Sienna: "Find my blue dinosaur!"
  Ringo: "Ooh! Should I check near the couch? That's where we found treasures before!"
  → RECALL: hint_pattern about couch being a common hiding spot
```

---

## Estimated Effort

| Task | Time |
|------|------|
| Index setup script | 1 hour |
| Embedding service | 30 min |
| Memory plugin | 2 hours |
| Memory manager (auto-triggers) | 2 hours |
| Orchestrator integration | 1 hour |
| Testing & tuning | 2 hours |
| **Total** | **~8-9 hours** |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Azure AI Search cost | Use free tier (50MB, 3 indexes) — more than enough |
| Memory noise (storing too much) | Importance scoring + category filtering |
| Stale memories | Timestamp-weighted retrieval (recent = more relevant) |
| Child says random things | Only store memories from meaningful interactions (treasure found, explicit preferences) |
| Embedding latency | Batch embed at session end, not mid-conversation |

---

## Success Criteria

Phase 2 is complete when:
1. ✅ Ringo references a past adventure in its greeting
2. ✅ Ringo remembers Sienna's favourite items across sessions
3. ✅ Ringo suggests looking in places where treasures were found before
4. ✅ Memories persist across reboots (stored in Azure AI Search)
5. ✅ No noticeable latency added to the conversation loop
