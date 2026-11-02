"""Tests for bounding the action items chat tool result (issue #4927).

Asking the chat to "show me all my tasks" can pull a full 500-item page and render each item over
several lines, which floods the chat model's context so it freezes or refuses ("that's quite a bit
of information to process at once") -- the same failure already fixed for the conversations tool in
#8503. get_action_items_tool now caps how many items (and how many characters) it returns and
appends a note that identifies omitted rows. These tests cover the two pure bounding helpers.
"""

from utils.retrieval.tools import action_item_tools as ai
from utils.retrieval.tools import result_bounds as rb


class TestCapActionItemsForLlm:
    def test_caps_and_flags_truncation(self):
        items = list(range(500))  # stand-ins; the database's ordering is preserved
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert truncated is True
        assert len(capped) == ai.MAX_ACTION_ITEMS_FOR_LLM
        assert capped == items[: ai.MAX_ACTION_ITEMS_FOR_LLM]  # first rows in database order kept

    def test_under_cap_is_untouched(self):
        items = list(range(50))
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert capped == items and truncated is False

    def test_exactly_at_cap_is_not_truncated(self):
        items = list(range(ai.MAX_ACTION_ITEMS_FOR_LLM))
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert truncated is False and len(capped) == ai.MAX_ACTION_ITEMS_FOR_LLM

    def test_empty_list(self):
        capped, truncated = ai._cap_action_items_for_llm([])
        assert capped == [] and truncated is False


class TestBoundedActionItemsResult:
    def test_truncated_appends_guidance_note_without_claiming_a_total(self):
        out = ai._bounded_action_items_result("1. [Pending] ship it\n   ID: a", truncated=True)
        assert "more were omitted, not absent" in out
        assert "Showing 1 action items" in out
        assert "narrower" in out
        # No definitive total is claimed: the page is limit-capped, not necessarily the full set.
        assert "total" not in out.lower()

    def test_not_truncated_short_result_unchanged(self):
        body = "1. [Pending] ship it\n   ID: a"
        assert ai._bounded_action_items_result(body, truncated=False) == body

    def test_oversized_result_is_clipped_at_a_line_boundary_with_note(self):
        big = "1. [Pending] first\n" + ("x" * 30000) + "\n2. [Pending] second\n" + ("y" * 40000)
        out = ai._bounded_action_items_result(big, truncated=False)
        assert len(out) <= ai.MAX_RESULT_CHARS + 400  # budget plus the appended note
        assert "more were omitted, not absent" in out
        # Clipped back to a line boundary, so the final record before the note is not sliced
        # mid-field (the trailing 40k-character run is dropped whole, not cut partway).
        note_idx = out.index("[Showing")
        body = out[:note_idx].rstrip("\n")
        assert not body.endswith("y")

    def test_shared_bound_note_does_not_claim_relevance_and_accepts_order(self):
        generic = rb.bounded_result("one result line", truncated=True)
        assert "more may exist" in generic
        assert "most relevant" not in generic

        ordered = rb.bounded_result("1. row", truncated=True, noun="events", order="newest first", shown=1)
        assert "Rows are ordered newest first" in ordered
        assert "Showing 1 events" in ordered
