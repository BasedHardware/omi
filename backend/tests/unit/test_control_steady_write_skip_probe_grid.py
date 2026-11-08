"""Control steady-write skip: activation probe value grid."""

from tests.unit.control_steady_skip_fleet_helpers import *  # noqa: F401,F403


def test_probe_empty_0_0p0_0p0_0p0():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        0.0,
        0.0,
    )


def test_probe_empty_0_0p0_5p0_9p5():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        5.0,
        9.5,
    )


def test_probe_empty_0_0p0_0p0_4p0():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        0.0,
        4.0,
    )


def test_probe_empty_0_0p0_6p5_0p0():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        6.5,
        0.0,
    )


def test_probe_empty_0_0p0_12p0_3p0():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        12.0,
        3.0,
    )


def test_probe_empty_0_0p0_0p0_100p0():
    cell(
        sample_control(rings='empty', active=False, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        False,
        0.0,
        0.0,
        100.0,
    )


def test_probe_empty_0_1p5_0p0_0p0():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        0.0,
        0.0,
    )


def test_probe_empty_0_1p5_5p0_9p5():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        5.0,
        9.5,
    )


def test_probe_empty_0_1p5_0p0_4p0():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        0.0,
        4.0,
    )


def test_probe_empty_0_1p5_6p5_0p0():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        6.5,
        0.0,
    )


def test_probe_empty_0_1p5_12p0_3p0():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        12.0,
        3.0,
    )


def test_probe_empty_0_1p5_0p0_100p0():
    cell(
        sample_control(rings='empty', active=False, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        False,
        1.5,
        0.0,
        100.0,
    )


def test_probe_empty_0_7p25_0p0_0p0():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        0.0,
        0.0,
    )


def test_probe_empty_0_7p25_5p0_9p5():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        5.0,
        9.5,
    )


def test_probe_empty_0_7p25_0p0_4p0():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        0.0,
        4.0,
    )


def test_probe_empty_0_7p25_6p5_0p0():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        6.5,
        0.0,
    )


def test_probe_empty_0_7p25_12p0_3p0():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        12.0,
        3.0,
    )


def test_probe_empty_0_7p25_0p0_100p0():
    cell(
        sample_control(rings='empty', active=False, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        False,
        7.25,
        0.0,
        100.0,
    )


def test_probe_empty_1_0p0_0p0_0p0():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        0.0,
        0.0,
    )


def test_probe_empty_1_0p0_5p0_9p5():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        5.0,
        9.5,
    )


def test_probe_empty_1_0p0_0p0_4p0():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        0.0,
        4.0,
    )


def test_probe_empty_1_0p0_6p5_0p0():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        6.5,
        0.0,
    )


def test_probe_empty_1_0p0_12p0_3p0():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        12.0,
        3.0,
    )


def test_probe_empty_1_0p0_0p0_100p0():
    cell(
        sample_control(rings='empty', active=True, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        True,
        0.0,
        0.0,
        100.0,
    )


def test_probe_empty_1_1p5_0p0_0p0():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        0.0,
        0.0,
    )


def test_probe_empty_1_1p5_5p0_9p5():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        5.0,
        9.5,
    )


def test_probe_empty_1_1p5_0p0_4p0():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        0.0,
        4.0,
    )


def test_probe_empty_1_1p5_6p5_0p0():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        6.5,
        0.0,
    )


def test_probe_empty_1_1p5_12p0_3p0():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        12.0,
        3.0,
    )


def test_probe_empty_1_1p5_0p0_100p0():
    cell(
        sample_control(rings='empty', active=True, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        True,
        1.5,
        0.0,
        100.0,
    )


def test_probe_empty_1_7p25_0p0_0p0():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        0.0,
        0.0,
    )


def test_probe_empty_1_7p25_5p0_9p5():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        5.0,
        9.5,
    )


def test_probe_empty_1_7p25_0p0_4p0():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        0.0,
        4.0,
    )


def test_probe_empty_1_7p25_6p5_0p0():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        6.5,
        0.0,
    )


