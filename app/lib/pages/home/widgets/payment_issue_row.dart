import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/widgets/monthly_switch_sheet.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Home's one row for a declined renewal: a red dot, what happened, and Update.
///
/// Shown only while the subscription response carries a payment issue (the plan's Stripe
/// subscription is past_due or unpaid with an open invoice) and subscription UI is allowed.
/// Update opens Stripe's billing portal, where the card is changed and the invoice paid; on
/// return the subscription is fetched again, so a paid invoice removes the row. A declined yearly
/// renewal also offers Switch to Monthly: the same plan at its monthly price, confirmed in a sheet.
/// On a build that sells through Google Play neither action shows: one plain line says to update the card
/// on omi.me, and nothing opens. Both actions re-check that gate when tapped.
class PaymentIssueRow extends StatefulWidget {
  const PaymentIssueRow({super.key, this.portalPage, this.applyMonthlySwitch});

  /// The page that shows the portal URL; tests swap in a plain page. Defaults to the Stripe web view.
  final Widget Function(String url, VoidCallback onLoaded)? portalPage;

  /// The monthly switch's POST; tests swap in a fake. Defaults to the payment API.
  final MonthlySwitchApplier? applyMonthlySwitch;

  @override
  State<PaymentIssueRow> createState() => _PaymentIssueRowState();
}

class _PaymentIssueRowState extends State<PaymentIssueRow> {
  PaymentIssue? _shownIssue;

  @override
  Widget build(BuildContext context) {
    // The Play gate is watched with the issue: a refresh that only adds Play setup must hide the Stripe actions.
    final (issue, playBuild) = context.select<UsageProvider?, (PaymentIssue?, bool)>(
      (usage) => usage?.showSubscriptionUI == true
          ? (usage?.subscription?.paymentIssue, usage?.buysThroughPlay == true)
          : (null, false),
    );
    if (issue == null) {
      _shownIssue = null;
      return const SizedBox.shrink();
    }
    // A build that sells through Google Play opens no Stripe page and offers no charged switch.
    final offer = playBuild ? null : issue.monthlySwitch;
    if (_shownIssue != issue) {
      _shownIssue = issue;
      final monthlyShown = offer != null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _shownIssue == issue) {
          const TypedEvents().emit(const SubscriptionPaymentIssueShown());
          if (monthlyShown) const TypedEvents().emit(const SubscriptionPaymentIssueMonthlyShown());
        }
      });
    }
    final l10n = context.l10n;
    final plans = context.read<UsageProvider>().subscription?.availablePlans ?? const <SubscriptionPlan>[];
    final planName = planDisplayName(issue.plan, plans, l10n);
    final headlineSize = OmiType.headline.fontSize!;
    final largeText = MediaQuery.textScalerOf(context).scale(headlineSize) > headlineSize * 1.3;
    // Two actions never fit beside the text; one does until the text is large.
    final stackAction = offer != null || largeText;
    final message = Row(
      children: [
        ExcludeSemantics(
          child: SizedBox.square(
            dimension: 10,
            child: DecoratedBox(decoration: BoxDecoration(color: OmiColors.danger, shape: BoxShape.circle)),
          ),
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(l10n.paymentDeclinedTitle, style: OmiType.headline),
              Text(
                playBuild
                    ? l10n.playStripeUpdateCardToGetPlanBack(planName)
                    : offer == null
                        ? l10n.paymentDeclinedMessage(planName)
                        : l10n.paymentDeclinedMonthlyMessage(
                            planName, formatBillingPrice(offer.amount, offer.currency)),
                key: playBuild ? const ValueKey('payment_issue_update_on_web') : null,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ],
          ),
        ),
      ],
    );
    final update = OmiButton(
      key: const ValueKey('payment_issue_update'),
      label: l10n.update,
      size: OmiButtonSize.compact,
      pill: true,
      onPressed: () => openPaymentIssuePortal(context, portalPage: widget.portalPage),
    );
    final monthly = offer == null
        ? null
        : OmiButton(
            key: const ValueKey('payment_issue_monthly'),
            label: l10n.monthlySwitchTitle,
            variant: OmiButtonVariant.secondary,
            size: OmiButtonSize.compact,
            pill: true,
            // Wraps instead of truncating at the largest text sizes.
            maxLines: 2,
            // Synchronous: the sheet in front of the row is the progress, not a spinner on this button.
            onPressed: () => unawaited(
              showMonthlySwitchSheet(context, issue: issue, apply: widget.applyMonthlySwitch).catchError(
                (Object error, StackTrace stack) {
                  OmiButton.reportOnPressedError(error, stack, label: l10n.monthlySwitchTitle);
                  return false;
                },
              ),
            ),
          );
    final actions = monthly == null
        ? update
        : Wrap(
            alignment: WrapAlignment.end,
            spacing: OmiSpacing.sm,
            runSpacing: OmiSpacing.sm,
            // At large text Update, the primary, comes first so it never lands under Home's pinned Ask bar.
            children: largeText ? [update, monthly] : [monthly, update],
          );
    final row = DecoratedBox(
      key: const ValueKey('payment_issue_row'),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.sm, OmiSpacing.sm),
        child: playBuild
            ? message
            : stackAction
                ? Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    // With two actions only the text is one node; each button keeps its own.
                    children: [
                      offer == null ? message : MergeSemantics(child: message),
                      const SizedBox(height: OmiSpacing.sm),
                      actions,
                    ],
                  )
                : Row(children: [Expanded(child: message), const SizedBox(width: OmiSpacing.sm), update]),
      ),
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
      child: offer == null ? MergeSemantics(child: row) : row,
    );
  }
}

/// Opens Stripe's billing portal for the signed-in user, then refreshes the subscription.
///
/// The app never charges anything here: the card and the payment live on the Stripe-hosted page.
Future<void> openPaymentIssuePortal(
  BuildContext context, {
  Widget Function(String url, VoidCallback onLoaded)? portalPage,
}) async {
  final usage = context.read<UsageProvider>();
  // A build that sells through Google Play never opens the Stripe portal, even from a row drawn before it knew.
  if (usage.buysThroughPlay) return;
  const TypedEvents().emit(const SubscriptionPaymentIssueUpdateTapped());
  final navigator = Navigator.of(context);
  final l10n = context.l10n;
  final url = (await usage.openCustomerPortal())?['url'];
  if (usage.buysThroughPlay) return;
  if (url == null || url.isEmpty) {
    if (context.mounted) OmiFeedback.error(context, l10n.couldNotOpenPaymentSettings);
    return;
  }
  if (!context.mounted) return;
  void onLoaded() => const TypedEvents().emit(const SubscriptionPaymentIssuePortalOpened());
  await navigator.push(
    omiPageRoute(
      builder: (_) =>
          portalPage?.call(url, onLoaded) ??
          PaymentWebViewPage(checkoutUrl: url, title: l10n.managePaymentMethod, onLoaded: onLoaded),
    ),
  );
  await usage.fetchSubscription(fresh: true);
}
