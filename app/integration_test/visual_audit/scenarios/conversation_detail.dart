// Conversation detail: summary and transcript tabs, the top bar and its overflow menu, the
// recordings sheet of a grouped capture, and the people chip.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/capture_group.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;

import '../fakes.dart';
import '../harness.dart';
import '../screen_frame_fixtures.dart';

const _page = 'lib/pages/conversation_detail/page.dart (ConversationDetailPage)';
const _summaryTab = ConversationTab.summary;
const _transcriptTab = ConversationTab.transcript;

List<SingleChildWidget> _detailProviders(ServerConversation conversation, {ConversationProvider? provider}) => [
      ChangeNotifierProvider<ConversationProvider>.value(
        value: provider ?? (ConversationProvider(isSignedIn: () => true)..conversations = [conversation]),
      ),
      ChangeNotifierProvider(
        create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(conversation.createdAt),
      ),
    ];

Future<void> _pumpDetail(AuditRun a, ServerConversation conversation, {ConversationTab tab = _summaryTab}) => a.pump(
      ConversationDetailPage(conversation: conversation, initialTab: tab),
      providers: _detailProviders(conversation),
    );

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
    translations: [],
  );
}

final _david = Person(id: 'person-1', name: 'David', createdAt: DateTime(2026, 1, 1), updatedAt: DateTime(2026, 1, 1));
final _cachedDavid = {
  'cachedPeople': [jsonEncode(_david.toJson())],
};

/// The Omi v8 mock's conversation (#20037): today 12:40 PM, 14 minutes, filed under Work, a
/// summary of headed bullets, two voices and a recording (the One bar's waveform player). The lines
/// run on until the next one starts, except a quiet stretch from 6 to 11 minutes.
Future<void> _pumpDesignConversation(AuditRun a) async {
  final now = DateTime.now();
  final startedAt = DateTime(now.year, now.month, now.day, 12, 40);
  TranscriptSegment line(String id, int minute, double until, String text, {bool mine = false}) => TranscriptSegment(
        id: id,
        text: text,
        speaker: mine ? 'SPEAKER_0' : 'SPEAKER_1',
        isUser: mine,
        personId: null,
        start: minute * 60.0,
        end: until * 60,
        translations: [],
      );
  final conversation = ServerConversation(
    id: 'audit-design',
    createdAt: startedAt,
    startedAt: startedAt,
    finishedAt: startedAt.add(const Duration(minutes: 14)),
    folderId: 'folder-work',
    status: ConversationStatus.completed,
    structured: Structured(
      'Ship the widgets without waiting for chat',
      '## Widgets\n'
          '- Ship them on their own, not bundled with the homepage chat.\n'
          '- Priya would rather see them land now and fix the chat separately.\n\n'
          '## How Priya wants updates\n'
          '- In writing. She said it twice: message, don’t call.',
      emoji: '\u{1F4AC}',
      category: 'work',
    ),
    transcriptSegments: [
      line('0', 0, 1, 'So, the widgets. Do we wait for the chat?'),
      line('1', 1, 3, 'I’d rather not. They’re done.', mine: true),
      line('2', 3, 4, 'Let’s just push the widgets separately.'),
      line('3', 4, 6, 'Fine. I’ll open the PR on its own.', mine: true),
      line('4', 11, 12, 'Honestly, just message me, no need to call.'),
      line('5', 12, 13, 'Will do. Sam’s still waiting on me too.', mine: true),
      line('6', 13, 13.5, 'Ha. Call him.'),
      TranscriptSegment(
        id: '7',
        text: 'Tomorrow morning, first thing.',
        speaker: 'SPEAKER_0',
        isUser: true,
        personId: null,
        start: 13 * 60.0 + 30,
        end: 14 * 60.0,
        translations: [],
      ),
    ],
    speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1]),
    audioFiles: [
      AudioFile(id: 'audio-design', uid: 'audit', conversationId: 'audit-design', chunkTimestamps: [], duration: 840),
    ],
  );
  final folders = FolderProvider(
    foldersFetcher: () async => [
      Folder(
        id: 'folder-work',
        name: 'Work',
        color: '#6B7280',
        icon: '📁',
        createdAt: startedAt,
        updatedAt: startedAt,
        order: 0,
        isDefault: false,
        isSystem: false,
        conversationCount: 1,
      ),
    ],
  );
  await a.tester.runAsync(folders.loadFolders);
  await a.pump(
    ConversationDetailPage(conversation: conversation),
    providers: [
      ..._detailProviders(conversation),
      ChangeNotifierProvider<FolderProvider>.value(value: folders),
    ],
  );
}

