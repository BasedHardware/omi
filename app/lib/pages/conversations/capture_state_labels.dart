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
/// | [transcriptionUnavailable]   | Transcription unavailable    | the server said live transcription cannot run  |
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
String captureStateLabel(AppLocalizations l10n, CaptureDisplayState state, {Duration? bufferingFor}) {
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
      return l10n.transcriptionUnavailable;
    case CaptureDisplayState.processing:
      return l10n.processing;
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
