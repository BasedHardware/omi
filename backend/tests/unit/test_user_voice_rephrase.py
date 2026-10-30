"""The tiny local rephraser, its meaning guard, signature phrases and reaction habits (#23541).

One invented user who texts a friend (Mia) in lowercase with stretched words and
reacts to most of her messages with a heart.
"""

from datetime import datetime, timezone

import httpx
import pytest

from utils.llm import user_voice_rephrase
from utils.llm.user_voice import (
    VoiceExchange,
    build_profile,
    fit_reactions,
    profile_prompt_block,
    signature_phrases,
    suggest_reaction,
)
from utils.llm.user_voice_rephrase import guard, rephrase_draft, rephrase_messages

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
MIA_LINES = [
    'okk im here',
    'yeees lets go',
    'high key starving',
    'no hurry babe',
    'yeees i saw it',
    'high key the best',
    'omw now',
    'no hurry at all',
    'okk sounds good',
    'yeees omg',
    'that was high key fun',
    'no hurry tho',
]
MIA_SAID = ['are you here', 'dinner later?', 'did you see it', 'running late', 'want to come', 'the movie was good']


def _thread(runs=10, react_every=1, reaction='love', words_too=True):
    items = []
    for i in range(runs):
        items.append({'is_user': False, 'text': f'mia message {i}'})
        if i % react_every == 0:
            items.append({'is_user': True, 'reaction': reaction})
        if words_too or i % react_every:
            items.append({'is_user': True, 'text': 'okk'})
    items.append({'is_user': False, 'text': 'open run, not answered'})
    return items


def _mia(**kw):
    exchanges = [(a, b) for a, b in zip(MIA_SAID * 2, MIA_LINES)]
    return build_profile('p-mia', 'Mia', [], [], written_lines=MIA_LINES, exchanges=exchanges, now=NOW, **kw)


# --- signature phrases -------------------------------------------------------


def test_signature_phrases_are_the_users_own_not_shared_topic_words():
    phrases = signature_phrases(MIA_LINES, MIA_SAID)
    assert 'yeees' in phrases
    assert 'high key' in phrases
    assert 'no hurry' in phrases
    # "high" alone is inside "high key", so it is not listed twice
    assert 'high' not in phrases


def test_signature_phrases_need_enough_lines():
    assert signature_phrases(MIA_LINES[:3], MIA_SAID) == []


def test_phrases_reach_the_profile_and_the_prompt_block():
    profile = _mia()
    assert 'high key' in profile.phrases
    assert 'high key' in profile_prompt_block(profile)


# --- reactions -----------------------------------------------------------------


def test_reaction_habit_is_fitted_per_answered_run():
    habit = fit_reactions(_thread(runs=10, react_every=1))
    assert habit is not None
    assert habit.runs == 10  # the open run at the end is not counted
    assert habit.rate == 100
    assert habit.favourite == 'love'
    assert habit.reply_rate == 100


def test_reaction_alone_is_measured():
    habit = fit_reactions(_thread(runs=10, react_every=1, words_too=False))
    assert habit.reply_rate == 0


def test_no_reaction_items_means_no_habit():
    assert fit_reactions([{'is_user': False, 'text': 'hi'}, {'is_user': True, 'text': 'hey'}] * 10) is None


def test_too_few_runs_means_no_habit():
    assert fit_reactions(_thread(runs=3)) is None


def test_reaction_is_suggested_only_when_it_is_a_habit():
    often = _mia(thread=_thread(runs=10, react_every=1))
    rarely = _mia(thread=_thread(runs=10, react_every=5))
    assert suggest_reaction(often) == 'love'
    assert suggest_reaction(rarely) is None
    assert 'reacts to Mia' in profile_prompt_block(often)
    assert 'reacts to Mia' not in profile_prompt_block(rarely)


def test_reaction_items_never_show_in_the_open_thread():
    profile = _mia(thread=_thread(runs=10))
    block = profile_prompt_block(profile, 'open run', _thread(runs=10))
    assert 'None' not in block


# --- the meaning guard -----------------------------------------------------------


@pytest.mark.parametrize(
    'draft,candidate,reason',
    [
        ("I'll be there at 7.", 'omw be there at 8', 'numbers changed'),
        ('See https://x.co/a', 'see this', 'link changed'),
        ("I can't make it tonight.", 'i can make it tonight', 'negation changed'),
        ('Tell Sam I said hi.', 'tell her i said hi', 'name dropped'),
        ('Sounds good, see you then.', 'sounds good, see you and Jake', 'name added'),
        ('Okay.', 'okay sure thing, sounds really good to me', 'length x8.2'),
        ('Okay.', 'okay okay okay okay okay okay okay', 'repeats itself'),
        ("Yes, I'm excited!", 'Omg' + 'g' * 30, 'repeats itself'),
        ('In the pages of the journal.', 'In the journal of the journal', 'repeats itself'),
        ('洗衣篮都放在房间里。', '洗衣篮放洗衣篮放', 'repeats itself'),
        ('我到了', 'im here', 'language changed'),
        ('On my way.', 'omw\nsee u', 'extra lines'),
        ('On my way.', '', 'empty'),
    ],
)
def test_guard_refuses_a_rewrite_that_changes_the_meaning(draft, candidate, reason):
    assert guard(draft, candidate) == reason