final conversationDetailScenarios = <AuditScenario>[
  AuditScenario(
    id: 'conversation-detail-design',
    title: 'The Omi v8 conversation: title, chips, Summary | Transcript, one bottom bar',
    page: _page,
    state: 'The mock’s conversation (today 12:40 PM, 14 min, Work folder, two headed summary sections, eight lines, '
        'a 14 min recording)',
    run: (a) async {
      await _pumpDesignConversation(a);
      await a.shot('Open the conversation: it opens on Summary, with the Ask Omi bar', step: 'summary');
      await a.tap(find.byKey(const Key('conversation_tab_transcript')));
      await a.shot('Tap Transcript: the waveform player and the round Ask button', step: 'transcript');
      await a.tap(find.byKey(const Key('conversation_more')));
      await a.shot('Open the ⋯ menu: Summary Template first', step: 'overflow');
    },
  ),
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
          category: 'work',
        ),
      );
      a.server.conversations.add(conversation.toJson());
      final provider = ConversationProvider(isSignedIn: () => true);
      await a.tester.runAsync(provider.forceRefreshConversations);
      await a.pump(
        ConversationDetailPage(conversation: conversation),
        providers: _detailProviders(conversation, provider: provider),
      );
      await a.shot('Open an ungrouped conversation: Ask Omi, Star, Share and the overflow button', step: 'summary');
      await a.tap(find.byKey(const Key('conversation_more')));
      await a.shot('Open the overflow menu', step: 'overflow');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-screenshots',
    title: 'Meeting screenshots: strip, viewer and delete',
    page:
        'lib/pages/conversation_detail/widgets/conversation_screenshots_section.dart (ConversationScreenshotsSection)',
    state: 'A completed meeting whose fixture screenshot set has a banner (video call) and three strip frames',
    run: (a) async {
      final images = await a.tester.runAsync(renderScreenFrameFixtures);
      a.server.images.addAll(images!);
      final base = a.server.baseUrl;
      final conversation = ServerConversation(
        id: 'audit-meeting',
        createdAt: DateTime(2026, 9, 30, 10),
        structured: Structured(
          'Weekly product sync',
          'Maya walked through the Q4 onboarding roadmap. The team agreed to simplify the first recording, '
              'make saved memories easier to find, and roll the launch out at 10% before widening it.',
          emoji: '\u{1F4C5}',
          category: 'work',
        ),
      );
      a.server.conversations.add(conversation.toJson());
      a.server.screenFrameSets['audit-meeting'] = {
        'revision': 1,
        'banner': screenFrameJson(
          base,
          'f-call',
          'call.png',
          role: 'banner',
          rank: 0,
          caption: 'Weekly product sync on a video call',
        ),
        'strip': [
          screenFrameJson(
            base,
            'f-slide',
            'slide.png',
            role: 'strip',
            rank: 1,
            caption: 'Q4 onboarding roadmap slide',
            badge: 'slides',
          ),
          screenFrameJson(
            base,
            'f-editor',
            'editor.png',
            role: 'strip',
            rank: 2,
            caption: 'Onboarding flow code in the editor',
            badge: 'code',
          ),
          screenFrameJson(
            base,
            'f-doc',
            'doc.png',
            role: 'strip',
            rank: 3,
            caption: 'Launch checklist document',
            badge: 'document',
          ),
        ],
      };
      await _pumpDetail(a, conversation);
      final section = find.byKey(const ValueKey('conversation_screenshots_section'));
      expect(section, findsOneWidget);
      expect(find.text('What was on screen'), findsOneWidget);
      await a.shot('Open a meeting with approved screenshots: the strip follows the summary', step: 'strip');

      await a.tap(find.byKey(const ValueKey('conversation_screenshot_f-slide')));
      await a.settle();
      await a.shot('Tap a tile: the full-size viewer opens on that frame, swipeable across the set', step: 'viewer');
      globalNavigatorKey.currentState!.pop();
      await a.settle();

      await a.longPress(find.byKey(const ValueKey('conversation_screenshot_f-slide')));
      await a.shot('Long-press a tile: Open or Delete', step: 'menu');
      await a.tap(find.text('Delete'));
      expect(find.text('Delete Screenshot?'), findsOneWidget);
      await a.shot('Choose Delete: a destructive confirmation', step: 'confirm');
      await a.tap(find.text('Delete').last);
      expect(find.byKey(const ValueKey('conversation_screenshot_f-slide')), findsNothing);
      await a.shot('Confirm: the frame is gone and the strip closes up', step: 'deleted');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-transcript',
    title: 'Conversation transcript with two unnamed speakers',
    page: _page,
    state: 'One ungrouped conversation with two transcript segments from two unnamed speakers',
    run: (a) async {
      final conversation = auditConversation(
        'audit-transcript',
        title: 'Design catch-up with Alex',
        segments: [
          _segment('0', 'Let’s simplify the first recording experience.', 'SPEAKER_0'),
          _segment('1', 'Agreed — and make saved memories easier to find.', 'SPEAKER_1'),
        ],
      );
      await _pumpDetail(a, conversation, tab: _transcriptTab);
      await a.shot('Open the Transcript tab');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-grouped',
    title: 'Grouped conversation: header, overflow menu and recordings sheet',
    page: _page,
    state: 'One conversation whose capture group has a desktop and a pendant recording',
    run: (a) async {
      const group = CaptureGroup(
        id: 'group-2',
        primaryId: 'grouped-b',
        members: [
          CaptureGroupMember(id: 'grouped-b', source: 'desktop'),
          CaptureGroupMember(id: 'grouped-b-omi', source: 'omi'),
        ],
      );
      final grouped = auditConversation('grouped-b', title: 'Design catch-up with Alex', captureGroup: group);
      await _pumpDetail(a, grouped);
      await a.shot('Grouped conversation: header with the recordings chip, top bar', step: 'summary');
      await a.tap(find.byKey(const Key('conversation_more')));
      await a.shot('Open the overflow menu of a grouped conversation', step: 'overflow');

      globalNavigatorKey.currentState!.pop();
      await a.settle();
      await a.tap(find.byKey(const Key('conversation_detail_recordings')));
      expect(find.text('Recordings of this conversation'), findsOneWidget);
      await a.shot('Tap the recordings chip: one row per source, the omi source named Pendant', step: 'recordings');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-named',
    title: 'People chip: every speaker named',
    page: _page,
    state: 'Segments from the owner and from one cached, named person (David)',
    prefs: _cachedDavid,
    run: (a) async {
      final conversation = auditConversation(
        'people-a',
        title: 'Design catch-up',
        segments: [
          _segment('0', "Let's ship Friday.", 'SPEAKER_0', isUser: true),
          _segment('1', 'Sounds good to me.', 'SPEAKER_1', personId: 'person-1'),
        ],
      );
      await _pumpDetail(a, conversation);
      await a.shot('The people chip reads "You + 1 other"');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-mixed',
    title: 'People chip: one named speaker and three unnamed',
    page: _page,
    state: 'Segments from one cached, named person (David) and three unnamed speakers',
    prefs: _cachedDavid,
    run: (a) async {
      final conversation = auditConversation(
        'people-b',
        title: 'Team standup',
        segments: [
          _segment('0', 'Kicking off.', 'SPEAKER_0', personId: 'person-1'),
          _segment('1', 'On it.', 'SPEAKER_1'),
          _segment('2', 'Same here.', 'SPEAKER_2'),
          _segment('3', 'Agreed.', 'SPEAKER_3'),
        ],
      );
      await _pumpDetail(a, conversation);
      await a.shot('The people chip reads "David + 3 others"');
    },
  ),
  AuditScenario(
    id: 'conversation-detail-people-none',
    title: 'No people chip when nobody is named',
    page: _page,
    state: 'Segments from two unnamed speakers, none of them the owner',
    run: (a) async {
      final conversation = auditConversation(
        'people-c',
        title: 'Anonymous huddle',
        segments: [_segment('0', 'Hello.', 'SPEAKER_0'), _segment('1', 'Hi there.', 'SPEAKER_1')],
      );
      await _pumpDetail(a, conversation);
      await a.shot('No people chip is shown');
    },
  ),
];
