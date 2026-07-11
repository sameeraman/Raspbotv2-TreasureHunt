# Raspbotv2 Treasure Hunt — Phase 4 Plan: Advanced Navigation

**Date:** 2026-07-10  
**Status:** Planning  
**Depends on:** Phase 1 (Movement), Phase 2 (Memory — for spatial memories)

---

## Goal

Give Ringo **spatial awareness and intelligent navigation** — instead of blindly moving forward and hoping to see something, Ringo builds a mental model of the space, navigates purposefully between rooms/zones, avoids obstacles reliably, and can return to known locations.

---

## Current Limitations (Phase 1)

| Problem | Impact |
|---------|--------|
| No sense of "where am I" | Robot moves randomly, can't navigate to rooms |
| No obstacle memory | Hits the same wall repeatedly |
| Ultrasonic is forward-only | Can't detect side obstacles |
| No concept of rooms/zones | Can't understand "go to the kitchen" |
| Movements are time-based | "Move forward 2 seconds" gives inconsistent distances |

---

## Architecture

```
         Orchestrator Agent
               │
         Navigation Plugin (new)
               │
    ┌──────────┼──────────────┐
    │          │              │
 Spatial    Path         Obstacle
 Memory     Planner      Avoidance
    │          │              │
 ┌──┴──┐   ┌──┴──┐     ┌────┴────┐
 │Local │   │ A*  │     │Reactive │
 │Map   │   │Grid │     │Layer    │
 └──────┘   └─────┘     └─────────┘
```

---

## Components to Build

### 1. Local Occupancy Grid (`navigation/grid_map.py`)

A simple 2D grid map that the robot builds as it moves:

```python
@dataclass
class GridMap:
    resolution_cm: int = 10       # Each cell = 10cm x 10cm
    width_cells: int = 100        # 10m x 10m max area
    height_cells: int = 100
    grid: np.ndarray              # 0=unknown, 1=free, 2=obstacle
    robot_x: int                  # Current position (grid coords)
    robot_y: int
    robot_heading: float          # Degrees (0=north)
```

Built from:
- Ultrasonic readings (mark obstacles ahead)
- Movement commands (dead reckoning position updates)
- Vision (GPT-5.4 can estimate rough distances/room identification)

### 2. Dead Reckoning (`navigation/odometry.py`)

Estimate position from motor commands:

```python
class Odometry:
    def update(self, movement_type: str, speed: int, duration: float):
        """Update estimated position based on movement command."""
        # Mecanum kinematics → displacement estimate
        ...
    
    @property
    def position(self) -> tuple[float, float]:
        """Current estimated (x, y) in cm from start."""
        ...
    
    @property
    def heading(self) -> float:
        """Current heading in degrees."""
        ...
```

Note: Dead reckoning drifts — this is a rough estimate, not centimetre-accurate.

### 3. Zone/Room Recognition (`navigation/zone_detector.py`)

Uses vision (GPT-5.4) to identify which room/area the robot is in:

```python
class ZoneDetector:
    async def identify_zone(self, image_b64: str) -> str:
        """Ask GPT-5.4 to identify the room/area from the camera image.
        Returns: 'living_room', 'kitchen', 'hallway', 'bedroom', etc.
        """
        ...
```

Zones are stored in memory (Phase 2) so the robot remembers "the couch is in the living room."

### 4. Reactive Obstacle Avoidance (`navigation/avoidance.py`)

A state machine that wraps movement with reactive obstacle handling:

```python
class ObstacleAvoidance:
    async def move_toward(self, direction: str, distance_cm: float) -> MoveResult:
        """Move in a direction with reactive obstacle avoidance.
        
        If obstacle detected:
        1. Stop
        2. Try slight left/right offset
        3. If still blocked, report blocked path
        """
        ...
```

States: `MOVING` → `OBSTACLE_DETECTED` → `REROUTING` → `MOVING` or `BLOCKED`

### 5. Navigation Plugin (`plugins/navigation.py`)

Semantic Kernel plugin replacing basic `MovementPlugin` functions:

| Function | Description |
|----------|-------------|
| `go_to_zone(zone_name)` | Navigate toward a named zone (e.g., "kitchen") |
| `explore_area()` | Move around current area systematically |
| `move_toward_object(direction)` | Move toward something seen (left/right/center) |
| `return_to_start()` | Navigate back to starting position |
| `get_current_location()` | Report current zone and approximate position |
| `scan_surroundings()` | Rotate 360° taking photos, build spatial picture |

### 6. Spatial Memory Integration (uses Phase 2 Memory)

Store and recall spatial information:

```python
# Store when discovering locations
await memory.remember(
    content="The red couch is in the living room, about 2 meters from the start",
    category="spatial",
    tags=["living_room", "couch", "red"]
)

# Recall when searching
results = await memory.recall("where is the living room?")
```

---

## Navigation Strategy

Since this is an indoor robot with limited sensors (forward ultrasonic only + camera), the strategy is:

