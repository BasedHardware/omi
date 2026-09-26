/// Copy and share on a chat message must never rate the message.
///
/// Both actions used to call `setMessageNps(1)` as "implicit positive
/// feedback". The provider writes the rating back onto the message, so the
/// thumbs-up icon lit up as soon as share or copy ran — tapping share visibly
/// pressed thumbs-up. Only the explicit thumbs buttons may rate.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';

Finder faIcon(FaIconData icon) => find.byWidgetPredicate((w) => w is FaIcon && w.icon?.codePoint == icon.codePoint);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<int> ratings;

  setUp(() {
    ratings = [];
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    // Clipboard and share_plus both go over platform channels that have no
    // host in a widget test; answer them so the handlers run to completion.
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
    messenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (call) async => 'dev.fluttercommunity.plus/share/success',
    );
  });

  Future<void> pumpBar(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: MessageActionBar(
            messageText: 'hello',
            setMessageNps: (int value, {String? reason}) => ratings.add(value),
          ),
        ),
      ),
    );
  }

  testWidgets('tapping share does not rate the message', (tester) async {
    await pumpBar(tester);

    await tester.tap(faIcon(FontAwesomeIcons.share));
    await tester.pumpAndSettle();

    expect(ratings, isEmpty);
  });

  testWidgets('tapping copy does not rate the message', (tester) async {
    await pumpBar(tester);

    await tester.tap(faIcon(FontAwesomeIcons.copy));
    await tester.pumpAndSettle();

    expect(ratings, isEmpty);
  });

  testWidgets('thumbs up still rates the message explicitly', (tester) async {
    await pumpBar(tester);

    await tester.tap(faIcon(FontAwesomeIcons.thumbsUp));
    await tester.pumpAndSettle();

    expect(ratings, [1]);
  });
}
