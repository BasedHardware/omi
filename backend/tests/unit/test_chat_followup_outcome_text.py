"""Backend-authored outcome text must survive a pending follow-up marker.

A model can write its closing-question marker and still leave tool calls to run.
If the turn then ends on a safety limit or a provider error, the text the backend
appends to explain that lands *after* the marker — where the parser drops it with
the rest of the tail. The user would be left with a partial answer, no reason for
it, and a chip inviting them one hop further into a turn that never finished.
"""

from tests.unit.test_prompt_cache_integration import _get_agentic_module
from utils.chat_followup import FOLLOWUP_DELIMITER, split_followup_tail


async def _finished_answer(text: str) -> tuple[str, str | None]:
    agentic_mod = _get_agentic_module()
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = [f'Here is what I found.\n{FOLLOWUP_DELIMITER} Who else was in that call?']
    await agentic_mod._put_outcome_text(callback, full_response, text)
    return split_followup_tail(''.join(full_response))


async def test_guard_message_survives_and_voids_the_chip():
    answer, question = await _finished_answer('\n\nI seem to be stuck trying to answer that.')
    assert answer == 'Here is what I found.\n\nI seem to be stuck trying to answer that.'
    assert question is None, 'a turn that stopped on a limit must not invite a next question'


async def test_model_text_after_no_marker_is_untouched():
    agentic_mod = _get_agentic_module()
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = ['Here is what I found.']
    await agentic_mod._put_outcome_text(callback, full_response, '\n\nSorry, I encountered an error.')
    assert ''.join(full_response) == 'Here is what I found.\n\nSorry, I encountered an error.'
