import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _processingConversation({
  required DateTime createdAt,
  DateTime? finishedAt,
}) {
  return ServerConversation(
    id: 'processing-1',
    createdAt: createdAt,
    finishedAt: finishedAt,
    structured: Structured('Processing', 'Overview'),
    status: ConversationStatus.processing,
  );
}

String _processingTakingLonger(WidgetTester tester) {
  return AppLocalizations.of(tester.element(find.byType(Scaffold)))!.processingTakingLonger;
}

void main() {
  testWidgets('shows timeout warning and retry after two minutes of processing', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    final now = DateTime.now();
    final processingStartedAt = now.subtract(const Duration(minutes: 3));
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
              conversation: _processingConversation(
                // Long recording: created well before processing began.
                createdAt: processingStartedAt.subtract(const Duration(minutes: 10)),
                finishedAt: processingStartedAt,
              ),
              now: () => now,
              reprocess: (id) async {
                retryCalls += 1;
                return _processingConversation(createdAt: now, finishedAt: now);
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final warning = _processingTakingLonger(tester);
    expect(find.text(warning), findsOneWidget);
    expect(find.byKey(const Key('processing_conversation_retry_button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('processing_conversation_retry_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(retryCalls, 1);
    // Successful retry resets the local processing clock so the warning clears.
    expect(find.text(warning), findsNothing);
  });

  testWidgets('does not show timeout UI before two minutes of processing', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    final now = DateTime.now();

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: ProcessingConversationWidget(
              conversation: _processingConversation(
                createdAt: now.subtract(const Duration(minutes: 10)),
                finishedAt: now.subtract(const Duration(minutes: 1)),
              ),
              now: () => now,
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text(_processingTakingLonger(tester)), findsNothing);
    expect(find.byKey(const Key('processing_conversation_retry_button')), findsNothing);
  });

  testWidgets('long recording does not time out the moment processing begins', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    final now = DateTime.now();

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: ProcessingConversationWidget(
              conversation: _processingConversation(
                createdAt: now.subtract(const Duration(minutes: 15)),
                finishedAt: now,
              ),
              now: () => now,
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text(_processingTakingLonger(tester)), findsNothing);
    expect(find.byKey(const Key('processing_conversation_retry_button')), findsNothing);
  });

  testWidgets('retry errors show the snackbar instead of surfacing unhandled', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    final now = DateTime.now();
    final processingStartedAt = now.subtract(const Duration(minutes: 3));

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: ProcessingConversationWidget(
              conversation: _processingConversation(
                createdAt: processingStartedAt,
                finishedAt: processingStartedAt,
              ),
              now: () => now,
              reprocess: (id) async {
                throw FormatException('malformed reprocess body');
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byKey(const Key('processing_conversation_retry_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(
      find.text(AppLocalizations.of(tester.element(find.byType(Scaffold)))!.somethingWentWrong),
      findsOneWidget,
    );
  });
}
