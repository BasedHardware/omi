import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('conversation getter resolves when startedAt and createdAt fall on different days', () {
    // Regression for "Bad state: No conversation available": conversations are
    // grouped by the *local* day of their effective date (startedAt ??
    // createdAt), and tapping a list item selects that group's date. When
    // startedAt lands on an earlier calendar day than createdAt (session
    // spanning midnight / timezone edge), the detail provider must still
    // resolve the conversation instead of throwing from the non-null
    // `conversation` getter.
    //
    // The instant is derived from the host's UTC offset rather than pinned, so
    // the case actually under test — an effective date whose local calendar day
    // differs from its UTC one — is constructed on hosts either side of UTC.
    // The previously pinned 23:30 UTC only diverged ahead of UTC, so the
    // getter comparing raw (UTC) date components against the local day key
    // stayed green everywhere behind it. On a host at UTC the two days can
    // never diverge and this asserts plain resolution.
    final startedAt = _instantSplittingUtcAndLocalDay();
    final convo = ServerConversation(
      id: 'c1',
      startedAt: startedAt,
      createdAt: startedAt.add(const Duration(minutes: 45)),
      structured: Structured('Title', 'Overview'),
      status: ConversationStatus.completed,
    );

    final conversationProvider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversationProvider.dispose);
    conversationProvider.conversations = [convo];
    conversationProvider.groupConversationsByDate();

    // The date key the list item passes on tap is the group key.
    final groupDate = conversationProvider.groupedConversations.keys.single;

    final detailProvider = ConversationDetailProvider();
    addTearDown(detailProvider.dispose);
    detailProvider.conversationProvider = conversationProvider;

    detailProvider.updateConversation(convo.id, groupDate);

    expect(detailProvider.conversationOrNull, isNotNull);
    expect(detailProvider.conversation.id, 'c1');
    expect(detailProvider.conversation.structured.title, 'Title');
  });

  test('selected conversation is never replaced by another one in the day group', () {
    // The detail page drives delete, visibility and rename off this getter, so
    // resolving to a different conversation destroys or publicly shares the
    // wrong one. When the selected conversation leaves the group (deleted on
    // another device, merged away, or filtered out by the discarded/short
    // toggles) the getter must report a miss rather than substitute a sibling.
    final selected = _conversationAt('selected', DateTime(2026, 7, 18, 9));
    final sibling = _conversationAt('sibling', DateTime(2026, 7, 18, 11));

    final conversationProvider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversationProvider.dispose);
    conversationProvider.conversations = [selected, sibling];
    conversationProvider.groupConversationsByDate();

    final groupDate = conversationProvider.groupedConversations.keys.single;

    final detailProvider = ConversationDetailProvider();
    addTearDown(detailProvider.dispose);
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.updateConversation(selected.id, groupDate);

    expect(detailProvider.conversation.id, 'selected');

    conversationProvider.conversations = [sibling];
    conversationProvider.groupConversationsByDate();

    // Previously this resolved to the surviving sibling and rebound the tracked
    // id to it, so a delete or visibility change hit the wrong conversation.
    expect(detailProvider.conversationOrNull?.id, 'selected');
    expect(detailProvider.conversationOrNull?.id, 'selected');
  });

  test('selected conversation survives a transient empty day group', () {
    // A refresh can momentarily empty the group; the page must keep showing the
    // conversation it was opened with instead of blanking or retargeting.
    final selected = _conversationAt('selected', DateTime(2026, 7, 18, 9));

    final conversationProvider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversationProvider.dispose);
    conversationProvider.conversations = [selected];
    conversationProvider.groupConversationsByDate();

    final groupDate = conversationProvider.groupedConversations.keys.single;

    final detailProvider = ConversationDetailProvider();
    addTearDown(detailProvider.dispose);
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.updateConversation(selected.id, groupDate);

    conversationProvider.conversations = [];
    conversationProvider.groupConversationsByDate();

    expect(detailProvider.conversationOrNull?.id, 'selected');
  });
}

/// A UTC instant whose *local* calendar day differs from its UTC one, as
/// server timestamps do for real users on both sides of UTC: late in the UTC
/// day lands on the next local day ahead of UTC, the start of it on the
/// previous local day behind. The offset is read at that instant, not now, so
/// a DST boundary between the two cannot flip which side it falls on.
DateTime _instantSplittingUtcAndLocalDay() {
  final offset = DateTime.utc(2026, 7, 18, 12).toLocal().timeZoneOffset;
  return offset.isNegative ? DateTime.utc(2026, 7, 18, 0, 0) : DateTime.utc(2026, 7, 18, 23, 59);
}

/// Both these fixtures must land in one day group, so they are anchored in
/// local time: a UTC-pinned pair a couple of hours apart straddles local
/// midnight at far-enough offsets and splits into two groups.
ServerConversation _conversationAt(String id, DateTime startedAt) {
  return ServerConversation(
    id: id,
    startedAt: startedAt,
    createdAt: startedAt,
    structured: Structured(id, 'Overview'),
    status: ConversationStatus.completed,
  );
}
