import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memories_load_error.dart';

Widget _app({required bool showLoadError}) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: const [Locale('en')],
    home: Scaffold(
      body: MemoriesEmptyOrError(
        showLoadError: showLoadError,
        onRetry: () {},
        emptyState: const Center(key: Key('memories_empty_state'), child: Text('🧠 No memories yet')),
      ),
    ),
  );
}

void main() {
  testWidgets('a failed load renders retry, not the empty memories state', (tester) async {
    await tester.pumpWidget(_app(showLoadError: true));

    expect(find.byKey(const Key('memories_load_error')), findsOneWidget);
    expect(find.byKey(const Key('memories_load_retry')), findsOneWidget);
    expect(find.byKey(const Key('memories_empty_state')), findsNothing);
    expect(find.text("Couldn't load memories"), findsOneWidget);
    expect(find.text('🧠 No memories yet'), findsNothing);
  });

  testWidgets('a genuine empty account still shows the empty state', (tester) async {
    await tester.pumpWidget(_app(showLoadError: false));

    expect(find.byKey(const Key('memories_empty_state')), findsOneWidget);
    expect(find.byKey(const Key('memories_load_retry')), findsNothing);
    expect(find.text('🧠 No memories yet'), findsOneWidget);
  });
}
