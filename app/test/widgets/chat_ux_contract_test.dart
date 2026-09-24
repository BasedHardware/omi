/// Chat surfaces on the mobile UX contract (lane 3): a failed reply offers Try Again, the
/// feedback sheet is localized with a neutral Submit, the drawer keeps Clear Chat at the bottom and
/// labels its per-app Disable, and a composer button that cannot send looks disabled.
library;

import 'dart:ui' show Tristate;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/chat_apps_drawer.dart';
import 'package:omi/pages/chat/widgets/chat_composer_parts.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';

Widget _host(Widget child, {Locale locale = const Locale('en')}) {
  return MaterialApp(
    locale: locale,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: child),
  );
}

App _chatApp(String id, String name) => App(
      id: id,
      name: name,
      author: 'Omi',
      description: '',
      image: '',
      capabilities: {'chat'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: 0,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

void main() {
  group('failed reply', () {
    testWidgets('shows the localized reason and Try Again, which retries', (tester) async {
      var retries = 0;
      await tester.pumpWidget(_host(ChatReplyError(onRetry: () => retries++)));

      expect(find.text("Omi couldn't reply. Check your connection and try again."), findsOneWidget);
      await tester.tap(find.text('Try Again'));
      expect(retries, 1);
    });

    testWidgets('a reply that cannot be retried shows no button', (tester) async {
      await tester.pumpWidget(_host(const ChatReplyError()));
      expect(find.text('Try Again'), findsNothing);
    });

    testWidgets('is translated', (tester) async {
      await tester.pumpWidget(_host(ChatReplyError(onRetry: () {}), locale: const Locale('de')));
      expect(find.text('Omi konnte nicht antworten. Prüfe deine Verbindung und versuche es erneut.'), findsOneWidget);
    });
  });

  testWidgets('feedback sheet: localized title and reasons, Submit disabled until a reason is chosen', (tester) async {
    String? submitted;
    await tester.pumpWidget(
      _host(Builder(
        builder: (context) => TextButton(
          onPressed: () => showFeedbackBottomSheet(context, onSubmit: (reason, comment) => submitted = reason),
          child: const Text('open'),
        ),
      )),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.text('What Went Wrong?'), findsOneWidget);
    expect(find.text('Incorrect or made up'), findsOneWidget);
    final submit = tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Submit'));
    expect(submit.onPressed, isNull);
    expect(submit.variant, OmiButtonVariant.primary, reason: 'neutral white primary, not off-palette blue');

    await tester.tap(find.text('Too verbose'));
    await tester.pump();
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    expect(submitted, 'too_verbose');
  });

  testWidgets('thumb labels are the pair Helpful / Not Helpful', (tester) async {
    await tester.pumpWidget(_host(MessageActionBar(messageText: 'hi', setMessageNps: (int v, {String? reason}) {})));
    expect(find.byTooltip('Helpful'), findsOneWidget);
    expect(find.byTooltip('Not Helpful'), findsOneWidget);
  });

  testWidgets('composer round button looks disabled and is announced disabled when it cannot send', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(_host(const Center(
      child: ChatComposerRoundButton(icon: FaIcon(FontAwesomeIcons.arrowUp), label: 'Send message', onPressed: null),
    )));

    final node = tester.getSemantics(find.bySemanticsLabel('Send message'));
    expect(node.flagsCollection.isEnabled, Tristate.isFalse);
    final circle = tester.widget<AnimatedContainer>(find.byType(AnimatedContainer));
    expect((circle.decoration! as BoxDecoration).color, isNot(OmiColors.accent));
    expect(tester.getSize(find.byType(GestureDetector)).height, greaterThanOrEqualTo(44));
    handle.dispose();
  });

  group('chat apps drawer', () {
    late MessageProvider messages;
    late AppProvider apps;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      messages = MessageProvider()..chatApps = [_chatApp('a1', 'Notes'), _chatApp('a2', 'Coach')];
      apps = AppProvider()..selectedChatAppId = 'a2';
    });

    Future<void> pumpDrawer(WidgetTester tester, {required ValueChanged<App> onDisable, VoidCallback? onClear}) async {
      final key = GlobalKey<ScaffoldState>();
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<MessageProvider>.value(value: messages),
            ChangeNotifierProvider<AppProvider>.value(value: apps),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(
              key: key,
              endDrawer: ChatAppsDrawer(
                onSelectApp: (_) {},
                onEnableApps: () {},
                onDisableApp: onDisable,
                onClearChat: onClear ?? () {},
              ),
              body: const SizedBox(),
            ),
          ),
        ),
      );
      key.currentState!.openEndDrawer();
      await tester.pumpAndSettle();
    }

    testWidgets('Clear Chat sits below the app list', (tester) async {
      await pumpDrawer(tester, onDisable: (_) {});
      final clear = tester.getTopLeft(find.text('Clear Chat')).dy;
      expect(clear, greaterThan(tester.getTopLeft(find.text('Enable Apps')).dy));
      expect(clear, greaterThan(tester.getTopLeft(find.text('Notes')).dy));
    });

    testWidgets('each non-current app has one labelled Disable control', (tester) async {
      App? disabled;
      await pumpDrawer(tester, onDisable: (app) => disabled = app);

      expect(find.byTooltip('Disable Notes'), findsOneWidget);
      expect(find.byTooltip('Disable Coach'), findsNothing, reason: 'the app you are chatting with');
      await tester.tap(find.byTooltip('Disable Notes'));
      expect(disabled?.id, 'a1');
    });
  });
}
