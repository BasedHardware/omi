/// The caller's own dream-agent runs, decrypted server-side (`GET /v1/dream/runs`). A dogfood
/// surface: the backend answers 404 unless the account is in the dream cohort.
library;

import 'package:omi/backend/schema/gen/dream_wire.g.dart' as wire;

String _str(Object? value) => value is String ? value : '';
int _int(Object? value) => value is num ? value.toInt() : 0;
double _double(Object? value) => value is num ? value.toDouble() : 0;
List<Map<String, dynamic>> _maps(Object? value) =>
    value is List ? value.whereType<Map<String, dynamic>>().toList(growable: false) : const [];
List<String> _strings(Object? value) => value is List ? value.whereType<String>().toList(growable: false) : const [];

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

  static DreamEdit fromJson(Map<String, dynamic> json) => DreamEdit(
        kind: _str(json['kind']),
        targetLabel: _str(json['target_label']),
        before: _str(json['before']),
        after: _str(json['after']),
        reason: _str(json['reason']),
        evidenceCount: _int(json['evidence_count']),
        outcome: _str(json['outcome']),
      );
}

class DreamTerm {
  const DreamTerm({required this.kind, required this.spelling, required this.aliases});

  final String kind;
  final String spelling;
  final List<String> aliases;

  static DreamTerm fromJson(Map<String, dynamic> json) =>
      DreamTerm(kind: _str(json['kind']), spelling: _str(json['spelling']), aliases: _strings(json['aliases']));
}

class DreamFeedback {
  const DreamFeedback(
      {required this.component, required this.failureClass, required this.severity, required this.count});

  final String component;
  final String failureClass;
  final String severity;
  final int count;

  static DreamFeedback fromJson(Map<String, dynamic> json) => DreamFeedback(
        component: _str(json['component']),
        failureClass: _str(json['failure_class']),
        severity: _str(json['severity']),
        count: _int(json['count']),
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

  static DreamRun? fromGenerated(wire.GeneratedDreamRun value) {
    final json = value.toJson();
    // Idle and deadline passes may have no run id; preserve their stable display id.
    if ((json['run_id'] as String? ?? '').isEmpty) json['run_id'] = json['status'] ?? 'idle';
    return fromJson(json);
  }

  /// Returns null for a row without an id or timestamp so one malformed run never hides the rest.
  static DreamRun? fromJson(Map<String, dynamic> json) {
    final id = _str(json['run_id']);
    final created = DateTime.tryParse(_str(json['created_at']));
    if (id.isEmpty || created == null) return null;
    final error = _str(json['error_type']);
    return DreamRun(
      runId: id,
      createdAt: created.toLocal(),
      manual: json['trigger'] == 'manual',
      status: _status(_str(json['status'])),
      errorType: error.isEmpty ? null : error,
      recordsRead: _int(json['records_read']),
      recordsQueuedAfter: _int(json['records_queued_after']),
      dirtyDropped: _int(json['dirty_dropped']),
      tokens: _int(json['tokens']),
      costUsd: _double(json['cost_usd']),
      edits: _maps(json['edits']).map(DreamEdit.fromJson).toList(growable: false),
      questions: _maps(json['questions']).map((q) => _str(q['text'])).where((t) => t.isNotEmpty).toList(),
      slowTasks: _maps(json['slow_tasks']).map((t) => _str(t['description'])).where((t) => t.isNotEmpty).toList(),
      vocabulary: _maps(json['vocabulary']).map(DreamTerm.fromJson).where((t) => t.spelling.isNotEmpty).toList(),
      feedback: _maps(json['feedback']).map(DreamFeedback.fromJson).toList(growable: false),
      privacyRejected: _int(json['privacy_rejected']),
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

  static DreamReport fromGenerated(wire.GeneratedDreamRunsResponse value) => fromJson(value.toJson());

  static DreamReport fromJson(Map<String, dynamic> json) => DreamReport(
        live: json['mode'] == 'on',
        passesToday: _int(json['passes_today']),
        passesLimit: _int(json['passes_limit']),
        manualRunsToday: _int(json['manual_runs_today']),
        manualRunsLimit: _int(json['manual_runs_limit']),
        queuedChanges: _int(json['queued_changes']),
        runs: _maps(json['runs']).map(DreamRun.fromJson).whereType<DreamRun>().toList(growable: false),
      );
}

/// Why a run-now request did not produce a run.
enum DreamRunNowRefusal { inProgress, limit }
