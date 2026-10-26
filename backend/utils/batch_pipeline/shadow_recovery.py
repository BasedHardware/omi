"""Paid recovery without projection, accounting, notification or transcript IO."""

from types import SimpleNamespace

from config.batch_pipeline_shadow import shadow_percent
from config.policy import RecoveryPolicy
from config.batch_pipeline_empty_asr import terminal_empty_allowed
from config.batch_language_recovery import language_guarded, below_silence_threshold, allowed
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import WorkItem, held_vad_census, held_silence_allowed
from utils.batch_pipeline.recovery_disposition import inspect_audio, MultilingualEmpty, padded_empty
from utils.batch_pipeline.recovery_recognizers import recognizer_attempt, independent_ready
from utils.batch_pipeline.recovery_steps import ProviderStep, run_sync, run_async


def guarded_recovery(repository, segment, item, job, audio, duration, spans, stt, second_stt, ready):
    """Mirror the serving disposition without writing content or user accounting."""
    speech = sum(span['end'] - span['start'] for span in spans)
    receipts = {}

    def receipt(provider, outcome, count):
        receipts[provider] = {
            'provider': provider,
            'outcome': outcome,
            'word_count': count,
            'vad_speech_seconds': speech,
        }

    if not spans and not allowed(duration):
        receipt('soniox', 'refused', None)
        return 'paid_skipped', receipts
    if not repository.paid(segment, 'modulate'):
        receipt('modulate', 'refused', None)
        return 'paid_skipped', receipts
    payload, first, count = recognizer_attempt(
        lambda: stt(
            item, SimpleNamespace(language=job.get('language')), audio, multilingual=True, force_recognition=True
        )
    )
    receipt('modulate', first, count)
    if payload is not None:
        return 'recovered', receipts
    if not allowed(duration) or not ready() or not repository.paid(segment, 'soniox'):
        receipt('soniox', 'refused', None)
        return 'failed_held', receipts
    from utils.batch_pipeline.recovery_recognizers import second_transcribe, second_transcribe_async

    reply = yield ProviderStep(
        second_stt,
        (item, audio, MultilingualEmpty(duration, spans)),
        second_transcribe_async if second_stt is second_transcribe else None,
    )
    payload, second, count = recognizer_attempt(reply.result)
    receipt('soniox', second, count)
    if payload is not None:
        return 'recovered', receipts
    if first == second == 'empty' and below_silence_threshold(held_vad_census({**job['item'], **job}, speech)):
        return 'empty', receipts
    return 'failed_held', receipts


def recover(repository, artifacts, segment, *, stt=None, second_stt=None, inspect=inspect_audio):
    """Synchronous synthetic/operator adapter; serving uses the async coordinator."""
    return run_sync(_recover_steps(repository, artifacts, segment, stt=stt, second_stt=second_stt, inspect=inspect))


async def recover_async(repository, artifacts, segment, *, stt=None, second_stt=None, inspect=inspect_audio):
    return await run_async(
        _recover_steps(repository, artifacts, segment, stt=stt, second_stt=second_stt, inspect=inspect)
    )


def _recover_steps(repository, artifacts, segment, *, stt=None, second_stt=None, inspect=inspect_audio):
    # These import the provider clients only at invocation, on the CPU backend.
    from utils.batch_pipeline.quarantine_recovery import (
        second_provider_eligible,
        SECOND_PROVIDER,
    )

    from utils.batch_pipeline.recovery_recognizers import transcribe, second_transcribe, second_transcribe_async

    stt, second_stt = stt or transcribe, second_stt or second_transcribe
    job = repository.start_recovery(segment)
    if job is None:
        return 'held'
    item = WorkItem(**job['item'])
    policy = RecoveryPolicy.from_dict(job['recovery_policy'])
    speech, vad, outcome, receipts = 0.0, 'unknown', 'error', None
    try:
        audio = artifacts.fetch_audio(item)
        _, duration, spans = inspect(item, audio)
        speech, vad = sum(span['end'] - span['start'] for span in spans), 'strict'
        if language_guarded(job):
            outcome, receipts = yield from guarded_recovery(
                repository,
                segment,
                item,
                job,
                audio,
                duration,
                spans,
                stt,
                second_stt,
                independent_ready if second_stt is second_transcribe else lambda: True,
            )
        elif not spans:
            outcome = 'empty' if held_silence_allowed({**job['item'], **job}, 0) else 'failed_held'
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
                            reply = yield ProviderStep(
                                second_stt,
                                (item, audio, empty),
                                second_transcribe_async if second_stt is second_transcribe else None,
                            )
                            payload = reply.result()
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
    census = held_vad_census({**job['item'], **job}, speech if vad == 'strict' else None)
    repository.finish(
        segment, outcome, speech=census or 0.0, vad='strict' if census is not None else 'unknown', recognizers=receipts
    )
    return outcome
