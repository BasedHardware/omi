"""Generated grid: bare-ladder shapes. Cross-verified cell by cell at emit time.

Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window

Each test re-drives its cell through the real boundary
(``drive_cell``) and compares the full observable freeze against the
literal the emit-time cross-verify produced; the independent model walk and
the emitter live outside the tree. Do not edit frozen literals by hand.
"""

from tests.unit.batch_projection_storm_gate_grid_harness import drive_cell


def _drive(monkeypatch, caplog, **params):
    return drive_cell(monkeypatch, caplog, **params)


def test_d_dorm_f1_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f1_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f2_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f3_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f4_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_dorm_f5_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='dormant_switch',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f1_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=1,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f2_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=2,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f3_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=3,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4],
        'sleeps': [0.15, 0.3, 0.6],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f4_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=4,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': 'projected',
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g0_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=0,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_inf_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='info',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en00000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.0,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_abo_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_abo_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_abo_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='aborted',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_exp_dmn00000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=None,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3],
        'sleeps': [0.15, 0.3],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_exp_dmn100000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=10.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'deadline_exhausted',
        'retry_after': 0.0,
        'body_calls': [1],
        'sleeps': [0.15],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }


def test_d_abse_f5_g4096_war_en05000_exp_dmn3000000(monkeypatch, caplog) -> None:
    assert _drive(
        monkeypatch,
        caplog,
        residual_schedule=[1.0, 1.0, 1.0, 1.0],
        wave_wait=0.5,
        damper_mode='absent_store',
        generation=4096,
        log_mode='warning',
        entry_wait=0.5,
        aborts=5,
        hostile_peek=False,
        deadline_margin=300.0,
        abort_kind='expired',
    ) == {
        'result': None,
        'raised': 'attempts_exhausted',
        'retry_after': 0.0,
        'body_calls': [1, 2, 3, 4, 5],
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }
