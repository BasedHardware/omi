import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';

/// A dark MaterialApp with the app's localizations, whose home is a button that runs [onPressed]
/// with a context below the Navigator and a Scaffold. Tap it with [tapTrigger].
Widget feedbackHarness(
  void Function(BuildContext context) onPressed, {
  TargetPlatform platform = TargetPlatform.android,
  GlobalKey<NavigatorState>? navigatorKey,
}) {
  return MaterialApp(
    navigatorKey: navigatorKey,
    theme: ThemeData(useMaterial3: false, brightness: Brightness.dark, platform: platform),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: OutlinedButton(onPressed: () => onPressed(context), child: const Text('trigger')),
        ),
      ),
    ),
  );
}

Future<void> tapTrigger(WidgetTester tester) async {
  await tester.tap(find.text('trigger'));
  await tester.pumpAndSettle();
}
