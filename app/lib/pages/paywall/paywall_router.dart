import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/pages/paywall/web_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Decides which paywall a surface opens. Every opener asks here first; when the reader is in a
/// non-control arm the variant page is shown and the opener does nothing else. Control readers
/// are exposed (they are the experiment's denominator) and the opener shows the `PlansSheet`
/// exactly as before. Paid readers (the sheet owns upgrades, switches and cancellation) and App
/// Review builds (subscription UI hidden) are not in the experiment at all.
abstract final class PaywallRouter {
  /// True when a variant paywall was shown and the opener must not open the `PlansSheet`.
  /// [record] replaces the exposure sink for tests.
  static Future<bool> openVariant(
    BuildContext context, {
    required String source,
    bool trackOpen = true,
    PaywallExperimentConfig? config,
    bool Function(String key, String variant)? record,
    void Function(Object? result)? onResult,
  }) async {
    final usage = context.read<UsageProvider>();
    if (!usage.showSubscriptionUI) return false;
    if (usage.subscription?.subscription.plan.isPaid == true) return false;
    final resolved = config ?? await PaywallExperiment.resolve();
    if (!context.mounted) return false;
    if (!context.read<UsageProvider>().showSubscriptionUI) return false;
    // The trial page promises a free trial; only a reader the backend says can still get one sees
    // it. Anyone else in that arm (a former subscriber, or a subscription not loaded yet) gets the
    // shipped sheet from the opener, exactly like control.
    final trialBlocked =
        resolved.variant == PaywallVariant.trial && context.read<UsageProvider>().subscription?.trialEligible != true;

    // The reader is about to see a paywall: the variant page below, or the sheet the opener shows
    // right after a false return. Either way they count for their arm.
    PaywallExperiment.recordExposure(resolved, record: record);
    const TypedEvents().emit(PaywallVariantShown(variant: variantWire(resolved.variant), source: sourceWire(source)));
    if (resolved.isControl || trialBlocked) return false;

    if (trackOpen) {
      final plan = usage.subscription?.subscription.plan.wireName ?? 'unknown';
      PlatformManager.instance.analytics.paywallOpened(source, currentPlan: plan);
    }
    final page = switch (resolved.variant) {
      PaywallVariant.outline => OutlinePaywallPage(source: source),
      PaywallVariant.web => WebPaywallPage(source: source, url: resolved.webUrl!),
      PaywallVariant.trial => TrialPaywallPage(source: source),
      PaywallVariant.control => null,
    };
    if (page == null) return false;
    final result = await routeToPage(context, page);
    onResult?.call(result);
    return true;
  }

  static PaywallVariantShownVariant variantWire(PaywallVariant variant) => switch (variant) {
        PaywallVariant.control => PaywallVariantShownVariant.control,
        PaywallVariant.outline => PaywallVariantShownVariant.outline,
        PaywallVariant.web => PaywallVariantShownVariant.web,
        PaywallVariant.trial => PaywallVariantShownVariant.trial,
      };

  static PaywallVariantShownSource sourceWire(String source) {
    for (final value in PaywallVariantShownSource.values) {
      if (value.wireName == source) return value;
    }
    return PaywallVariantShownSource.unknown;
  }
}
