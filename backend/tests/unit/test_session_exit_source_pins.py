"""Source pins for the listen session-exit custody wiring.

Needle tests over ``routers/listen/runtime.py`` and
``routers/transcribe.py``: every previously-bare exit site routes
through the step table, the replay row owns exactly the final usage
flush, the pre-session cohort warm stays in front of the session, and
the lines that already owned their faults keep their text.

Failure-Class: FC-listen-session-exit-custody-faults-escape-as-asgi-crashes
"""

import re
from pathlib import Path

import pytest

from routers.listen.session_exit import SESSION_EXIT_STEPS

pytestmark = [pytest.mark.filterwarnings('ignore::DeprecationWarning')]

BACKEND = Path(__file__).resolve().parents[2]


def _source(*parts):
    return (BACKEND.joinpath(*parts)).read_text(encoding='utf-8')


def runtime_source():
    return _source('routers', 'listen', 'runtime.py')


def transcribe_source():
    return _source('routers', 'transcribe.py')


def session_exit_source():
    return _source('routers', 'listen', 'session_exit.py')


def occurrences(source, needle):
    return len(re.findall(re.escape(needle), source))


class TestReplayRowWiring:
    def test_usage_flush_rides_the_replay_row_exactly_once(self):
        source = runtime_source()
        needle = "run_exit_step_replay(SESSION_EXIT_STEPS['usage_flush'], self._flush_usage, final=True"
        assert occurrences(source, needle) == 1

    def test_no_bare_final_usage_flush_remains(self):
        assert '_flush_usage(final=True)' not in runtime_source()

    def test_usage_flush_is_the_only_replay_budget_row(self):
        source = runtime_source()
        assert occurrences(source, 'run_exit_step_replay(') == 1


class TestSyncRowWiring:
    @pytest.mark.parametrize(
        'key',
        [
            'no_audio_observation_close',
            'ws_close_record',
            'cohort_finish',
            'unregister_session',
            'finish_live_transcription',
            'transcript_outcome',
            'lane_meter',
            'onboarding_cleanup',
            'speaker_ordinals',
            'idle_arm_record',
            'receiver_clear',
            'transcripts_clear',
            'speakers_clear',
            'idle_arm_session',
            'no_audio_record',
        ],
    )
    def test_sync_row_is_wired_in_runtime(self, key):
        assert f"SESSION_EXIT_STEPS['{key}']" in runtime_source()

    @pytest.mark.parametrize('key', ['demand_publish', 'multi_channel_tail', 'language_summary', 'final_drain'])
    def test_async_row_is_wired_in_runtime(self, key):
        assert f"SESSION_EXIT_STEPS['{key}']" in runtime_source()

    def test_sync_twin_call_count_matches_the_fifteen_sync_rows(self):
        assert occurrences(runtime_source(), 'run_exit_step_sync(') == 15

    def test_run_exit_step_call_count_matches_the_five_async_report_rows(self):
        assert occurrences(runtime_source(), 'run_exit_step(') == 5

    def test_every_referenced_step_key_exists_in_the_table(self):
        source = runtime_source()
        keys = set(re.findall(r"SESSION_EXIT_STEPS\['([a-z_]+)'\]", source))
        assert keys <= set(SESSION_EXIT_STEPS)
        assert keys == {key for key in SESSION_EXIT_STEPS if key != 'warm_cohorts'}


class TestTeardownEnvelopeCannotRaise:
    def test_ordinal_ledger_records_through_a_custody_closure(self):
        source = runtime_source()
        assert 'def _record_live_speaker_ordinals()' in source
        assert "SESSION_EXIT_STEPS['speaker_ordinals'], _record_live_speaker_ordinals" in source

    def test_idle_arm_still_receives_the_recorded_ordinals(self):
        source = runtime_source()
        assert 'ordinal_holder[0] if ordinal_holder else None' in source

    def test_buffer_clears_follow_the_idle_arm_unconditionally(self):
        source = runtime_source()
        clear_row = source.index("SESSION_EXIT_STEPS['receiver_clear']")
        arm_row = source.index("SESSION_EXIT_STEPS['idle_arm_record']")
        assert arm_row < clear_row

    def test_parity_capture_keeps_its_own_reported_seam(self):
        assert 'Listen parity capture teardown failed' in runtime_source()

    def test_pusher_close_keeps_its_own_error_line(self):
        assert "logger.error('Pusher close failed type=%s', type(error).__name__)" in runtime_source()

    def test_stt_finish_keeps_its_own_error_line(self):
        assert "logger.error('STT finish failed type=%s', type(error).__name__)" in runtime_source()

    def test_in_body_deletion_fence_line_keeps_its_text_and_gains_a_site(self):
        source = runtime_source()
        assert "'Listen teardown deletion fence unavailable type=%s%s'" in source
        assert source.index('exit_step_site_field') < source.index(
            "'Listen teardown deletion fence unavailable type=%s%s'"
        )

    def test_admission_guard_label_stays_truthful(self):
        assert 'listen session failed before supervision' in runtime_source()


class TestPreSessionFence:
    def test_transcribe_bounds_the_cohort_warm(self):
        source = transcribe_source()
        assert "run_exit_step(SESSION_EXIT_STEPS['warm_cohorts'], warm_rollout_cohorts, request.uid" in source

    def test_no_bare_cohort_warm_remains(self):
        assert 'await warm_rollout_cohorts(request.uid)' not in transcribe_source()

    def test_cohort_warm_precedes_the_session_task(self):
        source = transcribe_source()
        assert source.index(
            "run_exit_step(SESSION_EXIT_STEPS['warm_cohorts'], warm_rollout_cohorts, request.uid"
        ) < source.index('run_listen_session(request)')


class TestImportBoundaries:
    def test_runtime_imports_the_table_from_session_exit(self):
        source = runtime_source()
        assert (
            'from .session_exit import SESSION_EXIT_STEPS, run_exit_step, run_exit_step_replay, run_exit_step_sync'
            in source
        )
        assert 'from .session_exit import exit_step_site_field' in source

    def test_transcribe_imports_only_the_table_and_the_driver(self):
        assert 'from routers.listen.session_exit import SESSION_EXIT_STEPS, run_exit_step' in transcribe_source()

    def test_session_exit_imports_its_contention_family_from_teardown_custody(self):
        source = session_exit_source()
        assert 'from utils.batch_pipeline.teardown_custody import' in source
        # Light module: the only backend import is the teardown custody
        # family, so a candidate without this module dies at collection.
        backend_imports = re.findall(
            r'^from (?!utils\.batch_pipeline\.teardown_custody)((?:database|routers|utils|config|models)[\w.]* import)',
            source,
            re.M,
        )
        assert backend_imports == []

    def test_failure_class_trailer_is_declared_in_the_module(self):
        assert 'Failure-Class: FC-listen-session-exit-custody-faults-escape-as-asgi-crashes' in session_exit_source()
