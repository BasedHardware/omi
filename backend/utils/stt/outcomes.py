"""Privacy-safe semantic outcomes for pre-recorded transcription boundaries."""

from __future__ import annotations

from typing import Any, Iterator

import httpx

from config.prerecorded_stt import PrerecordedSTTConfigurationError, PrerecordedSTTService, TranscriptionOutcome

_KNOWN_PROVIDERS = {
    PrerecordedSTTService.DEEPGRAM,
    PrerecordedSTTService.MODULATE,
    PrerecordedSTTService.PARAKEET,
}

_PUBLIC_FAILURES: dict[TranscriptionOutcome, tuple[int, str, str]] = {
    TranscriptionOutcome.EMPTY_UNEXPECTED: (
        502,
        'stt_empty_unexpected',
        'Speech was detected, but the transcription provider returned no transcript.',
    ),
    TranscriptionOutcome.TIMEOUT: (504, 'stt_timeout', 'The transcription provider timed out.'),
    TranscriptionOutcome.UPSTREAM_ERROR: (
        502,
        'stt_upstream_error',
        'The transcription provider could not complete the request.',
    ),
    TranscriptionOutcome.CONFIG_ERROR: (
        503,
        'stt_provider_configuration_error',
        'The transcription provider is temporarily unavailable.',
    ),
    # Keep FastAPI's existing 422 validation contract intact. Runtime audio
    # validation uses 400 so generated clients do not lose HTTPValidationError.
    TranscriptionOutcome.INVALID_INPUT: (400, 'stt_invalid_input', 'The audio input is invalid.'),
}


def bounded_provider(provider: str | None) -> str:
    """Return a stable provider label without accepting arbitrary cardinality."""

    normalized = (provider or '').strip().lower()
    return normalized if normalized in _KNOWN_PROVIDERS else 'unknown'


class TranscriptionFailure(RuntimeError):
    """Typed terminal failure whose exposed fields never contain provider text."""

    def __init__(
        self,
        outcome: TranscriptionOutcome,
        *,
        provider: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        if outcome not in _PUBLIC_FAILURES:
            raise ValueError(f'{outcome.value} is not a failure outcome')
        status_code, error_code, public_message = _PUBLIC_FAILURES[outcome]
        self.outcome = outcome
        self.provider = bounded_provider(provider)
        self.retryable = (
            outcome
            in {
                TranscriptionOutcome.EMPTY_UNEXPECTED,
                TranscriptionOutcome.TIMEOUT,
                TranscriptionOutcome.UPSTREAM_ERROR,
            }
            if retryable is None
            else retryable
        )
        self.status_code = status_code
        self.error_code = error_code
        self.public_message = public_message
        super().__init__(public_message)

    def as_detail(self) -> dict[str, Any]:
        """Safe, machine-readable HTTP/SSE payload."""

        return {
            'error': self.error_code,
            'outcome': self.outcome.value,
            'provider': self.provider,
            'retryable': self.retryable,
            'message': self.public_message,
        }


def _exception_chain(error: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def failure_from_exception(error: BaseException, *, provider: str | None = None) -> TranscriptionFailure:
    """Map internal provider exceptions to the closed public failure contract."""

    chain = tuple(_exception_chain(error))
    typed_failure = next((item for item in chain if isinstance(item, TranscriptionFailure)), None)
    if isinstance(typed_failure, TranscriptionFailure):
        return typed_failure
    configuration_error = next(
        (item for item in chain if isinstance(item, PrerecordedSTTConfigurationError)),
        None,
    )
    if isinstance(configuration_error, PrerecordedSTTConfigurationError):
        return TranscriptionFailure(
            TranscriptionOutcome.CONFIG_ERROR,
            provider=configuration_error.provider,
            retryable=False,
        )
    if any(isinstance(item, (TimeoutError, httpx.TimeoutException)) for item in chain):
        return TranscriptionFailure(TranscriptionOutcome.TIMEOUT, provider=provider)
    if isinstance(error, (ValueError, TypeError)):
        return TranscriptionFailure(
            TranscriptionOutcome.INVALID_INPUT,
            provider=provider,
            retryable=False,
        )
    return TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider)


def empty_unexpected_failure(provider: str | None = None) -> TranscriptionFailure:
    """Create the shared failure for speech-positive audio with an empty result."""

    return TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider=provider)
