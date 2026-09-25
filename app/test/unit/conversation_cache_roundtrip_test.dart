import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

ServerConversation _conversation({List<AppResponse> appResults = const [], ConversationSource? source}) {
  return ServerConversation(
    id: 'test-id',
    createdAt: DateTime.utc(2026, 7, 1, 12, 0, 0),
    structured: Structured('Test', 'Test'),
    appResults: appResults,
    source: source,
  );
}

void main() {
  group('ServerConversation cache round trip', () {
    test('serializes conversation source using its wire value', () {
      final conv = _conversation(source: ConversationSource.sdcard);
      final json = conv.toJson();

      expect(json['source'], 'sdcard');
      expect(ServerConversation.fromJson(json).source, ConversationSource.sdcard);
    });

    test('toJson output with app results parses back without throwing and preserves them', () {
      final conv = _conversation(appResults: [AppResponse('summary text', appId: 'app-1')]);
      final restored = ServerConversation.fromJson(jsonDecode(jsonEncode(conv.toJson())));
      expect(restored.appResults, hasLength(1));
      expect(restored.appResults.first.appId, 'app-1');
      expect(restored.appResults.first.content, 'summary text');
    });

    test('legacy cache entry with appId-keyed plugins_results does not crash', () {
      // Written by ServerConversation.toJson before the wire-format fix:
      // plugins_results entries had 'appId' instead of the required 'plugin_id' key.
      // Legacy plugins_results recovery is intentionally dropped with the field's
      // removal: caches written since the wire-format fix carry apps_results, which
      // remains the only read path. Ancient cache entries re-hydrate from the server.
      final legacyJson = {
        'id': 'legacy-id',
        'created_at': '2026-07-01T12:00:00.000Z',
        'structured': {'title': 'Legacy', 'overview': ''},
        'started_at': null,
        'finished_at': null,
        'plugins_results': [
          {'appId': 'app-1', 'content': 'legacy summary'},
        ],
      };
      final restored = ServerConversation.fromJson(legacyJson);
      expect(restored.id, 'legacy-id');
      expect(restored.appResults, isEmpty);
    });

    test('plugin result with null plugin_id round trips', () {
      final conv = _conversation(appResults: [AppResponse('no app id', appId: null)]);
      final restored = ServerConversation.fromJson(jsonDecode(jsonEncode(conv.toJson())));
      expect(restored.appResults, hasLength(1));
      expect(restored.appResults.first.appId, isNull);
    });
  });
}
