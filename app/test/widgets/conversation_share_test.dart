import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';

ServerConversation _conversation(String id, {String title = 'Design review'}) => ServerConversation(
      id: id,
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured(title, 'Overview'),
      status: ConversationStatus.completed,
    );

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('Sharing a conversation (#19242)', () {
    testWidgets('detail page Share button does not ask "Share Conversation?" before the share sheet', (tester) async {
      final conversation = _conversation('conv-1');
      final conversationProvider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      )..conversations = [conversation];
      final detailProvider = ConversationDetailProvider()..updateConversation(conversation);
      addTearDown(conversationProvider.dispose);
      addTearDown(detailProvider.dispose);

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detailProvider),
            ChangeNotifierProvider<ConversationProvider>.value(value: conversationProvider),
            ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider<FolderProvider>(create: (_) => FolderProvider()),
            ChangeNotifierProvider<AppProvider>(create: (_) => AppProvider()),
            ChangeNotifierProvider<SpeechProfileProvider>(create: (_) => SpeechProfileProvider()),
            ChangeNotifierProvider<PeopleProvider>(create: (_) => PeopleProvider(autoInitialize: false)),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: ConversationDetailPage(conversation: conversation),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(find.byKey(const Key('conversation_share')));
      await tester.pumpAndSettle();

      expect(find.text('Share Conversation?'), findsNothing);
      expect(find.text('Anyone with the link can view'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('long-press Share action does not ask "Share Conversation?" before the share sheet', (tester) async {
      final conversation = _conversation('conv-2');
      final conversationProvider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      )..conversations = [conversation];
      addTearDown(conversationProvider.dispose);

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversationProvider),
            ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider<FolderProvider>(create: (_) => FolderProvider()),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(
              body: ConversationListItem(
                conversation: conversation,
                date: DateTime(2026, 9, 20),
                conversationIdx: 0,
              ),
            ),
          ),
        ),
      );

      await tester.longPress(find.byType(ConversationListItem));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('conversation_action_share')));
      await tester.pumpAndSettle();

      expect(find.text('Share Conversation?'), findsNothing);
      expect(find.text('Anyone with the link can view'), findsNothing);
    });

    testWidgets('shareConversation helper proceeds directly without confirmation modal', (tester) async {
      final conversation = _conversation('conv-3');
      late BuildContext capturedContext;

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) {
                capturedContext = context;
                return const SizedBox();
              },
            ),
          ),
        ),
      );

      await shareConversation(capturedContext, conversation);
      await tester.pumpAndSettle();

      expect(find.text('Share Conversation?'), findsNothing);
      expect(find.text('Anyone with the link can view'), findsNothing);
    });
  });
}
