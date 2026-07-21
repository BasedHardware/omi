"""Regression test: an empty daily-summary overview must not produce an empty push body.

utils.other.notifications._send_summary_notification built the notification body with
str(summary_data.get('overview', 'Tap to see your daily summary')). get's default only applies to
an ABSENT key. DailySummaryPayload.overview defaults to "", so a thin day yields a present-but-empty
overview -> get returns "" -> the fallback string is dead code -> an empty daily-summary push. The
body now falls back to the default text when overview is empty.
"""

import utils.other.notifications as notif


class _FakeConvo:
    transcript_segments = [object()]
    discarded = False


def _drive(monkeypatch, overview):
    sent = []
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *a, **k: True)
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *a, **k: None)
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *a, **k: [{'is_locked': False, 'id': 'c1'}])
    monkeypatch.setattr(notif, 'deserialize_conversation', lambda d: _FakeConvo())
    monkeypatch.setattr(
        notif,
        'generate_comprehensive_daily_summary',
        lambda *a, **k: {'overview': overview, 'headline': 'H', 'day_emoji': 'X'},
    )
    monkeypatch.setattr(notif.daily_summaries_db, 'create_daily_summary', lambda *a, **k: 'sid')
    monkeypatch.setattr(notif.postprocess_executor, 'submit', lambda *a, **k: None)
    monkeypatch.setattr(notif, 'day_summary_webhook', lambda *a, **k: None)
    monkeypatch.setattr(notif, 'send_notification', lambda *a, **k: sent.append(a))

    notif._send_summary_notification(('u1', ['tok1']))
    assert sent, 'send_notification was not called'
    return sent[0][2]  # summary_body is the 3rd positional arg


def test_empty_overview_uses_fallback_body(monkeypatch):
    body = _drive(monkeypatch, '')
    assert body == 'Tap to see your daily summary'


def test_nonempty_overview_is_used(monkeypatch):
    body = _drive(monkeypatch, 'You had 3 conversations today.')
    assert body == 'You had 3 conversations today.'
