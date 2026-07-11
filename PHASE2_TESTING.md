# Phase 2 Testing Guide — Memory Agent

This guide covers testing the Memory Agent (Azure AI Search + embeddings). Phase 2 builds on Phase 1, so complete the Phase 1 tests first.

---

## Prerequisites

### Additional Azure Services (beyond Phase 1)

| Service | What to Provision | Notes |
|---------|-------------------|-------|
| Azure AI Search | Search service (Free tier is fine) | Free tier: 50MB, 3 indexes |
| Azure OpenAI | `text-embedding-3-small` deployment | Same OpenAI resource as Phase 1 |

### Update `.env`

Add these to your existing `.env`:

```env
# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your-admin-key-here
AZURE_SEARCH_INDEX=ringo-memory

# Azure OpenAI Embedding
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### Install Updated Dependencies

```bash
cd Raspbotv2-TreasureHunt
pip install -r requirements.txt
```

This adds `azure-search-documents>=11.6.0`.

---

## Test 1: Create the Search Index

**What it tests:** The `setup_search_index.py` script creates the `ringo-memory` index with the correct fields and vector config.

```bash
python scripts/setup_search_index.py
```

**Expected output:**
```
✅ Index 'ringo-memory' created/updated successfully!
   Endpoint: https://your-search-service.search.windows.net
   Fields: 8
   Vector dimensions: 1536 (text-embedding-3-small)
```

**Verify in Azure Portal:**
1. Go to your Azure AI Search resource → Indexes
2. You should see `ringo-memory` with 8 fields
3. Click into it — verify `content_vector` has 1536 dimensions

---

## Test 2: Embedding Service

**What it tests:** The embedding wrapper generates 1536-dim vectors from text.

```bash
python -c "
import asyncio
from config import load_config
from services.embedding import EmbeddingService

cfg = load_config()
emb = EmbeddingService(
    endpoint=cfg.azure_openai.endpoint,
    api_key=cfg.azure_openai.api_key,
    deployment=cfg.azure_openai.embedding_deployment,
    api_version=cfg.azure_openai.api_version,
)

async def test():
    # Single embedding
    vec = await emb.embed('Sienna loves her red teddy bear')
    print(f'✅ Single embedding: {len(vec)} dimensions')
    print(f'   First 5 values: {vec[:5]}')

    # Batch embedding
    texts = ['red teddy bear', 'blue dinosaur', 'purple unicorn']
    vecs = await emb.embed_batch(texts)
    print(f'✅ Batch embedding: {len(vecs)} vectors, each {len(vecs[0])} dims')

asyncio.run(test())
"
```

**Expected output:**
```
✅ Single embedding: 1536 dimensions
   First 5 values: [0.012..., -0.034..., ...]
✅ Batch embedding: 3 vectors, each 1536 dims
```

---

## Test 3: Memory Plugin — Store and Recall

**What it tests:** Full roundtrip: store a memory → recall it via vector search.

```bash
python -c "
import asyncio
from config import load_config
from services.embedding import EmbeddingService
from plugins.memory import MemoryPlugin

cfg = load_config()
emb = EmbeddingService(
    endpoint=cfg.azure_openai.endpoint,
    api_key=cfg.azure_openai.api_key,
    deployment=cfg.azure_openai.embedding_deployment,
    api_version=cfg.azure_openai.api_version,
)
mem = MemoryPlugin(
    search_endpoint=cfg.azure_search.endpoint,
    search_key=cfg.azure_search.key,
    index_name=cfg.azure_search.index_name,
    embedding_service=emb,
)
mem.set_session_id('test-001')

