"""Audio-timeline v2 feature flag (AUDIO_TIMELINE_V2) and speaker-clock switch.

Runtime-selected rollout switches keep their env parsing in a pure ``config/``
module and read mutable env at the call boundary, never at import. The flag
admits *new eligible recordings only*: single-channel, server-STT live capture.
Flag off means existing v1 wire and persistence are unchanged.
"""

from config.refactor_switches import default_off as rollout_default_off, default_on as rollout_default_on

import os

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})
_FALSY = frozenset({'0', 'false', 'no', 'off'})


def audio_timeline_v2_enabled() -> bool:
    """Read AUDIO_TIMELINE_V2 at the call boundary. Default off."""
    return rollout_default_off('AUDIO_TIMELINE_V2', os.getenv('AUDIO_TIMELINE_V2', '').strip().lower() in _TRUTHY)


def soniox_elapsed_axis_mode() -> str:
    """Select Soniox's unverified elapsed send axis; default to measurement only."""
    value = os.getenv('SONIOX_ELAPSED_AXIS', 'shadow').strip().lower()
    return value if value in ('off', 'shadow', 'on') else 'shadow'


def live_speaker_capture_clock_enabled() -> bool:
    """Read LIVE_SPEAKER_CAPTURE_CLOCK at the call boundary. Default on.

    Runtime kill switch for the always-on capture-clock speaker-ID path (the
    §9 addition that positions live speaker clips and the ring buffer on the
    capture clock for every server-STT session, flag or not). Prod can revert
    speaker-ID windows to the legacy first-audio + provider-time formula
    without a deploy by setting this to a falsy value; persisted fields and
    the wire are on the v2 flag, not this switch. Unbound stays default-on.

    The switch only applies to legacy (clock-only) sessions: a v2 session's
    speaker queries and persisted offsets project capture samples onto the
    wall axis, so its ring buffer stays capture-positioned regardless of the
    switch (see ``ListenReceiver._write_ring_buffer_frame``).
    """
    return rollout_default_on(
        'LIVE_SPEAKER_CAPTURE_CLOCK', os.getenv('LIVE_SPEAKER_CAPTURE_CLOCK', '').strip().lower() not in _FALSY
    )


def live_capture_window_retention_enabled() -> bool:
    """Retain more observed capture anchors/send spans for delayed finals. Default off."""
    return rollout_default_off(
        'LIVE_CAPTURE_WINDOW_RETENTION', os.getenv('LIVE_CAPTURE_WINDOW_RETENTION', '').strip().lower() in _TRUTHY
    )


def capture_anchor_limit() -> int:
    return 512 if live_capture_window_retention_enabled() else 64


def capture_send_span_limit() -> int:
    return 16384 if live_capture_window_retention_enabled() else 4096


def live_capture_window_merge_preservation_enabled() -> bool:
    """Keep provider pieces when live text repair would discard known capture proof. Default off."""
    return rollout_default_off(
        'LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION',
        os.getenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', '').strip().lower() in _TRUTHY,
    )


def live_capture_window_strict_projection_enabled() -> bool:
    """Reject legacy windows across observed wall hiatuses. Default off for parity."""
    return rollout_default_off(
        'LIVE_CAPTURE_WINDOW_STRICT_PROJECTION',
        os.getenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', '').strip().lower() in _TRUTHY,
    )


def live_capture_window_merge_union_enabled() -> bool:
    """Union known live windows across receiver-proven received gaps. Default off."""
    return rollout_default_off(
        'LIVE_CAPTURE_WINDOW_MERGE_UNION', os.getenv('LIVE_CAPTURE_WINDOW_MERGE_UNION', '').strip().lower() in _TRUTHY
    )


def live_capture_window_translator_sends_enabled() -> bool:
    """Record observed raw replay and managed pre-finalize sends. Default off."""
    return rollout_default_off(
        'LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS',
        os.getenv('LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS', '').strip().lower() in _TRUTHY,
    )


def soniox_wire_ledger_enabled() -> bool:
    """Account every emitted Soniox sample, refusing unknown capture origins. Default off."""
    return rollout_default_off('SONIOX_WIRE_LEDGER', os.getenv('SONIOX_WIRE_LEDGER', 'false').strip().lower() == 'true')


def soniox_ordered_finalize_enabled() -> bool:
    """Verify FIFO finalize predictions at the probed 16 kHz wire rate. Default off."""
    return rollout_default_off(
        'SONIOX_ORDERED_FINALIZE', os.getenv('SONIOX_ORDERED_FINALIZE', 'false').strip().lower() == 'true'
    )