### Exploration Mode (looking for treasure)
1. **Ask Sienna** for hints → identify target zone
2. **Vision check** → GPT-5.4 identifies current room
3. **If wrong room** → rotate, find openings (doorways/gaps), move through
4. **If right room** → systematic sweep (rotate, scan, move forward, repeat)
5. **If obstacle** → reactive avoidance (back up, offset, retry)

### Targeted Mode (approaching seen object)
1. **Object detected** in frame → estimate position (left/center/right)
2. **Align** → rotate toward object
3. **Approach** → move forward with ultrasonic checking
4. **Confirm** → re-check with vision when close

### Return Mode (going home)
1. **Reverse dead reckoning** → approximate path back
2. **Vision assist** → recognize start zone
3. **Stop** when back at approximate start position

---

## Implementation Tasks

### Navigation Core
- [ ] Create `navigation/` package directory
- [ ] Create `navigation/grid_map.py` — 2D occupancy grid
- [ ] Create `navigation/odometry.py` — dead reckoning from motor commands
- [ ] Create `navigation/zone_detector.py` — vision-based room identification
- [ ] Create `navigation/avoidance.py` — reactive obstacle avoidance state machine

### Navigation Plugin
- [ ] Create `plugins/navigation.py` — SK plugin (replaces basic movement for exploration)
- [ ] Implement `go_to_zone()` — multi-step zone navigation
- [ ] Implement `explore_area()` — systematic area sweep
- [ ] Implement `scan_surroundings()` — 360° panoramic scan
- [ ] Implement `return_to_start()` — dead reckoning return

### Integration
- [ ] Update `hardware/motor.py` — add odometry callbacks (notify on each move)
- [ ] Update `agents/orchestrator.py` — register navigation plugin
- [ ] Update `agents/prompts.py` — add navigation awareness to system prompt
- [ ] Wire spatial memories into Memory Agent (Phase 2)
- [ ] Update `main.py` — initialize navigation subsystem

### Testing
- [ ] Test dead reckoning accuracy over short distances
- [ ] Test obstacle avoidance state machine
- [ ] Test zone detection with various room images
- [ ] Test `return_to_start` accuracy
- [ ] Full integration test: "go to the kitchen and look around"

---

## New File Structure (additions in Phase 4)

```
Raspbotv2-TreasureHunt/
├── ...existing files...
├── navigation/
│   ├── __init__.py
│   ├── grid_map.py            # 2D occupancy grid
│   ├── odometry.py            # Dead reckoning position tracker
│   ├── zone_detector.py       # Vision-based room identification
│   └── avoidance.py           # Reactive obstacle avoidance
└── plugins/
    ├── ...existing...
    └── navigation.py          # Advanced navigation SK plugin
```

---

## Hardware Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| Forward-only ultrasonic | Use camera + vision to detect side obstacles; rotate before moving |
| No wheel encoders | Time-based dead reckoning (imprecise but functional) |
| Mecanum wheel slip | Keep speeds low (already enforced); accept ~20% position error |
| No LIDAR | Vision-based spatial understanding via GPT-5.4 |
| 480p camera | Sufficient for room recognition; limit vision queries to reduce latency |

---

## Example Session with Navigation

```
Sienna: "Find my blue cup! It's in the kitchen."
Ringo: "The kitchen! Let me figure out how to get there..."

[Navigation activates]
1. Ringo scans surroundings → GPT-5.4: "This looks like a living room"
2. Ringo rotates → sees doorway on the right
3. Ringo moves toward doorway with obstacle avoidance
4. Ringo enters new zone → GPT-5.4: "This looks like a kitchen"
5. Ringo: "I think I'm in the kitchen now! Let me look around..."
6. Ringo does systematic sweep (rotate + scan)
7. Ringo: "I see something blue on the counter! Is that your cup?"
```

---

## Estimated Effort

| Task | Time |
|------|------|
| Grid map & odometry | 3 hours |
| Zone detector | 2 hours |
| Obstacle avoidance state machine | 3 hours |
| Navigation plugin (6 functions) | 4 hours |
| Motor odometry callbacks | 1 hour |
| Orchestrator integration | 2 hours |
| Physical testing & tuning | 5 hours |
| **Total** | **~20 hours** |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Dead reckoning drift | Reset position when zone is recognized by vision; keep sessions short |
| Getting stuck | Timeout + ask Sienna for help ("I'm a bit lost — can you point me?") |
| Slow GPT-5.4 vision queries | Cache zone detection; don't re-query if robot hasn't moved |
| False zone identification | Use 2+ consecutive confirmations before declaring new zone |
| Doorway navigation | Move slowly; ultrasonic catches door frames; back up and adjust |

---

## Success Criteria

Phase 4 is complete when:
1. ✅ Ringo can navigate from one room to another (2-3 room house)
2. ✅ Ringo avoids obstacles without getting stuck (95%+ success)
3. ✅ Ringo can identify which room it's in via vision
4. ✅ Ringo can return to approximate starting position
5. ✅ "Go to the kitchen" results in robot arriving in the kitchen
6. ✅ Spatial memories persist ("I found the cup in the kitchen last time")
