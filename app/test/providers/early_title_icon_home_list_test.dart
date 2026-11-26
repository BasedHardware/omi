// Reliability experiment `early_title_icon`: Home's list takes an ended conversation as soon as the
// server has fixed its title and emoji, while its status is still `processing`. Off, the list takes only
// completed rows, so Home keeps its "Processing…" row until the summary is stored.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/conversations/early_title.dart';
import 'package:omi/utils/reliability_experiments.dart';

final start = DateTime.utc(2026, 11, 18, 12);

ServerConversation row(
  String id, {
  required ConversationTileState tile,
  bool titleLocked = true,
  String title = 'Venue and speaker plan',
  String emoji = '🚀',
  bool recording = false,
}) =>
    ServerConversation(
      id: id,
      status: tile == ConversationTileState.done ? ConversationStatus.completed : ConversationStatus.processing,
      createdAt: start,
      startedAt: start,
      finishedAt: start.add(const Duration(minutes: 9)),
      structured: Structured(title, tile == ConversationTileState.done ? 'The summary.' : '', emoji: emoji),
      v3: ConversationV3Fields(kind: 'conversation', tileState: tile, titleLocked: titleLocked, recording: recording),
    );

http.Response json(Object body, [Map<String, String> headers = const {}]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), 200,
        headers: {'content-type': 'application/json; charset=utf-8', ...headers});

http.Response page(Iterable<ServerConversation> rows) => json(
    [for (final c in rows) c.toJson()], {'x-omi-conversation-page-size': '${rows.length}', 'x-omi-has-more': 'false'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-early-title'});
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  });
  tearDown(() => ReliabilityExperiments.overrideForTesting(null));

  ConversationProvider providerFor(List<ServerConversation> Function() listed) {
    ServerConversation? byId(Uri uri) => listed().where((c) => uri.path.endsWith('/${c.id}')).firstOrNull;
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          final uri = Uri.parse(request.url);
          final one = byId(uri);
          return one != null ? json(one.toJson()) : page(listed());
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    return provider;
  }

  test('the rule: ended, title fixed, summary not stored yet, experiment on', () {
    final writing = row('c', tile: ConversationTileState.writing);
    expect(titledBeforeSummary(writing), isFalse, reason: 'off');
    ReliabilityExperiments.overrideForTesting({earlyTitleIconExperiment});
    expect(titledBeforeSummary(writing), isTrue);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.transcribing)), isTrue);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.writing, titleLocked: false)), isFalse,
        reason: 'the title made from the first words can still change');
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.writing, title: ' ')), isFalse);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.writing, emoji: '')), isFalse);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.live)), isFalse);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.done)), isFalse);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.failed)), isFalse);
    expect(titledBeforeSummary(row('c', tile: ConversationTileState.writing, recording: true)), isFalse);
  });

  for (final on in [false, true]) {
    test(
        'experiment ${on ? 'on: the titled row is listed before its summary' : 'off: only the completed row is listed'}',
        () async {
      if (on) ReliabilityExperiments.overrideForTesting({earlyTitleIconExperiment});
      var listed = [row('ended', tile: ConversationTileState.writing)];
      final provider = providerFor(() => listed);

      // The full Home read and the bounded re-read of recent rows both see it.
      expect(await provider.fetchConversations(), isTrue);
      expect(provider.conversations.map((c) => c.id), on ? ['ended'] : isEmpty);
      await provider.refreshRecentConversations(start.subtract(const Duration(hours: 1)));
      expect(provider.conversations.map((c) => c.id), on ? ['ended'] : isEmpty);
      if (on) {
        final shown = provider.conversations.single;
        expect(shown.structured.title, 'Venue and speaker plan');
        expect(shown.v3?.tileState, ConversationTileState.writing);
        expect(provider.processingConversations.where((c) => c.id == 'ended'), isEmpty,
            reason: 'one row, not also a processing row');
        expect(provider.groupedConversations.values.expand((rows) => rows).map((c) => c.id), ['ended']);
      }

      // The summary is stored: the same row, now done, either way.
      listed = [row('ended', tile: ConversationTileState.done)];
      await provider.refreshRecentConversations(start.subtract(const Duration(hours: 1)));
      expect(provider.conversations.map((c) => c.id), ['ended']);
      expect(provider.conversations.single.v3?.tileState, ConversationTileState.done);
      expect(provider.conversations.single.structured.overview, 'The summary.');
    });
  }

  test('on: a row whose title is not fixed yet stays off the list', () async {
    ReliabilityExperiments.overrideForTesting({earlyTitleIconExperiment});
    final provider = providerFor(() => [
          row('waiting', tile: ConversationTileState.transcribing, titleLocked: false, title: 'Okay so', emoji: '💬'),
        ]);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations, isEmpty);
  });
}