def test_probe_empty_1_7p25_12p0_3p0():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        12.0,
        3.0,
    )


def test_probe_empty_1_7p25_0p0_100p0():
    cell(
        sample_control(rings='empty', active=True, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        False,
        0,
        True,
        7.25,
        0.0,
        100.0,
    )


def test_probe_member_0_0p0_0p0_0p0():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        0.0,
        0.0,
    )


def test_probe_member_0_0p0_5p0_9p5():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        5.0,
        9.5,
    )


def test_probe_member_0_0p0_0p0_4p0():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        0.0,
        4.0,
    )


def test_probe_member_0_0p0_6p5_0p0():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        6.5,
        0.0,
    )


def test_probe_member_0_0p0_12p0_3p0():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        12.0,
        3.0,
    )


def test_probe_member_0_0p0_0p0_100p0():
    cell(
        sample_control(rings='member', active=False, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        False,
        0.0,
        0.0,
        100.0,
    )


def test_probe_member_0_1p5_0p0_0p0():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        0.0,
        0.0,
    )


def test_probe_member_0_1p5_5p0_9p5():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        5.0,
        9.5,
    )


def test_probe_member_0_1p5_0p0_4p0():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        0.0,
        4.0,
    )


def test_probe_member_0_1p5_6p5_0p0():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        6.5,
        0.0,
    )


def test_probe_member_0_1p5_12p0_3p0():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        12.0,
        3.0,
    )


def test_probe_member_0_1p5_0p0_100p0():
    cell(
        sample_control(rings='member', active=False, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        False,
        1.5,
        0.0,
        100.0,
    )


def test_probe_member_0_7p25_0p0_0p0():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        0.0,
        0.0,
    )


def test_probe_member_0_7p25_5p0_9p5():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        5.0,
        9.5,
    )


def test_probe_member_0_7p25_0p0_4p0():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        0.0,
        4.0,
    )


def test_probe_member_0_7p25_6p5_0p0():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        6.5,
        0.0,
    )


def test_probe_member_0_7p25_12p0_3p0():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        12.0,
        3.0,
    )


def test_probe_member_0_7p25_0p0_100p0():
    cell(
        sample_control(rings='member', active=False, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        False,
        7.25,
        0.0,
        100.0,
    )


def test_probe_member_1_0p0_0p0_0p0():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        0.0,
        0.0,
    )


def test_probe_member_1_0p0_5p0_9p5():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        5.0,
        9.5,
    )


def test_probe_member_1_0p0_0p0_4p0():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        0.0,
        4.0,
    )


def test_probe_member_1_0p0_6p5_0p0():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        6.5,
        0.0,
    )


def test_probe_member_1_0p0_12p0_3p0():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        12.0,
        3.0,
    )


def test_probe_member_1_0p0_0p0_100p0():
    cell(
        sample_control(rings='member', active=True, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        True,
        0.0,
        0.0,
        100.0,
    )


def test_probe_member_1_1p5_0p0_0p0():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        0.0,
        0.0,
    )


def test_probe_member_1_1p5_5p0_9p5():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        5.0,
        9.5,
    )


def test_probe_member_1_1p5_0p0_4p0():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        0.0,
        4.0,
    )


def test_probe_member_1_1p5_6p5_0p0():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        6.5,
        0.0,
    )


def test_probe_member_1_1p5_12p0_3p0():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        12.0,
        3.0,
    )


def test_probe_member_1_1p5_0p0_100p0():
    cell(
        sample_control(rings='member', active=True, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        True,
        1.5,
        0.0,
        100.0,
    )


def test_probe_member_1_7p25_0p0_0p0():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        0.0,
        0.0,
    )


def test_probe_member_1_7p25_5p0_9p5():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        5.0,
        9.5,
    )


def test_probe_member_1_7p25_0p0_4p0():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        0.0,
        4.0,
    )


def test_probe_member_1_7p25_6p5_0p0():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        6.5,
        0.0,
    )


