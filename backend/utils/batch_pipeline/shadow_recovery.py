"""Paid recovery without projection, accounting, notification or transcript IO."""

from types import SimpleNamespace

from config.batch_pipeline_shadow import shadow_percent
from config.policy import RecoveryPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.recovery_disposition import inspect_audio, MultilingualEmpty, padded_empty


def recover(repository, artifacts, segment, *, stt=None, second_stt=None, inspect=inspect_audio):
    # These import the provider clients only at invocation, on the CPU backend.
    from utils.batch_pipeline.quarantine_recovery import transcribe, second_transcribe, second_provider_eligible

    stt, second_stt = stt or transcribe, second_stt or second_transcribe
    job = repository.start_recovery(segment)
    if job is None:
        return 'held'
    item = WorkItem(**job['item'])
    policy = RecoveryPolicy.from_dict(job['recovery_policy'])
    speech, vad, outcome = 0.0, 'unknown', 'error'
    try:
        audio = artifacts.fetch_audio(item)
        _, _, spans = inspect(item, audio)
        speech, vad = sum(span['end'] - span['start'] for span in spans), 'strict'
        if not spans:
            outcome = 'empty'
        elif not shadow_percent() or not repository.paid(segment, 'modulate'):
            outcome = 'paid_skipped'
        else:
            # The same record-lane recognizers and strict validation; the
            # account quota/accounting adapter is deliberately never invoked.
            try:
                payload = stt(item, SimpleNamespace(language=job.get('language')), audio, multilingual=True)
                outcome = 'recovered' if payload.get('words') else 'failed_held'
            except MultilingualEmpty as empty:
                outcome = 'failed_held'
                if policy.terminal_empty_disposition and padded_empty(job):
                    outcome = 'empty'
                elif second_provider_eligible(job, empty):
                    if not repository.paid(segment, 'deepgram'):
                        outcome = 'paid_skipped'
                    else:
                        try:
                            payload = second_stt(item, audio, empty)
                            outcome = 'recovered' if payload.get('words') else 'failed_held'
                        except MultilingualEmpty:
                            outcome = 'empty' if policy.terminal_empty_disposition else 'failed_held'
                        except BatchPrivacyBlocked:
                            raise
                        except Exception:
                            outcome = 'failed_held'
            except BatchPrivacyBlocked:
                raise
            except Exception:
                outcome = 'failed_held'
    except Exception:
        outcome = 'error'
    repository.finish(segment, outcome, speech=speech, vad=vad)
    return outcome
