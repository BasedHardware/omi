"""Closed relevance decision and terminal metric vocabulary; no runtime dependencies."""

TERMINAL_PATHS = frozenset(
    {
        'dead_letter',
        'byok_abandoned',
        'orphan_terminal',
        'oversized_terminal',
        'deferred_retry',
        'user_restore',
        'import',
        'external_text',
        'sync_intake',
        'lifecycle_terminal',
        'fixture_seed',
    }
)
DECISION_TRIGGERS = TERMINAL_PATHS | frozenset(
    {
        'capture_end',
        'client_finalize',
        'sync_update',
        'first_open',
        'user_reprocess',
        'merge',
        'smart_merge',
        'server_recovery',
        'backfill',
    }
)
DECIDERS = frozenset({'policy', 'user', 'rule', 'model', 'jev', 'override', 'deterministic'})

# Terminal defaults have a closed vocabulary, independent of exception text.
TERMINAL_METRIC_TRIGGERS = frozenset(
    {
        'dead_letter',
        'byok_abandoned',
        'orphan_terminal',
        'oversized_terminal',
        'deferred_retry',
        'sync_intake',
        'user_restore',
        'import',
        'external_text',
        'lifecycle_terminal',
        'fixture_seed',
    }
)
TERMINAL_METRIC_REASONS = frozenset(
    {
        'dead_letter_default',
        'byok_abandoned_default',
        'orphan_terminal_default',
        'oversized_terminal_default',
        'deferred_retry_default',
        'sync_intake_default',
        'user_restore_default',
        'import_default',
        'external_text_default',
        'lifecycle_terminal_default',
        'fixture_seed_default',
        'already_discarded',
        'restored',
        'calendar_overlap',
        'empty_transcript',
        'filler_only',
        'no_content_words',
        'mic_check',
        'explicit_reminder',
        'substantial_length',
    }
)
