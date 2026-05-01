import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/chat_service.dart';

class _FakePathProvider extends PathProviderPlatform {
  _FakePathProvider(this.tempDir);
  final String tempDir;
  @override
  Future<String?> getApplicationDocumentsPath() async => tempDir;
  @override
  Future<String?> getApplicationSupportPath() async => tempDir;
  @override
  Future<String?> getTemporaryPath() async => tempDir;
}

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

http.StreamedResponse _streamed(List<String> lines) {
  final body = lines.map((l) => '$l\n').join();
  return http.StreamedResponse(
    Stream.fromIterable([utf8.encode(body)]),
    200,
  );
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('chat_provider_test');
    PathProviderPlatform.instance = _FakePathProvider(tempDir.path);
    Hive.init(tempDir.path);
  });

  setUp(() async {
    if (!Hive.isBoxOpen(ChatBoxes.messages)) {
      await Hive.openBox<Map>(ChatBoxes.messages);
    }
    await Hive.box<Map>(ChatBoxes.messages).clear();
  });

  tearDownAll(() async {
    await Hive.deleteFromDisk();
    await tempDir.delete(recursive: true);
  });

  test('send pushes user message then streamed assistant message', () async {
    final mock = MockClient.streaming((req, body) async {
      return _streamed([
        'data: Hello, ',
        'data: Matheus.',
        'done: ${base64.encode(utf8.encode("{}"))}',
      ]);
    });
    final provider = ChatProvider(service: ChatService(client: _client(mock)));

    await provider.send('hi');

    expect(provider.messages, hasLength(2));
    expect(provider.messages[0].role, ChatRole.user);
    expect(provider.messages[0].text, 'hi');
    expect(provider.messages[1].role, ChatRole.assistant);
    expect(provider.messages[1].text, 'Hello, Matheus.');
    expect(provider.messages[1].streaming, isFalse);
    expect(provider.sending, isFalse);
  });

  test('think: lines accumulate as deduped tool events', () async {
    final mock = MockClient.streaming((req, body) async {
      return _streamed([
        'think: Searching memory',
        'think: Searching memory', // duplicate, must not double
        'data: Here is what I found.',
        'think: Reading calendar|app_id:nooto-cal',
        'data: ' ' Today is busy.',
        'done: ${base64.encode(utf8.encode("{}"))}',
      ]);
    });
    final provider = ChatProvider(service: ChatService(client: _client(mock)));

    await provider.send('what do you know');

    final assistant = provider.messages[1];
    expect(assistant.toolEvents, ['Searching memory', 'Reading calendar']);
    expect(assistant.text, contains('Here is what I found'));
    expect(assistant.text, contains('Today is busy'));
    expect(assistant.streaming, isFalse);
  });

  test('error replaces streaming message with friendly fallback', () async {
    final mock = MockClient.streaming((req, body) async {
      return http.StreamedResponse(const Stream<List<int>>.empty(), 500);
    });
    final provider = ChatProvider(service: ChatService(client: _client(mock)));

    await provider.send('oops');

    expect(provider.messages, hasLength(2));
    expect(provider.messages[1].role, ChatRole.assistant);
    expect(provider.messages[1].text, contains("couldn't reach the server"));
    expect(provider.messages[1].streaming, isFalse);
    expect(provider.error, isNotNull);
  });

  test('empty trimmed text does not send', () async {
    var requestCount = 0;
    final mock = MockClient.streaming((req, body) async {
      requestCount += 1;
      return _streamed(['data: x', 'done: ${base64.encode(utf8.encode("{}"))}']);
    });
    final provider = ChatProvider(service: ChatService(client: _client(mock)));

    await provider.send('   ');
    await provider.send('');

    expect(requestCount, 0);
    expect(provider.messages, isEmpty);
  });

  test('persists messages and rehydrates on next provider', () async {
    final mock = MockClient.streaming((req, body) async {
      return _streamed([
        'data: Roundtrip works.',
        'done: ${base64.encode(utf8.encode("{}"))}',
      ]);
    });

    final p1 = ChatProvider(service: ChatService(client: _client(mock)));
    await p1.send('persist?');

    // New provider instance reads the same Hive box.
    final p2 = ChatProvider(service: ChatService(client: _client(mock)));

    expect(p2.messages, hasLength(2));
    expect(p2.messages[0].text, 'persist?');
    expect(p2.messages[1].text, 'Roundtrip works.');
  });

  test('drops streaming-flagged messages on rehydrate (interrupted stream)',
      () async {
    final box = Hive.box<Map>(ChatBoxes.messages);
    await box.put('user-1', ChatMessage(
      id: 'user-1',
      role: ChatRole.user,
      text: 'still here',
      createdAt: DateTime.parse('2026-04-30T10:00:00Z'),
    ).toJson());
    await box.put('assistant-1', ChatMessage(
      id: 'assistant-1',
      role: ChatRole.assistant,
      text: 'partial reply...',
      createdAt: DateTime.parse('2026-04-30T10:00:01Z'),
      streaming: true,
    ).toJson());

    final mock = MockClient.streaming((req, body) async => _streamed([]));
    final provider = ChatProvider(service: ChatService(client: _client(mock)));

    expect(provider.messages, hasLength(1));
    expect(provider.messages[0].id, 'user-1');
    // Stale streaming row should also be wiped from disk.
    expect(box.get('assistant-1'), isNull);
  });

  test('trims to retention limit', () async {
    final box = Hive.box<Map>(ChatBoxes.messages);
    // Pre-seed 199 messages (one below cap).
    for (var i = 0; i < 199; i++) {
      await box.put('seed-$i', ChatMessage(
        id: 'seed-$i',
        role: i.isEven ? ChatRole.user : ChatRole.assistant,
        text: 'msg $i',
        createdAt: DateTime.fromMillisecondsSinceEpoch(i * 1000),
      ).toJson());
    }

    final mock = MockClient.streaming((req, body) async {
      return _streamed([
        'data: pong',
        'done: ${base64.encode(utf8.encode("{}"))}',
      ]);
    });
    final provider = ChatProvider(service: ChatService(client: _client(mock)));
    expect(provider.messages, hasLength(199));

    await provider.send('one more');

    // 199 + 1 user + 1 assistant = 201 → trims to 200.
    expect(provider.messages.length, ChatBoxes.retentionLimit);
    expect(box.length, ChatBoxes.retentionLimit);
  });
}
