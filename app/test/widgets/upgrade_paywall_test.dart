import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/settings/widgets/standalone_plans_sheet.dart';
import 'package:omi/pages/settings/widgets/upgrade_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';

// With the Superwall pilot off (every store build), each upgrade entry point asks the paywall
// experiment first: a variant arm gets its page, control gets the plans sheet, and the web
// variant's fallback (forceNative) always gets the sheet.

Future<void> _open(WidgetTester tester, {PaywallExperimentConfig? experiment, bool forceNative = false}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider(
      create: (_) => UsageProvider(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => openUpgradePaywall(
              context,
              source: 'usage_page',
              forceNative: forceNative,
              experiment: experiment,
            ),
            child: const Text('upgrade'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('upgrade'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  setUp(PaywallExperiment.resetForTesting);

  testWidgets('control opens the plans sheet', (tester) async {
    await _open(tester, experiment: PaywallExperimentConfig.control);
    expect(find.byType(StandalonePlansSheet), findsOneWidget);
    expect(find.byType(OutlinePaywallPage), findsNothing);
  });

  testWidgets('a variant arm opens its paywall instead of the sheet', (tester) async {
    await _open(tester, experiment: const PaywallExperimentConfig(variant: PaywallVariant.outline));
    expect(find.byType(OutlinePaywallPage), findsOneWidget);
    expect(find.byType(StandalonePlansSheet), findsNothing);
  });

  testWidgets('forceNative skips the experiment and opens the sheet', (tester) async {
    await _open(
      tester,
      experiment: const PaywallExperimentConfig(variant: PaywallVariant.outline),
      forceNative: true,
    );
    expect(find.byType(StandalonePlansSheet), findsOneWidget);
    expect(find.byType(OutlinePaywallPage), findsNothing);
  });
}
