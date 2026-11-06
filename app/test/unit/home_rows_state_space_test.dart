import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/home_rows.dart';

// Model-based walk of the Home row state space. Every combination of episode shape, member
// state, local processing flag and summary age goes through buildHomeRows, and the rows it
// returns must satisfy the invariants below in every state, not only in the states a
// hand-written example names. A new state that breaks an invariant fails here first.

final _start = DateTime(2026, 11, 6, 12);
final _now = DateTime(2026, 11, 6, 13);
const _ages = [0, 10, 20, 240];

enum _Member { transcribing, writingNotes, ready, noise, failed, locked, discarded, deleted }

/// Members a Home row must show somewhere (nothing a user should lose from Home).
const _shownStates = {_Member.transcribing, _Member.writingNotes, _Member.ready, _Member.locked};

ServerConversation _conversation(String id, _Member state, int minute) {
  final at = _start.add(Duration(minutes: minute));
  var structured = Structured('Title $id', '');
  var status = ConversationStatus.completed;
  String? homeStep;
  var locked = false;
  var discarded = false;
  var deleted = false;
  switch (state) {
    case _Member.transcribing:
      structured = Structured('', '');
    case _Member.writingNotes:
      status = ConversationStatus.processing;
      structured = Structured('', '');
      homeStep = 'writing_notes';
    case _Member.ready:
      homeStep = 'ready';
    case _Member.noise:
      homeStep = 'noise';
    case _Member.failed:
      homeStep = 'failed';
    case _Member.locked:
      locked = true;
    case _Member.discarded:
      discarded = true;
    case _Member.deleted:
      deleted = true;
  }
  return ServerConversation(
    id: id,
    createdAt: at,
    startedAt: at,
    finishedAt: at.add(const Duration(minutes: 1)),
    structured: structured,
    status: status,
    homeStep: homeStep,
    isLocked: locked,
    discarded: discarded,
    deleted: deleted,
  );
}

Episode _episode(List<ServerConversation> members,
        {required bool live, required bool composed, required int ageMinutes}) =>
    Episode(
      id: 'e',
      live: live,
      startedAt: _start,
      lastActivityAt: _now.subtract(Duration(minutes: ageMinutes)),
      moments: composed
          ? [
              EpisodeMoment(
                id: 'm',
                conversationId: members.first.id,
                startedAt: _start,
                endedAt: _start.add(const Duration(hours: 1)),
                points: const [EpisodePoint('A real point')],
              ),
            ]
          : const [],
      conversationIds: [for (final m in members) m.id],
      members: members,
      title: 'Evening planning',
      emoji: '📝',
    );

class _Scenario {
  _Scenario(this.states, this.flags, {required this.live, required this.composed, required this.age});
  final List<_Member> states;

  /// Whether each member is still in the app's local processing list.
  final List<bool> flags;
  final bool live;
  final bool composed;
  final int age;

  String describe() => '${states.length} member(s) ${[
        for (var i = 0; i < states.length; i++) '${states[i].name}${flags[i] ? "+local" : ""}'
      ]} live=$live composed=$composed ageMin=$age';
}

List<_Scenario> _scenarios() {
  final out = <_Scenario>[];
  final count = _Member.values.length;
  for (final n in [1, 2]) {
    final combos = n == 1 ? count : count * count;
    for (var c = 0; c < combos; c++) {
      final states = n == 1 ? [_Member.values[c]] : [_Member.values[c ~/ count], _Member.values[c % count]];
      for (var bits = 0; bits < (1 << n); bits++) {
        final flags = [for (var i = 0; i < n; i++) bits & (1 << i) != 0];
        for (final live in [false, true]) {
          for (final composed in [false, true]) {
            for (final age in _ages) {
              out.add(_Scenario(states, flags, live: live, composed: composed, age: age));
            }
          }
        }
      }
    }
  }
  return out;
}

/// The member's own server-side state says it is still in progress.
bool _serverUnfinished(ServerConversation m) =>
    m.clientProcessing != null || m.processingDeferred || homeStepOf(m) != null;

bool _covers(HomeRow row, String id) =>
    row.conversation.id == id ||
    row.episodeConversationIds.contains(id) ||
    (row.episode?.members.any((m) => m.id == id) ?? false);

List<String> _violations(_Scenario s, List<ServerConversation> members, Episode episode,
    List<ServerConversation> processing, List<HomeRow> rows) {
  final out = <String>[];
  // A processing hold is justified by the summary wait, or by a member the server still reports as
  // unfinished. A hold kept only by a stale local entry for a member the server says is finished is not.
  final justified = episode.awaitingSummary(_now) || members.any(_serverUnfinished);

  for (final row in rows) {
    // Episode-level rows only: a single recording's own row keeps its conversation id, and
    // the fold's synthetic episode carries an empty id.
    final isEpisodeRow = row.episode?.id == episode.id;
    if (!episode.live && episode.composed && row.isProcessing && isEpisodeRow) {
      out.add('composed-episode-shows-processing');
    }
    if (!episode.live && row.isProcessing && isEpisodeRow && !justified) {
      out.add('stale-processing-hold');
    }
    if (row.episode == null &&
        !row.isProcessing &&
        (isHomeNoise(row.conversation) || homeStepOf(row.conversation) == HomeStep.failed)) {
      out.add('standalone-noise-or-failed-shown');
    }
    final episodeMembers = row.episode?.members ?? const <ServerConversation>[];
    if (row.episode != null &&
        !row.isProcessing &&
        episodeMembers.isNotEmpty &&
        episodeMembers.every((m) => m.homeStep == 'noise' || m.homeStep == 'failed')) {
      out.add('episode-row-of-only-noise-or-failed');
    }
  }
  for (var i = 0; i + 1 < rows.length; i++) {
    if (rows[i].isProcessing && rows[i + 1].isProcessing && rows[i].day == rows[i + 1].day) {
      out.add('adjacent-processing-rows-not-folded');
    }
    if (rows[i].startedAt.isBefore(rows[i + 1].startedAt)) out.add('rows-out-of-order');
  }
  for (var i = 0; i < members.length; i++) {
    final state = s.states[i];
    if (!_shownStates.contains(state)) continue;
    final covering = rows.where((r) => _covers(r, members[i].id)).length;
    if (covering == 0) out.add('recording-dropped-from-home');
    if (covering > 1) out.add('recording-shown-more-than-once');
  }
  return out;
}

void main() {
  test('every Home row state keeps its invariants', () {
    final scenarios = _scenarios();
    final violations = <String, List<String>>{};
    for (final s in scenarios) {
      final members = [for (var i = 0; i < s.states.length; i++) _conversation('c$i', s.states[i], i)];
      final episode = _episode(members, live: s.live, composed: s.composed, ageMinutes: s.age);
      final processing = [
        for (var i = 0; i < members.length; i++)
          if (s.flags[i]) members[i]
      ];
      final rows = buildHomeRows(
        members,
        [episode],
        enabled: true,
        processingConversations: processing,
        processingTitle: 'Processing',
        finishingTitle: 'Finishing up…',
        groupAwaitingTranscript: true,
        now: _now,
      );
      for (final code in _violations(s, members, episode, processing, rows)) {
        violations.putIfAbsent(code, () => []).add(s.describe());
      }
    }
    final report = StringBuffer('scenarios=${scenarios.length}\n');
    for (final entry in violations.entries) {
      report.writeln('${entry.key}: ${entry.value.length}');
      for (final example in entry.value.take(3)) {
        report.writeln('    $example');
      }
    }
    // ignore: avoid_print
    print(report);
    expect(violations, isEmpty, reason: report.toString());
  });
}
