"""Lazy, bounded translation metrics."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from prometheus_client import REGISTRY, Counter, Histogram


class TranslationMetrics(Protocol):
    def cache(self, layer: str, result: str) -> None:
        ...

    def batch(self, provider: str, target_language: str, size: int) -> None:
        ...

    def success(
        self,
        provider: str,
        target_language: str,
        method: str,
        characters: int,
        sentences: int,
        elapsed_seconds: float,
    ) -> None:
        ...

    def error(self, provider: str, error_type: str) -> None:
        ...

    def skip(self, target_language: str, reason: str) -> None:
        ...


class NoopTranslationMetrics:
    def cache(self, layer: str, result: str) -> None:
        return None

    def batch(self, provider: str, target_language: str, size: int) -> None:
        return None

    def success(
        self,
        provider: str,
        target_language: str,
        method: str,
        characters: int,
        sentences: int,
        elapsed_seconds: float,
    ) -> None:
        return None

    def error(self, provider: str, error_type: str) -> None:
        return None

    def skip(self, target_language: str, reason: str) -> None:
        return None


class PrometheusTranslationMetrics:
    def __init__(self) -> None:
        self._requests = _counter(
            'omi_translation_requests_total',
            'Total translation requests',
            ['provider', 'target_lang', 'method'],
        )
        self._latency = _histogram(
            'omi_translation_latency_seconds',
            'End-to-end translation latency',
            ['provider', 'target_lang'],
            [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        self._characters = _counter(
            'omi_translation_chars_total',
            'Characters translated',
            ['provider', 'target_lang'],
        )
        self._sentences = _counter(
            'omi_translation_sentences_total',
            'Sentences translated',
            ['provider', 'target_lang'],
        )
        self._cache_ops = _counter(
            'omi_translation_cache_ops_total',
            'Translation cache operations',
            ['layer', 'result'],
        )
        self._errors = _counter(
            'omi_translation_errors_total',
            'Translation errors',
            ['provider', 'error_type'],
        )
        self._batch_size = _histogram(
            'omi_translation_batch_size',
            'Sentences per translation provider call',
            ['provider'],
            [1, 2, 5, 10, 20, 50, 100, 200],
        )
        self._skips = _counter(
            'omi_translation_skip_total',
            'Translations skipped',
            ['target_lang', 'reason'],
        )

    def cache(self, layer: str, result: str) -> None:
        self._cache_ops.labels(layer=_bounded(layer), result=_bounded(result)).inc()

    def batch(self, provider: str, target_language: str, size: int) -> None:
        self._batch_size.labels(provider=_bounded_provider(provider)).observe(size)

    def success(
        self,
        provider: str,
        target_language: str,
        method: str,
        characters: int,
        sentences: int,
        elapsed_seconds: float,
    ) -> None:
        provider_label = _bounded_provider(provider)
        target_label = _bounded_language(target_language)
        self._requests.labels(provider=provider_label, target_lang=target_label, method=_bounded_method(method)).inc()
        self._latency.labels(provider=provider_label, target_lang=target_label).observe(elapsed_seconds)
        self._characters.labels(provider=provider_label, target_lang=target_label).inc(characters)
        self._sentences.labels(provider=provider_label, target_lang=target_label).inc(sentences)

    def error(self, provider: str, error_type: str) -> None:
        self._errors.labels(provider=_bounded_provider(provider), error_type=_bounded_error(error_type)).inc()

    def skip(self, target_language: str, reason: str) -> None:
        self._skips.labels(target_lang=_bounded_language(target_language), reason=_bounded_reason(reason)).inc()


_default_metrics: TranslationMetrics | None = None
_default_metrics_lock = Lock()


def get_translation_metrics() -> TranslationMetrics:
    global _default_metrics
    if _default_metrics is None:
        with _default_metrics_lock:
            if _default_metrics is None:
                _default_metrics = PrometheusTranslationMetrics()
    return _default_metrics


def _counter(name: str, doc: str, labels: list[str]) -> Counter:
    try:
        return Counter(name, doc, labels)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def _histogram(name: str, doc: str, labels: list[str], buckets: list[float]) -> Histogram:
    try:
        return Histogram(name, doc, labels, buckets=buckets)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def _bounded(value: str) -> str:
    normalized = ''.join(char for char in value.casefold() if char.isalnum() or char in {'_', '-'})
    return normalized[:32] or 'other'


def _bounded_provider(value: str) -> str:
    normalized = _bounded(value)
    return normalized if normalized in {'google', 'nllb', 'cache'} else 'other'


def _bounded_language(value: str) -> str:
    base = value.split('-', 1)[0]
    normalized = _bounded(base)
    return normalized if 2 <= len(normalized) <= 8 else 'other'


def _bounded_method(value: str) -> str:
    normalized = _bounded(value)
    return normalized if normalized in {'batch', 'whole_text', 'sentence'} else 'other'


def _bounded_error(value: str) -> str:
    normalized = _bounded(value)
    return normalized if normalized in {'api_error', 'invalid_response', 'config_error'} else 'other'


def _bounded_reason(value: str) -> str:
    normalized = _bounded(value)
    return normalized if normalized in {'empty', 'target_language', 'cached'} else 'other'
