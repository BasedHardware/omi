"""Generated band: the backstop line's label vocabulary.

Every documented valid label shape reports its operation field;
every hostile shape reports nothing rather than interpolating
unvalidated text into the line. Spec-computed cell by cell.

Failure-Class: FC-drain-cap-storm-handoff-booked-as-production-error
"""

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.pump import drain_backstop_report


def _err(stamp, label, cls):
    """A contention exhaustion carrying the case's window and label."""
    return cls('drain storm', retry_after=stamp, operation=label)


def test_v0000() -> None:
    """label='finish', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0001() -> None:
    """label='finish', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0002() -> None:
    """label='finish', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0003() -> None:
    """label='finish', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0004() -> None:
    """label='finish', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0005() -> None:
    """label='finish', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0006() -> None:
    """label='finish', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0007() -> None:
    """label='finish', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0008() -> None:
    """label='finish', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0009() -> None:
    """label='finish', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0010() -> None:
    """label='finish', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'finish', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0011() -> None:
    """label='finish', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'finish', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=finish exception_type=FirestoreContentionExhausted'
    )


def test_v0012() -> None:
    """label='offer', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0013() -> None:
    """label='offer', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0014() -> None:
    """label='offer', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0015() -> None:
    """label='offer', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0016() -> None:
    """label='offer', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0017() -> None:
    """label='offer', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0018() -> None:
    """label='offer', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0019() -> None:
    """label='offer', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0020() -> None:
    """label='offer', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0021() -> None:
    """label='offer', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0022() -> None:
    """label='offer', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'offer', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0023() -> None:
    """label='offer', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'offer', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=offer exception_type=FirestoreContentionExhausted'
    )


def test_v0024() -> None:
    """label='reserve', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0025() -> None:
    """label='reserve', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0026() -> None:
    """label='reserve', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0027() -> None:
    """label='reserve', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0028() -> None:
    """label='reserve', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0029() -> None:
    """label='reserve', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0030() -> None:
    """label='reserve', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0031() -> None:
    """label='reserve', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0032() -> None:
    """label='reserve', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0033() -> None:
    """label='reserve', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0034() -> None:
    """label='reserve', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'reserve', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0035() -> None:
    """label='reserve', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'reserve', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=reserve exception_type=FirestoreContentionExhausted'
    )


def test_v0036() -> None:
    """label='ready', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0037() -> None:
    """label='ready', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0038() -> None:
    """label='ready', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0039() -> None:
    """label='ready', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0040() -> None:
    """label='ready', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0041() -> None:
    """label='ready', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0042() -> None:
    """label='ready', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0043() -> None:
    """label='ready', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0044() -> None:
    """label='ready', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0045() -> None:
    """label='ready', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0046() -> None:
    """label='ready', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'ready', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0047() -> None:
    """label='ready', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'ready', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=ready exception_type=FirestoreContentionExhausted'
    )


def test_v0048() -> None:
    """label='projection_input', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0049() -> None:
    """label='projection_input', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0050() -> None:
    """label='projection_input', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0051() -> None:
    """label='projection_input', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0052() -> None:
    """label='projection_input', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0053() -> None:
    """label='projection_input', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0054() -> None:
    """label='projection_input', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0055() -> None:
    """label='projection_input', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0056() -> None:
    """label='projection_input', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0057() -> None:
    """label='projection_input', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0058() -> None:
    """label='projection_input', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'projection_input', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0059() -> None:
    """label='projection_input', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'projection_input', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=projection_input exception_type=FirestoreContentionExhausted'
    )


def test_v0060() -> None:
    """label='take', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0061() -> None:
    """label='take', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0062() -> None:
    """label='take', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0063() -> None:
    """label='take', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0064() -> None:
    """label='take', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0065() -> None:
    """label='take', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0066() -> None:
    """label='take', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0067() -> None:
    """label='take', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0068() -> None:
    """label='take', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0069() -> None:
    """label='take', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0070() -> None:
    """label='take', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0071() -> None:
    """label='take', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=take exception_type=FirestoreContentionExhausted'
    )


