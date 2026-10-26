import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// A transcript kept across a list refresh (ServerConversation.keepingTranscriptOf) may be out of
/// date: the server can have re-transcribed, re-labelled speakers or synced more audio since. The
/// detail page must re-read it rather than show the kept lines as current.
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

ServerConversation _row({required List<TranscriptSegment> lines}) => ServerConversation(
      id: 'conversation-1',
      createdAt: DateTime.utc(2026, 10, 25, 9),
      structured: Structured('Ski trip', 'A useful summary.'),
      transcriptSegments: lines,
      // App results present, so the page's separate app-results fill does not fetch.
      appResults: [AppResponse('summary', appId: 'app-1')],
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late int reads;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    reads = 0;
  });

  Future<void> open(WidgetTester tester, ServerConversation row) async {
    final conversations = ConversationProvider(isSignedIn: () => false)
      ..conversations = [row]
      ..groupedConversations = {
        conversationLocalDayKey(row.createdAt): [row],
      };
    final detail = ConversationDetailProvider(fetchConversation: (_) async {
      reads++;
      return _row(lines: [_line('fresh')]);
    });
    final apps = AppProvider();
    detail.setProviders(apps, conversations);
    addTearDown(() {
      detail.dispose();
      conversations.dispose();
      apps.dispose();
    });
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<AppProvider>.value(value: apps),
          ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (_) => PeopleProvider()),
          ChangeNotifierProvider(
            create: (_) => IntegrationProvider(
              fetchStatus: (_) async => null,
              saveStatus: (_, __) async => false,
              deleteStatus: (_) async => false,
              persistPref: (_, __) async {},
            ),
          ),
        ],
        child: ConversationDetailPage(conversation: row),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
  }

  testWidgets('opening a conversation whose transcript was carried re-reads it', (tester) async {
    final listRow = _row(lines: const []);
    final carried = listRow.keepingTranscriptOf(_row(lines: [_line('old')]));
    expect(carried.transcriptCarried, isTrue);

    await open(tester, carried);

    expect(reads, 1);
    expect(find.textContaining('fresh', findRichText: true), findsWidgets);
  });

  testWidgets('a transcript read from the server is trusted on open', (tester) async {
    await open(tester, _row(lines: [_line('current')]));

    expect(reads, 0);
  });

  testWidgets('returning to the app re-reads the open conversation', (tester) async {
    await open(tester, _row(lines: [_line('current')]));

    tester
        .state<ConversationDetailPageState>(find.byType(ConversationDetailPage))
        .didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();

    expect(reads, 1);
  });
}
