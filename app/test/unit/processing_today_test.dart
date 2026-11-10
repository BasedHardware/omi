import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/activity/past_processing_section.dart';
import 'package:omi/pages/conversations/home_rows.dart';

void main() {
  final midnight = DateTime(2026, 11, 10);
  ServerConversation row(String id, DateTime at, String step) => ServerConversation(
      id: id, createdAt: at.toUtc(), startedAt: at.toUtc(), structured: Structured('Planning', ''), homeStep: step);
  List<HomeRow> home(List<ServerConversation> rows, {bool todayOnly = true, List<Episode> episodes = const []}) =>
      buildHomeRows(rows, episodes,
          enabled: episodes.isNotEmpty, groupAwaitingTranscript: true, processingTodayOnly: todayOnly, now: midnight);

  for (final step in ['transcribing', 'writing_notes']) {
    test('$step moves at local midnight; ready returns to its original day', () {
      final old = row('old', midnight.subtract(const Duration(seconds: 1)), step);
      final today = row('today', midnight, step);
      expect(home([old, today]).single.conversation.id, 'today');
      expect(home([old, today], todayOnly: false), hasLength(2));
      expect(pastProcessingConversations(pending: [], conversations: [old, today], now: midnight).single.id, 'old');
      final ready = row('old', old.startedAt!, 'ready');
      expect(home([ready]).single.day, DateTime(2026, 11, 9));
      expect(pastProcessingConversations(pending: [], conversations: [ready], now: midnight), isEmpty);
    });
  }

  test('pending work reaches Activity without loading its Home day; completion overrides stale work', () {
    final at = midnight.subtract(const Duration(hours: 1));
    final pending = [
      PendingWorkItem(
          id: 'conv:old', kind: 'conversation', state: 'transcribing', conversationIds: ['old'], startedAt: at.toUtc())
    ];
    expect(pastProcessingConversations(pending: pending, conversations: [], now: midnight).single.id, 'old');
    expect(pastProcessingConversations(pending: pending, conversations: [row('old', at, 'ready')], now: midnight),
        isEmpty);
    expect(pastProcessingConversations(pending: pending, conversations: [], attentionIds: {'old'}, now: midnight),
        isEmpty);
  });

  test('unfinished past episode is hidden but composed notes stay visible', () {
    final at = midnight.subtract(const Duration(hours: 2));
    final member = row('member', at, 'writing_notes');
    final episode = Episode(
        id: 'e', live: false, startedAt: at, lastActivityAt: at, conversationIds: ['member'], members: [member]);
    expect(home([member], episodes: [episode]), isEmpty);
    final ready = row('member', at, 'ready');
    final second = row('second', at, 'ready');
    final waitingEpisode = Episode(
        id: 'e',
        live: false,
        startedAt: at,
        lastActivityAt: at,
        members: [ready, second],
        conversationIds: ['member', 'second'],
        closedAt: midnight.subtract(const Duration(minutes: 1)));
    expect(
        pastProcessingConversations(
                pending: [], conversations: [ready, second], episodes: [waitingEpisode], now: midnight)
            .map((c) => c.id)
            .toSet(),
        {'member', 'second'});
    final composed = Episode(
        id: 'e',
        live: false,
        startedAt: at,
        lastActivityAt: at,
        members: [ready, second],
        conversationIds: ['member', 'second'],
        title: 'Finished occasion',
        moments: [
          EpisodeMoment(
              id: 'm',
              conversationId: 'member',
              startedAt: at,
              endedAt: at,
              points: const [EpisodePoint('A finished note')])
        ]);
    expect(home([ready, second], episodes: [composed]).single.isProcessing, isFalse);
    expect(
        pastProcessingConversations(pending: [], conversations: [ready, second], episodes: [composed], now: midnight),
        isEmpty);
  });

  test('future, failed, noise, deleted and locked rows are not past processing', () {
    final at = midnight.subtract(const Duration(hours: 1));
    expect(
        pastProcessingConversations(pending: [], conversations: [
          row('future', midnight.add(const Duration(days: 1)), 'transcribing'),
          row('failed', at, 'failed'),
          row('noise', at, 'noise'),
          ServerConversation(
              id: 'deleted', createdAt: at, structured: Structured('', ''), homeStep: 'transcribing', deleted: true),
          ServerConversation(
              id: 'locked', createdAt: at, structured: Structured('', ''), homeStep: 'transcribing', isLocked: true),
        ], now: midnight),
        isEmpty);
  });
}
