import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/pages/settings/widgets/standalone_plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Shows the upgrade offer in place and logs `Paywall Opened` with [source] (a `PaywallOpenedSource`
/// wire name) once. [trackOpen] is false when the opener already logged it.
///
/// The paywall experiment ([PaywallRouter]) picks the reader's arm; control, paid readers and any
/// failure get the existing plans sheet over the current screen. [forceNative] skips the router and
/// opens the sheet itself: the web variant's fallback, so a dead page never loops back into itself.
Future<void> openUpgradePaywall(
  BuildContext context, {
  required String source,
  bool trackOpen = true,
  bool forceNative = false,
  @visibleForTesting PaywallExperimentConfig? experiment,
}) async {
  void logOpen() {
    if (!trackOpen) return;
    trackOpen = false;
    final plan = context.read<UsageProvider>().subscription?.subscription.plan.wireName ?? 'unknown';
    PlatformManager.instance.analytics.paywallOpened(source, currentPlan: plan);
  }

  if (!forceNative) {
    // The router logs `Paywall Opened` itself when it shows a variant.
    if (await PaywallRouter.openVariant(context, source: source, trackOpen: trackOpen, config: experiment)) return;
    if (!context.mounted) return;
  }
  logOpen();
  await showStandalonePlansSheet(context, analyticsSource: source);
}