def test_v0072() -> None:
    """label='paid', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0073() -> None:
    """label='paid', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0074() -> None:
    """label='paid', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0075() -> None:
    """label='paid', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0076() -> None:
    """label='paid', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0077() -> None:
    """label='paid', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0078() -> None:
    """label='paid', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0079() -> None:
    """label='paid', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0080() -> None:
    """label='paid', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0081() -> None:
    """label='paid', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0082() -> None:
    """label='paid', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'paid', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0083() -> None:
    """label='paid', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'paid', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=paid exception_type=FirestoreContentionExhausted'
    )


def test_v0084() -> None:
    """label='handoff', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0085() -> None:
    """label='handoff', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0086() -> None:
    """label='handoff', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0087() -> None:
    """label='handoff', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0088() -> None:
    """label='handoff', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0089() -> None:
    """label='handoff', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0090() -> None:
    """label='handoff', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0091() -> None:
    """label='handoff', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0092() -> None:
    """label='handoff', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0093() -> None:
    """label='handoff', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0094() -> None:
    """label='handoff', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'handoff', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0095() -> None:
    """label='handoff', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'handoff', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=handoff exception_type=FirestoreContentionExhausted'
    )


def test_v0096() -> None:
    """label='start_recovery', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0097() -> None:
    """label='start_recovery', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0098() -> None:
    """label='start_recovery', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0099() -> None:
    """label='start_recovery', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0100() -> None:
    """label='start_recovery', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0101() -> None:
    """label='start_recovery', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0102() -> None:
    """label='start_recovery', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0103() -> None:
    """label='start_recovery', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0104() -> None:
    """label='start_recovery', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0105() -> None:
    """label='start_recovery', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0106() -> None:
    """label='start_recovery', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'start_recovery', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0107() -> None:
    """label='start_recovery', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'start_recovery', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=start_recovery exception_type=FirestoreContentionExhausted'
    )


def test_v0108() -> None:
    """label='recovery_transport_failed', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0109() -> None:
    """label='recovery_transport_failed', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0110() -> None:
    """label='recovery_transport_failed', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0111() -> None:
    """label='recovery_transport_failed', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0112() -> None:
    """label='recovery_transport_failed', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0113() -> None:
    """label='recovery_transport_failed', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0114() -> None:
    """label='recovery_transport_failed', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0115() -> None:
    """label='recovery_transport_failed', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0116() -> None:
    """label='recovery_transport_failed', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0117() -> None:
    """label='recovery_transport_failed', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0118() -> None:
    """label='recovery_transport_failed', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0119() -> None:
    """label='recovery_transport_failed', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'recovery_transport_failed', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=recovery_transport_failed exception_type=FirestoreContentionExhausted'
    )


def test_v0120() -> None:
    """label='batch_pull shard=scheduler_00', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0121() -> None:
    """label='batch_pull shard=scheduler_00', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0122() -> None:
    """label='batch_pull shard=scheduler_00', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0123() -> None:
    """label='batch_pull shard=scheduler_00', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0124() -> None:
    """label='batch_pull shard=scheduler_00', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0125() -> None:
    """label='batch_pull shard=scheduler_00', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0126() -> None:
    """label='batch_pull shard=scheduler_00', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0127() -> None:
    """label='batch_pull shard=scheduler_00', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0128() -> None:
    """label='batch_pull shard=scheduler_00', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0129() -> None:
    """label='batch_pull shard=scheduler_00', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0130() -> None:
    """label='batch_pull shard=scheduler_00', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0131() -> None:
    """label='batch_pull shard=scheduler_00', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_00', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_00 exception_type=FirestoreContentionExhausted'
    )


def test_v0132() -> None:
    """label='batch_pull shard=scheduler_31', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0133() -> None:
    """label='batch_pull shard=scheduler_31', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0134() -> None:
    """label='batch_pull shard=scheduler_31', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0135() -> None:
    """label='batch_pull shard=scheduler_31', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0136() -> None:
    """label='batch_pull shard=scheduler_31', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0137() -> None:
    """label='batch_pull shard=scheduler_31', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0138() -> None:
    """label='batch_pull shard=scheduler_31', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0139() -> None:
    """label='batch_pull shard=scheduler_31', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0140() -> None:
    """label='batch_pull shard=scheduler_31', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0141() -> None:
    """label='batch_pull shard=scheduler_31', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0142() -> None:
    """label='batch_pull shard=scheduler_31', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0143() -> None:
    """label='batch_pull shard=scheduler_31', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_31', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=batch_pull shard=scheduler_31 exception_type=FirestoreContentionExhausted'
    )


