"""Collapse observability is countable, bounded and independent of matching policy."""

from types import SimpleNamespace
from utils.live_speaker_collapse import LiveSpeakerCollapseMonitor


def test_emits_once_after_both_segment_and_rejection_thresholds():
    monitor = LiveSpeakerCollapseMonitor()
    for i in range(10):
        assert not monitor.observe(0, 'scope', f's{i}')
    assert not monitor.match(0, 'scope', 's0', accepted=False)
    assert not monitor.match(0, 'scope', 's1', accepted=False)
    assert monitor.match(0, 'scope', 's2', accepted=False)
    for i in range(10, 200):
        assert not monitor.observe(0, 'scope', f's{i}')
        assert not monitor.match(0, 'scope', f's{i}', accepted=False)
    assert len(monitor.recent_segments) == len(monitor.recent_matches) == 128


def test_emits_when_segments_reach_threshold_after_rejections():
    monitor = LiveSpeakerCollapseMonitor()
    for i in range(3):
        assert not monitor.observe(0, 'scope', f's{i}')
        assert not monitor.match(0, 'scope', f's{i}', accepted=False)
    for i in range(3, 9):
        assert not monitor.observe(0, 'scope', f's{i}')
    assert monitor.observe(0, 'scope', 's9')


def test_distinct_speaker_or_scope_and_accepted_match_break_rejections():
    monitor = LiveSpeakerCollapseMonitor()
    for i in range(30):
        assert not monitor.observe(i % 2, 'scope', f's{i}')
        assert not monitor.match(i % 2, 'scope', f's{i}', accepted=False)
    assert not monitor.observe(0, 'new-provider', 'new')
    assert not monitor.match(0, 'scope', 'old-async-match', accepted=False)
    for i in range(10):
        assert not monitor.observe(0, 'new-provider', f'n{i}')
    for i in range(2):
        assert not monitor.match(0, 'new-provider', f'n{i}', accepted=False)
    assert not monitor.match(0, 'new-provider', 'n2', accepted=True)
    assert not monitor.match(0, 'new-provider', 'n3', accepted=False)
    assert monitor.rejected_matches == 1


def test_replays_are_not_consecutive_new_segments_or_new_rejections():
    monitor = LiveSpeakerCollapseMonitor()
    for _ in range(20):
        assert not monitor.observe(0, 'scope', 'replayed')
        assert not monitor.match(0, 'scope', 'replayed', accepted=False)
    assert monitor.consecutive_segments == monitor.rejected_matches == 1


def test_controller_emits_metric_and_log_without_changing_speaker_maps(caplog):
    from routers.listen.speakers import SpeakerMatcher
    from utils.metrics import OMI_LIVE_SPEAKER_COLLAPSE_TOTAL

    # No providers are loaded when constructing the matcher.
    controller = SpeakerMatcher(SimpleNamespace(limits=SimpleNamespace(speaker_queue_size=100)))
    before = OMI_LIVE_SPEAKER_COLLAPSE_TOTAL._value.get()
    for i in range(3):
        controller.observe_segment(0, 'scope', f's{i}')
        controller.collapse_monitor.match(0, 'scope', f's{i}', accepted=False)
    for i in range(3, 10):
        controller.observe_segment(0, 'scope', f's{i}')
    assert OMI_LIVE_SPEAKER_COLLAPSE_TOTAL._value.get() == before + 1
    assert 'event=live_speaker_collapse' in caplog.text
    assert not controller.speaker_to_person and not controller.voice_identity_status
    controller.clear()
    assert controller.collapse_monitor.consecutive_segments == 0


def test_range_receipt_is_not_a_manual_voice_decision():
    from routers.listen.speakers import SpeakerMatcher

    matcher = SpeakerMatcher(SimpleNamespace())
    receipt = {'segments': {'s': {'speaker_id': 0, 'generation': 2, 'person_id': 'person', 'segment_only': True}}}
    assert matcher._manual_voice_decision(receipt, 0) is None
