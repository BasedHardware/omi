import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/pages/conversations/home_card_rows.dart';

void main() {
  final now = DateTime(2026, 11, 15, 12);
  HomeFeedCard card(String id, String step, {String kind = 'conversation', int minute = 0}) => HomeFeedCard(
      id: '$kind:$id',
      kind: kind,
      detailId: id,
      startedAt: now.subtract(Duration(minutes: minute)),
      title: 'Fixture $id',
      emoji: '',
      preview: 'Own notes',
      status: 'completed',
      homeStep: step,
      starred: false,
      isLocked: false,
      hasTasks: false,
      memberCount: kind == 'episode' ? 2 : 1,
      sources: const [],
      summaryAvailable: true,
      revision: 'fixture');
  for (final a in ['ready', 'noise', 'transcribing', 'writing_notes', 'failed']) {
    for (final b in ['ready', 'noise', 'transcribing', 'writing_notes', 'failed']) {
      test('compact pending scope and atomic replacement: $a/$b', () {
        final cards = [card('a', a), card('finished', 'ready', kind: 'episode', minute: 1), card('b', b, minute: 2)];
        final rows = buildHomeCardRows(cards, [], now: now, processingTitle: 'Processing');
        final pendingIds = {
          if (['transcribing', 'writing_notes'].contains(a)) 'a',
          if (['transcribing', 'writing_notes'].contains(b)) 'b'
        };
        final processing = rows.where((r) => r.isProcessing).toList();
        expect(processing.length, pendingIds.isEmpty ? 0 : 1);
        if (processing.isNotEmpty) {
          expect(rows.first, processing.single);
          expect(processing.single.count, pendingIds.length);
          expect(processing.single.episode!.members.map((m) => m.id).toSet(), pendingIds);
          expect(processing.single.episode!.conversationIds.toSet(), pendingIds);
        }
        expect(rows.where((r) => !r.isProcessing).map((r) => r.conversation.id).toSet(),
            {'episode:finished', if (a == 'ready') 'a', if (b == 'ready') 'b'});
        expect(
            buildHomeCardRows(cards.reversed.toList(), [], now: now, processingTitle: 'Processing')
                .map((r) => r.conversation.id),
            rows.map((r) => r.conversation.id));
        final replaced =
            buildHomeCardRows([card('owner', 'ready', kind: 'episode')], [], now: now, processingTitle: 'Processing');
        expect(replaced.map((r) => r.conversation.id), ['episode:owner']);
        expect(replaced.single.isProcessing, isFalse);
      });
    }
  }
}
