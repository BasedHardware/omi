import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Home's one row for a declined renewal: a red dot, what happened, and Update.
///
/// Shown only while the subscription response carries a payment issue (the plan's Stripe
/// subscription is past_due or unpaid with an open invoice) and subscription UI is allowed.
/// Update opens Stripe's billing portal, where the card is changed and the invoice paid; on
/// return the subscription is fetched again, so a paid invoice removes the row.
class PaymentIssueRow extends StatelessWidget {
  const PaymentIssueRow({super.key, this.portalPage});

  /// The page that shows the portal URL; tests swap in a plain page. Defaults to the Stripe web view.
  final Widget Function(String url)? portalPage;

  @override
  Widget build(BuildContext context) {
    final issue = context.select<UsageProvider?, PaymentIssue?>(
      (usage) => usage?.showSubscriptionUI == true ? usage?.subscription?.paymentIssue : null,
    );
    if (issue == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    final plans = context.read<UsageProvider>().subscription?.availablePlans ?? const <SubscriptionPlan>[];
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
      child: MergeSemantics(
        child: DecoratedBox(
          key: const ValueKey('payment_issue_row'),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.sm, OmiSpacing.sm),
            child: Row(
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
                        l10n.paymentDeclinedMessage(planDisplayName(issue.plan, plans, l10n)),
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                OmiButton(
                  key: const ValueKey('payment_issue_update'),
                  label: l10n.update,
                  size: OmiButtonSize.compact,
                  pill: true,
                  onPressed: () => openPaymentIssuePortal(context, portalPage: portalPage),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Opens Stripe's billing portal for the signed-in user, then refreshes the subscription.
///
/// The app never charges anything here: the card and the payment live on the Stripe-hosted page.
Future<void> openPaymentIssuePortal(BuildContext context, {Widget Function(String url)? portalPage}) async {
  final navigator = Navigator.of(context);
  final usage = context.read<UsageProvider>();
  final l10n = context.l10n;
  final url = (await usage.openCustomerPortal())?['url'];
  if (url == null || url.isEmpty) {
    if (context.mounted) OmiFeedback.error(context, l10n.couldNotOpenPaymentSettings);
    return;
  }
  await navigator.push(
    omiPageRoute(
      builder: (_) => portalPage?.call(url) ?? PaymentWebViewPage(checkoutUrl: url, title: l10n.managePaymentMethod),
    ),
  );
  await usage.fetchSubscription();
}