async def test():
    # Store memories
    print('--- Storing memories ---')
    r1 = await mem.remember(
        content='Found Sienna red teddy bear near the couch in the living room',
        category='treasure_found',
        importance=4,
        tags='teddy,red,couch,living room',
    )
    print(f'  {r1}')

    r2 = await mem.remember(
        content='Sienna loves unicorns and the colour purple',
        category='favourite',
        importance=5,
        tags='unicorn,purple',
    )
    print(f'  {r2}')

    r3 = await mem.remember(
        content='Sienna often hides things behind the cushions on the couch',
        category='hint_pattern',
        importance=3,
        tags='couch,cushions,hiding spot',
    )
    print(f'  {r3}')

    # Wait a moment for indexing
    import time
    print('  Waiting 3s for index to update...')
    time.sleep(3)

    # Recall via vector search
    print()
    print('--- Recalling memories ---')
    result = await mem.recall('where did we find treasures before?')
    print(f'  {result}')
    print()

    result = await mem.recall('what does Sienna like?')
    print(f'  {result}')
    print()

    # Test favourites
    print('--- Favourites ---')
    favs = await mem.recall_favourites()
    print(f'  {favs}')
    print()

    # Test recent adventures
    print('--- Recent Adventures ---')
    recent = await mem.recall_recent_adventures()
    print(f'  {recent}')

    print()
    print('✅ Memory store/recall roundtrip works!')

asyncio.run(test())
"
```

**What to check:**
- All 3 memories store without error
- `recall('where did we find treasures before?')` returns the teddy bear memory
- `recall('what does Sienna like?')` returns the unicorn/purple memory
- `recall_favourites()` returns the favourite
- `recall_recent_adventures()` returns the treasure_found memory

---

## Test 4: Memory Manager — Auto-Detection

**What it tests:** The MemoryManager automatically detects favourites, treasure finds, and hint patterns from conversation text.

```bash
python -c "
import asyncio
from config import load_config
from services.embedding import EmbeddingService
from plugins.memory import MemoryPlugin
from agents.memory_manager import MemoryManager

cfg = load_config()
emb = EmbeddingService(
    endpoint=cfg.azure_openai.endpoint,
    api_key=cfg.azure_openai.api_key,
    deployment=cfg.azure_openai.embedding_deployment,
    api_version=cfg.azure_openai.api_version,
)
mem = MemoryPlugin(
    search_endpoint=cfg.azure_search.endpoint,
    search_key=cfg.azure_search.key,
    index_name=cfg.azure_search.index_name,
    embedding_service=emb,
)
mgr = MemoryManager(mem)
mgr.start_session()
mgr.set_target('blue dinosaur')

async def test():
    print('--- Simulating conversation exchanges ---')
    print()

    # Exchange 1: Sienna mentions a favourite
    print('Exchange 1: Favourite detection')
    await mgr.observe_exchange(
        user_text='I love playing with my spaceship toys!',
        assistant_text='Ooh spaceships are so cool! Beep boop!'
    )
    print('  (should auto-store favourite: spaceship toys)')
    print()

    # Exchange 2: A location hint
    print('Exchange 2: Hint pattern detection')
    await mgr.observe_exchange(
        user_text='Maybe try looking near the bookshelf?',
        assistant_text='Great idea! Let me check near the bookshelf!'
    )
    print('  (should auto-store hint pattern: near the bookshelf)')
    print()

    # Exchange 3: Treasure found
    print('Exchange 3: Treasure found detection')
    await mgr.observe_exchange(
        user_text='Yes! You found it! That is my dinosaur!',
        assistant_text='YAY! I found the blue dinosaur! What an adventure!'
    )
    print('  (should auto-store treasure_found: blue dinosaur)')
    print()

    # End session — store summary
    print('--- Ending session ---')
    await mgr.end_session_summary()
    print('  (should store session summary as story_moment)')
    print()

    # Verify memories were stored
    import time
    print('Waiting 3s for index...')
    time.sleep(3)

    print()
    print('--- Verifying stored memories ---')
    result = await mem.recall('spaceship toys')
    print(f'Spaceship search: {result}')
    print()

    result = await mem.recall_recent_adventures()
    print(f'Recent adventures: {result}')

    print()
    print('✅ Memory manager auto-detection works!')

