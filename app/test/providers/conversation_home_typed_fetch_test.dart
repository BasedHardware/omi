import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation row(int i) {
  final start = DateTime.utc(2026, 11, 1).add(Duration(minutes: i * 3));
  return ServerConversation(
      id: 'c$i',
      createdAt: start,
      startedAt: start,
      finishedAt: start.add(const Duration(minutes: 2)),
      structured: Structured('Fixture $i', 'Summary'));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  });
  test('lifecycle reads stay passive while detail opens carry explicit intent', () async {
    final headers = <Map<String, String>>[];
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          headers.add(request.headers);
          return http.Response(jsonEncode(row(0).toJson()), 200);
        });
    await api.byId('c0');
    expect(headers.single, isNot(contains('X-Omi-Recording-Detail')));
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    await provider.refreshTypedDetail('c0');
    expect(headers.last['X-Omi-Recording-Detail'], '1');
  });
  test('typed initial and older pages acknowledge held members and use the raw storage cursor', () async {
    final members = [for (var i = 0; i < 50; i++) row(i)];
    final offsets = <String?>[];
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          final offset = Uri.parse(request.url).queryParameters['offset'];
          offsets.add(offset);
          expect(request.headers['X-Omi-Home-Episode-Ids']!.split(','), hasLength(50));
          return http.Response('[]', 200, headers: {
            'x-omi-home-suppressed-ids': members.map((c) => c.id).join(','),
            'x-omi-conversation-page-size': offsets.length == 1 ? '50' : '1',
          });
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true)
      ..conversations = members
      ..heldHomeEpisodes = () => {'episode': members};
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations.map((c) => c.id).toSet(), members.map((c) => c.id).toSet());
    expect(await provider.getMoreConversationsFromServer(), isTrue);
    expect(offsets, ['0', '50'], reason: 'restored snapshots never advance the storage cursor');
    expect(provider.conversations, hasLength(50));
    expect(identical(provider.conversations.firstWhere((c) => c.id == 'c0'), members.first), isTrue);
  });
  test('typed metadata preserves truncation and restores only acknowledged omitted IDs', () async {
    final held = [row(0), row(1)];
    var count = -1;
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (_) async => http.Response(jsonEncode([row(2).toJson()]), 200, headers: {
              'x-omi-home-suppressed-ids': 'c0,unknown',
              'x-omi-conversation-page-size': '50',
              'x-omi-list-truncated': 'true',
            }));
    final result = await api.list(heldHomeEpisodes: {'episode': held}, onStorageCount: (value) => count = value);
    final success = result as ApiSuccess<List<ServerConversation>>;
    expect(success.data.map((c) => c.id), ['c2', 'c0']);
    expect(identical(success.data.last, held.first), isTrue);
    expect(success.truncated, isTrue);
    expect(count, 50);
  });
}