def test_v0144() -> None:
    """label='batch_claim shard=scheduler_07', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0145() -> None:
    """label='batch_claim shard=scheduler_07', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0146() -> None:
    """label='batch_claim shard=scheduler_07', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0147() -> None:
    """label='batch_claim shard=scheduler_07', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0148() -> None:
    """label='batch_claim shard=scheduler_07', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0149() -> None:
    """label='batch_claim shard=scheduler_07', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0150() -> None:
    """label='batch_claim shard=scheduler_07', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0151() -> None:
    """label='batch_claim shard=scheduler_07', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0152() -> None:
    """label='batch_claim shard=scheduler_07', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0153() -> None:
    """label='batch_claim shard=scheduler_07', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0154() -> None:
    """label='batch_claim shard=scheduler_07', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0155() -> None:
    """label='batch_claim shard=scheduler_07', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_07', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_07 exception_type=FirestoreContentionExhausted'
    )


def test_v0156() -> None:
    """label='batch_claim shard=scheduler_63', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0157() -> None:
    """label='batch_claim shard=scheduler_63', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0158() -> None:
    """label='batch_claim shard=scheduler_63', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0159() -> None:
    """label='batch_claim shard=scheduler_63', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0160() -> None:
    """label='batch_claim shard=scheduler_63', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0161() -> None:
    """label='batch_claim shard=scheduler_63', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0162() -> None:
    """label='batch_claim shard=scheduler_63', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0163() -> None:
    """label='batch_claim shard=scheduler_63', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0164() -> None:
    """label='batch_claim shard=scheduler_63', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0165() -> None:
    """label='batch_claim shard=scheduler_63', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0166() -> None:
    """label='batch_claim shard=scheduler_63', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0167() -> None:
    """label='batch_claim shard=scheduler_63', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_claim shard=scheduler_63', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 operation=batch_claim shard=scheduler_63 exception_type=FirestoreContentionExhausted'
    )


