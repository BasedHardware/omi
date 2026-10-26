"""Paid recovery without projection, accounting, notification or transcript IO."""

from types import SimpleNamespace

from config.batch_pipeline_shadow import shadow_percent
from config.policy import RecoveryPolicy
from config.batch_pipeline_empty_asr import terminal_empty_allowed
from config.batch_language_recovery import language_guarded, below_silence_threshold
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.recovery_disposition import inspect_audio, MultilingualEmpty, padded_empty


def recover(repository, artifacts, segment, *, stt=None, second_stt=None, inspect=inspect_audio):
    # These import the provider clients only at invocation, on the CPU backend.
    from utils.batch_pipeline.quarantine_recovery import (
        second_provider_eligible,
        SECOND_PROVIDER,
    )

    from utils.batch_pipeline.recovery_recognizers import transcribe, second_transcribe

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
                if policy.terminal_empty_disposition and padded_empty(job) and terminal_empty_allowed(empty.spans):
                    outcome = 'empty'
                elif second_provider_eligible(job, empty):
                    provider = 'soniox' if language_guarded(job) else SECOND_PROVIDER
                    if not repository.paid(segment, provider):
                        outcome = 'paid_skipped'
                    else:
                        try:
                            payload = second_stt(item, audio, empty)
                            outcome = 'recovered' if payload.get('words') else 'failed_held'
                        except MultilingualEmpty:
                            outcome = (
                                'empty'
                                if (
                                    below_silence_threshold(speech)
                                    if language_guarded(job)
                                    else policy.terminal_empty_disposition and terminal_empty_allowed(empty.spans)
                                )
                                else 'failed_held'
                            )
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
