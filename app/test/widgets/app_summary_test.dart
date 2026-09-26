import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/app_summary.dart';

Widget _app(Widget child, {double width = 360}) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: Center(child: SizedBox(width: width, child: child))),
    );

void main() {
  testWidgets('a long app name wraps instead of overflowing', (tester) async {
    await tester.pumpWidget(_app(
      const AppDetailHeader(name: 'RPG Translator: Speak Gamer, Think Human', author: 'Omi', official: true),
      width: 220,
    ));
    expect(tester.takeException(), isNull);
    expect(find.text('RPG Translator: Speak Gamer, Think Human'), findsOneWidget);
  });

  testWidgets('stats show ratings, users and the trigger in columns', (tester) async {
    var tapped = 0;
    await tester.pumpWidget(_app(AppDetailStats(
      ratingCount: 26,
      rating: '3.3',
      installs: 45600,
      trigger: 'Conversation Creation',
      onRatingTap: () => tapped++,
    )));
    expect(find.text('26+ RATINGS'), findsOneWidget);
    expect(find.text('3.3'), findsOneWidget);
    expect(find.text('out of 5'), findsOneWidget);
    expect(find.text('USERS'), findsOneWidget);
    expect(find.text('45.6K'), findsOneWidget);
    expect(find.text('TRIGGER'), findsOneWidget);
    expect(find.text('Conversation Creation'), findsOneWidget);

    await tester.tap(find.byKey(const Key('app_stat_ratings')));
    expect(tapped, 1);
  });

  testWidgets('a new app with no ratings, users or trigger draws no stats', (tester) async {
    await tester.pumpWidget(_app(const AppDetailStats(ratingCount: 0, rating: '0.0', installs: 0)));
    expect(find.byType(VerticalDivider), findsNothing);
    expect(find.text('USERS'), findsNothing);
  });
}
