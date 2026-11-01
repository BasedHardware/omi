import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_pacing.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';

/// A moment a free Omi owner has just felt what the paid plan keeps.
enum PaywallMoment {
  /// Back from reading the summary of their own conversation.
  ahaFirstSummary('aha_first_summary', Duration(milliseconds: 400)),

  /// The free allowance locked a conversation they can see in their list.
  freeCap('free_cap', Duration(milliseconds: 1200));

  const PaywallMoment(this.source, this.beat);

  /// The paywall `source` analytics see.
  final String source;

  /// How long the screen settles before the offer slides up.
  final Duration beat;
}

/// Offers the paywall at a [PaywallMoment]: once per moment per account, never within
/// [PaywallPacing.window] of any other paywall, only to a free reader who owns an Omi, and never
/// with the subscription UI hidden. The first-summary offer is a trial offer, so only a
/// trial-eligible reader gets it; at the cap anyone else gets the plans sheet. The live
/// `paywall-variant` arm still owns the design: the offer opens through [PaywallRouter], and the
/// plans sheet is what the router's openers fall back to.
abstract final class ValueMomentPaywall {
  /// How long a summary stays on screen before leaving it counts as having read it.
  static const summaryDwell = Duration(seconds: 3);

  /// Queues the offer for [moment] about [conversation]. Returns true when it was queued. The
  /// moment is spent only when an offer actually opens, so a paced or not-yet-eligible reader gets
  /// it at the next such moment. With [usage], a reader known not to qualify queues nothing.
  /// [queue], [open] and [reviewRequested] replace the app queue, the paywall and the store-review
  /// latch in tests.
  static bool offer(
    PaywallMoment moment, {
    required ServerConversation conversation,
    UsageProvider? usage,
    PromptQueue? queue,
    Future<void> Function(BuildContext context, String source)? open,
    bool Function()? reviewRequested,
  }) {
    if (_spent(moment) || PaywallPacing.shownRecently() || !ownsOmi(conversation)) return false;
    if (moment == PaywallMoment.ahaFirstSummary && !_summarized(conversation)) return false;
    if (usage != null && !mayOffer(usage, moment)) return false;
    return (queue ?? PromptQueue.instance).enqueue(
      'value-moment-${moment.source}',
      PromptPriority.low,
      show: (context) => _show(
        context,
        moment,
        open ?? _open,
        reviewRequested ?? () => AppReviewService().requestedThisSession,
      ),
    );
  }

  /// Paired an Omi on this phone, or [conversation] was captured by one.
  static bool ownsOmi(ServerConversation conversation) {
    final device = SharedPreferencesUtil().btDevice;
    if (device.id.isNotEmpty && device.type.analyticsVendor == 'omi') return true;
    return switch (conversation.source) {
      ConversationSource.omi ||
      ConversationSource.friend ||
      ConversationSource.openglass ||
      ConversationSource.sdcard =>
        true,
      _ => false,
    };
  }

  static bool _summarized(ServerConversation conversation) =>
      conversation.status == ConversationStatus.completed &&
      !conversation.isLocked &&
      !conversation.discarded &&
      !conversation.deleted;

  static String _spentKey(PaywallMoment moment) => 'paywallMomentSpent:${moment.source}:${SharedPreferencesUtil().uid}';

  static bool _spent(PaywallMoment moment) => SharedPreferencesUtil().getBool(_spentKey(moment));

  static Future<void> _show(
    BuildContext context,
    PaywallMoment moment,
    Future<void> Function(BuildContext context, String source) open,
    bool Function() reviewRequested,
  ) async {
    await Future<void>.delayed(moment.beat);
    if (!context.mounted) return;
    // Another paywall may have opened while this one waited in the queue. A store-review sheet
    // asked for this session (it fires while a summary is read) is never stacked with a paywall.
    if (_spent(moment) || PaywallPacing.shownRecently() || reviewRequested()) return;
    final usage = context.read<UsageProvider>();
    if (usage.subscription == null) {
      await usage.fetchSubscription().timeout(const Duration(seconds: 6), onTimeout: () {});
      // A tapped Upgrade (e.g. "Processing paused") may have opened the plans sheet meanwhile.
      if (!context.mounted || PaywallPacing.shownRecently()) return;
    }
    if (!eligible(usage, moment)) return;
    await SharedPreferencesUtil().saveBool(_spentKey(moment), true);
    if (!context.mounted) return;
    await open(context, moment.source);
  }

  /// The arm's paywall, else the plans sheet (control, or a reader the trial page can't serve).
  static Future<void> _open(BuildContext context, String source) async {
    if (await PaywallRouter.openVariant(context, source: source)) return;
    if (!context.mounted) return;
    await showPlansSheetPrompt(context, source: source);
  }

  /// False only for a reader known not to qualify; an unloaded subscription is checked when the
  /// offer opens.
  static bool mayOffer(UsageProvider usage, PaywallMoment moment) =>
      usage.subscription == null || eligible(usage, moment);

  /// A free reader with the subscription UI on; for the first-summary offer, one who can still
  /// start a trial.
  @visibleForTesting
  static bool eligible(UsageProvider usage, PaywallMoment moment) {
    final subscription = usage.subscription;
    if (!usage.showSubscriptionUI || subscription == null) return false;
    if (subscription.subscription.plan != PlanType.basic) return false;
    return moment == PaywallMoment.freeCap || subscription.trialEligible;
  }
}