def test_probe_member_1_7p25_12p0_3p0():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        12.0,
        3.0,
    )


def test_probe_member_1_7p25_0p0_100p0():
    cell(
        sample_control(rings='member', active=True, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        1,
        True,
        7.25,
        0.0,
        100.0,
    )


def test_probe_three_0_0p0_0p0_0p0():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        0.0,
        0.0,
    )


def test_probe_three_0_0p0_5p0_9p5():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        5.0,
        9.5,
    )


def test_probe_three_0_0p0_0p0_4p0():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        0.0,
        4.0,
    )


def test_probe_three_0_0p0_6p5_0p0():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        6.5,
        0.0,
    )


def test_probe_three_0_0p0_12p0_3p0():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        12.0,
        3.0,
    )


def test_probe_three_0_0p0_0p0_100p0():
    cell(
        sample_control(rings='three', active=False, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        False,
        0.0,
        0.0,
        100.0,
    )


def test_probe_three_0_1p5_0p0_0p0():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        0.0,
        0.0,
    )


def test_probe_three_0_1p5_5p0_9p5():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        5.0,
        9.5,
    )


def test_probe_three_0_1p5_0p0_4p0():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        0.0,
        4.0,
    )


def test_probe_three_0_1p5_6p5_0p0():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        6.5,
        0.0,
    )


def test_probe_three_0_1p5_12p0_3p0():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        12.0,
        3.0,
    )


def test_probe_three_0_1p5_0p0_100p0():
    cell(
        sample_control(rings='three', active=False, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        False,
        1.5,
        0.0,
        100.0,
    )


def test_probe_three_0_7p25_0p0_0p0():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        0.0,
        0.0,
    )


def test_probe_three_0_7p25_5p0_9p5():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        5.0,
        9.5,
    )


def test_probe_three_0_7p25_0p0_4p0():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        0.0,
        4.0,
    )


def test_probe_three_0_7p25_6p5_0p0():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        6.5,
        0.0,
    )


def test_probe_three_0_7p25_12p0_3p0():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        12.0,
        3.0,
    )


def test_probe_three_0_7p25_0p0_100p0():
    cell(
        sample_control(rings='three', active=False, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        False,
        7.25,
        0.0,
        100.0,
    )


def test_probe_three_1_0p0_0p0_0p0():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        0.0,
        0.0,
    )


def test_probe_three_1_0p0_5p0_9p5():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        5.0,
        9.5,
    )


def test_probe_three_1_0p0_0p0_4p0():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        0.0,
        4.0,
    )


def test_probe_three_1_0p0_6p5_0p0():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        6.5,
        0.0,
    )


def test_probe_three_1_0p0_12p0_3p0():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        12.0,
        3.0,
    )


def test_probe_three_1_0p0_0p0_100p0():
    cell(
        sample_control(rings='three', active=True, service=0.0, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        True,
        0.0,
        0.0,
        100.0,
    )


def test_probe_three_1_1p5_0p0_0p0():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        0.0,
        0.0,
    )


def test_probe_three_1_1p5_5p0_9p5():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        5.0,
        9.5,
    )


def test_probe_three_1_1p5_0p0_4p0():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        0.0,
        4.0,
    )


def test_probe_three_1_1p5_6p5_0p0():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        6.5,
        0.0,
    )


def test_probe_three_1_1p5_12p0_3p0():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        12.0,
        3.0,
    )


def test_probe_three_1_1p5_0p0_100p0():
    cell(
        sample_control(rings='three', active=True, service=1.5, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        True,
        1.5,
        0.0,
        100.0,
    )


def test_probe_three_1_7p25_0p0_0p0():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=0.0, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        0.0,
        0.0,
    )


def test_probe_three_1_7p25_5p0_9p5():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=5.0, live=9.5),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        5.0,
        9.5,
    )


def test_probe_three_1_7p25_0p0_4p0():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=0.0, live=4.0),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        0.0,
        4.0,
    )


def test_probe_three_1_7p25_6p5_0p0():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=6.5, live=0.0),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        6.5,
        0.0,
    )


