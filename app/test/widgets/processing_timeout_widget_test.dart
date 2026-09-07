import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _processingConversation({required DateTime createdAt}) {
  return ServerConversation(
    id: 'processing-1',
    createdAt: createdAt,
    structured: Structured('Processing', 'Overview'),
    status: ConversationStatus.processing,
  );
}

void main() {
  testWidgets('shows timeout warning and retry after two minutes', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    final createdAt = DateTime.now().subtract(const Duration(minutes: 3));
    var retryCalls = 0;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: ProcessingConversationWidget(
              conversation: _processingConversation(createdAt: createdAt),
              now: () => DateTime.now(),
              reprocess: (id) async {
                retryCalls += 1;
                return _processingConversation(createdAt: DateTime.now());
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('Still working — this is taking longer than usual.'), findsOneWidget);
    expect(find.byKey(const Key('processing_conversation_retry_button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('processing_conversation_retry_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(retryCalls, 1);
  });

  testWidgets('does not show timeout UI before two minutes', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: ProcessingConversationWidget(conversation: _processingConversation(createdAt: DateTime.now())),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('Still working — this is taking longer than usual.'), findsNothing);
    expect(find.byKey(const Key('processing_conversation_retry_button')), findsNothing);
  });
}
