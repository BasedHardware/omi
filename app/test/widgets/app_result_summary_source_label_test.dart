import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';

ServerConversation _conversationWithSections() {
  final structured = Structured('Sprint sync', 'Short compatibility paragraph.', emoji: '🧠');
  structured.sections = [const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday')];
  return ServerConversation(id: 'conv-1', createdAt: DateTime(2026, 7, 1, 9).toUtc(), structured: structured);
}

Future<void> _pumpSummary(
  WidgetTester tester, {
  App? app,
  AppResponse? response,
  bool asSliver = false,
  bool legacyApp = false,
}) async {
  final conversation = _conversationWithSections();
  final selection = response == null
      ? ConversationSummarySelection.select(conversation)
      : ConversationSummarySelection(
          content: response.content,
          kind: legacyApp || response.appId != null ? ConversationSummaryKind.app : ConversationSummaryKind.overview,
          appId: response.appId,
          resultIndex: legacyApp || response.appId != null ? 0 : null,
        );
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: asSliver
            ? CustomScrollView(
                slivers: [
                  AppResultDetailWidget(
                    summarySelection: selection,
                    app: app,
                    conversation: conversation,
                    asSliver: true,
                  ),
                ],
              )
            : AppResultDetailWidget(summarySelection: selection, app: app, conversation: conversation),
      ),
    ),
  );
  await tester.pump();
}

App _templateApp() => App(
      id: 'app-1',
      name: 'My Template',
      author: 'tester',
      description: 'test',
      image: '',
      capabilities: {'memories'},
      status: 'approved',
      category: 'test',
      approved: true,
      ratingCount: 0,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

void main() {
  // The attribution row under a summary opens the app that wrote it. Omi's own summary and an app
  // the catalog no longer knows have nowhere to open, so they show no row (the bottom pill still
  // names the source: "Summary" / "Unknown App", SCA-359).
  group('summary attribution row', () {
    testWidgets('a first-party summary (appId == null) shows no row', (tester) async {
      await _pumpSummary(tester, app: null, response: AppResponse('First-party overview', appId: null));

      expect(find.text('Summary'), findsNothing);
      expect(find.text('Unknown App'), findsNothing);
      expect(find.byIcon(Icons.arrow_forward_ios), findsNothing);
    });

    testWidgets('the sliver summary shows no row for a first-party summary either', (tester) async {
      await _pumpSummary(tester, app: null, asSliver: true);

      expect(find.text('Summary'), findsNothing);
      expect(find.byIcon(Icons.arrow_forward_ios), findsNothing);
    });

    testWidgets('an app result whose catalog lookup failed shows no row', (tester) async {
      await _pumpSummary(tester, app: null, response: AppResponse('App summary', appId: 'missing-app'));

      expect(find.text('Unknown App'), findsNothing);
      expect(find.byIcon(Icons.arrow_forward_ios), findsNothing);
    });

    testWidgets('an unattributed legacy app result shows no row', (tester) async {
      await _pumpSummary(tester, response: AppResponse('Imported app output.'), legacyApp: true);

      expect(find.text('Unknown App'), findsNothing);
      expect(find.byIcon(Icons.arrow_forward_ios), findsNothing);
    });

    testWidgets('a resolved app result shows the app name and opens it', (tester) async {
      await _pumpSummary(
        tester,
        app: _templateApp(),
        response: AppResponse('App summary', appId: 'app-1'),
      );

      expect(find.text('My Template'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_forward_ios), findsOneWidget);
      expect(find.text('Unknown App'), findsNothing);
    });

    testWidgets('the sliver summary shows a resolved app too', (tester) async {
      await _pumpSummary(
        tester,
        app: _templateApp(),
        response: AppResponse('App summary', appId: 'app-1'),
        asSliver: true,
      );

      expect(find.text('My Template'), findsOneWidget);
    });
  });
}
