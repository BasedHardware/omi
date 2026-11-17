import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/synced_conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';

ServerConversation _conversation({
  ConversationStatus status = ConversationStatus.completed,
  String? homeStep,
}) {
  final conversation = ServerConversation(
    id: 'synced-1',
    createdAt: DateTime.utc(2026, 11, 17, 8),
    structured: Structured('Venue planning', ''),
    status: status,
  );
  return homeStep == null ? conversation : conversation.withHomeStep(homeStep);
}

Future<AppLocalizations> _pump(WidgetTester tester, Future<ReprocessResult> Function(String) reprocess) async {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  );
  addTearDown(provider.dispose);
  await tester.pumpWidget(
    ChangeNotifierProvider<ConversationProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SyncedConversationListItem(
            conversation: _conversation(homeStep: 'failed'),
            date: DateTime.utc(2026, 11, 17),
            conversationIdx: 0,
            showReprocess: true,
            reprocess: reprocess,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return AppLocalizations.of(tester.element(find.byType(Scaffold)));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionPendingConversations.reset();
  });
  tearDown(TranscriptionPendingConversations.reset);

  testWidgets('a reprocess answered transcription pending says not transcribed, not nothing', (tester) async {
    final l10n = await _pump(tester, (_) async => const ReprocessTranscriptionPending());
    await tester.tap(find.byIcon(Icons.refresh_outlined));
    await tester.pump();
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.somethingWentWrong), findsNothing);
    await tester.pumpAndSettle(const Duration(seconds: 5));
  });

  testWidgets('a reprocess inside the transcription window shows the waiting copy and the notice', (tester) async {
    final l10n = await _pump(
      tester,
      (_) async => ReprocessTranscriptionPending(
        _conversation(status: ConversationStatus.processing, homeStep: 'transcribing'),
      ),
    );
    await tester.tap(find.byIcon(Icons.refresh_outlined));
    await tester.pump();
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.somethingWentWrong), findsNothing);
    await tester.pumpAndSettle(const Duration(seconds: 5));
  });

  testWidgets('a failed reprocess is an error, no longer silent', (tester) async {
    final l10n = await _pump(tester, (_) async => const ReprocessFailed(statusCode: 500));
    await tester.tap(find.byIcon(Icons.refresh_outlined));
    await tester.pump();
    expect(find.text(l10n.somethingWentWrong), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 10));
  });
}