asyncio.run(test())
"
```

**What to check:**
- "I love playing with my spaceship toys" → auto-stores a `favourite`
- "near the bookshelf" → auto-stores a `hint_pattern`
- "You found it!" with target="blue dinosaur" → auto-stores `treasure_found`
- `end_session_summary()` → stores a `story_moment`

---

## Test 5: Memory Context Injection at Session Start

**What it tests:** Memory context is retrieved and injected into the orchestrator's system prompt for personalised greetings.

```bash
python -c "
import asyncio
from config import load_config
from services.embedding import EmbeddingService
from plugins.memory import MemoryPlugin
from agents.memory_manager import MemoryManager

cfg = load_config()
emb = EmbeddingService(
    endpoint=cfg.azure_openai.endpoint,
    api_key=cfg.azure_openai.api_key,
    deployment=cfg.azure_openai.embedding_deployment,
    api_version=cfg.azure_openai.api_version,
)
mem = MemoryPlugin(
    search_endpoint=cfg.azure_search.endpoint,
    search_key=cfg.azure_search.key,
    index_name=cfg.azure_search.index_name,
    embedding_service=emb,
)
mgr = MemoryManager(mem)

async def test():
    context = await mgr.get_greeting_context()
    if context:
        print('✅ Memory context retrieved for greeting:')
        print('─' * 40)
        print(context)
        print('─' * 40)
        print()
        print('This context gets injected into Ringo system prompt')
        print('so the greeting references past adventures.')
    else:
        print('ℹ️  No memory context yet (expected if this is the first run)')
        print('   Run Test 3 or Test 4 first to populate memories.')

asyncio.run(test())
"
```

---

## Test 6: Orchestrator with Memory — Full Chat

**What it tests:** The orchestrator uses memory context in its greeting and has access to memory functions during conversation.

> **Requires:** Memories populated from Tests 3 or 4.

```bash
python -c "
import asyncio
from config import load_config
from hardware.camera import Camera
from hardware.motor import MotorController
from hardware.ultrasonic import UltrasonicSensor
from services.embedding import EmbeddingService
from plugins.vision import VisionPlugin
from plugins.movement import MovementPlugin
from plugins.safety import SafetyPlugin
from plugins.memory import MemoryPlugin
from agents.orchestrator import RingoOrchestrator
from agents.memory_manager import MemoryManager

cfg = load_config()
cam = Camera(); cam.open()
motor = MotorController(max_speed=cfg.safety.max_motor_speed)
ultra = UltrasonicSensor()

emb = EmbeddingService(
    endpoint=cfg.azure_openai.endpoint,
    api_key=cfg.azure_openai.api_key,
    deployment=cfg.azure_openai.embedding_deployment,
    api_version=cfg.azure_openai.api_version,
)
vp = VisionPlugin(cam, cfg.azure_openai.endpoint, cfg.azure_openai.api_key,
                   cfg.azure_openai.vision_deployment, cfg.azure_openai.api_version)
mp = MovementPlugin(motor, ultra)
sp = SafetyPlugin(ultra, cfg.safety.max_session_minutes)
mem_plugin = MemoryPlugin(
    search_endpoint=cfg.azure_search.endpoint,
    search_key=cfg.azure_search.key,
    index_name=cfg.azure_search.index_name,
    embedding_service=emb,
)
mgr = MemoryManager(mem_plugin)

async def test():
    # Get memory context for greeting
    mgr.start_session()
    memory_context = await mgr.get_greeting_context()
    print(f'Memory context: {repr(memory_context[:100])}...' if memory_context else 'No memory context')
    print()

    # Create orchestrator with memory
    orch = RingoOrchestrator(
        openai_config=cfg.azure_openai,
        vision_plugin=vp,
        movement_plugin=mp,
        safety_plugin=sp,
        memory_plugin=mem_plugin,
    )

    # Start treasure hunt with memory context
    print('--- Treasure Hunt with Memory ---')
    greeting = await orch.start_treasure_hunt(memory_context=memory_context)
    print(f'Ringo: {greeting}')
    print()

    # Chat — Ringo can recall memories
    response = await orch.chat('Do you remember what I like?')
    print(f'Ringo: {response}')
    print()

    response = await orch.chat('Find my purple unicorn!')
    print(f'Ringo: {response}')
    print()

    print('✅ Orchestrator with memory works!')

