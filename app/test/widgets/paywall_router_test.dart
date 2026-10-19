import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';

// The router exposes every eligible reader, control included (the experiment's denominator), and
// never a reader who is not in the experiment.

Future<BuildContext> _context(WidgetTester tester, UsageProvider usage) async {
  late BuildContext captured;
  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) {
            captured = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    ),
  );
  return captured;
}

UserSubscriptionResponse _response(
        {required PlanType plan, bool showSubscriptionUi = true, bool trialEligible = false}) =>
    UserSubscriptionResponse(
      trialEligible: trialEligible,
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: showSubscriptionUi,
    );

void main() {
  testWidgets('a free reader in control is exposed as control and the opener keeps the sheet', (tester) async {
    final context = await _context(tester, UsageProvider());
    final exposures = <String>[];
    final shown = await PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: PaywallExperimentConfig.control,
      record: (key, variant) {
        exposures.add('$key=$variant');
        return true;
      },
    );
    expect(shown, isFalse, reason: 'control means the opener shows the PlansSheet');
    expect(exposures, ['paywall-variant=control']);
  });

  testWidgets('a reader whose subscription UI is hidden is never exposed', (tester) async {
    final usage = UsageProvider();
    usage.debugSetSubscription(_response(plan: PlanType.basic, showSubscriptionUi: false));
    final context = await _context(tester, usage);
    final exposures = <String>[];
    final shown = await PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: const PaywallExperimentConfig(variant: PaywallVariant.outline),
      record: (key, variant) {
        exposures.add('$key=$variant');
        return true;
      },
    );
    expect(shown, isFalse);
    expect(exposures, isEmpty);
  });

  testWidgets('a paid reader is never exposed and keeps the sheet', (tester) async {
    final usage = UsageProvider();
    usage.debugSetSubscription(_response(plan: PlanType.unlimitedV2));
    final context = await _context(tester, usage);
    final exposures = <String>[];
    final shown = await PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: const PaywallExperimentConfig(variant: PaywallVariant.outline),
      record: (key, variant) {
        exposures.add('$key=$variant');
        return true;
      },
    );
    expect(shown, isFalse);
    expect(exposures, isEmpty);
  });

  testWidgets('trial arm: a former subscriber on the free plan is exposed as trial but keeps the sheet',
      (tester) async {
    final usage = UsageProvider();
    usage.debugSetSubscription(_response(plan: PlanType.basic, trialEligible: false));
    final context = await _context(tester, usage);
    final exposures = <String>[];
    final shown = await PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: const PaywallExperimentConfig(variant: PaywallVariant.trial, onboardingPaywall: true),
      record: (key, variant) {
        exposures.add('$key=$variant');
        return true;
      },
    );
    expect(shown, isFalse, reason: 'no trial page for a reader the backend will not give a trial');
    expect(find.byType(TrialPaywallPage), findsNothing);
    expect(exposures, ['paywall-variant=trial']);
  });

  testWidgets('trial arm: a first-time subscriber sees the trial page', (tester) async {
    final usage = UsageProvider();
    usage.debugSetSubscription(_response(plan: PlanType.basic, trialEligible: true));
    final context = await _context(tester, usage);
    final pending = PaywallRouter.openVariant(
      context,
      source: 'usage_page',
      config: const PaywallExperimentConfig(variant: PaywallVariant.trial, onboardingPaywall: true),
      record: (key, variant) => true,
    );
    await tester.pumpAndSettle();
    expect(find.byType(TrialPaywallPage), findsOneWidget);
    Navigator.of(tester.element(find.byType(TrialPaywallPage))).pop(false);
    await tester.pumpAndSettle();
    expect(await pending, isTrue);
  });
}
