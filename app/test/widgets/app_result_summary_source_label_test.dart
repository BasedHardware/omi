import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';

ServerConversation _conversationWithSections() {
  final structured = Structured('Sprint sync', 'Short compatibility paragraph.', emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday'),
  ];
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: structured,
  );
}

Future<void> _pumpSummary(WidgetTester tester, {App? app, AppResponse? response, bool asSliver = false}) async {
  final conversation = _conversationWithSections();
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
                    appResponse: response ?? AppResponse(conversation.structured.overview, appId: null),
                    app: app,
                    conversation: conversation,
                    asSliver: true,
                  ),
                ],
              )
            : AppResultDetailWidget(
                appResponse: response ?? AppResponse(conversation.structured.overview, appId: null),
                app: app,
                conversation: conversation,
              ),
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
  // SCA-359: the summary attribution row used to render "Unknown App" for every
  // first-party (notes v2) summary because findAppById(null) is null by design.
  // First-party must label itself "Summary"; "Unknown App" is only for a
  // non-null app id whose catalog lookup failed.
  group('summary source label', () {
    testWidgets('a first-party summary (appId == null) is labeled Summary, not Unknown App', (tester) async {
      await _pumpSummary(tester, app: null, response: AppResponse('First-party overview', appId: null));

      expect(find.text('Summary'), findsOneWidget);
      expect(find.text('Unknown App'), findsNothing);
    });

    testWidgets('the sliver attribution labels a first-party summary Summary too', (tester) async {
      await _pumpSummary(tester, app: null, asSliver: true);

      expect(find.text('Summary'), findsOneWidget);
      expect(find.text('Unknown App'), findsNothing);
    });

    testWidgets('an app result whose catalog lookup failed is Unknown App', (tester) async {
      await _pumpSummary(tester, app: null, response: AppResponse('App summary', appId: 'missing-app'));

      expect(find.text('Unknown App'), findsOneWidget);
      expect(find.text('Summary'), findsNothing);
    });

    testWidgets('a resolved app result shows the app name', (tester) async {
      await _pumpSummary(tester, app: _templateApp(), response: AppResponse('App summary', appId: 'app-1'));

      expect(find.text('My Template'), findsOneWidget);
      expect(find.text('Unknown App'), findsNothing);
    });
  });
}
