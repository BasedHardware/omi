import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';

/// List responses omit transcript_segments (backend/routers/conversations.py: "Clients should treat
/// omitted transcript_segments as unknown/not loaded, not as an empty transcript"). The detail page
/// fetches the full conversation once, on open, and reads it back out of this list. A list refresh
/// (app resumed, connection restored) then put the transcript-less row back, and an open
/// transcript vanished.
TranscriptSegment _line(String text) => TranscriptSegment(
      id: text,
      text: text,
      speaker: 'SPEAKER_0',
      isUser: true,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

ServerConversation _row(String id,
        {List<TranscriptSegment> lines = const [], bool locked = false, String title = 't'}) =>
    ServerConversation(
      id: id,
      createdAt: DateTime(2026, 10, 25, 9),
      structured: Structured(title, 'overview'),
      status: ConversationStatus.completed,
      transcriptSegments: lines,
      isLocked: locked,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<ServerConversation> page;
  late ConversationProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    page = [];
    provider =
        ConversationProvider(conversationListFetcher: () async => (items: page, ok: true), isSignedIn: () => true);
  });
  tearDown(() => provider.dispose());

  /// The state after the detail page loaded a conversation in full.
  void loaded(ServerConversation full) => provider.conversations = [full];

  test('a background refresh keeps a transcript the detail page already loaded', () async {
    loaded(_row('a', lines: [_line('hello')]));
    page = [_row('a', title: 'renamed')]; // the list row: no transcript

    await provider.forceRefreshConversations();

    final row = provider.conversations.single;
    expect(row.transcriptSegments.map((s) => s.text), ['hello'], reason: 'an open transcript vanished');
    expect(row.structured.title, 'renamed', reason: 'everything else still comes from the fresh row');
  });

  test('a full reload keeps it too', () async {
    loaded(_row('a', lines: [_line('hello')]));
    page = [_row('a')];

    await provider.fetchConversations();

    expect(provider.conversations.single.transcriptSegments.map((s) => s.text), ['hello']);
  });

  test('a fresh row that carries its own transcript replaces the loaded one', () async {
    loaded(_row('a', lines: [_line('old')]));
    page = [
      _row('a', lines: [_line('new')])
    ];

    await provider.forceRefreshConversations();

    expect(provider.conversations.single.transcriptSegments.map((s) => s.text), ['new']);
  });

  test('a conversation that became locked does not keep its transcript', () async {
    // The list redacts locked conversations on purpose; carrying lines over would undo that.
    loaded(_row('a', lines: [_line('hello')]));
    page = [_row('a', locked: true)];

    await provider.forceRefreshConversations();

    expect(provider.conversations.single.transcriptSegments, isEmpty);
  });

  test('withTranscriptSegments changes the transcript and nothing else', () {
    // Every field this test can build without a nested fixture is set away from its default, so
    // a field the copy drops changes toJson; the fields toJson leaves out are checked directly.
    final photos = <ConversationPhoto>[];
    final audioFiles = <AudioFile>[];
    final matchSnippets = <TranscriptMatchSnippet>[];
    final apps = ['app-1'];
    final source = ServerConversation(
      id: 'x',
      createdAt: DateTime.utc(2026, 10, 25, 9),
      onDeviceProvenance: {'model': 'm'},
      clientProcessing: {'state': 's'},
      structured: Structured('T', 'O'),
      startedAt: DateTime.utc(2026, 10, 25, 9),
      finishedAt: DateTime.utc(2026, 10, 25, 9, 30),
      appResults: [AppResponse('summary', appId: 'app-1')],
      suggestedSummarizationApps: apps,
      photos: photos,
      audioFiles: audioFiles,
      discarded: true,
      deleted: true,
      source: ConversationSource.sdcard,
      language: 'en',
      status: ConversationStatus.processing,
      isLocked: true,
      starred: true,
      folderId: 'f',
      visibility: ConversationVisibility.shared,
      siriVisibilityValid: false,
      matchSnippets: matchSnippets,
      summaryRetryable: true,
      processingDeferred: true,
      captureCoverage: 'partial',
    )..isNew = true;

    final copy = source.withTranscriptSegments([_line('hello')]);

    expect(copy.toJson()..remove('transcript_segments'), source.toJson()..remove('transcript_segments'));
    expect(copy.transcriptSegments.map((s) => s.text), ['hello']);
    expect(copy.isNew, isTrue);
    expect(copy.transcriptCarried, isFalse);
    expect(identical(copy.audioFiles, audioFiles), isTrue);
    expect(identical(copy.matchSnippets, matchSnippets), isTrue);
    expect(identical(copy.photos, photos), isTrue);
  });

  test('a kept transcript is marked as carried, so the detail page re-reads it', () {
    final kept = _row('a').keepingTranscriptOf(_row('a', lines: [_line('hello')]));
    expect(kept.transcriptCarried, isTrue);
    expect(_row('a', lines: [_line('new')]).keepingTranscriptOf(kept).transcriptCarried, isFalse);
  });
}
