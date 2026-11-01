import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_notes.dart' show LivePreviewNotesResult;
import 'package:omi/services/live_preview/local_preview_admission.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

enum LivePreviewPlatform { ios, android }

/// Typed local-preview telemetry. Closed enums and integers only: no
/// transcript text, audio, locale string or identity ever leaves the phone.
class LivePreviewTelemetry {
  LivePreviewTelemetry({void Function(RegisteredEvent event)? emit}) : _emit = emit ?? const TypedEvents().emit;

  final void Function(RegisteredEvent event) _emit;

  void engineSelected(LivePreviewStart start, {required LivePreviewPlatform platform, required int osMajor}) {
    _emit(LivePreviewEngineSelected(
      engine: LivePreviewEngineSelectedEngine.values.byName(start.engine.name),
      reason: LivePreviewEngineSelectedReason.values.byName(start.reason.name),
      platform: LivePreviewEngineSelectedPlatform.values.byName(platform.name),
      osMajor: osMajor,
      bundledInstalled: start.bundledInstalled,
    ));
  }

  /// The client did not ask for local preview (or stopped honouring a grant
  /// mid-session) because its routing could not journal pendant audio.
  void notRequested(String reasonWireName, {required bool midSession}) {
    _emit(LivePreviewNotRequested(
      reason: LivePreviewNotRequestedReason.values.firstWhere((value) => value.wireName == reasonWireName),
      midSession: midSession,
    ));
  }

  void verdict(LocalPreviewVerdictReport report, {required LivePreviewPlatform platform}) {
    _emit(LivePreviewVerdict(
      verdict: LivePreviewVerdictVerdict.values.firstWhere((value) => value.wireName == report.outcome.wireName),
      platform: LivePreviewVerdictPlatform.values.byName(platform.name),
      verdictLatencyMs: report.verdictLatencyMs,
      holdDurationMs: report.holdDurationMs,
      heldFrames: report.heldFrames,
      holdTimeoutReplayed: report.holdTimeoutReplayed,
    ));
  }

  void firstWord(LivePreviewEngineKind engine, {required int latencyMs}) {
    _emit(LivePreviewFirstWord(engine: LivePreviewFirstWordEngine.values.byName(engine.name), latencyMs: latencyMs));
  }

  /// Preview-to-record disagreement is not computed in this release: the
  /// record lands later through sync/batch with no reliable span match on
  /// the phone. Word count and audio duration let a follow-up normalise it.
  void sessionEnded(
    LivePreviewEngineKind engine, {
    required int previewWords,
    required int previewAudioMs,
    required int droppedAudioMs,
  }) {
    _emit(LivePreviewSessionEnded(
      engine: LivePreviewSessionEndedEngine.values.byName(engine.name),
      previewWords: previewWords,
      previewAudioMs: previewAudioMs,
      droppedAudioMs: droppedAudioMs,
    ));
  }

  /// One on-device live-notes attempt: which engine, how it went, how long it
  /// took and how many bullets it drafted. Never any text.
  void notesRun({
    required String engine,
    required LivePreviewNotesResult outcome,
    required int latencyMs,
    required int bulletCount,
  }) {
    _emit(LivePreviewNotes(
      engine: LivePreviewNotesEngine.values.firstWhere((value) => value.wireName == engine),
      outcome: switch (outcome) {
        LivePreviewNotesResult.ok => LivePreviewNotesOutcome.ok,
        LivePreviewNotesResult.unavailable => LivePreviewNotesOutcome.unavailable,
        LivePreviewNotesResult.error => LivePreviewNotesOutcome.error,
        LivePreviewNotesResult.droppedBusy => LivePreviewNotesOutcome.droppedBusy,
      },
      latencyMs: latencyMs,
      bulletCount: bulletCount,
    ));
  }
}
