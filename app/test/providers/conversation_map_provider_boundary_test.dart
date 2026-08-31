import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('map boundary follows active text and speaker search groups', () {
    final feed = _conversation('feed');
    final searchMatch = _conversation('search-match');
    final provider = _provider()..conversations = [feed];
    addTearDown(provider.dispose);

    provider
      ..previousQuery = 'alice'
      ..selectedSpeakerId = 'speaker-1'
      ..searchedConversations = [searchMatch]
      ..groupConversationsByDate();

    expect(provider.displayedConversations.map((conversation) => conversation.id), ['search-match']);
  });

  test('map boundary follows client-side short, starred, date, and folder filters', () {
    final visible = _conversation(
      'visible',
      durationSeconds: 120,
      starred: true,
      folderId: 'folder-1',
      startedAt: DateTime(2026, 8, 1, 12),
    );
    final short = _conversation(
      'short',
      durationSeconds: 10,
      starred: true,
      folderId: 'folder-1',
      startedAt: DateTime(2026, 8, 1, 13),
    );
    final unstarred = _conversation(
      'unstarred',
      durationSeconds: 120,
      folderId: 'folder-1',
      startedAt: DateTime(2026, 8, 1, 14),
    );
    final wrongFolder = _conversation(
      'wrong-folder',
      durationSeconds: 120,
      starred: true,
      folderId: 'folder-2',
      startedAt: DateTime(2026, 8, 1, 15),
    );
    final wrongDate = _conversation(
      'wrong-date',
      durationSeconds: 120,
      starred: true,
      folderId: 'folder-1',
      startedAt: DateTime(2026, 8, 2, 12),
    );
    final provider = _provider()
      ..showShortConversations = false
      ..shortConversationThreshold = 60
      ..showStarredOnly = true
      ..selectedFolderId = 'folder-1'
      ..selectedStartDate = DateTime(2026, 8, 1)
      ..selectedEndDate = DateTime(2026, 8, 1)
      ..conversations = [visible, short, unstarred, wrongFolder, wrongDate];
    addTearDown(provider.dispose);

    provider.groupConversationsByDate();

    expect(provider.displayedConversations.map((conversation) => conversation.id), ['visible']);
  });
}

ConversationProvider _provider() => ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );

ServerConversation _conversation(
  String id, {
  int durationSeconds = 120,
  bool starred = false,
  String? folderId,
  DateTime? startedAt,
}) {
  final start = startedAt ?? DateTime.utc(2026, 8, 1, 12);
  return ServerConversation(
    id: id,
    createdAt: start,
    startedAt: start,
    finishedAt: start.add(Duration(seconds: durationSeconds)),
    structured: Structured('Title', 'Overview'),
    starred: starred,
    folderId: folderId,
  );
}
