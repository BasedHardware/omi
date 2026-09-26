import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/ui/ui.dart';

/// Motion N3: the Today live card grows into Live — its orb flies to the Live page's orb.
void main() {
  Widget app(Widget card) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Scaffold(
            body: Column(
              children: [
                card,
                TextButton(
                  onPressed: () => Navigator.of(context).push(
                    omiPageRoute<void>(
                      builder: (_) => const Scaffold(
                        body: Center(child: Hero(tag: kLiveOrbHeroTag, child: OmiOrb(size: 92, live: true))),
                      ),
                    ),
                  ),
                  child: const Text('open live'),
                ),
              ],
            ),
          ),
        ),
      );

  testWidgets('a wearable card carries the orb hero, and it flies into the Live orb', (tester) async {
    await tester.pumpWidget(app(const LiveCaptureCard(source: 'omi', status: 'Listening', paused: false)));
    final cardHero = find.byWidgetPredicate((w) => w is Hero && w.tag == kLiveOrbHeroTag);
    expect(cardHero, findsOneWidget);
    expect(tester.getSize(cardHero), const Size(44, 44));

    await tester.tap(find.text('open live'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 150));
    // Mid-flight the orb is between the card's size and the page's.
    final flying = tester.getSize(find.byType(OmiOrb).last);
    expect(flying.width, greaterThan(44));
    expect(flying.width, lessThan(92));

    await tester.pump(const Duration(seconds: 1));
    expect(tester.getSize(find.byType(OmiOrb).last), const Size(92, 92));
  });

  testWidgets('a phone card has no orb to fly', (tester) async {
    await tester.pumpWidget(app(const LiveCaptureCard(source: 'phone', status: 'Listening', paused: false)));
    expect(find.byWidgetPredicate((w) => w is Hero && w.tag == kLiveOrbHeroTag), findsNothing);
  });
}
