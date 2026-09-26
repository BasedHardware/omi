// Share on a conversation (IMG_1146): the system share sheet opens straight away — no
// "Share Conversation? Anyone with the link can view" question first.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final en = lookupAppLocalizations(const Locale('en'));
  final shares = <MethodCall>[];

  setUp(() {
    shares.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (call) async {
        shares.add(call);
        return 'dev.fluttercommunity.plus/share/success';
      },
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('dev.fluttercommunity.plus/share'), null);
  });

  testWidgets('Share opens the system share sheet straight away, with no question first', (tester) async {
    final conversation = ServerConversation(
      id: 'conversation-1',
      createdAt: DateTime.utc(2026, 9, 23),
      structured: Structured('Cafe Stop and Nearby Shops', ''),
      visibility: ConversationVisibility.shared,
    );
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => shareConversation(context, conversation),
              child: const Text('share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('share'));
    await tester.pump();

    expect(find.text(en.shareConversationQuestion), findsNothing);
    expect(find.text(en.anyoneWithLinkCanView), findsNothing);
    expect(shares, hasLength(1), reason: 'the system share sheet, at once');
    expect('${shares.single.arguments}', contains('conversation-1'));
  });

  testWidgets('a private conversation does not ask either: it goes straight to making the link', (tester) async {
    final conversation = ServerConversation(
      id: 'conversation-2',
      createdAt: DateTime.utc(2026, 9, 23),
      structured: Structured('Cafe Stop and Nearby Shops', ''),
    );
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => shareConversation(context, conversation),
              child: const Text('share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('share'));
    await tester.pump();
    expect(find.text(en.shareConversationQuestion), findsNothing, reason: 'no question before the sheet');
    expect(find.text(en.anyoneWithLinkCanView), findsNothing);
    await tester.pumpAndSettle();
    expect(find.text(en.shareConversationQuestion), findsNothing);
    // No server in a hermetic test: the link cannot be made, and it says so.
    expect(find.text(en.conversationUrlNotShared), findsOneWidget);
    expect(shares, isEmpty);
  });
}
