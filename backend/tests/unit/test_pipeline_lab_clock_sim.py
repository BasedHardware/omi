"""Pipeline lab clock, simulated mode: frozen wall clock and the product's monotonic and loop clocks."""

import asyncio
import datetime as dt
import sys
import threading
import time
import types

import pytest

from testing.pipeline_lab.stack import clock as clock_module
from testing.pipeline_lab.stack.clock import CLOCK_MODES, LabClock, installed_clock

T0 = dt.datetime(2026, 3, 14, 9, 0, tzinfo=dt.timezone.utc)

_FIXTURE_SOURCE = '''
import asyncio
import time
from time import monotonic


def read_attr():
    return time.monotonic()


def read_bound():
    return monotonic()


def read_ns():
    return time.monotonic_ns()


async def read_loop():
    return asyncio.get_running_loop().time()


def poll_until(seconds):
    """A product budget loop: ends only if monotonic advances within one event."""
    deadline = time.monotonic() + seconds
    spins = 0
    while time.monotonic() < deadline:
        time.sleep(0.005)
        spins += 1
    return spins
'''


@pytest.fixture()
def product_module():
    """A module whose ``__name__`` is under a product package, as ``utils.*`` code is."""
    name = 'utils.plab_clock_sim_fixture'
    module = types.ModuleType(name)
    exec(compile(_FIXTURE_SOURCE, name, 'exec'), module.__dict__)
    sys.modules[name] = module
    yield module
    sys.modules.pop(name, None)


def test_modes_and_frozen_sim_clock():
    assert CLOCK_MODES == ('sim', 'tick')
    clock = LabClock.for_mode(T0, 'sim')
    assert clock.mode == 'sim' and not clock.tick
    first = clock.timestamp()
    time.sleep(0.02)
    assert clock.timestamp() == first == T0.timestamp()
    clock.set(T0 + dt.timedelta(minutes=5))
    assert clock.now() == T0 + dt.timedelta(minutes=5)
    assert LabClock.for_mode(T0, 'tick').mode == 'tick'
    with pytest.raises(ValueError):
        LabClock.for_mode(T0, 'wall')


def test_sim_wall_clock_ignores_real_time_under_install():
    clock = LabClock.for_mode(T0, 'sim')
    with installed_clock(clock):
        before = time.time()
        time.sleep(0.02)
        assert time.time() == before == T0.timestamp()
        clock.set(T0 + dt.timedelta(hours=2))
        assert time.time() == (T0 + dt.timedelta(hours=2)).timestamp()


def test_product_monotonic_follows_the_replay_across_events(product_module):
    clock = LabClock.for_mode(T0, 'sim')
    with installed_clock(clock, product_monotonic=True):
        start = product_module.read_attr()
        assert product_module.read_bound() >= start  # ``from time import monotonic`` is patched too
        clock.set(T0 + dt.timedelta(hours=2))
        jumped = product_module.read_attr()
        # Two virtual hours passed: a deadline armed at 09:00 is over, as in production.
        assert jumped - start == pytest.approx(7200)
        assert abs(product_module.read_ns() / 1e9 - product_module.read_attr()) < 1
        # The lab (and every library) keeps real monotonic time.
        assert abs(time.monotonic() - clock_module._REAL_MONOTONIC()) < 1


def test_product_monotonic_is_frozen_within_the_grace(product_module):
    clock = LabClock.for_mode(T0, 'sim')
    with installed_clock(clock, product_monotonic=True):
        first = product_module.read_attr()
        time.sleep(0.02)
        assert product_module.read_attr() == first  # a lease checked at its expiry decides the same every run
    assert clock.late_monotonic_reads == 0


def test_product_monotonic_moves_after_the_grace_so_budget_loops_end(product_module):
    clock = LabClock.for_mode(T0, 'sim', monotonic_grace=0.02)
    with installed_clock(clock, product_monotonic=True):
        # A frozen monotonic would spin this budget loop forever; past the grace it ends.
        assert product_module.poll_until(0.05) >= 1
    assert clock.late_monotonic_reads >= 1
    clock.set(T0 + dt.timedelta(minutes=1))  # the next event starts frozen again
    assert clock.monotonic() == clock.monotonic()


def test_product_monotonic_never_decreases_when_set_goes_back(product_module):
    clock = LabClock.for_mode(T0 + dt.timedelta(hours=1), 'sim')
    with installed_clock(clock, product_monotonic=True):
        late = product_module.read_attr()
        clock.set(T0)
        assert product_module.read_attr() >= late


def test_loop_time_is_virtual_for_product_callers_only(product_module):
    clock = LabClock.for_mode(T0, 'sim')

    async def body():
        loop = asyncio.get_running_loop()
        product_before = await product_module.read_loop()
        clock.set(T0 + dt.timedelta(hours=1))
        product_after = await product_module.read_loop()
        real_before = loop.time()
        await asyncio.sleep(0.01)  # asyncio's scheduler still runs on real time: no hang
        await asyncio.wait_for(asyncio.sleep(0), timeout=1)
        return product_after - product_before, loop.time() - real_before

    with installed_clock(clock, product_monotonic=True):
        virtual, real = asyncio.run(body())
    assert virtual == pytest.approx(3600)
    assert 0 < real < 5


def test_threading_waits_stay_real_under_product_monotonic(product_module):
    clock = LabClock.for_mode(T0, 'sim')
    with installed_clock(clock, product_monotonic=True):
        clock.set(T0 + dt.timedelta(days=1))
        started = time.perf_counter()
        assert threading.Event().wait(0.02) is False
        assert time.perf_counter() - started < 2


def test_product_monotonic_is_opt_in_and_restored(product_module):
    real_monotonic, real_loop_time = time.monotonic, asyncio.BaseEventLoop.time
    clock = LabClock.for_mode(T0, 'sim')
    with installed_clock(clock):
        assert time.monotonic is real_monotonic  # scenarios and the classic chain keep real monotonic
        before = product_module.read_attr()
        clock.set(T0 + dt.timedelta(hours=3))
        assert product_module.read_attr() - before < 5
    with installed_clock(clock, product_monotonic=True):
        assert time.monotonic is not real_monotonic
    assert time.monotonic is real_monotonic and asyncio.BaseEventLoop.time is real_loop_time
    assert product_module.read_bound.__globals__['monotonic'] is real_monotonic


def test_classic_chain_runs_on_the_sim_clock_unless_the_v3_switch_says_tick():
    from testing.pipeline_lab.chain.run import chain_clock_mode
    from testing.pipeline_lab.stack.overlay import Overlay

    assert chain_clock_mode(Overlay()) == 'sim'
    assert chain_clock_mode(Overlay.from_mapping({'model_config': {'v3': {'clock': 'tick'}}})) == 'tick'
    with pytest.raises(ValueError, match='model_config.v3.clock'):
        chain_clock_mode(Overlay.from_mapping({'model_config': {'v3': {'clock': 'wall'}}}))


def test_chain_smoke_script_finds_homebrew_java_like_the_scenario_stack():
    from pathlib import Path

    from testing.pipeline_lab.scenario.stack import JAVA_HOMES

    script = (Path(clock_module.__file__).parent / 'run_chain_smoke.sh').read_text()
    assert all(home in script for home in JAVA_HOMES)
