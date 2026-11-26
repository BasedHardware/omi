"""Capture the serving resolver and evidence-builder witnesses during replay."""

from contextvars import ContextVar
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

from utils.observability import owner_recognition_diagnostics as diagnostics
from utils.speakers import processing as speaker_processing


def record_speaker_trace(state, leaves):
    log_summary = diagnostics.log_summary
    finish = speaker_processing.finish
    build_evidence = speaker_processing.build_evidence
    scoped = ContextVar('capture_evidence_owner', default=False)
    # observe_resolver reads its module-local clock at entry and in its
    # finally block. Record the actual readings before returning them to the
    # resolver. Other modules (and the fixture meter) retain their own clock.
    monotonic = diagnostics.time.monotonic
    samples = ContextVar('resolver_clock_reads', default=())
    state.speaker_trace = {'exits': [], 'evidence': [], 'resolver_clock_seconds': []}

    def witness_monotonic():
        value = monotonic()
        prior = samples.get()
        if len(prior) < 3:
            samples.set((*prior, value))
        return value

    def observe_exit(event, data):
        if event == 'resolver_exit':
            readings = samples.get()
            samples.set(())
            if data.get('uid') == state.uid and data.get('conversation') == state.cid:
                state.speaker_trace['exits'].append(diagnostics.contract.summary(data))
                state.speaker_trace['resolver_clock_seconds'].extend(readings)
        return log_summary(event, data)

    def observe_finish(token, uid, conversation, receipt, **kwargs):
        bound = scoped.set(uid == state.uid and conversation.id == state.cid)
        try:
            return finish(token, uid, conversation, receipt, **kwargs)
        finally:
            scoped.reset(bound)

    def observe_evidence(*args, **kwargs):
        evidence = build_evidence(*args, **kwargs)
        if scoped.get():
            state.speaker_trace['evidence'].append(sha256(evidence.model_dump_json().encode()).hexdigest())
        return evidence

    leaves.enter_context(patch.object(diagnostics, 'time', SimpleNamespace(monotonic=witness_monotonic)))
    leaves.enter_context(patch.object(diagnostics, 'log_summary', observe_exit))
    leaves.enter_context(patch.object(speaker_processing, 'finish', observe_finish))
    leaves.enter_context(patch.object(speaker_processing, 'build_evidence', observe_evidence))
