import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversations/home_rows.dart';

import '../helpers/home_ready_members_fixture.dart';

void main() {
  test('Today pending members of an older owner share the one row; terminal members do not count', () {
    final now = DateTime(2026, 11, 15, 12, 36);
    final fixture = HomeSettledNoiseFixture(now);
    List<HomeRow> project({bool reverse = false}) => buildHomeRows(
        reverse
            ? [...fixture.localPending.reversed, ...fixture.members.reversed]
            : [...fixture.members, ...fixture.localPending],
        reverse ? [fixture.older, fixture.waiting] : [fixture.waiting, fixture.older],
        enabled: true,
        groupAwaitingTranscript: true,
        processingTodayOnly: true,
        now: now,
        liveConversationIds: fixture.live.conversationIds.toSet(),
        liveEpisodeId: fixture.live.id,
        processingConversations: fixture.localPending);
    final rows = project();
    final pending = rows.where((r) => r.isProcessing).single;
    expect(rows.first, pending);
    expect(pending.day, localHomeDay(now));
    expect(pending.step, HomeStep.transcribing);
    expect(pending.count, 3);
    expect(pending.episode!.members.map((m) => m.id).toSet(), fixture.localPending.map((m) => m.id).toSet());
    expect(rows.where((r) => r.isTemporaryMember).map((r) => r.conversation.id).toSet(),
        fixture.members.take(10).map((m) => m.id).toSet());
    expect(rows.where((r) => r.conversation.homeStep == 'noise'), isEmpty);
    expect(project(reverse: true).map((r) => r.conversation.id), rows.map((r) => r.conversation.id));
  });

  test('known server step wins over an unknown local entry, otherwise transcription is the safe fallback', () {
    final now = DateTime(2026, 11, 15, 12);
    final local = HomeSettledNoiseFixture(now).localPending.first;
    List<HomeRow> project({String? knownStep}) => buildHomeRows([local], [],
        enabled: true,
        groupAwaitingTranscript: true,
        processingConversations: [local],
        knownConversations: [if (knownStep != null) local.withHomeStep(knownStep)]);
    expect(project().single.step, HomeStep.transcribing);
    expect(project(knownStep: 'writing_notes').single.step, HomeStep.writingNotes);
    expect(project(knownStep: 'ready').single.isProcessing, isFalse);
    expect(project(knownStep: 'noise'), isEmpty);
  });
}