def test_probe_three_1_7p25_12p0_3p0():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=12.0, live=3.0),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        12.0,
        3.0,
    )


def test_probe_three_1_7p25_0p0_100p0():
    cell(
        sample_control(rings='three', active=True, service=7.25, batch=0.0, live=100.0),
        2,
        QUEUE,
        True,
        3,
        True,
        7.25,
        0.0,
        100.0,
    )


def test_probe_fresh_0_0p0_reads_the_fresh_cells():
    cell(
        sample_control(rings="fresh", priority=0, active=False, service=0.0),
        0,
        FRESH_QUEUE,
        True,
        1,
        False,
        0.0,
        0.0,
        0.0,
    )


def test_probe_fresh_0_2p0_reads_the_fresh_cells():
    cell(
        sample_control(rings="fresh", priority=0, active=False, service=2.0),
        0,
        FRESH_QUEUE,
        True,
        1,
        False,
        2.0,
        0.0,
        0.0,
    )


def test_probe_fresh_1_0p0_reads_the_fresh_cells():
    cell(
        sample_control(rings="fresh", priority=0, active=True, service=0.0),
        0,
        FRESH_QUEUE,
        True,
        1,
        True,
        0.0,
        0.0,
        0.0,
    )


def test_probe_fresh_1_2p0_reads_the_fresh_cells():
    cell(
        sample_control(rings="fresh", priority=0, active=True, service=2.0),
        0,
        FRESH_QUEUE,
        True,
        1,
        True,
        2.0,
        0.0,
        0.0,
    )


def test_probe_fresh_nonmember_reads_the_defaults():
    cell(sample_control(rings="empty"), 0, FRESH_QUEUE, False, 0, False, 0.0, 0.0, 0.0)


def test_probe_gone_document_reads_the_pure_defaults():
    cell(sample_control(rings="gone"), 2, QUEUE, False, 0, False, None, None, None)


def test_probe_gone_document_reads_the_fresh_defaults():
    cell(sample_control(rings="gone"), 0, FRESH_QUEUE, False, 0, False, None, None, None)


def test_probe_member_document_under_priority_zero_reads_zero_cells():
    cell(sample_control(rings="member", active=True), 0, FRESH_QUEUE, False, 0, False, 0.0, 0.0, 0.0)


def test_probe_is_pure_over_a_warm_document():
    from copy import deepcopy

    doc = sample_control(rings="member", active=True, service=2.0)
    before = deepcopy(doc)
    probe(doc, 2, QUEUE)
    assert doc == before


def test_probe_injects_nothing_into_a_gone_document():
    doc = sample_control(rings="gone")
    probe(doc, 2, QUEUE)
    assert doc == {}


def test_probe_pair_is_stable_over_a_warm_document():
    doc = sample_control(rings="member", active=True)
    assert probe(doc, 2, QUEUE) == probe(doc, 2, QUEUE)


def test_probe_pair_flips_when_the_ring_gains_the_queue():
    doc = sample_control()
    before = probe(doc, 2, QUEUE)
    doc["rings"]["2"].append(QUEUE)
    assert probe(doc, 2, QUEUE) != before


def test_probe_pair_flips_when_the_ring_loses_the_queue():
    doc = sample_control(rings="member")
    before = probe(doc, 2, QUEUE)
    doc["rings"]["2"].remove(QUEUE)
    assert probe(doc, 2, QUEUE) != before


def test_probe_pair_flips_when_active_turns_on():
    doc = sample_control()
    before = probe(doc, 2, QUEUE)
    doc["p2_active"] = True
    assert probe(doc, 2, QUEUE) != before


def test_probe_pair_flips_when_the_frontier_seeds_service():
    doc = sample_control()
    before = probe(doc, 2, QUEUE)
    doc["p2_service"] = 5.0
    assert probe(doc, 2, QUEUE) != before


def test_probe_pair_flips_when_a_floor_lowers():
    doc = sample_control(batch=10.0)
    before = probe(doc, 2, QUEUE)
    doc["p2_batch_available_at"] = 4.0
    assert probe(doc, 2, QUEUE) != before


