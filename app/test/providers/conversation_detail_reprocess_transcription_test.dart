import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../helpers/summary_fixtures.dart';

/// Records the loading state each crash report saw; the reporter itself fails.
class _ReportingProvider extends ConversationDetailProvider {
  final List<bool> loadingWhenReported = [];

  @override
  Future<void> reportReprocessCrash(Object error, StackTrace stackTrace, ServerConversation target) async {
    loadingWhenReported.add(loadingReprocessTranscription);
    throw StateError('crash reporter unavailable');
  }
}

T _showing<T extends ConversationDetailProvider>(T provider, ServerConversation conversation) => provider
  ..selectedDate = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt)
  ..setCachedConversation(conversation);

Future<TranscriptionReprocessResult> _retranscribed(String _) async =>
    TranscriptionReprocessResult(conversation: summaryConversation(overview: 'New summary'));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('reprocessTranscription updates the conversation on success', () async {
    final provider = _providerWithConversation();
    addTearDown(provider.dispose);

    final refreshed = ServerConversation(
      id: 'c1',
      createdAt: DateTime.utc(2026, 7, 18, 9),
      startedAt: DateTime.utc(2026, 7, 18, 9),
      structured: Structured('Re-transcribed', 'New overview'),
      status: ConversationStatus.completed,
      transcriptSegments: const [],
    );

    final ok = await provider.reprocessTranscription(
      client: (_) async => TranscriptionReprocessResult(conversation: refreshed),
    );

    expect(ok, isTrue);
    expect(provider.loadingReprocessTranscription, isFalse);
    expect(provider.conversation.structured.title, 'Re-transcribed');
  });

  test('reprocessTranscription reports no audio without mutating the conversation', () async {
    final provider = _providerWithConversation();
    addTearDown(provider.dispose);

    final ok = await provider.reprocessTranscription(
      client: (_) async => const TranscriptionReprocessResult(errorCode: 'no_audio'),
    );

    expect(ok, isFalse);
    expect(provider.loadingReprocessTranscription, isFalse);
    expect(provider.conversation.structured.title, 'Original');
  });

  test('reprocessTranscription reports a generic failure and clears loading', () async {
    final provider = _providerWithConversation();
    addTearDown(provider.dispose);

    final ok = await provider.reprocessTranscription(
      client: (_) async => const TranscriptionReprocessResult(errorCode: 'failed'),
    );

    expect(ok, isFalse);
    expect(provider.loadingReprocessTranscription, isFalse);
    expect(provider.conversation.structured.title, 'Original');
  });

  test('a running re-transcription blocks every summary entry point', () async {
    final provider = summaryProvider(summaryConversation());
    addTearDown(provider.dispose);
    final response = Completer<TranscriptionReprocessResult>();
    final pending = provider.reprocessTranscription(client: (_) => response.future);

    expect(provider.anyReprocessInFlight, isTrue);
    expect(await provider.reprocessConversation(), isFalse);
    response.complete(const TranscriptionReprocessResult(errorCode: 'failed'));
    await pending;
    expect(provider.anyReprocessInFlight, isFalse);
  });

  test('a re-transcription replaces the last failed summary request', () async {
    final provider = summaryProvider(
      summaryConversation(),
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async => const ReprocessBusy(),
    );
    addTearDown(provider.dispose);
    expect(await provider.reprocessConversation(appId: 'pg'), isFalse);
    expect(provider.summaryFailure, isNotNull);

    expect(await provider.reprocessTranscription(client: _retranscribed), isTrue);

    expect(provider.summaryFailure, isNull);
    expect(provider.lastFailedReprocessConversationId, isNull);
    expect(provider.lastFailedReprocessAppId, isNull);
    expect(provider.conversation.structured.overview, 'New summary');
  });

  test('an older detail read landing after the re-transcription never overwrites it', () async {
    final original = summaryConversation(overview: 'Old summary');
    final staleRead = Completer<ServerConversation?>();
    final provider = _showing(ConversationDetailProvider(fetchConversation: (_) => staleRead.future), original);
    addTearDown(provider.dispose);

    final read = provider.refreshConversation();
    expect(await provider.reprocessTranscription(client: _retranscribed), isTrue);
    staleRead.complete(original);

    expect(await read, isFalse);
    expect(provider.conversation.structured.overview, 'New summary');
  });

  test('a throwing re-transcription settles the page before crash reporting, which may throw too', () async {
    final provider = _showing(_ReportingProvider(), summaryConversation());
    addTearDown(provider.dispose);

    expect(await provider.reprocessTranscription(client: (_) async => throw StateError('transport')), isFalse);

    expect(provider.loadingWhenReported, [false]);
    expect(provider.loadingReprocessTranscription, isFalse);
    expect(provider.reprocessConversationId, isEmpty);
    expect(provider.error, 'REPROCESS_TRANSCRIPTION_FAILED');
  });

  test('a failure after the reader opened another conversation is not announced there', () async {
    final provider = summaryProvider(summaryConversation(id: 'a'));
    addTearDown(provider.dispose);
    final response = Completer<TranscriptionReprocessResult>();
    final pending = provider.reprocessTranscription(client: (_) => response.future);
    provider.setCachedConversation(summaryConversation(id: 'b'));
    response.complete(const TranscriptionReprocessResult(errorCode: 'no_audio'));

    expect(await pending, isFalse);
    expect(provider.error, isNull);
    expect(provider.loadingReprocessTranscription, isFalse);
    expect(provider.conversation.id, 'b');
  });

  test('a result landing after the page lost its conversation still completes for its target', () async {
    final provider = _showing(_ReportingProvider(), summaryConversation());
    addTearDown(provider.dispose);
    final response = Completer<TranscriptionReprocessResult>();
    final pending = provider.reprocessTranscription(client: (_) => response.future);
    provider.selectedDate = DateTime(2000);
    response.complete(await _retranscribed('conv-summary'));

    expect(await pending, isTrue);
    expect(provider.loadingWhenReported, isEmpty, reason: 'analytics must not need an open conversation');
    expect(provider.loadingReprocessTranscription, isFalse);
  });

  testWidgets('a re-transcription supersedes the pending speaker summary refresh', (tester) async {
    var summaryRequests = 0;
    final original = summaryConversation(overview: 'Old summary');
    final provider = _showing(
      ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          summaryRequests++;
          return const ReprocessFailed();
        },
        fetchConversation: (_) async => original,
      ),
      original,
    );
    addTearDown(provider.dispose);
    expect(await provider.assignSpeaker(['s0'], 'person-1'), isTrue);
    expect(provider.offerSpeakerSummaryRefresh, isTrue);

    expect(await provider.reprocessTranscription(client: _retranscribed), isTrue);
    await tester.pump(const Duration(seconds: 5));

    expect(summaryRequests, 0);
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
  });

  testWidgets('a re-transcription ends the labeling pass, so leaving regenerates nothing', (tester) async {
    var summaryRequests = 0;
    final original = summaryConversation(overview: 'Old summary');
    final provider = _showing(
      ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          summaryRequests++;
          return const ReprocessFailed();
        },
        fetchConversation: (_) async => original,
      ),
      original,
    );
    addTearDown(provider.dispose);
    provider.beginSpeakerLabelingSession();
    expect(await provider.assignSpeaker(['s0'], 'person-1'), isTrue);

    expect(await provider.reprocessTranscription(client: _retranscribed), isTrue);
    expect(provider.speakerLabelingSessionActive, isFalse);
    provider.setCachedConversation(summaryConversation(id: 'other'));
    await tester.pump(const Duration(seconds: 5));

    expect(summaryRequests, 0);
  });
}

ConversationDetailProvider _providerWithConversation() {
  final startedAt = DateTime.utc(2026, 7, 18, 9);
  final conversation = ServerConversation(
    id: 'c1',
    createdAt: startedAt,
    startedAt: startedAt,
    structured: Structured('Original', 'Overview'),
    status: ConversationStatus.completed,
  );

  final conversationProvider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  );
  conversationProvider.conversations = [conversation];
  conversationProvider.groupConversationsByDate();

  final detailProvider = ConversationDetailProvider();
  detailProvider.conversationProvider = conversationProvider;
  detailProvider.updateConversation(conversation.id, conversationProvider.groupedConversations.keys.single);
  return detailProvider;
}
