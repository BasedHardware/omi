import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/omi_theme.dart';

/// Pumps [home] inside the production theme with English localizations.
Future<void> pumpUi(WidgetTester tester, Widget home, {TargetPlatform? platform}) async {
  final theme = buildOmiTheme();
  await tester.pumpWidget(
    MaterialApp(
      theme: platform == null ? theme : theme.copyWith(platform: platform),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: home,
    ),
  );
}

/// A root page with a button that pushes [page], so back/close behaviour can be observed.
class PushHost extends StatelessWidget {
  const PushHost({super.key, required this.page});

  final Widget page;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page)),
          child: const Text('open'),
        ),
      ),
    );
  }
}
