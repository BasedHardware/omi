import 'package:omi/l10n/app_localizations.dart';

/// What a live or just-finished capture is doing, as the reader should see it (hub audit #25).
///
/// The in-progress card on the conversations list, the capturing page and the processing page all
/// name a state through [captureStateLabel], so the same moment never has two names:
///
/// | State                        | Label                        | When                                           |
/// |------------------------------|------------------------------|------------------------------------------------|
/// | [listening]                  | Listening                    | live capture with live transcription           |
/// | [capturing]                  | Capturing                    | live capture from a camera device (photos)     |
/// | [recording]                  | Recording                    | audio saved for later (no live transcription)  |
/// | [paused]                     | Paused                       | the reader paused, or the OS interrupted audio (a call, another app) |
/// | [muted]                      | Muted                        | the device's mic is muted                      |
/// | [reconnecting]               | Reconnecting…                | the transcription connection dropped and is being restored |
/// | [bufferingOffline]           | Offline, buffering (· 3m)    | a custom speech endpoint is unreachable; audio is kept locally |
/// | [transcriptionUnavailable]   | Transcriptions are unavailable, recording continues on device and will process later | the server said live transcription cannot run; the WAL keeps recording regardless |
/// | [processing]                 | Processing                   | capture ended; the conversation is being made  |
///
/// An audio-session interruption is **Paused**, not Reconnecting: nothing is reconnecting, the OS
/// took the microphone.
enum CaptureDisplayState {
  listening,
  capturing,
  recording,
  paused,
  muted,
  reconnecting,
  bufferingOffline,
  transcriptionUnavailable,
  processing,
}

/// The one label for [state]. [bufferingFor] adds the elapsed minutes to [CaptureDisplayState.bufferingOffline].
/// The capturing page uses the full transcription-outage sentence so the reader learns recording
/// still continues and will be processed later; the Home card uses [captureCardCopy].
String captureStateLabel(
  AppLocalizations l10n,
  CaptureDisplayState state, {
  Duration? bufferingFor,
}) {
  switch (state) {
    case CaptureDisplayState.listening:
      return l10n.listening;
    case CaptureDisplayState.capturing:
      return l10n.capturing;
    case CaptureDisplayState.recording:
      return l10n.recording;
    case CaptureDisplayState.paused:
      return l10n.paused;
    case CaptureDisplayState.muted:
      return l10n.muted;
    case CaptureDisplayState.reconnecting:
      return l10n.reconnecting;
    case CaptureDisplayState.bufferingOffline:
      final minutes = bufferingFor?.inMinutes ?? 0;
      return minutes < 1 ? l10n.captureOfflineBuffering : l10n.captureOfflineBufferingFor(minutes);
    case CaptureDisplayState.transcriptionUnavailable:
      return l10n.transcriptionUnavailableRecordingContinues;
    case CaptureDisplayState.processing:
      return l10n.processing;
  }
}

/// What the Home live card says for a state: a short [status] (line 1, must fit one line at 320pt
/// and 1.3x text in English), an optional [detail] (line 2, after the timer), and for a problem
/// the [explanation] its details sheet shows. [warning] marks a problem (amber glyph, tappable).
class CaptureCardCopy {
  const CaptureCardCopy(this.status, {this.detail, this.explanation});

  final String status;
  final String? detail;
  final String? explanation;

  bool get warning => explanation != null;
}

/// The Home card's copy for [state]. [micTaken] marks a pause the OS or another app caused (not
/// the reader), which is a problem with an explanation rather than a plain Paused.
CaptureCardCopy captureCardCopy(AppLocalizations l10n, CaptureDisplayState state, {bool micTaken = false}) {
  switch (state) {
    case CaptureDisplayState.paused when micTaken:
      return CaptureCardCopy(l10n.paused,
          detail: l10n.captureMicInUseElsewhere, explanation: l10n.captureMicInterruptedDetail);
    case CaptureDisplayState.reconnecting:
      return CaptureCardCopy(l10n.reconnecting,
          detail: l10n.captureStillRecording, explanation: l10n.transcriptionPausedReconnecting);
    case CaptureDisplayState.bufferingOffline:
      return CaptureCardCopy(l10n.offline,
          detail: l10n.captureAudioSavedTranscribesLater, explanation: l10n.captureCustomSttUnreachableDetail);
    case CaptureDisplayState.transcriptionUnavailable:
      return CaptureCardCopy(l10n.captureNotTranscribing,
          detail: l10n.captureAudioSavedTranscribesLater, explanation: l10n.transcriptionUnavailableRecordingContinues);
    default:
      return CaptureCardCopy(captureStateLabel(l10n, state));
  }
}

/// Resolves the state of a live capture from the capture provider's signals, in priority order:
/// an interruption or pause, then a server-side transcription failure, then offline buffering,
/// then a dropped transcription connection, then live.
CaptureDisplayState liveCaptureDisplayState({
  bool audioInterrupted = false,
  bool paused = false,
  bool deviceMuted = false,
  bool transcriptionUnavailable = false,
  Duration? bufferingFor,
  bool reconnecting = false,
  bool capturingPhotos = false,
}) {
  if (audioInterrupted) return CaptureDisplayState.paused;
  if (paused) return deviceMuted ? CaptureDisplayState.muted : CaptureDisplayState.paused;
  if (transcriptionUnavailable) return CaptureDisplayState.transcriptionUnavailable;
  if (bufferingFor != null) return CaptureDisplayState.bufferingOffline;
  if (reconnecting) return CaptureDisplayState.reconnecting;
  return capturingPhotos ? CaptureDisplayState.capturing : CaptureDisplayState.listening;
}
