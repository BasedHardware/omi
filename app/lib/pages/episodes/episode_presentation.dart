import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/live_start_anchor.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/speaker_label.dart';

/// Shared rules for how a live episode reads on Home, its page and the device page.
abstract final class EpisodePresentation {
  /// The shared localized live length keeps seconds as the episode grows.
  static String runningLength(Duration elapsed, AppLocalizations l10n) {
    return OmiDuration.live(elapsed.inSeconds, l10n);
  }

  /// How long the live episode has run, counted from one stable start: the episode's own start
  /// (the server opens it at the first words), else the earliest capture start seen while
  /// streaming. [anchor] keeps that start across the moments a source briefly reads null (a
  /// pendant health lease lapsing, a socket reconnect), so the label never drops to 0s and back.
  static Duration elapsed(Episode? episode, CaptureProvider capture, DateTime now, {LiveStartAnchor? anchor}) {
    final start = (anchor ?? LiveStartAnchor()).resolve(
      episode: episode,
      captureStart: capture.liveCaptureStartedAt,
      // Phone recordings have a stable per-recording identity through pause/reconnect.
      // Pendant session rolls remain part of the continuous wear timer.
      captureId: capture.liveCaptureSource == 'phone' ? capture.activeRecordingId : null,
      streaming: streamingSource(capture) != null,
      now: now,
    );
    if (start == null) return Duration.zero;
    final span = now.difference(start);
    return span.isNegative ? Duration.zero : span;
  }

  /// The last two moment headings, newest last: "lunch plans, git support for agents".
  static String topics(Episode? episode) {
    if (episode == null) return '';
    final headings = [
      for (final moment in episode.moments)
        if (moment.heading.trim().isNotEmpty) moment.heading.trim()
    ];
    final recent = headings.length > 2 ? headings.sublist(headings.length - 2) : headings;
    return recent.join(', ');
  }

  /// Who is in the conversation, named exactly as the transcript names them: the owner, then each
  /// speaker resolved to one of the user's people, in order of first appearance. An unresolved
  /// speaker ("Speaker 1") is not named here, so the header never knows more than the transcript.
  static List<String> participants(List<TranscriptSegment> segments, List<Person> people, AppLocalizations l10n,
      {String? ownerLabel, String? Function(String personId)? personName}) {
    final names = SpeakerNames.forSegments(segments, people: people, l10n: l10n);
    final owner = <String>{};
    // Display names are not identities: two People records can share a name.
    final others = <String, String>{};
    for (final segment in segments) {
      if (segment.isUser) {
        final name = ownerLabel ?? names.forSegment(segment);
        if (name.isNotEmpty) owner.add(name);
        continue;
      }
      final person = personById(people, segment.personId);
      final name = (segment.personId == null ? null : personName?.call(segment.personId!)) ??
          (person == null ? null : names.forSegment(segment, person: person));
      if (segment.personId != null && name != null && name.trim().isNotEmpty) {
        others.putIfAbsent(segment.personId!, () => name.trim());
      }
    }
    return [...owner, ...others.values];
  }

  /// The source capturing right now, or null when nothing is streaming live (Transcribe Later,
  /// a dropped pendant and a call keep their own Home card).
  static String? streamingSource(CaptureProvider provider) {
    if (provider.isPhoneMicBatchRecording) return null;
    final source = provider.liveCaptureSource;
    if (source != null && source != 'phone') {
      return SharedPreferencesUtil().batchModeEnabled ? null : source;
    }
    final phone = provider.recordingState == RecordingState.record ||
        provider.recordingState == RecordingState.systemAudioRecord ||
        provider.recordingState == RecordingState.initialising ||
        provider.recordingState == RecordingState.interrupted ||
        provider.isPhoneMicPaused;
    return phone ? 'phone' : null;
  }

  /// The capture's state, resolved exactly as the Home capture card and the live page resolve it.
  static CaptureDisplayState displayState(CaptureProvider provider) {
    if (provider.localSttFailure != null) return CaptureDisplayState.recording;
    final interruption = captureInterruption(
      interrupted: provider.recordingState == RecordingState.interrupted,
      readerPaused: provider.isPaused || provider.isPhoneMicPaused,
      osHoldsMic: provider.isCallActive,
    );
    // The pendant's own audio health outranks the transcription connection: a
    // link that owes audio is either failing (recovery exhausted) or still being
    // verified, and neither may claim Listening. A confirmed-subscription quiet
    // verifies (CaptureIngressHealth), so silence between words stays Listening.
    final pendantLive = provider.liveCaptureSource != null && provider.liveCaptureSource != 'phone';
    final pendantPaused = provider.isPaused || provider.isPhoneMicPaused || provider.isCallActive;
    return liveCaptureDisplayState(
      audioInterrupted: interruption == CaptureInterruption.micTaken,
      reconnecting: interruption == CaptureInterruption.recovering,
      paused: provider.isPaused || provider.isPhoneMicPaused || provider.isCallActive,
      pendantNoAudio: pendantLive && !pendantPaused && provider.pendantCaptureActionRequired,
      pendantUnverified: pendantLive && !pendantPaused && !provider.pendantCaptureVerified,
      transcriptionUnavailable: provider.terminalTranscriptionFailure != null || provider.localSttFailure != null,
      bufferingFor: provider.customSttBufferingDuration,
      capturingPhotos: provider.photos.isNotEmpty,
    );
  }

  static bool isListening(CaptureDisplayState state) =>
      state == CaptureDisplayState.listening ||
      state == CaptureDisplayState.capturing ||
      state == CaptureDisplayState.recording;

  static bool canPause(CaptureProvider provider) =>
      provider.liveCaptureSource != null &&
      LiveCaptureCard.canPause(provider.recordingDevice, source: provider.liveCaptureSource);

  static String updatedLabel(Episode episode, DateTime now, AppLocalizations l10n) {
    final updated = episode.stateUpdatedAt;
    final minutes = updated == null ? 0 : now.difference(updated).inMinutes;
    return minutes < 1 ? l10n.episodeUpdatedJustNow : l10n.episodeUpdatedMinutesAgo(minutes);
  }
}
