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
    final issue = context.select<UsageProvider?, PaymentIssue?>(
      (usage) => usage?.showSubscriptionUI == true ? usage?.subscription?.paymentIssue : null,
    );
    if (issue == null) {
      _shownIssue = null;
      return const SizedBox.shrink();
    }
    if (_shownIssue != issue) {
      _shownIssue = issue;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _shownIssue == issue) {
          const TypedEvents().emit(const SubscriptionPaymentIssueShown());
          if (issue.monthlySwitch != null) const TypedEvents().emit(const SubscriptionPaymentIssueMonthlyShown());
        }
      });
    }
    final l10n = context.l10n;
    final plans = context.read<UsageProvider>().subscription?.availablePlans ?? const <SubscriptionPlan>[];
    final offer = issue.monthlySwitch;
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
                offer == null
                    ? l10n.paymentDeclinedMessage(planName)
                    : l10n.paymentDeclinedMonthlyMessage(planName, formatBillingPrice(offer.amount, offer.currency)),
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
        child: stackAction
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
  const TypedEvents().emit(const SubscriptionPaymentIssueUpdateTapped());
  final navigator = Navigator.of(context);
  final usage = context.read<UsageProvider>();
  final l10n = context.l10n;
  final url = (await usage.openCustomerPortal())?['url'];
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
  await usage.fetchSubscription();
}
