// Aggregates privacy-safe on-device transcription usage for typed analytics.
// Emission is best-effort and must never affect capture or local custody.
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

enum OnDeviceUsageRoute { allowance, custom, offlineBatch }

/// Counts completed on-device transcription, never transcript text or record ids.
/// Live sockets aggregate their chunks into one event; a finished offline WAL is
/// one event. Analytics failures must not affect capture or local custody.
class OnDeviceUsageTracker {
  OnDeviceUsageTracker({
    required this.route,
    void Function(RegisteredEvent event)? emit,
  }) : _emit = emit ?? const TypedEvents().emit;

  final OnDeviceUsageRoute route;
  final void Function(RegisteredEvent event) _emit;
  int _audioMs = 0;
  int _segmentCount = 0;

  void record({required int audioMs, required int segmentCount}) {
    if (audioMs > 0) _audioMs += audioMs;
    if (segmentCount > 0) _segmentCount += segmentCount;
  }

  void flush() {
    if (_segmentCount == 0) {
      _audioMs = 0;
      return;
    }
    final event = OnDeviceTranscriptionUsed(
      route: switch (route) {
        OnDeviceUsageRoute.allowance => OnDeviceTranscriptionUsedRoute.allowance,
        OnDeviceUsageRoute.custom => OnDeviceTranscriptionUsedRoute.custom,
        OnDeviceUsageRoute.offlineBatch => OnDeviceTranscriptionUsedRoute.offlineBatch,
      },
      audioMs: _audioMs,
      segmentCount: _segmentCount,
    );
    _audioMs = 0;
    _segmentCount = 0;
    try {
      _emit(event);
    } catch (_) {
      // Usage telemetry is supplemental to transcription.
    }
  }
}
