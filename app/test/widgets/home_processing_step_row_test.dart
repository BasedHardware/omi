/// The Home processing row names the current step and how many recordings one row stands for.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/ui/ui.dart';

ServerConversation _conversation() {
  final started = DateTime(2026, 11, 5, 9);
  return ServerConversation(
    id: 'processing',
    createdAt: started,
    startedAt: started,
    finishedAt: started.add(const Duration(minutes: 6, seconds: 31)),
    structured: Structured('Ignored server title', ''),
    status: ConversationStatus.processing,
  );
}

Future<void> _pumpRow(WidgetTester tester, {required HomeStep step, int count = 1}) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    locale: const Locale('en'),
    home: Scaffold(
      body: ProcessingConversationRow(conversation: _conversation(), step: step, count: count),
    ),
  ));
  await tester.pump();
}

void main() {
  testWidgets('transcribing single recording shows a count, never its duration as processing age', (tester) async {
    await _pumpRow(tester, step: HomeStep.transcribing);
    expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
    expect(find.text('Processing…'), findsOneWidget);
    expect(find.text('Ignored server title'), findsNothing);
    expect(find.text('Transcribing… · 1 recording'), findsOneWidget);
    expect(find.textContaining('6m 31s'), findsNothing);
    expect(find.byType(OmiActivityRing), findsOneWidget);
    expect(find.byIcon(Icons.error_outline_rounded), findsNothing);
    final semantics = tester.getSemantics(find.byKey(const Key('home_processing_row')));
    expect(semantics.label, contains('Transcribing… · 1 recording'));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('writing notes for three recordings says how many it stands for', (tester) async {
    await _pumpRow(tester, step: HomeStep.writingNotes, count: 3);
    final meta = tester.widget<Text>(find.text('Writing notes… · 3 recordings'));
    expect(meta.data, contains('3 recordings'));
    expect(find.byType(OmiActivityRing), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a single writing-notes recording also labels its count', (tester) async {
    await _pumpRow(tester, step: HomeStep.writingNotes);
    expect(find.text('Writing notes… · 1 recording'), findsOneWidget);
    expect(find.textContaining('6m 31s'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('an unknown local step never defaults to writing notes', (tester) async {
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: ProcessingConversationRow(conversation: _conversation()))));
    await tester.pump();
    expect(find.text('Transcribing… · 1 recording'), findsOneWidget);
    expect(find.textContaining('Writing notes'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
