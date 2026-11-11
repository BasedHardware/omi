import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:shared_preferences/shared_preferences.dart';

ServerConversation _conversation(int i) => ServerConversation(
      id: 'conv-$i',
      createdAt: DateTime.utc(2026, 9, 16, 9).subtract(Duration(minutes: i)),
      structured: Structured('Conversation $i — café ✓', 'Summary $i with ünïcödé.', emoji: '🧠', category: 'other'),
      transcriptSegments: [
        for (var j = 0; j < 20; j++)
          TranscriptSegment(
              id: 'seg-$i-$j',
              text: 'Transcript line $j of conversation $i — naïve façade.',
              speaker: 'SPEAKER_0${j % 2}',
              isUser: j.isEven,
              personId: null,
              start: j * 2.0,
              end: j * 2.0 + 1,
              translations: [])
      ],
    );

/// The conversation list is parsed on resume and re-cached on every refresh.
/// Both paths must give identical results on and off the UI isolate.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    offUiIsolateFallbacks = 0;
  });

  tearDown(() {
    expect(offUiIsolateFallbacks, 0, reason: 'the payload must cross isolates, or the work silently returns to the UI');
  });

  test('a large list body parses identically on a background isolate', () async {
    final body = utf8.encode(jsonEncode([for (var i = 0; i < 30; i++) _conversation(i).toJson()]));
    final inline = parseConversationListBody(jsonDecode(utf8.decode(body)) as List<dynamic>);

    final previous = conversationListBackgroundParseBytes;
    addTearDown(() => conversationListBackgroundParseBytes = previous);
    conversationListBackgroundParseBytes = 1;
    final viaIsolate = await offUiIsolate(
        () => parseConversationListBody(jsonDecode(utf8.decode(body)) as List<dynamic>),
        size: body.length,
        threshold: conversationListBackgroundParseBytes);

    expect(viaIsolate.map((c) => jsonEncode(c.toJson())), inline.map((c) => jsonEncode(c.toJson())));
    expect(inline.first.structured.title, 'Conversation 0 — café ✓');
  });

  test('background cache encoding round-trips and matches the setter', () async {
    final previous = SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold;
    addTearDown(() => SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = previous);
    final conversations = [for (var i = 0; i < 25; i++) _conversation(i)];

    SharedPreferencesUtil().cachedConversations = conversations;
    final viaSetter = SharedPreferencesUtil().getStringList('cachedConversations');

    SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = 1;
    await SharedPreferencesUtil().cacheConversations(conversations);

    expect(SharedPreferencesUtil().getStringList('cachedConversations'), viaSetter);
    expect(SharedPreferencesUtil().cachedConversations.map((c) => c.id), conversations.map((c) => c.id));
  });

  test('a slow background cache write never lands over a later clear', () async {
    final previous = SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold;
    addTearDown(() => SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = previous);
    SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = 1;

    final slow = SharedPreferencesUtil().cacheConversations([for (var i = 0; i < 25; i++) _conversation(i)]);
    // Sign-out clears the cache while the encode is still running.
    SharedPreferencesUtil().cachedConversations = <ServerConversation>[];
    await slow;

    expect(SharedPreferencesUtil().cachedConversations, isEmpty);
  });

  test('a background cache write in flight at sign-out never restores the old account cache', () async {
    final previous = SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold;
    addTearDown(() => SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = previous);
    SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = 1;

    final slow = SharedPreferencesUtil().cacheConversations([for (var i = 0; i < 25; i++) _conversation(i)]);
    await SharedPreferencesUtil().clear();
    await slow;

    expect(SharedPreferencesUtil().getStringList('cachedConversations'), isEmpty);
  });
}
