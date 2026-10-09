// Conversation detail before the UI program: summary and transcript tabs, the top bar and its
// pull-down overflow menu, and the same speaker seeds the current people-chip scenarios use.
// Grouped captures (and their recordings sheet) did not exist yet.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../fakes.dart';
import '../../../harness.dart';

const _page = 'lib/pages/conversation_detail/page.dart (ConversationDetailPage)';
const _summaryTab = 1;
const _transcriptTab = 0;

/// The top bar's ellipsis button, which opens a PullDownButton menu.
final _more = find.bySemanticsLabel('More options');

List<SingleChildWidget> _detailProviders(ServerConversation conversation, {ConversationProvider? provider}) => [
      ChangeNotifierProvider<ConversationProvider>.value(
          value: provider ?? (ConversationProvider(isSignedIn: () => true)..conversations = [conversation])),
      ChangeNotifierProvider(
          create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(conversation.createdAt)),
    ];

Future<void> _pumpDetail(AuditRun a, ServerConversation conversation, {int tab = _summaryTab}) =>
    a.pump(ConversationDetailPage(conversation: conversation, initialTabIndex: tab),
        providers: _detailProviders(conversation));

TranscriptSegment _segment(String id, String text, String speaker, {bool isUser = false, String? personId}) {
  final start = double.parse(id) * 3;
  return TranscriptSegment(
      id: id,
      text: text,
      speaker: speaker,
      isUser: isUser,
      personId: personId,
      start: start,
      end: start + 3,
      translations: []);
}

/// There was no people chip yet: the summary header in the frame that pairs with today's chip,
/// then the transcript, where this revision showed who spoke.
Future<void> _headerThenSpeakers(AuditRun a) async {
  await a.shot('The summary header, where the people chip is today');
  await a.tap(find.bySemanticsLabel('Transcript').first);
  await a.shot('Open the Transcript tab: the speaker labels', step: 'transcript');
}

final _david = Person(id: 'person-1', name: 'David', createdAt: DateTime(2026, 1, 1), updatedAt: DateTime(2026, 1, 1));
final _cachedDavid = {
  'cachedPeople': [jsonEncode(_david.toJson())]
};

final conversationDetailScenarios = <AuditScenario>[
  AuditScenario(
    id: 'conversation-detail-summary',
    title: 'Conversation summary, top bar and overflow menu',
    page: _page,
    state: 'One ungrouped conversation served by the fixture backend and loaded into ConversationProvider',
    run: (a) async {
      final conversation = ServerConversation(
          id: 'audit-conversation',
          createdAt: DateTime(2026, 9, 20, 10),
          structured: Structured(
              'Design catch-up with Alex',
              'We agreed to simplify the first recording experience, make saved memories easier to find, and send '
                  'the revised design notes on Friday.',
              emoji: '💬',
              category: 'work'));
      a.server.conversations.add(conversation.toJson());
      final provider = ConversationProvider(isSignedIn: () => true);
      await a.tester.runAsync(provider.forceRefreshConversations);
      await a.pump(ConversationDetailPage(conversation: conversation),
          providers: _detailProviders(conversation, provider: provider));
      await a.shot('Open an ungrouped conversation: Ask Omi, Star, Share and the overflow button', step: 'summary');
      await a.tap(_more);
      await a.shot('Open the overflow menu', step: 'overflow');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-transcript',
    title: 'Conversation transcript with two unnamed speakers',
    page: _page,
    state: 'One ungrouped conversation with two transcript segments from two unnamed speakers',
    run: (a) async {
      final conversation = auditConversation('audit-transcript', title: 'Design catch-up with Alex', segments: [
        _segment('0', 'Let’s simplify the first recording experience.', 'SPEAKER_0'),
        _segment('1', 'Agreed — and make saved memories easier to find.', 'SPEAKER_1'),
      ]);
      await _pumpDetail(a, conversation, tab: _transcriptTab);
      await a.shot('Open the Transcript tab');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-named',
    title: 'Speakers: every speaker named (no people chip yet)',
    page: _page,
    state: 'Segments from the owner and from one cached, named person (David)',
    prefs: _cachedDavid,
    run: (a) async {
      final conversation = auditConversation('people-a', title: 'Design catch-up', segments: [
        _segment('0', "Let's ship Friday.", 'SPEAKER_0', isUser: true),
        _segment('1', 'Sounds good to me.', 'SPEAKER_1', personId: 'person-1'),
      ]);
      await _pumpDetail(a, conversation);
      await _headerThenSpeakers(a);
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-mixed',
    title: 'Speakers: one named speaker and three unnamed (no people chip yet)',
    page: _page,
    state: 'Segments from one cached, named person (David) and three unnamed speakers',
    prefs: _cachedDavid,
    run: (a) async {
      final conversation = auditConversation('people-b', title: 'Team standup', segments: [
        _segment('0', 'Kicking off.', 'SPEAKER_0', personId: 'person-1'),
        _segment('1', 'On it.', 'SPEAKER_1'),
        _segment('2', 'Same here.', 'SPEAKER_2'),
        _segment('3', 'Agreed.', 'SPEAKER_3'),
      ]);
      await _pumpDetail(a, conversation);
      await _headerThenSpeakers(a);
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-none',
    title: 'Speakers: nobody named (no people chip yet)',
    page: _page,
    state: 'Segments from two unnamed speakers, none of them the owner',
    run: (a) async {
      final conversation = auditConversation('people-c', title: 'Anonymous huddle', segments: [
        _segment('0', 'Hello.', 'SPEAKER_0'),
        _segment('1', 'Hi there.', 'SPEAKER_1'),
      ]);
      await _pumpDetail(a, conversation);
      await _headerThenSpeakers(a);
    },
  ),
];
