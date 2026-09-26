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

    test('the reader\'s pause is Muted, whatever the source', () {
      // The reader's Mute reads Muted; only the OS taking the microphone reads Paused.
      expect(liveCaptureDisplayState(paused: true), CaptureDisplayState.muted);
      expect(liveCaptureDisplayState(audioInterrupted: true), CaptureDisplayState.paused);
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

  test('the transcription outage says recording continues', () {
    expect(
      captureStateLabel(l10n, CaptureDisplayState.transcriptionUnavailable),
      'Transcriptions are unavailable, recording continues on device and will process later',
    );
  });

  test('the Home card: a short status, the consequence, and an explanation for problems only', () {
    final outage = captureCardCopy(l10n, CaptureDisplayState.transcriptionUnavailable);
    expect(outage.status, 'Not transcribing');
    expect(outage.detail, 'Audio saved, transcribes later');
    expect(outage.explanation, l10n.transcriptionUnavailableRecordingContinues);
    expect(outage.warning, isTrue);

    final reconnecting = captureCardCopy(l10n, CaptureDisplayState.reconnecting);
    expect(reconnecting.status, 'Reconnecting…');
    expect(reconnecting.detail, 'Still recording');
    expect(reconnecting.warning, isTrue);

    expect(captureCardCopy(l10n, CaptureDisplayState.bufferingOffline).status, 'Offline');

    // A pause the reader chose is not a problem; one the OS forced is explained.
    final userPause = captureCardCopy(l10n, CaptureDisplayState.paused);
    expect(userPause.status, 'Paused');
    expect(userPause.warning, isFalse);
    final micTaken = captureCardCopy(l10n, CaptureDisplayState.paused, micTaken: true);
    expect(micTaken.status, 'Paused');
    expect(micTaken.detail, 'Mic in use by another app');
    expect(micTaken.warning, isTrue);

    expect(captureCardCopy(l10n, CaptureDisplayState.listening).warning, isFalse);

    // Reconnecting with the socket up is the microphone restarting: no "Still recording" claim.
    final stall = captureCardCopy(l10n, CaptureDisplayState.reconnecting, socketDown: false);
    expect(stall.detail, isNull);
    expect(stall.warning, isFalse);
  });

  test('interrupted: the OS holding the mic, capture recovering, or a reader pause that wins', () {
    expect(captureInterruption(interrupted: true, readerPaused: false, osHoldsMic: true), CaptureInterruption.micTaken);
    expect(
        captureInterruption(interrupted: true, readerPaused: false, osHoldsMic: false), CaptureInterruption.recovering);
    expect(captureInterruption(interrupted: true, readerPaused: true, osHoldsMic: true), CaptureInterruption.none);
    expect(captureInterruption(interrupted: false, readerPaused: false, osHoldsMic: true), CaptureInterruption.none);
  });
}
