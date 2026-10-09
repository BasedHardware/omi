/// The caller's own dream-agent runs, decrypted server-side (`GET /v1/dream/runs`). A dogfood
/// surface: the backend answers 404 unless the account is in the dream cohort.
library;

import 'package:omi/backend/schema/gen/dream_wire.g.dart' as wire;

List<Map<String, dynamic>> _maps(Object? value) =>
    value is List ? value.whereType<Map<String, dynamic>>().toList(growable: false) : const [];

enum DreamRunStatus { complete, failed, deadline, idle, other }

DreamRunStatus _status(String value) => switch (value) {
      'complete' => DreamRunStatus.complete,
      'failed' => DreamRunStatus.failed,
      'deadline' => DreamRunStatus.deadline,
      'idle' => DreamRunStatus.idle,
      _ => DreamRunStatus.other,
    };

/// What the agent proposed for one record. In shadow mode [outcome] is `shadow`: nothing changed.
class DreamEdit {
  const DreamEdit({
    required this.kind,
    required this.targetLabel,
    required this.before,
    required this.after,
    required this.reason,
    required this.evidenceCount,
    required this.outcome,
  });

  final String kind;
  final String targetLabel;
  final String before;
  final String after;
  final String reason;
  final int evidenceCount;
  final String outcome;

  bool get applied => outcome == 'applied';

  factory DreamEdit.fromGenerated(wire.GeneratedDreamReportEdit generated) => DreamEdit(
        kind: generated.kind,
        targetLabel: generated.targetLabel,
        before: generated.before,
        after: generated.after,
        reason: generated.reason,
        evidenceCount: generated.evidenceCount,
        outcome: generated.outcome,
      );
}

class DreamTerm {
  const DreamTerm({required this.kind, required this.spelling, required this.aliases});

  final String kind;
  final String spelling;
  final List<String> aliases;

  factory DreamTerm.fromGenerated(wire.GeneratedDreamReportTerm generated) =>
      DreamTerm(kind: generated.kind, spelling: generated.spelling, aliases: generated.aliases);
}

class DreamFeedback {
  const DreamFeedback(
      {required this.component, required this.failureClass, required this.severity, required this.count});

  final String component;
  final String failureClass;
  final String severity;
  final int count;

  factory DreamFeedback.fromGenerated(wire.GeneratedDreamReportFeedback generated) => DreamFeedback(
        component: generated.component,
        failureClass: generated.failureClass,
        severity: generated.severity,
        count: generated.count,
      );
}

class DreamRun {
  const DreamRun({
    required this.runId,
    required this.createdAt,
    required this.manual,
    required this.status,
    required this.errorType,
    required this.recordsRead,
    required this.recordsQueuedAfter,
    required this.dirtyDropped,
    required this.tokens,
    required this.costUsd,
    required this.edits,
    required this.questions,
    required this.slowTasks,
    required this.vocabulary,
    required this.feedback,
    required this.privacyRejected,
  });

  final String runId;
  final DateTime createdAt;
  final bool manual;
  final DreamRunStatus status;
  final String? errorType;
  final int recordsRead;
  final int recordsQueuedAfter;
  final int dirtyDropped;
  final int tokens;
  final double costUsd;
  final List<DreamEdit> edits;
  final List<String> questions;
  final List<String> slowTasks;
  final List<DreamTerm> vocabulary;
  final List<DreamFeedback> feedback;
  final int privacyRejected;

  bool get isEmpty => edits.isEmpty && questions.isEmpty && slowTasks.isEmpty && vocabulary.isEmpty && feedback.isEmpty;

  /// A malformed row never hides the other runs. All field decoding stays in the wire model.
  static DreamRun? fromJson(Map<String, dynamic> json) {
    try {
      final generated = wire.GeneratedDreamRun.fromJson(json);
      return generated.runId.isEmpty ? null : DreamRun.fromGenerated(generated);
    } on FormatException {
      return null;
    }
  }

  factory DreamRun.fromGenerated(wire.GeneratedDreamRun generated) => DreamRun(
        // Idle and deadline passes may carry no run id; use their status so they can render.
        runId: generated.runId.isEmpty ? generated.status : generated.runId,
        createdAt: generated.createdAt.toLocal(),
        manual: generated.trigger == 'manual',
        status: _status(generated.status),
        errorType: generated.errorType?.isEmpty == true ? null : generated.errorType,
        recordsRead: generated.recordsRead,
        recordsQueuedAfter: generated.recordsQueuedAfter,
        dirtyDropped: generated.dirtyDropped,
        tokens: generated.tokens,
        costUsd: generated.costUsd,
        edits: (generated.edits ?? []).map(DreamEdit.fromGenerated).toList(growable: false),
        questions: (generated.questions ?? []).map((q) => q.text).where((t) => t.isNotEmpty).toList(),
        slowTasks: (generated.slowTasks ?? []).map((t) => t.description).where((t) => t.isNotEmpty).toList(),
        vocabulary:
            (generated.vocabulary ?? []).map(DreamTerm.fromGenerated).where((t) => t.spelling.isNotEmpty).toList(),
        feedback: (generated.feedback ?? []).map(DreamFeedback.fromGenerated).toList(growable: false),
        privacyRejected: generated.privacyRejected,
      );
}

class DreamReport {
  const DreamReport({
    required this.live,
    required this.passesToday,
    required this.passesLimit,
    required this.manualRunsToday,
    required this.manualRunsLimit,
    required this.queuedChanges,
    required this.runs,
  });

  /// False in shadow mode: every proposal is a preview and nothing in the account changed.
  final bool live;
  final int passesToday;
  final int passesLimit;
  final int manualRunsToday;
  final int manualRunsLimit;
  final int queuedChanges;
  final List<DreamRun> runs;

  int get manualRunsLeft => (manualRunsLimit - manualRunsToday).clamp(0, manualRunsLimit);

  static DreamReport fromJson(Map<String, dynamic> json) {
    // Validate the envelope separately so malformed historical rows can be omitted.
    final envelope = wire.GeneratedDreamRunsResponse.fromJson({...json, 'runs': []});
    final runs = _maps(json['runs']).map(DreamRun.fromJson).whereType<DreamRun>().toList(growable: false);
    return DreamReport._fromGenerated(envelope, runs);
  }

  factory DreamReport.fromGenerated(wire.GeneratedDreamRunsResponse generated) => DreamReport._fromGenerated(
        generated,
        generated.runs.where((run) => run.runId.isNotEmpty).map(DreamRun.fromGenerated).toList(growable: false),
      );

  factory DreamReport._fromGenerated(wire.GeneratedDreamRunsResponse generated, List<DreamRun> runs) => DreamReport(
        live: generated.mode == 'on',
        passesToday: generated.passesToday,
        passesLimit: generated.passesLimit,
        manualRunsToday: generated.manualRunsToday,
        manualRunsLimit: generated.manualRunsLimit,
        queuedChanges: generated.queuedChanges,
        runs: runs,
      );
}

/// Why a run-now request did not produce a run.
enum DreamRunNowRefusal { inProgress, limit }
