"""Generated band: hostile storm stamps keep the report total.

A carrier whose stamped window is a bool, a string, None,
non-finite, zero or negative keeps the documented zero window
(retry_after_ms=0) instead of raising; the line's remaining fields
stay byte-for-byte the documented shape. Spec-computed cell by
cell: the spec reads the raw attribute, so a bool stamp collapses
exactly as the documented contract says.

Failure-Class: FC-drain-cap-storm-handoff-booked-as-production-error
"""

from types import SimpleNamespace

from utils.batch_pipeline.pump import drain_backstop_report


def _carrier(stamp, label):
    """A hostile-shaped carrier: the raw attributes are read as-is."""
    return SimpleNamespace(retry_after=stamp, operation=label)


def test_h0000() -> None:
    """stamp=True, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0001() -> None:
    """stamp=True, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0002() -> None:
    """stamp=True, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0003() -> None:
    """stamp=True, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0004() -> None:
    """stamp=True, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0005() -> None:
    """stamp=True, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0006() -> None:
    """stamp=True, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0007() -> None:
    """stamp=True, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0008() -> None:
    """stamp=True, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0009() -> None:
    """stamp=True, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0010() -> None:
    """stamp=True, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0011() -> None:
    """stamp=True, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0012() -> None:
    """stamp=True, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0013() -> None:
    """stamp=True, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0014() -> None:
    """stamp=True, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0015() -> None:
    """stamp=True, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0016() -> None:
    """stamp=True, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0017() -> None:
    """stamp=True, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0018() -> None:
    """stamp=True, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0019() -> None:
    """stamp=True, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0020() -> None:
    """stamp=True, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0021() -> None:
    """stamp=True, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0022() -> None:
    """stamp=True, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0023() -> None:
    """stamp=True, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(True, None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0024() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0025() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0026() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0027() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0028() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0029() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0030() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0031() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0032() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0033() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0034() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0035() -> None:
    """stamp=True, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(True, 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0036() -> None:
    """stamp=False, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0037() -> None:
    """stamp=False, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0038() -> None:
    """stamp=False, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0039() -> None:
    """stamp=False, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0040() -> None:
    """stamp=False, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0041() -> None:
    """stamp=False, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0042() -> None:
    """stamp=False, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0043() -> None:
    """stamp=False, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0044() -> None:
    """stamp=False, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0045() -> None:
    """stamp=False, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0046() -> None:
    """stamp=False, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0047() -> None:
    """stamp=False, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0048() -> None:
    """stamp=False, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0049() -> None:
    """stamp=False, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0050() -> None:
    """stamp=False, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0051() -> None:
    """stamp=False, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0052() -> None:
    """stamp=False, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0053() -> None:
    """stamp=False, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0054() -> None:
    """stamp=False, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0055() -> None:
    """stamp=False, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0056() -> None:
    """stamp=False, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0057() -> None:
    """stamp=False, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0058() -> None:
    """stamp=False, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0059() -> None:
    """stamp=False, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(False, None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0060() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0061() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0062() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0063() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0064() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0065() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0066() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0067() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0068() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0069() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0070() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0071() -> None:
    """stamp=False, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(False, 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0072() -> None:
    """stamp='4.2', label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0073() -> None:
    """stamp='4.2', label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0074() -> None:
    """stamp='4.2', label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0075() -> None:
    """stamp='4.2', label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0076() -> None:
    """stamp='4.2', label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0077() -> None:
    """stamp='4.2', label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0078() -> None:
    """stamp='4.2', label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0079() -> None:
    """stamp='4.2', label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0080() -> None:
    """stamp='4.2', label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0081() -> None:
    """stamp='4.2', label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0082() -> None:
    """stamp='4.2', label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0083() -> None:
    """stamp='4.2', label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0084() -> None:
    """stamp='4.2', label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0085() -> None:
    """stamp='4.2', label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0086() -> None:
    """stamp='4.2', label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0087() -> None:
    """stamp='4.2', label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0088() -> None:
    """stamp='4.2', label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0089() -> None:
    """stamp='4.2', label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0090() -> None:
    """stamp='4.2', label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0091() -> None:
    """stamp='4.2', label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0092() -> None:
    """stamp='4.2', label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0093() -> None:
    """stamp='4.2', label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0094() -> None:
    """stamp='4.2', label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0095() -> None:
    """stamp='4.2', label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0096() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0097() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0098() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0099() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0100() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0101() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0102() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0103() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0104() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0105() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0106() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0107() -> None:
    """stamp='4.2', label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier('4.2', 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0108() -> None:
    """stamp=None, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0109() -> None:
    """stamp=None, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0110() -> None:
    """stamp=None, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0111() -> None:
    """stamp=None, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0112() -> None:
    """stamp=None, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0113() -> None:
    """stamp=None, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0114() -> None:
    """stamp=None, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0115() -> None:
    """stamp=None, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0116() -> None:
    """stamp=None, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0117() -> None:
    """stamp=None, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0118() -> None:
    """stamp=None, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0119() -> None:
    """stamp=None, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0120() -> None:
    """stamp=None, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0121() -> None:
    """stamp=None, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0122() -> None:
    """stamp=None, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0123() -> None:
    """stamp=None, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0124() -> None:
    """stamp=None, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0125() -> None:
    """stamp=None, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0126() -> None:
    """stamp=None, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0127() -> None:
    """stamp=None, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0128() -> None:
    """stamp=None, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0129() -> None:
    """stamp=None, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0130() -> None:
    """stamp=None, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0131() -> None:
    """stamp=None, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(None, None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0132() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0133() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0134() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0135() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0136() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0137() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0138() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0139() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0140() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0141() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0142() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0143() -> None:
    """stamp=None, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(None, 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0144() -> None:
    """stamp=nan, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0145() -> None:
    """stamp=nan, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0146() -> None:
    """stamp=nan, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0147() -> None:
    """stamp=nan, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0148() -> None:
    """stamp=nan, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0149() -> None:
    """stamp=nan, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0150() -> None:
    """stamp=nan, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0151() -> None:
    """stamp=nan, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0152() -> None:
    """stamp=nan, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0153() -> None:
    """stamp=nan, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0154() -> None:
    """stamp=nan, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0155() -> None:
    """stamp=nan, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0156() -> None:
    """stamp=nan, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0157() -> None:
    """stamp=nan, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0158() -> None:
    """stamp=nan, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0159() -> None:
    """stamp=nan, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0160() -> None:
    """stamp=nan, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0161() -> None:
    """stamp=nan, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0162() -> None:
    """stamp=nan, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0163() -> None:
    """stamp=nan, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0164() -> None:
    """stamp=nan, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0165() -> None:
    """stamp=nan, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0166() -> None:
    """stamp=nan, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0167() -> None:
    """stamp=nan, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0168() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0169() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0170() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0171() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0172() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0173() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0174() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0175() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0176() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0177() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0178() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0179() -> None:
    """stamp=nan, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('nan'), 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0180() -> None:
    """stamp=inf, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0181() -> None:
    """stamp=inf, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0182() -> None:
    """stamp=inf, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0183() -> None:
    """stamp=inf, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0184() -> None:
    """stamp=inf, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0185() -> None:
    """stamp=inf, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0186() -> None:
    """stamp=inf, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0187() -> None:
    """stamp=inf, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0188() -> None:
    """stamp=inf, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0189() -> None:
    """stamp=inf, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0190() -> None:
    """stamp=inf, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0191() -> None:
    """stamp=inf, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0192() -> None:
    """stamp=inf, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0193() -> None:
    """stamp=inf, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0194() -> None:
    """stamp=inf, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0195() -> None:
    """stamp=inf, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0196() -> None:
    """stamp=inf, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0197() -> None:
    """stamp=inf, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0198() -> None:
    """stamp=inf, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0199() -> None:
    """stamp=inf, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0200() -> None:
    """stamp=inf, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0201() -> None:
    """stamp=inf, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0202() -> None:
    """stamp=inf, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0203() -> None:
    """stamp=inf, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0204() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0205() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0206() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0207() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0208() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0209() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0210() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0211() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0212() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0213() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0214() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0215() -> None:
    """stamp=inf, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('inf'), 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0216() -> None:
    """stamp=-inf, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0217() -> None:
    """stamp=-inf, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0218() -> None:
    """stamp=-inf, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0219() -> None:
    """stamp=-inf, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0220() -> None:
    """stamp=-inf, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0221() -> None:
    """stamp=-inf, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0222() -> None:
    """stamp=-inf, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0223() -> None:
    """stamp=-inf, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0224() -> None:
    """stamp=-inf, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0225() -> None:
    """stamp=-inf, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0226() -> None:
    """stamp=-inf, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0227() -> None:
    """stamp=-inf, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0228() -> None:
    """stamp=-inf, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0229() -> None:
    """stamp=-inf, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0230() -> None:
    """stamp=-inf, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0231() -> None:
    """stamp=-inf, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0232() -> None:
    """stamp=-inf, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0233() -> None:
    """stamp=-inf, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0234() -> None:
    """stamp=-inf, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0235() -> None:
    """stamp=-inf, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0236() -> None:
    """stamp=-inf, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0237() -> None:
    """stamp=-inf, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0238() -> None:
    """stamp=-inf, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0239() -> None:
    """stamp=-inf, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0240() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0241() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0242() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0243() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0244() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0245() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0246() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0247() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0248() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0249() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0250() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0251() -> None:
    """stamp=-inf, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(float('-inf'), 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0252() -> None:
    """stamp=-4.2, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0253() -> None:
    """stamp=-4.2, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0254() -> None:
    """stamp=-4.2, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0255() -> None:
    """stamp=-4.2, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0256() -> None:
    """stamp=-4.2, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0257() -> None:
    """stamp=-4.2, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0258() -> None:
    """stamp=-4.2, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0259() -> None:
    """stamp=-4.2, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0260() -> None:
    """stamp=-4.2, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0261() -> None:
    """stamp=-4.2, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0262() -> None:
    """stamp=-4.2, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0263() -> None:
    """stamp=-4.2, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0264() -> None:
    """stamp=-4.2, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0265() -> None:
    """stamp=-4.2, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0266() -> None:
    """stamp=-4.2, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0267() -> None:
    """stamp=-4.2, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0268() -> None:
    """stamp=-4.2, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0269() -> None:
    """stamp=-4.2, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0270() -> None:
    """stamp=-4.2, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0271() -> None:
    """stamp=-4.2, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0272() -> None:
    """stamp=-4.2, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0273() -> None:
    """stamp=-4.2, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0274() -> None:
    """stamp=-4.2, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0275() -> None:
    """stamp=-4.2, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0276() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0277() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0278() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0279() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0280() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0281() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0282() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0283() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0284() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0285() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0286() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0287() -> None:
    """stamp=-4.2, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(-4.2, 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0288() -> None:
    """stamp=0, label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0289() -> None:
    """stamp=0, label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0290() -> None:
    """stamp=0, label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0291() -> None:
    """stamp=0, label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0292() -> None:
    """stamp=0, label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0293() -> None:
    """stamp=0, label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0294() -> None:
    """stamp=0, label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0295() -> None:
    """stamp=0, label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0296() -> None:
    """stamp=0, label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0297() -> None:
    """stamp=0, label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0298() -> None:
    """stamp=0, label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0299() -> None:
    """stamp=0, label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0300() -> None:
    """stamp=0, label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0301() -> None:
    """stamp=0, label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0302() -> None:
    """stamp=0, label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0303() -> None:
    """stamp=0, label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0304() -> None:
    """stamp=0, label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0305() -> None:
    """stamp=0, label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0306() -> None:
    """stamp=0, label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0307() -> None:
    """stamp=0, label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0308() -> None:
    """stamp=0, label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0309() -> None:
    """stamp=0, label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0310() -> None:
    """stamp=0, label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0311() -> None:
    """stamp=0, label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(0, None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0312() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0313() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0314() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0315() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0316() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0317() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0318() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0319() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0320() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0321() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0322() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0323() -> None:
    """stamp=0, label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier(0, 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0324() -> None:
    """stamp=(1+1j), label='take', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0325() -> None:
    """stamp=(1+1j), label='take', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0326() -> None:
    """stamp=(1+1j), label='take', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0327() -> None:
    """stamp=(1+1j), label='take', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0328() -> None:
    """stamp=(1+1j), label='take', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0329() -> None:
    """stamp=(1+1j), label='take', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0330() -> None:
    """stamp=(1+1j), label='take', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0331() -> None:
    """stamp=(1+1j), label='take', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0332() -> None:
    """stamp=(1+1j), label='take', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0333() -> None:
    """stamp=(1+1j), label='take', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0334() -> None:
    """stamp=(1+1j), label='take', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0335() -> None:
    """stamp=(1+1j), label='take', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'take'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=take exception_type=SimpleNamespace'
    )


def test_h0336() -> None:
    """stamp=(1+1j), label=None, attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0337() -> None:
    """stamp=(1+1j), label=None, attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0338() -> None:
    """stamp=(1+1j), label=None, attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0339() -> None:
    """stamp=(1+1j), label=None, attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0340() -> None:
    """stamp=(1+1j), label=None, attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0341() -> None:
    """stamp=(1+1j), label=None, attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0342() -> None:
    """stamp=(1+1j), label=None, attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0343() -> None:
    """stamp=(1+1j), label=None, attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0344() -> None:
    """stamp=(1+1j), label=None, attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0345() -> None:
    """stamp=(1+1j), label=None, attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0346() -> None:
    """stamp=(1+1j), label=None, attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0347() -> None:
    """stamp=(1+1j), label=None, attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), None), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 exception_type=SimpleNamespace'
    )


def test_h0348() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=0, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0349() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=0, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0350() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=1, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=1, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0351() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=1, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=1, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=1 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0352() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=2, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=2, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0353() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=2, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=2, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=2 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0354() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=5, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=5, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0355() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=5, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=5, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=5 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0356() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=7, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=7, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0357() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=7, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=7, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=7 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0358() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=11, cap=4."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


def test_h0359() -> None:
    """stamp=(1+1j), label='batch_claim shard=scheduler_07', attempt=11, cap=6."""
    level, line = drain_backstop_report(_carrier((1 + 1j), 'batch_claim shard=scheduler_07'), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=0 operation=batch_claim shard=scheduler_07 exception_type=SimpleNamespace'
    )


# hostile-storm band: 360 cells
