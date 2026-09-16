// Versioned scenario/result contract for deterministic recording-recovery
// replay (C3 lane of the mobile development foundation).
//
// Consumers:
// - C2 (semantic controls) drives replay scenarios and reads
//   [CaptureScenarioResult]s through this adapter — never capture internals.
// - C4 (verification integration) discovers runnable scenario ids from
//   [CaptureScenarioCatalog] and maps them to runner selections.
// - The concrete replay engine lives with the capture tests; this file owns
//   only the stable, additive contract between lanes.
library;

import 'dart:convert';

const String captureScenarioContractVersion = 'capture-scenario/v1';

/// A named, versioned replay scenario. Ids are stable identifiers: runners,
/// CI selection and receipts reference them by string.
class CaptureScenarioDescriptor {
  final String id;
  final String description;

  /// True when the scenario is an adverse/negative variant: it must fail (or
  /// force retention) when a specific guard is removed, proving the oracle can
  /// reject wrong behavior.
  final bool negative;

  const CaptureScenarioDescriptor({required this.id, required this.description, this.negative = false});

  Map<String, Object?> toJson() => {'id': id, 'description': description, 'negative': negative};
}

/// One entry in a scenario's failure/evidence timeline. Timestamps are
/// scenario-relative virtual time, not wall clock.
class CaptureScenarioTimelineEntry {
  final Duration at;
  final String event;
  final Map<String, Object?> details;

  const CaptureScenarioTimelineEntry({required this.at, required this.event, this.details = const {}});

  Map<String, Object?> toJson() => {
        'at_ms': at.inMilliseconds,
        'event': event,
        if (details.isNotEmpty) 'details': details,
      };
}

enum CaptureScenarioOutcome { passed, failed }

/// The result of replaying one scenario against real production capture/WAL
/// objects. [observations] carries scenario-specific structured state (WAL
/// counts by status, uploaded byte totals, state-transition sequences); it is
/// evidence, not a pass claim — [outcome] records the runner's verdict.
class CaptureScenarioResult {
  final String scenarioId;
  final String contractVersion;
  final CaptureScenarioOutcome outcome;
  final String? failureReason;
  final List<CaptureScenarioTimelineEntry> timeline;
  final Map<String, Object?> observations;

  const CaptureScenarioResult({
    required this.scenarioId,
    required this.outcome,
    required this.timeline,
    this.observations = const {},
    this.failureReason,
    this.contractVersion = captureScenarioContractVersion,
  });

  bool get passed => outcome == CaptureScenarioOutcome.passed;

  Map<String, Object?> toJson() => {
        'scenario_id': scenarioId,
        'contract_version': contractVersion,
        'outcome': outcome.name,
        if (failureReason != null) 'failure_reason': failureReason,
        'timeline': timeline.map((e) => e.toJson()).toList(),
        'observations': observations,
      };

  String toJsonString() => const JsonEncoder.withIndent('  ').convert(toJson());
}

/// The six concrete recording-recovery schedules (plus their adverse variants)
/// that C3 replays through the production capture -> frame processing ->
/// file-backed WAL -> recovery/upload path. C4 uses these ids for runner
/// discovery; new scenarios append additively and bump nothing — ids are
/// immutable once published.
class CaptureScenarioCatalog {
  static const String schemaVersion = 'capture-scenario-catalog/v1';

  static const List<CaptureScenarioDescriptor> recordingRecovery = [
    CaptureScenarioDescriptor(
      id: 'network-loss-reconnect-during-capture',
      description: 'Socket drops mid-capture; unsynced frames must persist to disk WAL, '
          'reconnect restores streaming, recovery drain uploads without local duplicates.',
    ),
    CaptureScenarioDescriptor(
      id: 'stale-native-event-after-stop-new-session',
      description: 'Native events carrying a retired session id must be dropped; a stale '
          'terminal idle cannot clobber the fresh session.',
      negative: true,
    ),
    CaptureScenarioDescriptor(
      id: 'interruption-resumption',
      description: 'Native audio-session interruption mirrors state without teardown; '
          'recovery resumes the same authoritative session.',
    ),
    CaptureScenarioDescriptor(
      id: 'partial-torn-persistence-reconstruction',
      description: 'Process reconstruction reloads WAL state from real temp files; torn '
          'wals.json falls back to the backup file; missing audio marks corrupted.',
    ),
    CaptureScenarioDescriptor(
      id: 'failed-upload-retry-recovery',
      description: 'Failed uploads stay retryable with bounded backoff; uploaded jobs '
          'resolve to synced only after server acknowledgement.',
    ),
    CaptureScenarioDescriptor(
      id: 'ownership-transition-outstanding-work',
      description: 'Account/device ownership transition during outstanding WAL work must '
          'not upload under a wrong identity; work stays local and retryable.',
    ),
  ];

  static List<String> get ids => recordingRecovery.map((s) => s.id).toList();
}
