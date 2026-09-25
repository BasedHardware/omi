import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';

Finder faIcon(FaIconData icon) => find.byWidgetPredicate((w) => w is FaIcon && w.icon?.codePoint == icon.codePoint);

bool thumbsUpLit(WidgetTester tester) => tester.widget<FaIcon>(faIcon(FontAwesomeIcons.thumbsUp)).color == Colors.white;

bool thumbsDownLit(WidgetTester tester) =>
    tester.widget<FaIcon>(faIcon(FontAwesomeIcons.thumbsDown)).color == Colors.white;

void main() {
  Future<void> pumpBar(WidgetTester tester, {int? currentNps, required bool saves}) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: MessageActionBar(
            messageText: 'hello',
            currentNps: currentNps,
            setMessageNps: (int value, {String? reason}) async => saves,
          ),
        ),
      ),
    );
  }

  testWidgets('thumbs up that fails to save does not stay lit', (tester) async {
    await pumpBar(tester, saves: false);

    await tester.tap(faIcon(FontAwesomeIcons.thumbsUp));
    await tester.pumpAndSettle();

    expect(thumbsUpLit(tester), isFalse);
  });

  testWidgets('clearing a rating that fails to save keeps it lit', (tester) async {
    await pumpBar(tester, currentNps: 1, saves: false);

    await tester.tap(faIcon(FontAwesomeIcons.thumbsUp));
    await tester.pumpAndSettle();

    expect(thumbsUpLit(tester), isTrue);
  });

  testWidgets('thumbs up that saves stays lit', (tester) async {
    await pumpBar(tester, saves: true);

    await tester.tap(faIcon(FontAwesomeIcons.thumbsUp));
    await tester.pumpAndSettle();

    expect(thumbsUpLit(tester), isTrue);
  });

  testWidgets('thumbs down with a reason that fails to save does not stay lit or thank the user', (tester) async {
    await pumpBar(tester, saves: false);

    await tester.tap(faIcon(FontAwesomeIcons.thumbsDown));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Too verbose'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(thumbsDownLit(tester), isFalse);
    expect(find.text('Thanks for your feedback!'), findsNothing);
  });
}
