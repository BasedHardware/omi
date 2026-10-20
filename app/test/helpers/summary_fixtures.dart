import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

const summaryFixtureTitle = 'Turn right at the next one, not this one.';

App summaryApp(String id, String name, {bool enabled = true}) => App(
      id: id,
      name: name,
      author: 'tester',
      description: 'A summary template',
      image: '',
      capabilities: {'memories'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: 0,
      enabled: enabled,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

TranscriptSegment summarySegment(
  String text, {
  bool isUser = false,
  int speaker = 0,
  String id = 's0',
  double start = 0,
  double end = 4,
}) =>
    TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_0$speaker',
      isUser: isUser,
      personId: null,
      translations: [],
      start: start,
      end: end,
    );

ServerConversation summaryConversation({
  String id = 'conv-summary',
  String title = summaryFixtureTitle,
  String overview = '',
  List<AppResponse> appResults = const [],
  List<TranscriptSegment>? segments,
}) =>
    ServerConversation(
      id: id,
      createdAt: DateTime(2026, 10, 17, 9, 30),
      startedAt: DateTime(2026, 10, 17, 9, 30),
      finishedAt: DateTime(2026, 10, 17, 9, 44),
      structured: Structured(title, overview, emoji: '🚗'),
      appResults: appResults,
      status: ConversationStatus.completed,
      transcriptSegments: segments ??
          [
            summarySegment(
              "Okay, so after the gas station it's the second light. Not the first one, the first one "
              'is a dead end into the parking garage. Then left on Valencia and the place is on the right.',
            ),
            summarySegment('Got it, second light.', isUser: true, id: 's1', start: 820, end: 840),
          ],
    );

/// Template list fetches a test controls: each call waits on a fresh completer.
class SummaryTemplateFetches {
  final List<Completer<List<App>>> enabled = [];
  final List<Completer<List<App>>> suggested = [];

  Future<List<App>> fetchEnabled() {
    final call = Completer<List<App>>();
    enabled.add(call);
    return call.future;
  }

  Future<List<App>> fetchSuggested(String conversationId) {
    final call = Completer<List<App>>();
    suggested.add(call);
    return call.future;
  }
}

/// A detail provider showing [conversation], with every network seam faked.
ConversationDetailProvider summaryProvider(
  ServerConversation conversation, {
  ConversationReprocessCall? reprocess,
  SummaryTemplateFetches? fetches,
  List<App> catalog = const [],
  PreferredSummaryAppWrite? writePreferredSummaryApp,
}) {
  final fakes = fetches ?? SummaryTemplateFetches();
  final provider = ConversationDetailProvider(
    reprocess:
        reprocess ?? (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async => const ReprocessFailed(),
    fetchConversation: (_) async => conversation,
    fetchEnabledSummaryApps: fakes.fetchEnabled,
    fetchSuggestedSummaryApps: fakes.fetchSuggested,
    writePreferredSummaryApp: writePreferredSummaryApp ?? (_) async => true,
  )
    ..selectedDate = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt)
    ..titleController = TextEditingController(text: conversation.structured.title)
    ..titleFocusNode = FocusNode();
  provider.appProvider = AppProvider()..apps = List.of(catalog);
  provider.setCachedConversation(conversation);
  return provider;
}

/// The app shell the summary widgets need, providers above the navigator like production.
Widget summaryHarness(ConversationDetailProvider provider, Widget home, {ThemeData? theme}) {
  return ChangeNotifierProvider<ConversationDetailProvider>.value(
    value: provider,
    child: MaterialApp(
      locale: const Locale('en'),
      theme: theme ?? buildOmiTheme(brightness: Brightness.dark),
      debugShowCheckedModeBanner: false,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    ),
  );
}

AppLocalizations summaryL10n(WidgetTester tester) => AppLocalizations.of(tester.element(find.byType(Scaffold).first));