def test_v0168() -> None:
    """label='', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0169() -> None:
    """label='', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0170() -> None:
    """label='', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0171() -> None:
    """label='', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0172() -> None:
    """label='', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0173() -> None:
    """label='', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0174() -> None:
    """label='', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0175() -> None:
    """label='', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0176() -> None:
    """label='', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0177() -> None:
    """label='', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0178() -> None:
    """label='', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0179() -> None:
    """label='', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0180() -> None:
    """label='UPPER', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0181() -> None:
    """label='UPPER', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0182() -> None:
    """label='UPPER', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0183() -> None:
    """label='UPPER', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0184() -> None:
    """label='UPPER', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0185() -> None:
    """label='UPPER', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0186() -> None:
    """label='UPPER', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0187() -> None:
    """label='UPPER', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0188() -> None:
    """label='UPPER', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0189() -> None:
    """label='UPPER', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0190() -> None:
    """label='UPPER', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'UPPER', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0191() -> None:
    """label='UPPER', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'UPPER', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0192() -> None:
    """label='9lead', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0193() -> None:
    """label='9lead', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0194() -> None:
    """label='9lead', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0195() -> None:
    """label='9lead', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0196() -> None:
    """label='9lead', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0197() -> None:
    """label='9lead', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0198() -> None:
    """label='9lead', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0199() -> None:
    """label='9lead', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0200() -> None:
    """label='9lead', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0201() -> None:
    """label='9lead', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0202() -> None:
    """label='9lead', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, '9lead', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0203() -> None:
    """label='9lead', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, '9lead', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0204() -> None:
    """label='has space', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0205() -> None:
    """label='has space', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0206() -> None:
    """label='has space', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0207() -> None:
    """label='has space', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0208() -> None:
    """label='has space', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0209() -> None:
    """label='has space', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0210() -> None:
    """label='has space', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0211() -> None:
    """label='has space', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0212() -> None:
    """label='has space', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0213() -> None:
    """label='has space', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0214() -> None:
    """label='has space', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'has space', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0215() -> None:
    """label='has space', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'has space', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0216() -> None:
    """label='drop table owners', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0217() -> None:
    """label='drop table owners', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0218() -> None:
    """label='drop table owners', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0219() -> None:
    """label='drop table owners', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0220() -> None:
    """label='drop table owners', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0221() -> None:
    """label='drop table owners', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0222() -> None:
    """label='drop table owners', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0223() -> None:
    """label='drop table owners', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0224() -> None:
    """label='drop table owners', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0225() -> None:
    """label='drop table owners', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0226() -> None:
    """label='drop table owners', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'drop table owners', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0227() -> None:
    """label='drop table owners', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'drop table owners', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0228() -> None:
    """label='batch_pull shard=scheduler_64', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0229() -> None:
    """label='batch_pull shard=scheduler_64', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0230() -> None:
    """label='batch_pull shard=scheduler_64', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0231() -> None:
    """label='batch_pull shard=scheduler_64', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0232() -> None:
    """label='batch_pull shard=scheduler_64', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0233() -> None:
    """label='batch_pull shard=scheduler_64', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0234() -> None:
    """label='batch_pull shard=scheduler_64', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0235() -> None:
    """label='batch_pull shard=scheduler_64', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0236() -> None:
    """label='batch_pull shard=scheduler_64', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0237() -> None:
    """label='batch_pull shard=scheduler_64', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0238() -> None:
    """label='batch_pull shard=scheduler_64', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0239() -> None:
    """label='batch_pull shard=scheduler_64', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_64', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0240() -> None:
    """label='batch_pull shard=scheduler_000', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0241() -> None:
    """label='batch_pull shard=scheduler_000', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0242() -> None:
    """label='batch_pull shard=scheduler_000', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0243() -> None:
    """label='batch_pull shard=scheduler_000', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0244() -> None:
    """label='batch_pull shard=scheduler_000', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0245() -> None:
    """label='batch_pull shard=scheduler_000', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0246() -> None:
    """label='batch_pull shard=scheduler_000', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0247() -> None:
    """label='batch_pull shard=scheduler_000', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0248() -> None:
    """label='batch_pull shard=scheduler_000', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0249() -> None:
    """label='batch_pull shard=scheduler_000', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0250() -> None:
    """label='batch_pull shard=scheduler_000', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0251() -> None:
    """label='batch_pull shard=scheduler_000', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_000', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0252() -> None:
    """label='take;', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0253() -> None:
    """label='take;', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=0, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0254() -> None:
    """label='take;', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0255() -> None:
    """label='take;', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=0, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0256() -> None:
    """label='take;', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0257() -> None:
    """label='take;', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=6, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0258() -> None:
    """label='take;', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0259() -> None:
    """label='take;', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=6, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0260() -> None:
    """label='take;', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0261() -> None:
    """label='take;', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=11, cap=4)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0262() -> None:
    """label='take;', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(_err(4.2, 'take;', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0263() -> None:
    """label='take;', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(_err(7.7, 'take;', FirestoreContentionExhausted), attempt=11, cap=6)
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0264() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=0,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0265() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=0,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0266() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=0,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0267() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=0,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0268() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=6,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0269() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=6,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0270() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=6,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0271() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=6,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0272() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=11,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0273() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=11,
        cap=4,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0274() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=11,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0275() -> None:
    """label='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', FirestoreContentionExhausted),
        attempt=11,
        cap=6,
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0276() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=0, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0277() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=0, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=0, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0278() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=0, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0279() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=0, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=0, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=0 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0280() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=6, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0281() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=6, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=6, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0282() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=6, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0283() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=6, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=6, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=6 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0284() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=11, cap=4, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0285() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=11, cap=4, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=11, cap=4
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=4 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


def test_v0286() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=11, cap=6, stamp=4.20."""
    level, line = drain_backstop_report(
        _err(4.2, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=4200 exception_type=FirestoreContentionExhausted'
    )


def test_v0287() -> None:
    """label='batch_pull shard=scheduler_0a', attempt=11, cap=6, stamp=7.70."""
    level, line = drain_backstop_report(
        _err(7.7, 'batch_pull shard=scheduler_0a', FirestoreContentionExhausted), attempt=11, cap=6
    )
    assert level == 30
    assert (
        line
        == 'event=batch_merge_drain outcome=maintenance_backstop attempt=11 cap=6 retry_after_ms=7700 exception_type=FirestoreContentionExhausted'
    )


# vocabulary band: 288 cells
