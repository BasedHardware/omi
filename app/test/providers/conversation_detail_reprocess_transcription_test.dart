import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
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
