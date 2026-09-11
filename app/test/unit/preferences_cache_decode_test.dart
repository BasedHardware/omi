import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';

const _unreadable = ['not-json', '[]', '{"id": 42}'];

Person _person(String id) => Person(id: id, name: 'Alex', createdAt: DateTime.utc(2026), updatedAt: DateTime.utc(2026));

Memory _memory(String id) => Memory(
      id: id,
      uid: 'user-1',
      content: 'unsynced',
      category: MemoryCategory.manual,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      visibility: MemoryVisibility.private,
    );

ServerConversation _conversation(String id) =>
    ServerConversation(id: id, createdAt: DateTime.utc(2026), structured: Structured('Title', 'Overview'));

ServerMessage _message(String id) => ServerMessage(
      id,
      DateTime.utc(2026),
      'hello',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      const [],
      const [],
      const [],
    );

App _app(String id) => App.fromJson({
      'id': id,
      'uid': 'user-1',
      'name': 'Test App',
      'author': 'Author',
      'description': 'Desc',
      'image': 'https://example.com/icon.png',
      'capabilities': ['chat'],
      'status': 'approved',
      'approved': true,
      'rating_count': 0,
      'enabled': true,
      'deleted': false,
      'is_paid': false,
      'category': 'productivity-and-organization',
    });

Future<SharedPreferencesUtil> _prefs([Map<String, Object> values = const {}]) async {
  SharedPreferences.setMockInitialValues(values);
  await SharedPreferencesUtil.init();
  return SharedPreferencesUtil();
}

Future<void> _appendUnreadable(SharedPreferencesUtil prefs, String key) =>
    prefs.saveStringList(key, [...prefs.getStringList(key), ..._unreadable]);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('cached list getters skip unreadable entries', () {
    test('cachedPeople', () async {
      final prefs = await _prefs();
      prefs.cachedPeople = [_person('p1')];
      await _appendUnreadable(prefs, 'cachedPeople');
      expect(prefs.cachedPeople.map((p) => p.id), ['p1']);
      expect(prefs.getPersonById('p1')?.name, 'Alex');
    });

    test('cachedConversations', () async {
      final prefs = await _prefs();
      prefs.cachedConversations = [_conversation('c1')];
      await _appendUnreadable(prefs, 'cachedConversations');
      expect(prefs.cachedConversations.map((c) => c.id), ['c1']);
    });

    test('cachedMessages', () async {
      final prefs = await _prefs();
      prefs.cachedMessages = [_message('m1')];
      await _appendUnreadable(prefs, 'cachedMessages');
      expect(prefs.cachedMessages.map((m) => m.id), ['m1']);
    });

    test('appsList', () async {
      final prefs = await _prefs();
      prefs.appsList = [_app('app-1')];
      await _appendUnreadable(prefs, 'appsList');
      expect(prefs.appsList.map((a) => a.id), ['app-1']);
    });

    test('pendingMemories', () async {
      final prefs = await _prefs({'uid': 'user-1'});
      prefs.pendingMemories = [_memory('pending-1')];
      await _appendUnreadable(prefs, 'pendingMemories:user-1');
      expect(prefs.pendingMemories.map((m) => m.id), ['pending-1']);
    });
  });

  test('addCachedPerson still works after a bad entry and rewrites the cache clean', () async {
    final prefs = await _prefs({'cachedPeople': _unreadable});
    prefs.addCachedPerson(_person('p1'));
    expect(prefs.cachedPeople.map((p) => p.id), ['p1']);
    expect(prefs.getStringList('cachedPeople'), hasLength(1));
  });

  test('removePendingMemory removes the target when an unreadable entry is present', () async {
    final prefs = await _prefs({'uid': 'user-1'});
    prefs.pendingMemories = [_memory('pending-1'), _memory('pending-2')];
    await _appendUnreadable(prefs, 'pendingMemories:user-1');
    prefs.removePendingMemory('pending-1');
    expect(prefs.pendingMemories.map((m) => m.id), ['pending-2']);
  });

  group('modifiedConversationDetails', () {
    test('returns null for an unreadable value', () async {
      for (final value in _unreadable) {
        final prefs = await _prefs({'modifiedConversationDetails': value});
        expect(prefs.modifiedConversationDetails, isNull, reason: value);
      }
    });

    test('still returns a readable value', () async {
      final prefs = await _prefs({'modifiedConversationDetails': jsonEncode(_conversation('c1').toJson())});
      expect(prefs.modifiedConversationDetails?.id, 'c1');
    });
  });
}