def test_probe_pair_stays_when_a_floor_is_already_minimum():
    doc = sample_control(batch=0.0)
    before = probe(doc, 2, QUEUE)
    doc["p2_batch_available_at"] = min(doc["p2_batch_available_at"], 100.0)
    assert probe(doc, 2, QUEUE) == before


def test_probe_pair_stays_when_service_reseeds_to_the_same_value():
    doc = sample_control(active=True, service=2.0)
    before = probe(doc, 2, QUEUE)
    doc["p2_service"] = max(doc["p2_service"], 2.0)
    assert probe(doc, 2, QUEUE) == before


def test_probe_pair_stays_when_the_other_priority_changes():
    doc = sample_control()
    before = probe(doc, 2, QUEUE)
    doc["rings"]["0"].append(FRESH_QUEUE)
    doc["p0_service"] = 9.0
    assert probe(doc, 2, QUEUE) == before


def test_probe_is_hashable_and_reproducible():
    doc = sample_control(active=True)
    assert probe(doc, 2, QUEUE) == probe(doc, 2, QUEUE)
    assert len(probe(doc, 2, QUEUE)) == 5


def test_probe_watches_only_its_own_priority_fields():
    doc = {
        'rings': {'0': [FRESH_QUEUE], '2': []},
        'p2_active': True,
        'p2_service': 3.0,
        'p2_batch_available_at': 0.0,
        'p2_live_available_at': 0.0,
    }
    got = probe(doc, 0, FRESH_QUEUE)
    assert got[0] == ('ring', 0, True, 1)
    assert got[1] == ('active', 0, False)
    assert got[2] == ('service', 0, None)
    assert got[3] == ('batch_available_at', 0, None)
    assert got[4] == ('live_available_at', 0, None)


def test_probe_extra_three_1_8p0_2p0():
    cell(
        sample_control(rings='three', active=True, service=4.5, batch=8.0, live=2.0),
        2,
        QUEUE,
        True,
        3,
        True,
        4.5,
        8.0,
        2.0,
    )


def test_probe_extra_three_0_8p0_2p0():
    cell(
        sample_control(rings='three', active=False, service=4.5, batch=8.0, live=2.0),
        2,
        QUEUE,
        True,
        3,
        False,
        4.5,
        8.0,
        2.0,
    )


def test_probe_extra_three_1_0p5_0p5():
    cell(
        sample_control(rings='three', active=True, service=4.5, batch=0.5, live=0.5),
        2,
        QUEUE,
        True,
        3,
        True,
        4.5,
        0.5,
        0.5,
    )


def test_probe_extra_three_0_0p5_0p5():
    cell(
        sample_control(rings='three', active=False, service=4.5, batch=0.5, live=0.5),
        2,
        QUEUE,
        True,
        3,
        False,
        4.5,
        0.5,
        0.5,
    )


def test_probe_extra_member_1_8p0_2p0():
    cell(
        sample_control(rings='member', active=True, service=4.5, batch=8.0, live=2.0),
        2,
        QUEUE,
        True,
        1,
        True,
        4.5,
        8.0,
        2.0,
    )


def test_probe_extra_member_0_8p0_2p0():
    cell(
        sample_control(rings='member', active=False, service=4.5, batch=8.0, live=2.0),
        2,
        QUEUE,
        True,
        1,
        False,
        4.5,
        8.0,
        2.0,
    )


def test_probe_extra_member_1_0p5_0p5():
    cell(
        sample_control(rings='member', active=True, service=4.5, batch=0.5, live=0.5),
        2,
        QUEUE,
        True,
        1,
        True,
        4.5,
        0.5,
        0.5,
    )


def test_probe_extra_member_0_0p5_0p5():
    cell(
        sample_control(rings='member', active=False, service=4.5, batch=0.5, live=0.5),
        2,
        QUEUE,
        True,
        1,
        False,
        4.5,
        0.5,
        0.5,
    )
