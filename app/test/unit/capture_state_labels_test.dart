import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));

  group('liveCaptureDisplayState', () {
    test('an audio interruption is Paused, never Reconnecting', () {
      final state = liveCaptureDisplayState(audioInterrupted: true, reconnecting: true);
      expect(state, CaptureDisplayState.paused);
      expect(captureStateLabel(l10n, state), 'Paused');
    });

    test('a paused device is Muted, a paused phone is Paused', () {
      expect(liveCaptureDisplayState(paused: true, deviceMuted: true), CaptureDisplayState.muted);
      expect(liveCaptureDisplayState(paused: true), CaptureDisplayState.paused);
    });

    test('a server-side failure outranks buffering and reconnecting', () {
      expect(
        liveCaptureDisplayState(
          transcriptionUnavailable: true,
          bufferingFor: const Duration(minutes: 2),
          reconnecting: true,
        ),
        CaptureDisplayState.transcriptionUnavailable,
      );
    });

    test('live capture is Listening, or Capturing with photos', () {
      expect(liveCaptureDisplayState(), CaptureDisplayState.listening);
      expect(liveCaptureDisplayState(capturingPhotos: true), CaptureDisplayState.capturing);
    });
  });

  test('every state has one localized label', () {
    for (final state in CaptureDisplayState.values) {
      expect(captureStateLabel(l10n, state, bufferingFor: const Duration(minutes: 3)), isNotEmpty);
    }
    expect(captureStateLabel(l10n, CaptureDisplayState.processing), 'Processing');
    expect(captureStateLabel(l10n, CaptureDisplayState.bufferingOffline), 'Offline, buffering');
    expect(
      captureStateLabel(l10n, CaptureDisplayState.bufferingOffline, bufferingFor: const Duration(minutes: 3)),
      'Offline, buffering · 3 min',
    );
  });

  test('the transcription outage says recording continues; the compact variant stays short', () {
    expect(
      captureStateLabel(l10n, CaptureDisplayState.transcriptionUnavailable),
      'Transcriptions are unavailable, recording continues on device and will process later',
    );
    expect(
      captureStateLabel(l10n, CaptureDisplayState.transcriptionUnavailable, compact: true),
      'Transcription unavailable · saving on device',
    );
    // Compact only affects the outage sentence; other states are identical either way.
    expect(
      captureStateLabel(l10n, CaptureDisplayState.paused, compact: true),
      captureStateLabel(l10n, CaptureDisplayState.paused),
    );
  });
}
