import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/paywall_reask.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

bool _checking = false;

bool _isFree(UsageProvider usage) =>
    usage.showSubscriptionUI && usage.subscription?.subscription.plan == PlanType.basic;

/// On app open (launch or back from the background): when [PaywallReask] says a re-ask is due for
/// this free reader and their arm shows it, queue the paywall. [PromptQueue] holds it while the
/// reader records, is on a call or another prompt is up, and drops it if they subscribed meanwhile.
Future<void> queuePaywallReask(BuildContext context) async {
  if (_checking) return;
  _checking = true;
  try {
    final usage = context.read<UsageProvider>();
    if (usage.subscription == null) await usage.fetchSubscription();
    if (!context.mounted || !_isFree(usage)) return;
    if (!await PaywallReask.checkDue() || !context.mounted) return;
    PromptQueue.instance.enqueue(
      PaywallReask.promptId,
      PromptPriority.low,
      canShowNow: () => context.mounted && _isFree(context.read<UsageProvider>()),
      show: _openPaywall,
    );
  } finally {
    _checking = false;
  }
}

/// The paywall the reader would get anywhere else: their `paywall-variant` arm, or for control the
/// plans sheet over the Usage page (the router already exposed them, so the page skips it).
Future<void> _openPaywall(BuildContext context) async {
  if (await PaywallRouter.openVariant(context, source: _source)) return;
  if (!context.mounted) return;
  final plan = context.read<UsageProvider>().subscription?.subscription.plan.wireName ?? 'unknown';
  PlatformManager.instance.analytics.paywallOpened(_source, currentPlan: plan);
  await routeToPage(context, const UsagePage(showUpgradeDialog: true, paywallSource: _source, forceNativePaywall: true));
}

const _source = 'app_open_reask';
