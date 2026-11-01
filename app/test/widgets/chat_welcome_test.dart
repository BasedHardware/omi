import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/home_redesign.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/chat_starters.dart';

void main() {
  // These cover the redesigned Home (home-redesign test arm).
  setUp(() => HomeRedesign.setForTesting(true));
  tearDown(HomeRedesign.resetForTesting);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Widget host({required bool animate}) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: ChatGreeting(
              isConnected: true, name: 'Yinka', hour: 19, todayCount: 0, welcome: true, animateWelcome: animate),
        ),
      );

  testWidgets('the first time, Omi types its welcome in: dots, then the message', (tester) async {
    expect(ChatWelcome.pending, isTrue);
    expect(ChatWelcome.shown, isFalse);
    await tester.pumpWidget(host(animate: true));
    expect(find.byKey(const Key('chat_welcome_typing')), findsOneWidget);
    expect(find.text('What do you want to know?'), findsNothing);

    await tester.pump(const Duration(milliseconds: 1400));
    expect(find.byKey(const Key('chat_welcome_typing')), findsNothing);
    expect(find.byKey(const Key('chat_welcome_message')), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    expect(ChatWelcome.shown, isTrue, reason: 'typed in once');
    expect(ChatWelcome.pending, isTrue, reason: 'still shown until the first message is sent');
  });

  testWidgets('later visits show it settled; sending a message retires it', (tester) async {
    await tester.pumpWidget(host(animate: false));
    expect(find.byKey(const Key('chat_welcome_typing')), findsNothing);
    expect(find.textContaining("Hi, I'm Omi."), findsOneWidget);

    ChatWelcome.markDone();
    expect(ChatWelcome.pending, isFalse);
  });
}
