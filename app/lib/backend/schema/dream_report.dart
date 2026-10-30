/// The caller's own dream-agent runs, decrypted server-side (`GET /v1/dream/runs`). A dogfood
/// surface: the backend answers 404 unless the account is in the dream cohort.
library;

import 'gen/dream_wire.g.dart' as wire;

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

  static DreamEdit fromJson(Map<String, dynamic> json) =>
      DreamEdit.fromGenerated(wire.GeneratedDreamReportEdit.fromJson(json));

  factory DreamEdit.fromGenerated(wire.GeneratedDreamReportEdit value) => DreamEdit(
        kind: value.kind,
        targetLabel: value.targetLabel,
        before: value.before,
        after: value.after,
        reason: value.reason,
        evidenceCount: value.evidenceCount,
        outcome: value.outcome,
      );
}

class DreamTerm {
  const DreamTerm({
    required this.kind,
    required this.spelling,
    required this.aliases,
  });

  final String kind;
  final String spelling;
  final List<String> aliases;

  static DreamTerm fromJson(Map<String, dynamic> json) =>
      DreamTerm.fromGenerated(wire.GeneratedDreamReportTerm.fromJson(json));

  factory DreamTerm.fromGenerated(wire.GeneratedDreamReportTerm value) => DreamTerm(
        kind: value.kind,
        spelling: value.spelling,
        aliases: value.aliases,
      );
}

class DreamFeedback {
  const DreamFeedback({
    required this.component,
    required this.failureClass,
    required this.severity,
    required this.count,
  });

  final String component;
  final String failureClass;
  final String severity;
  final int count;

  static DreamFeedback fromJson(Map<String, dynamic> json) => DreamFeedback.fromGenerated(
        wire.GeneratedDreamReportFeedback.fromJson(json),
      );

  factory DreamFeedback.fromGenerated(
    wire.GeneratedDreamReportFeedback value,
  ) =>
      DreamFeedback(
        component: value.component,
        failureClass: value.failureClass,
        severity: value.severity,
        count: value.count,
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

  /// Isolate malformed history rows without bypassing the backend-owned wire decoder.
  static DreamRun? fromJson(Map<String, dynamic> json) {
    try {
      return DreamRun.fromGenerated(wire.GeneratedDreamRun.fromJson(json));
    } on FormatException {
      return null;
    }
  }

  static DreamRun? fromGenerated(wire.GeneratedDreamRun value) {
    if (value.runId.isEmpty) return null;
    return DreamRun(
      runId: value.runId,
      createdAt: value.createdAt.toLocal(),
      manual: value.trigger == 'manual',
      status: _status(value.status),
      errorType: value.errorType?.isEmpty == true ? null : value.errorType,
      recordsRead: value.recordsRead,
      recordsQueuedAfter: value.recordsQueuedAfter,
      dirtyDropped: value.dirtyDropped,
      tokens: value.tokens,
      costUsd: value.costUsd,
      edits: (value.edits ?? []).map(DreamEdit.fromGenerated).toList(growable: false),
      questions: (value.questions ?? []).map((q) => q.text).where((t) => t.isNotEmpty).toList(),
      slowTasks: (value.slowTasks ?? []).map((t) => t.description).where((t) => t.isNotEmpty).toList(),
      vocabulary: (value.vocabulary ?? []).map(DreamTerm.fromGenerated).where((t) => t.spelling.isNotEmpty).toList(),
      feedback: (value.feedback ?? []).map(DreamFeedback.fromGenerated).toList(growable: false),
      privacyRejected: value.privacyRejected,
    );
  }
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
    // The history endpoint tolerates an invalid row, while allowance fields still
    // use the generated contract. Decode each run before decoding the envelope.
    final rawRuns = json['runs'];
    final validRuns = <wire.GeneratedDreamRun>[];
    if (rawRuns is List) {
      for (final row in rawRuns.whereType<Map<String, dynamic>>()) {
        try {
          final run = wire.GeneratedDreamRun.fromJson(row);
          if (run.runId.isNotEmpty) validRuns.add(run);
        } on FormatException {
          continue;
        }
      }
    }
    return DreamReport.fromGenerated(
      wire.GeneratedDreamRunsResponse.fromJson({
        ...json,
        'runs': validRuns.map((run) => run.toJson()).toList(growable: false),
      }),
    );
  }

  factory DreamReport.fromGenerated(wire.GeneratedDreamRunsResponse value) => DreamReport(
        live: value.mode == 'on',
        passesToday: value.passesToday,
        passesLimit: value.passesLimit,
        manualRunsToday: value.manualRunsToday,
        manualRunsLimit: value.manualRunsLimit,
        queuedChanges: value.queuedChanges,
        runs: value.runs.map(DreamRun.fromGenerated).whereType<DreamRun>().toList(growable: false),
      );
}

/// Why a run-now request did not produce a run.
enum DreamRunNowRefusal { inProgress, limit }
