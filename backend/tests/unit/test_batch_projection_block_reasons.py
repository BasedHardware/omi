"""Projection refusal reasons are closed log tokens, never exception text."""

import logging

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionBlocked
from database.batch_pipeline_projection_protocol import ProjectionGenerationAmbiguous
from utils.batch_pipeline import projection
from utils.batch_pipeline.context import resolve_context
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.sync import recording_lineage


def _context_inputs():
    item = WorkItem('segment', 'synthetic-owner', 1000, 'gs://synthetic/unit.wav', 10, Priority.FRESH)
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',), source='omi')
    context = {
        'owner_id': item.owner_id,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': item.segment_id,
        'capture_at': item.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
        'filenames': [],
    }
    return item, binding, context


@pytest.mark.parametrize(
    ('case', 'block_reason', 'message'),
    [
        (
            'intake_binding_mismatch',
            'intake_binding_mismatch',
            'authenticated intake metadata binding mismatch',
        ),
        ('invalid_recording_clock', 'invalid_recording_clock', 'invalid intake recording clock'),
        ('invalid_recording_identity', 'invalid_recording_identity', 'invalid intake recording identity'),
        ('invalid_recording_interval', 'invalid_recording_interval', 'invalid intake recording interval'),
        ('invalid_upload_filenames', 'invalid_upload_filenames', 'invalid intake upload filenames'),
        (
            'lineage_identity_missing',
            'lineage_identity_missing',
            'recording identity required for lineage resolution',
        ),
        ('lineage_ambiguous', 'lineage_ambiguous', 'recording generation binding remains ambiguous'),
    ],
)
def test_context_projection_blocks_log_closed_reason_and_preserve_exception(
    monkeypatch, caplog, case, block_reason, message
):
    item, binding, context = _context_inputs()
    if case == 'intake_binding_mismatch':
        context['content_id'] = 'private-binding-secret'
    elif case == 'invalid_recording_clock':
        context['audio_start_seconds'] = float('nan')
    elif case == 'invalid_recording_identity':
        context['recording_session_id'] = ''
    elif case == 'invalid_recording_interval':
        context.update(audio_start_seconds=11, audio_end_seconds=10)
    elif case == 'invalid_upload_filenames':
        context['filenames'] = ['private-filename-secret', None]
    elif case in {'lineage_identity_missing', 'lineage_ambiguous'}:
        context.update(recording_session_id='synthetic-recording', filenames=['fixture.opus'])
        if case == 'lineage_identity_missing':
            context.pop('recording_session_id')
        monkeypatch.setattr(recording_lineage, 'lineage_resolution_requested', lambda *_a, **_kw: True)
        if case == 'lineage_ambiguous':
            monkeypatch.setattr(recording_lineage, 'plan_segment_targets', lambda *_a, **_kw: {})
            monkeypatch.setattr(recording_lineage, 'ambiguous_binding_pending', lambda *_a, **_kw: True)

    policy = ProjectionPolicy(projection_timing=True)
    with caplog.at_level(logging.INFO, logger=projection.__name__):
        with pytest.raises(ProjectionBlocked) as raised:
            with projection.projection_phase('context', policy):
                resolve_context(item, binding, context, None)

    expected_type = ProjectionGenerationAmbiguous if case == 'lineage_ambiguous' else ProjectionBlocked
    assert type(raised.value) is expected_type
    assert raised.value.args == (message,)
    assert raised.value.block_reason == block_reason
    assert f'exception_type={expected_type.__name__}' in caplog.text
    assert f'block_reason={block_reason}' in caplog.text
    assert message not in caplog.text
    assert 'private-binding-secret' not in caplog.text
    assert 'private-filename-secret' not in caplog.text


@pytest.mark.parametrize('kind', ['projection_blocked', 'other_exception'])
@pytest.mark.parametrize('reason_shape', ['missing', 'hostile_string', 'non_string'])
def test_unknown_or_hostile_reason_collapses_to_other_without_logging_private_text(caplog, kind, reason_shape):
    secret = 'private-binding-and-exception-secret'
    error = (
        ProjectionBlocked(f'private exception body: {secret}')
        if kind == 'projection_blocked'
        else ValueError(f'private exception body: {secret}')
    )
    if reason_shape == 'hostile_string':
        error.block_reason = f'unknown\nuid={secret}'
    elif reason_shape == 'non_string':
        error.block_reason = [secret]

    policy = ProjectionPolicy(projection_timing=True)
    with caplog.at_level(logging.INFO, logger=projection.__name__):
        with pytest.raises(type(error)) as raised:
            with projection.projection_phase('context', policy):
                raise error

    assert raised.value is error
    assert raised.value.args == (f'private exception body: {secret}',)
    assert 'block_reason=other' in caplog.text
    assert secret not in caplog.text
    assert 'private exception body' not in caplog.text
