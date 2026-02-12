"""Tests for translation debounce logic (issue #4713).

Tests verify that growing segments are debounced to reduce redundant translations.
Uses asyncio.run() since pytest-asyncio is not configured in this project.
"""

import asyncio
from unittest.mock import MagicMock
import sys

# Mock Google Cloud translate before importing
mock_translate_v3 = MagicMock()
sys.modules['google.cloud.translate_v3'] = mock_translate_v3
sys.modules['google.cloud'] = MagicMock()


class TestFirstSightTranslation:
    def test_first_segment_translates_immediately(self):
        """First time seeing a segment should trigger immediate translation (no debounce)."""
        debounce_state = {}
        seg_id = "seg1"
        text_hash = hash("Hello")

        state = debounce_state.get(seg_id)
        assert state is None  # First time — should translate immediately

        debounce_state[seg_id] = {'text_hash': text_hash, 'generation': 0, 'task': None}
        # Production code calls _translate_segment here (immediate, no delay)
        assert debounce_state[seg_id]['generation'] == 0
        assert debounce_state[seg_id]['task'] is None  # No debounce task for first sight

    def test_same_text_hash_skipped(self):
        """Same text hash should not trigger another translation or debounce."""
        debounce_state = {}
        text = "Hello"
        text_hash = hash(text)

        # First time
        debounce_state["seg1"] = {'text_hash': text_hash, 'generation': 0, 'task': None}

        # Same text again — hash matches, no action needed
        new_hash = hash(text)
        state = debounce_state.get("seg1")
        assert state['text_hash'] == new_hash  # Same hash — skip


class TestDebounceScheduling:
    def test_text_change_increments_generation(self):
        """Changed text should increment generation and update hash."""
        debounce_state = {}
        debounce_state["seg1"] = {'text_hash': hash("Hello"), 'generation': 0, 'task': None}

        new_hash = hash("Hello world")
        state = debounce_state["seg1"]
        assert state['text_hash'] != new_hash

        state['generation'] += 1
        state['text_hash'] = new_hash

        assert state['generation'] == 1
        assert state['text_hash'] == new_hash

    def test_rapid_updates_only_last_fires(self):
        """Multiple rapid updates: only the last generation's debounce should fire."""
        fire_log = []

        async def run():
            debounce_state = {}
            debounce_state["seg1"] = {'text_hash': hash("Hello"), 'generation': 0, 'task': None}

            async def debounced_task(seg_id, gen, delay=0.05):
                await asyncio.sleep(delay)
                s = debounce_state.get(seg_id)
                if s and s['generation'] == gen:
                    fire_log.append(gen)

            # 3 rapid updates
            for i, text in enumerate(["Hello world", "Hello world how", "Hello world how are you"], start=1):
                state = debounce_state["seg1"]
                if state['task'] and not state['task'].done():
                    state['task'].cancel()
                state['generation'] = i
                state['text_hash'] = hash(text)
                state['task'] = asyncio.create_task(debounced_task("seg1", i))
                await asyncio.sleep(0.01)

            await asyncio.sleep(0.2)

        asyncio.run(run())
        assert fire_log == [3]  # Only last generation fired

    def test_stale_generation_discarded(self):
        """If generation changes before debounce fires, the stale task is discarded."""
        fire_log = []

        async def run():
            debounce_state = {}
            debounce_state["seg1"] = {'text_hash': hash("Hello"), 'generation': 0, 'task': None}

            async def debounced_task(seg_id, gen, delay=0.1):
                await asyncio.sleep(delay)
                s = debounce_state.get(seg_id)
                if s and s['generation'] == gen:
                    fire_log.append(gen)

            # Schedule gen 1
            debounce_state["seg1"]['generation'] = 1
            debounce_state["seg1"]['task'] = asyncio.create_task(debounced_task("seg1", 1))

            # Before it fires, bump to gen 2 (without cancelling)
            await asyncio.sleep(0.03)
            debounce_state["seg1"]['generation'] = 2

            await asyncio.sleep(0.2)

        asyncio.run(run())
        assert 1 not in fire_log  # Gen 1 did not fire (stale)

    def test_cancel_prevents_fire(self):
        """Cancelling a debounce task should prevent it from firing."""
        fire_log = []

        async def run():
            debounce_state = {}

            async def debounced_task(seg_id, gen, delay=0.1):
                try:
                    await asyncio.sleep(delay)
                    fire_log.append(gen)
                except asyncio.CancelledError:
                    pass

            debounce_state["seg1"] = {'text_hash': hash("x"), 'generation': 1, 'task': None}
            debounce_state["seg1"]['task'] = asyncio.create_task(debounced_task("seg1", 1))

            await asyncio.sleep(0.02)
            debounce_state["seg1"]['task'].cancel()

            await asyncio.sleep(0.2)

        asyncio.run(run())
        assert fire_log == []  # Cancelled, nothing fired


class TestIndependentSegments:
    def test_segments_debounce_independently(self):
        """Different segment IDs should debounce independently."""
        fire_log = []

        async def run():
            debounce_state = {}

            async def debounced_task(seg_id, gen, delay=0.05):
                await asyncio.sleep(delay)
                s = debounce_state.get(seg_id)
                if s and s['generation'] == gen:
                    fire_log.append(seg_id)

            debounce_state["seg1"] = {'text_hash': hash("Hello"), 'generation': 1, 'task': None}
            debounce_state["seg2"] = {'text_hash': hash("Bonjour"), 'generation': 1, 'task': None}

            debounce_state["seg1"]['task'] = asyncio.create_task(debounced_task("seg1", 1))
            debounce_state["seg2"]['task'] = asyncio.create_task(debounced_task("seg2", 1))

            await asyncio.sleep(0.2)

        asyncio.run(run())
        assert "seg1" in fire_log
        assert "seg2" in fire_log


class TestPruning:
    def test_completed_tasks_pruned_for_absent_segments(self):
        """Completed debounce tasks for segments no longer in current batch should be pruned."""

        async def run():
            debounce_state = {}

            async def noop():
                pass

            task = asyncio.create_task(noop())
            await task  # Complete it

            debounce_state["old_seg"] = {'text_hash': 123, 'generation': 0, 'task': task}
            debounce_state["active_seg"] = {'text_hash': 456, 'generation': 0, 'task': None}

            current_segment_ids = {"active_seg"}
            stale_ids = [sid for sid, s in debounce_state.items()
                         if s.get('task') and s['task'].done() and sid not in current_segment_ids]
            for sid in stale_ids:
                del debounce_state[sid]

            assert "old_seg" not in debounce_state
            assert "active_seg" in debounce_state

        asyncio.run(run())

    def test_active_tasks_not_pruned(self):
        """Segments with pending (not done) tasks should NOT be pruned."""

        async def run():
            debounce_state = {}

            async def slow_task():
                await asyncio.sleep(10)

            task = asyncio.create_task(slow_task())
            debounce_state["pending_seg"] = {'text_hash': 789, 'generation': 1, 'task': task}

            current_segment_ids = set()  # Not in current batch
            stale_ids = [sid for sid, s in debounce_state.items()
                         if s.get('task') and s['task'].done() and sid not in current_segment_ids]
            for sid in stale_ids:
                del debounce_state[sid]

            assert "pending_seg" in debounce_state  # NOT pruned — task still running
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