@pytest.mark.parametrize(
    'draft,candidate',
    [
        ("I've arrived.", 'okk im here'),
        ("I'll be there at 7, Mia.", 'yeees omw be there at 7 mia'),
        ("I can't wait!", 'cant wait'),
        ('我马上到。', '我马上到啦'),
        ("That's hilarious.", 'hahahahaha'),
        ('太好笑了', '哈哈哈哈哈哈'),
    ],
)
def test_guard_keeps_a_rewrite_that_only_changes_the_wording(draft, candidate):
    assert guard(draft, candidate, ['Mia']) is None


# --- rephrase_draft ---------------------------------------------------------------


def test_rephrase_uses_the_engine_then_polishes():
    seen = {}

    def engine(messages):
        seen['messages'] = messages
        return '"okk im here!"'

    result = rephrase_draft("I've arrived.", _mia(), 'are you here', complete=engine)
    assert result.engine == 'local'
    assert result.text.startswith('okk im here')
    assert 'rephrased' in result.changes
    prompt = seen['messages'][1]['content']
    assert 'Draft: I\'ve arrived.' in prompt
    assert 'They said: are you here' in prompt
    assert '- okk im here' in prompt


def test_a_refused_rewrite_keeps_the_draft():
    result = rephrase_draft("I'll be there at 7.", _mia(), complete=lambda m: 'omw be there at 9')
    assert result.rejected == 'numbers changed'
    assert result.engine == 'none'
    assert '7' in result.text
    assert result.engine_error is None


def test_a_rewrite_that_copies_a_past_line_is_refused():
    profile = _mia()
    profile.examples.append('that movie was high key the best thing ever')
    result = rephrase_draft(
        'That show was really good.', profile, complete=lambda m: 'that movie was high key the best thing ever'
    )
    assert result.rejected == 'copied a past line'


def test_an_engine_failure_fails_open():
    def boom(messages):
        raise httpx.ReadTimeout('slow')

    result = rephrase_draft('On my way.', _mia(), complete=boom)
    assert result.engine_error == 'ReadTimeout'
    assert result.text.lower().startswith('on my way')


def test_off_unless_configured(monkeypatch):
    monkeypatch.delenv(user_voice_rephrase.REPHRASER_URL_ENV, raising=False)
    result = rephrase_draft("I've arrived.", _mia())
    assert result.engine == 'none'
    assert result.rejected is None


def test_unreliable_profile_is_left_alone():
    thin = build_profile('p-x', 'X', [], [], written_lines=['hi'], now=NOW)
    called = []
    result = rephrase_draft('Hello.', thin, complete=lambda m: called.append(m) or 'yo')
    assert result.text == 'Hello.'
    assert called == []


def test_local_server_request_shape(monkeypatch):
    monkeypatch.setenv(user_voice_rephrase.REPHRASER_URL_ENV, 'http://127.0.0.1:8090/v1')
    monkeypatch.setenv(user_voice_rephrase.REPHRASER_MODEL_ENV, 'qwen3-0.6b-user-voice')
    captured = {}

    def fake_post(url, json, timeout, follow_redirects):
        captured.update(url=url, body=json, timeout=timeout, follow_redirects=follow_redirects)
        return httpx.Response(
            200, json={'choices': [{'message': {'content': 'okk im here'}}]}, request=httpx.Request('POST', url)
        )

    monkeypatch.setattr(user_voice_rephrase.httpx, 'post', fake_post)
    result = rephrase_draft("I've arrived.", _mia(), 'are you here')
    assert result.text.startswith('okk im here')
    assert captured['url'] == 'http://127.0.0.1:8090/v1/chat/completions'
    assert captured['body']['model'] == 'qwen3-0.6b-user-voice'
    assert captured['body']['temperature'] == 0
    assert captured['body']['chat_template_kwargs'] == {'enable_thinking': False}
    assert captured['timeout'] == user_voice_rephrase.REPHRASER_TIMEOUT_SECONDS
    assert captured['follow_redirects'] is False


def test_prompt_shows_the_closest_replies_and_phrases():
    profile = _mia()
    profile.exchanges.append(VoiceExchange(them='dinner later?', me='yeees high key starving'))
    msgs = rephrase_messages(profile, 'Yes, I would love to get dinner.', 'dinner later?')
    assert msgs[0]['role'] == 'system'
    assert 'yeees high key starving' in msgs[1]['content']
    assert 'Phrases the user often uses:' in msgs[1]['content']


def test_default_model_name_keeps_an_mlx_adapter(monkeypatch):
    # mlx_lm.server applies --adapter-path only to the model called 'default_model'.
    monkeypatch.setenv(user_voice_rephrase.REPHRASER_URL_ENV, 'http://127.0.0.1:8090/v1')
    monkeypatch.delenv(user_voice_rephrase.REPHRASER_MODEL_ENV, raising=False)
    captured = {}

    def fake_post(url, json, timeout, follow_redirects):
        captured.update(body=json)
        return httpx.Response(
            200, json={'choices': [{'message': {'content': 'okk im here'}}]}, request=httpx.Request('POST', url)
        )

    monkeypatch.setattr(user_voice_rephrase.httpx, 'post', fake_post)
    rephrase_draft("I've arrived.", _mia(), 'are you here')
    assert captured['body']['model'] == 'default_model'
