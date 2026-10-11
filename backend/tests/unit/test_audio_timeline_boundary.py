"""Provider intervals that start exactly on a span boundary.

After a VAD skip the first post-gap segment naturally starts where the
previous provider span ends. The adjacency loop must skip a span whose
exclusive end equals the interval's inclusive start — it contributes no
sample — instead of pulling it into the straddle check and refusing the
interval as a fabricated capture gap.
"""

from utils.audio_timeline import SendMap


def _map():
    m = SendMap(16000)
    # provider 0..1000 -> capture 0..1000 ; VAD skip ; provider 1000..2000 -> capture 6000..7000
    m.add_accepted_spans([(0, 1000), (6000, 1000)])
    return m


def test_interval_starting_on_boundary_maps():
    m = _map()
    assert m.map_interval(1000, 1500) == (6000, 6500)


def test_interval_inside_second_span_unaffected():
    m = _map()
    assert m.map_interval(1001, 1500) == (6001, 6500)


def test_interval_crossing_real_gap_still_refused():
    m = _map()
    # 500..1500 spans the VAD gap -> genuinely straddled -> stays unplaced
    assert m.map_interval(500, 1500) is None
