import 'dart:convert';
import 'dart:io';

/// Journey evidence emitter (SCA-488 / C2).
///
/// Binds each journey run to the C1 `session-evidence-v1` accounting rules:
/// honest counts (`passed + failed + skipped == executed`), zero-execution
/// receipts are never success, failures name the missing invariant, and state
/// before/after plus real timestamps are recorded. Machine pass results are
/// produced only by executed test assertions — this file merely witnesses
/// them; an agent cannot author a pass.
class JourneyEvidence {
  JourneyEvidence._({
    required this.journeyId,
    required this.lane,
    required this.startedAt,
    required this.artifactIdentity,
  });

  final String journeyId;
  final String lane;
  final DateTime startedAt;
  final Map<String, Object?> artifactIdentity;
  DateTime? _finishedAt;

  int passed = 0;
  int failed = 0;
  int skipped = 0;
  final List<Map<String, Object?>> assertions = [];
  Map<String, Object?> stateBefore = {};
  Map<String, Object?> stateAfter = {};
  final List<String> timeline = [];

  static JourneyEvidence begin({
    required String journeyId,
    required String lane,
    Map<String, Object?>? artifactIdentity,
  }) {
    return JourneyEvidence._(
      journeyId: journeyId,
      lane: lane,
      startedAt: DateTime.now().toUtc(),
      artifactIdentity: artifactIdentity ?? const {},
    );
  }

  void note(String event) => timeline.add('${DateTime.now().toUtc().toIso8601String()} $event');

  void record(String name, {required bool ok, String? invariant, Object? detail}) {
    assertions.add({
      'name': name,
      'ok': ok,
      if (invariant != null) 'invariant': invariant,
      if (detail != null) 'detail': '$detail',
    });
    ok ? passed++ : failed++;
  }

  void skip(String name, String reason) {
    assertions.add({'name': name, 'skipped': true, 'reason': reason});
    skipped++;
  }

  Map<String, Object?> toJson() => {
        'journey_id': journeyId,
        'lane': lane,
        'contract_versions': {
          'evidence': 'session-evidence-v1-accounting',
          'journeys': 'seeded-journeys/v1',
        },
        'artifact': artifactIdentity,
        'started_at': startedAt.toIso8601String(),
        'finished_at': (_finishedAt ?? DateTime.now().toUtc()).toIso8601String(),
        'counts': {'passed': passed, 'failed': failed, 'skipped': skipped, 'executed': passed + failed + skipped},
        'outcome': failed > 0
            ? 'failed'
            : (passed + failed) == 0
                ? 'zero-execution'
                : 'passed',
        'assertions': assertions,
        'state_before': stateBefore,
        'state_after': stateAfter,
        'timeline': timeline,
      };

  /// Writes the receipt. Directory defaults to a temp dir; the runner passes
  /// `OMI_JOURNEY_EVIDENCE_DIR` to collect receipts for handoff.
  Future<String> write() async {
    _finishedAt = DateTime.now().toUtc();
    final dir = Platform.environment['OMI_JOURNEY_EVIDENCE_DIR'] ?? Directory.systemTemp.path;
    final target = Directory(dir);
    if (!target.existsSync()) target.createSync(recursive: true);
    final file = File('${target.path}/${journeyId}_${startedAt.microsecondsSinceEpoch}.json');
    await file.writeAsString(const JsonEncoder.withIndent('  ').convert(toJson()));
    return file.path;
  }
}
