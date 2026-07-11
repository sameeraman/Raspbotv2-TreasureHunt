"""Memory Manager — auto-triggers for storing and recalling memories.

Observes the conversation and automatically stores important memories
(treasure found, preferences learned, session summaries) without
the orchestrator needing to explicitly call the memory plugin.
"""

import uuid
from datetime import datetime, timezone

from plugins.memory import MemoryPlugin
from utils import setup_logger

logger = setup_logger("ringo.memory_manager")

# Keywords that suggest Sienna is expressing a preference
FAVOURITE_INDICATORS = [
    "i love", "i like", "my favourite", "my favorite", "i really like",
    "the best", "so cool", "so pretty", "i want",
]

# Keywords that suggest a treasure was found
FOUND_INDICATORS = [
    "found it", "i found", "that's it", "yes that's", "you found",
    "yay", "we found", "there it is",
]


class MemoryManager:
    """Observes conversations and auto-triggers memory storage/recall."""

    def __init__(self, memory_plugin: MemoryPlugin):
        self.memory = memory_plugin
        self._current_target: str = ""
        self._session_id: str = ""
        self._session_exchanges: list[dict] = []

    def start_session(self):
        """Initialize a new session for tracking."""
        self._session_id = str(uuid.uuid4())[:8]
        self._session_exchanges = []
        self._current_target = ""
        self.memory.set_session_id(self._session_id)
        logger.info(f"Memory manager session started: {self._session_id}")

    def set_target(self, target: str):
        """Set the current treasure hunt target (what Sienna is looking for)."""
        self._current_target = target
        logger.info(f"Hunt target set: '{target}'")

    async def observe_exchange(self, user_text: str, assistant_text: str):
        """Observe a conversation exchange and auto-store relevant memories.

        Called after each user→assistant turn in the conversation loop.
        """
        self._session_exchanges.append({
            "user": user_text,
            "assistant": assistant_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        user_lower = user_text.lower()
        assistant_lower = assistant_text.lower()

        # Check for favourite expressions
        await self._check_for_favourite(user_lower, user_text)

        # Check for treasure found
        await self._check_for_treasure_found(user_lower, assistant_lower)

        # Check for hint patterns (where things are found)
        await self._check_for_hint_pattern(user_lower, user_text)

    async def _check_for_favourite(self, user_lower: str, user_text: str):
        """Detect and store favourite things Sienna mentions."""
        for indicator in FAVOURITE_INDICATORS:
            if indicator in user_lower:
                # Extract what she likes (the part after the indicator)
                idx = user_lower.index(indicator) + len(indicator)
                favourite_thing = user_text[idx:].strip().rstrip("!.,?")
                if len(favourite_thing) > 2:
                    await self.memory.remember(
                        content=f"Sienna loves {favourite_thing}",
                        category="favourite",
                        importance=4,
                        tags=favourite_thing.replace(" ", ","),
                    )
                    logger.info(f"Auto-stored favourite: '{favourite_thing}'")
                break

    async def _check_for_treasure_found(self, user_lower: str, assistant_lower: str):
        """Detect when a treasure has been found and store the memory."""
        combined = user_lower + " " + assistant_lower
        found = any(indicator in combined for indicator in FOUND_INDICATORS)

        if found and self._current_target:
            # Try to determine location from recent context
            location = self._extract_location_hint()
            content = f"Found '{self._current_target}'"
            if location:
                content += f" {location}"

            await self.memory.remember(
                content=content,
                category="treasure_found",
                importance=4,
                tags=self._current_target.replace(" ", ","),
            )
            logger.info(f"Auto-stored treasure found: '{content}'")

    async def _check_for_hint_pattern(self, user_lower: str, user_text: str):
        """Detect location hints Sienna gives (useful for future hunts)."""
        location_words = [
            "near the", "next to", "behind the", "under the", "on the",
            "in the", "beside the", "by the",
        ]
        for loc in location_words:
            if loc in user_lower:
                idx = user_lower.index(loc)
                hint = user_text[idx:].strip().rstrip("!.,?")
                if len(hint) > 5:
                    await self.memory.remember(
                        content=f"Sienna often hides things {hint}",
                        category="hint_pattern",
                        importance=2,
                        tags="location,hint",
                    )
                    logger.debug(f"Auto-stored hint pattern: '{hint}'")
                break

    async def end_session_summary(self):
        """Store a summary of the session as a story_moment memory."""
        if not self._session_exchanges:
            return

        # Build a brief summary
        num_turns = len(self._session_exchanges)
        summary_parts = [f"Treasure hunt session with {num_turns} exchanges."]

        if self._current_target:
            summary_parts.append(f"Looking for: {self._current_target}.")

        # Check if treasure was found during this session
        all_text = " ".join(
            ex["user"] + " " + ex["assistant"]
            for ex in self._session_exchanges
        ).lower()
        if any(ind in all_text for ind in FOUND_INDICATORS):
            summary_parts.append("Treasure was found! 🎉")
        else:
            summary_parts.append("Treasure hunt ended before finding it.")

        summary = " ".join(summary_parts)

        await self.memory.remember(
            content=summary,
            category="story_moment",
            importance=3,
            tags="session,summary",
        )
        logger.info(f"Stored session summary: '{summary}'")

    async def get_greeting_context(self) -> str:
        """Get memory context for personalising the session greeting."""
        return await self.memory.get_session_context()
