import 'dart:io';
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
          enabled: episodes.isNotEmpty,
          groupAwaitingTranscript: true,
          processingTodayOnly: todayOnly,
          activityOnlyFailures: todayOnly,
          now: midnight);

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
    final expiredWait = ServerConversation(
        id: 'old',
        createdAt: at,
        startedAt: at,
        structured: Structured('', ''),
        status: ConversationStatus.processing,
        homeStep: 'failed');
    expect(pastProcessingConversations(pending: pending, conversations: [expiredWait], now: midnight), isEmpty);
    expect(home([expiredWait]), isEmpty);
    expect(failedActivityConversations(pending: pending, conversations: [expiredWait]).single.id, 'old');
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
  test('expired today wait is only in Activity; rollback restores the Home row', () {
    final at = midnight.add(const Duration(hours: 1));
    final expired = ServerConversation(
        id: 'expired',
        createdAt: at,
        startedAt: at,
        structured: Structured('', ''),
        status: ConversationStatus.processing,
        homeStep: 'failed');
    final pending = [
      PendingWorkItem(
          id: 'conv:expired', kind: 'conversation', state: 'summarizing', conversationIds: ['expired'], startedAt: at)
    ];
    final rows = buildHomeRows(
        [expired, row('older', midnight.subtract(const Duration(hours: 1)), 'writing_notes')], [],
        enabled: false,
        groupAwaitingTranscript: true,
        processingTodayOnly: true,
        activityOnlyFailures: true,
        now: midnight.add(const Duration(hours: 8)));
    expect(rows, isEmpty);
    expect(failedActivityConversations(pending: pending, conversations: [expired]).single.id, 'expired');
    expect(home([expired], todayOnly: false).single.conversation.id, 'expired');
    expect(
        pastProcessingConversations(
            pending: pending, conversations: [expired], now: midnight.add(const Duration(hours: 8))),
        isEmpty);
  });

  test('episode_id survives API, cache and transcript copy; older APIs omit it', () {
    final original = ServerConversation.fromJson({...row('member', midnight, 'ready').toJson(), 'episode_id': 'e'});
    expect(original.episodeId, 'e');
    expect(ServerConversation.fromJson(original.toJson()).episodeId, 'e');
    expect(ServerConversation.fromGenerated(original.toGenerated()).episodeId, 'e');
    expect(original.withTranscriptSegments([]).withHomeStep('ready').episodeId, 'e');
    expect(ServerConversation.fromJson(row('old', midnight, 'ready').toJson()).episodeId, isNull);
    expect(original.toJson(), isNot(contains('home_step')));
  });

  test('episode-owned row never flashes standalone before or after episode fetch', () {
    for (final step in ['ready', 'writing_notes', 'failed']) {
      final member = ServerConversation(
          id: 'member',
          createdAt: midnight,
          startedAt: midnight,
          structured: Structured('Planning', ''),
          homeStep: step,
          episodeId: 'e');
      final episode = Episode(
          id: 'e',
          live: false,
          startedAt: midnight,
          lastActivityAt: midnight,
          conversationIds: const [],
          members: const []);
      for (final episodes in [
        <Episode>[],
        [episode]
      ]) {
        final rows = home([member], episodes: episodes, todayOnly: step != 'failed');
        expect(rows, hasLength(1));
        expect(rows.single.episode?.id, 'e');
        expect(rows.single.episodeConversationIds, contains('member'));
      }
    }
  });

  test('queued past work is labelled as awaiting transcription', () {
    final items = [
      PendingWorkItem(
          id: 'conv:q',
          kind: 'conversation',
          state: 'queued',
          conversationIds: ['q'],
          startedAt: midnight.subtract(const Duration(hours: 1)))
    ];
    expect(homeStepOf(pastProcessingConversations(pending: items, conversations: [], now: midnight).single),
        HomeStep.transcribing);
  });

  test('UTC instants follow the local calendar in east and west zones', () {
    for (final instant in [DateTime.utc(2026, 11, 10, 0, 30), DateTime.utc(2026, 11, 10, 23, 30)]) {
      final local = instant.toLocal();
      final day = DateTime(local.year, local.month, local.day);
      expect(localHomeDay(instant), day);
      expect(
          buildHomeRows([row('local', instant, 'transcribing')], [],
              enabled: false,
              groupAwaitingTranscript: true,
              processingTodayOnly: true,
              now: day.add(const Duration(hours: 12))),
          hasLength(1));
    }
    if (Platform.environment['TZ'] == 'Pacific/Kiritimati') {
      expect(localHomeDay(DateTime.utc(2026, 11, 10, 23, 30)), DateTime(2026, 11, 11));
    }
    if (Platform.environment['TZ'] == 'Pacific/Pago_Pago') {
      expect(localHomeDay(DateTime.utc(2026, 11, 10, 0, 30)), DateTime(2026, 11, 9));
    }
  });

  test('DST uses civil midnight on both short and long local days', () {
    if (Platform.environment['TZ'] != 'America/New_York') return;
    for (final boundary in [
      (DateTime(2026, 3, 8), DateTime(2026, 3, 9), 23),
      (DateTime(2026, 11, 1), DateTime(2026, 11, 2), 25)
    ]) {
      expect(boundary.$2.difference(boundary.$1).inHours, boundary.$3);
      final before = row('before', boundary.$2.subtract(const Duration(seconds: 1)), 'transcribing');
      expect(
          buildHomeRows([before], [],
              enabled: false, groupAwaitingTranscript: true, processingTodayOnly: true, now: boundary.$2),
          isEmpty);
      expect(pastProcessingConversations(pending: [], conversations: [before], now: boundary.$2).single.id, 'before');
    }
  });

  test('loaded Home rows supplement a full pending window in Activity', () {
    final at = midnight.subtract(const Duration(hours: 1));
    final items = [
      for (var i = 0; i < 100; i++)
        PendingWorkItem(
            id: 'conv:$i', kind: 'conversation', state: 'transcribing', conversationIds: ['$i'], startedAt: at)
    ];
    final outside = row('outside-window', at, 'writing_notes');
    expect(home([outside]), isEmpty);
    expect(pastProcessingConversations(pending: items, conversations: [outside], now: midnight).map((c) => c.id),
        contains('outside-window'));
  });
  test('failed pending links reach Activity without a loaded Home day and dedupe ledger', () {
    final at = midnight.subtract(const Duration(days: 20));
    final pending = [
      PendingWorkItem(
          id: 'conv:f',
          kind: 'conversation',
          state: 'summarizing',
          conversationIds: ['f'],
          startedAt: at,
          homeStep: 'failed')
    ];
    expect(failedActivityConversations(pending: pending, conversations: []).single.id, 'f');
    expect(failedActivityConversations(pending: pending, conversations: [], attentionIds: {'f'}), isEmpty);
    expect(failedActivityConversations(pending: pending, conversations: [row('f', at, 'ready')]), isEmpty);
    expect(pastProcessingConversations(pending: pending, conversations: [], now: midnight), isEmpty);
  });

  test('failed episode members are hidden even when all members failed', () {
    final member = ServerConversation(
        id: 'f', createdAt: midnight, episodeId: 'e', homeStep: 'failed', structured: Structured('Failed notes', ''));
    final episode = Episode(
        id: 'e', live: false, startedAt: midnight, lastActivityAt: midnight, members: [member], conversationIds: ['f']);
    expect(home([member], episodes: [episode]), isEmpty);
    expect(failedActivityConversations(pending: [], conversations: [], episodes: [episode]).single.id, 'f');
    expect(home([member], episodes: [episode], todayOnly: false).single.episode?.id, 'e');
  });

  test('failure exclusion also protects ungrouped Home and locked legacy status', () {
    final failed = ServerConversation(
        id: 'f',
        createdAt: midnight,
        status: ConversationStatus.failed,
        isLocked: true,
        structured: Structured('', ''));
    expect(buildHomeRows([failed], [], enabled: false, activityOnlyFailures: true), isEmpty);
    expect(buildHomeRows([failed], [], enabled: false), hasLength(1));
    expect(failedActivityConversations(pending: [], conversations: [failed]).single.id, 'f');
  });
}