asyncio.run(test())
cam.close()
"
```

**What to check:**
- Greeting should reference past adventures (if memories exist)
- "Do you remember what I like?" should trigger a memory recall
- Responses remain child-friendly

---

## Test 7: Graceful Degradation (No Azure Search)

**What it tests:** When `AZURE_SEARCH_ENDPOINT` is empty, the system runs in Phase 1 mode without crashing.

```bash
# Temporarily clear search config
AZURE_SEARCH_ENDPOINT="" AZURE_SEARCH_KEY="" python -c "
from config import load_config
cfg = load_config()
print(f'Search endpoint: \"{cfg.azure_search.endpoint}\"')
print(f'Search key: \"{cfg.azure_search.key}\"')

# Simulate what main.py does
if cfg.azure_search.endpoint and cfg.azure_search.key:
    print('Memory system: ENABLED')
else:
    print('Memory system: DISABLED (no search config)')
    print('✅ Graceful degradation — runs in Phase 1 mode')
"
```

**Expected output:**
```
Search endpoint: ""
Search key: ""
Memory system: DISABLED (no search config)
✅ Graceful degradation — runs in Phase 1 mode
```

---

## Test 8: Full End-to-End with Memory (Orange Pi)

**What it tests:** Multiple sessions showing memory persistence.

### Session 1 — Build Memories

```bash
python main.py
```

1. Say **"Ringo"** to wake
2. Say **"Find my red teddy bear"**
3. Say **"I love unicorns!"** (auto-stores favourite)
4. Say **"It's near the couch"** (auto-stores hint pattern)
5. Say **"You found it!"** (auto-stores treasure_found)
6. Say **"Goodbye"** (stores session summary)

### Session 2 — Verify Memory Recall

```bash
python main.py
```

1. Say **"Ringo"** to wake
2. **Listen to the greeting** — it should reference the red teddy bear or the couch from Session 1
3. Say **"What do you remember?"** — Ringo should recall past adventures
4. Say **"Goodbye"**

**What to check:**
- ✅ Session 2 greeting mentions Session 1 adventures
- ✅ Ringo naturally references past discoveries
- ✅ No errors in the logs about memory operations

---

## Test 9: Verify Index Contents (Azure Portal)

After running tests, verify the stored data:

1. Go to Azure Portal → your AI Search resource
2. Click **Indexes** → `ringo-memory`
3. Click **Search explorer**
4. Run query: `*` (returns all documents)
5. Verify you see documents with:
   - Various `category` values (`treasure_found`, `favourite`, `hint_pattern`, `story_moment`)
   - `content` fields with human-readable text
   - `tags` arrays
   - `importance` scores
   - `session_id` values
   - `timestamp` values

---

## Cleanup — Reset Memory Index

If you want to start fresh (delete all memories):

```bash
python -c "
from config import load_config
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

cfg = load_config()
client = SearchClient(
    endpoint=cfg.azure_search.endpoint,
    index_name=cfg.azure_search.index_name,
    credential=AzureKeyCredential(cfg.azure_search.key),
)

# Get all document IDs
results = client.search(search_text='*', select=['id'], top=1000)
ids = [{'id': r['id']} for r in results]

if ids:
    client.delete_documents(documents=ids)
    print(f'🗑️  Deleted {len(ids)} memories')
else:
    print('Index is already empty')
"
```

Or recreate the entire index:

```bash
python scripts/setup_search_index.py
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `setup_search_index.py` fails | Bad search endpoint/key | Verify `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_KEY` |
| Embedding returns error | `text-embedding-3-small` not deployed | Deploy the model in Azure OpenAI Studio |
| Recall returns "I don't remember" | Index not yet updated | Wait 2-3 seconds after storing; AI Search indexing is near-real-time but not instant |
| Recall returns wrong memories | Too few memories stored | Store more diverse memories; vector search improves with volume |
| `Memory system disabled` log | Search env vars empty | Fill in `AZURE_SEARCH_*` in `.env` |
| `azure.core.exceptions.ResourceNotFoundError` | Index doesn't exist | Run `python scripts/setup_search_index.py` first |
