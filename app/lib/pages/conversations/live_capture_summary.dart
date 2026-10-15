import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/utils/enums.dart';

/// How a live capture reads at a glance: capturing fine, paused or waiting, or something the
/// person should look at.
enum CaptureTone { live, quiet, attention }

/// What is recording now and how it is going, in the words the Home card and the Home pill both
/// show. One source for both, so the two never disagree.
class LiveCaptureSummary {
  const LiveCaptureSummary({
    required this.source,
    required this.copy,
    required this.tone,
    this.batch = false,
    this.readerPaused = false,
    this.micTaken = false,
    this.unverified = false,
  });

  /// `phone`, or the capturing device's source key (`omi`, `limitless`, ...).
  final String source;
  final CaptureCardCopy copy;
  final CaptureTone tone;

  /// Transcribe Later: audio saved on the phone, no live transcript.
  final bool batch;

  /// The person paused it (Resume brings it back).
  final bool readerPaused;

  /// The OS or another app holds the microphone.
  final bool micTaken;

  /// A pendant link that is up but not yet proven to be capturing.
  final bool unverified;

  bool get isPhone => source == 'phone';

  /// Healthy and live: nothing to explain, the live transcript is the next thing to see.
  bool get healthy => tone == CaptureTone.live && !batch && copy.explanation == null;
}

/// Summarizes the capture in [provider], or null when nothing is recording. A pendant that dropped
/// mid-capture and an Omi call are not covered: their surfaces track those themselves.
LiveCaptureSummary? summarizeLiveCapture(AppLocalizations l10n, CaptureProvider provider) {
  final liveSource = provider.liveCaptureSource;
  final isDeviceRecording = liveSource != null && liveSource != 'phone';
  // Keep automatic repair and legitimate pendant sleep quiet: a restored link alone is not Listening.
  final unverified = isDeviceRecording && !provider.isPaused && !provider.pendantCaptureVerified;
  final prefs = SharedPreferencesUtil();

  if ((isDeviceRecording && prefs.batchModeEnabled) ||
      provider.isPhoneMicBatchRecording ||
      (provider.havingRecordingDevice && prefs.batchModeEnabled)) {
    return _summarizeBatch(l10n, provider, unverified: unverified);
  }

  // A phone-mic batch session reports RecordingState.record too; it is handled above.
  final isPhoneRecording = provider.recordingState == RecordingState.record ||
      provider.recordingState == RecordingState.systemAudioRecord ||
      provider.recordingState == RecordingState.initialising ||
      provider.recordingState == RecordingState.interrupted ||
      provider.isPhoneMicPaused;
  if (!isDeviceRecording && !isPhoneRecording) return null;

  // A pause the reader chose (the control reads Resume only then).
  final isAudioInterrupted = provider.recordingState == RecordingState.interrupted;
  var isPaused = false;
  if (isDeviceRecording) {
    isPaused = provider.isPaused && provider.recordingState == RecordingState.pause;
  } else {
    isPaused = provider.isPhoneMicPaused || provider.isPaused;
  }
  // `interrupted` is the OS holding the mic (explained, no control) or capture recovering on its own
  // (Reconnecting, Pause still works); a reader pause keeps Resume either way.
  final interruption = captureInterruption(
    interrupted: !isDeviceRecording && isAudioInterrupted,
    readerPaused: isPaused,
    osHoldsMic: provider.isCallActive,
  );
  final micTaken = interruption == CaptureInterruption.micTaken;
  final hasTerminalTranscriptionFailure =
      provider.terminalTranscriptionFailure != null || provider.localSttFailure != null;
  // WAL saves audio locally whatever the transcription connection does, so a degraded transcription
  // names the consequence ("Audio saved, transcribes later"), not a stop.
  final displayState = liveCaptureDisplayState(
    audioInterrupted: micTaken,
    paused: isPaused,
    transcriptionUnavailable: hasTerminalTranscriptionFailure,
    bufferingFor: provider.customSttBufferingDuration,
    reconnecting: interruption == CaptureInterruption.recovering,
    capturingPhotos: provider.photos.isNotEmpty,
  );
  // Initialising: the microphone is opening and no audio flows yet, so it is not Listening.
  final starting = !isDeviceRecording &&
      provider.recordingState == RecordingState.initialising &&
      displayState == CaptureDisplayState.listening;
  final copy = provider.localSttFailure != null
      ? CaptureCardCopy(l10n.transcriptionUnavailable,
          detail: l10n.setupOnDevice, explanation: l10n.transcriptionUnavailableRecordingSaved)
      : unverified
          ? CaptureCardCopy(l10n.captureSourcePendant)
          : starting
              ? CaptureCardCopy(l10n.captureStarting)
              : captureCardCopy(l10n, displayState, micTaken: micTaken, socketDown: !provider.transcriptServiceReady);

  final CaptureTone tone;
  if (copy.explanation != null) {
    tone = CaptureTone.attention;
  } else if (isPaused || unverified || displayState == CaptureDisplayState.reconnecting) {
    tone = CaptureTone.quiet;
  } else {
    tone = CaptureTone.live;
  }
  return LiveCaptureSummary(
    source: isDeviceRecording ? liveSource : 'phone',
    copy: copy,
    tone: tone,
    readerPaused: isPaused,
    micTaken: micTaken,
    unverified: unverified,
  );
}

LiveCaptureSummary _summarizeBatch(AppLocalizations l10n, CaptureProvider provider, {required bool unverified}) {
  final isLimitless = provider.recordingDevice?.type == DeviceType.limitless;
  final prefs = SharedPreferencesUtil();
  final muted = !isLimitless && provider.offlineMuted;
  // Native low-storage flag: capture is paused, so it must not look healthy.
  final storageFull = !isLimitless && prefs.getBool('batchStorageFull');
  final source =
      provider.isPhoneMicBatchRecording ? 'phone' : (provider.liveCaptureSource ?? (isLimitless ? 'limitless' : 'omi'));

  final CaptureCardCopy copy;
  if (isLimitless) {
    final minutesStored = (prefs.pendantPagesStored * 1.4 / 60).round();
    final almostFull = prefs.pendantStorageAlmostFull;
    final detail = [
      if (minutesStored > 0) l10n.pendantMinutesStored(minutesStored),
      if (almostFull) l10n.captureStorageAlmostFull,
    ].join('  ·  ');
    copy = CaptureCardCopy(l10n.recording,
        detail: detail.isEmpty ? null : detail, explanation: almostFull ? l10n.pendantStorageAlmostFull : null);
  } else if (storageFull) {
    copy = CaptureCardCopy(l10n.paused,
        detail: l10n.capturePhoneStorageFull, explanation: l10n.transcribeLaterStorageFull);
  } else if (muted) {
    copy = CaptureCardCopy(l10n.paused);
  } else if (unverified) {
    copy = CaptureCardCopy(l10n.captureSourcePendant);
  } else {
    copy = CaptureCardCopy(l10n.recording, detail: l10n.captureAudioSavedTranscribesLater);
  }
  return LiveCaptureSummary(
    source: source,
    copy: copy,
    tone:
        copy.explanation != null ? CaptureTone.attention : (muted || unverified ? CaptureTone.quiet : CaptureTone.live),
    batch: true,
    readerPaused: muted,
    unverified: unverified,
  );
}
