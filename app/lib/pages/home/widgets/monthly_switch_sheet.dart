import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/payment.dart' as payment_api;
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/pages/settings/widgets/yearly_switch.dart' show PlanSwitchFactRow;
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A declined yearly renewal moves to the same plan's monthly price (backend `utils/monthly_switch.py`).
/// Opened from the declined-payment Home row. The sheet shows the plan, what is charged today and that
/// the unpaid yearly charge is replaced; the server charges only that amount. A declined card changes
/// nothing: the reader keeps the row and can update the card instead.

/// The switch's POST: the response map, `error`/`status_code` on a refusal, or null when unknown.
typedef MonthlySwitchApplier = Future<Map<String, dynamic>?> Function({
  required String priceId,
  required int expectedAmount,
});

/// Opens the confirm sheet; resolves true once the reader is on monthly.
Future<bool> showMonthlySwitchSheet(BuildContext context,
    {required PaymentIssue issue, MonthlySwitchApplier? apply}) async {
  const TypedEvents().emit(const SubscriptionPaymentIssueMonthlyTapped());
  var switched = false;
  await showOmiSheet<void>(
    context: context,
    title: context.l10n.monthlySwitchTitle,
    builder: (_) => MonthlySwitchSheet(issue: issue, apply: apply, onSwitched: () => switched = true),
  );
  return switched;
}

class MonthlySwitchSheet extends StatefulWidget {
  const MonthlySwitchSheet({super.key, required this.issue, this.apply, this.onSwitched});

  /// Carries a non-null [PaymentIssue.monthlySwitch].
  final PaymentIssue issue;
  final MonthlySwitchApplier? apply;
  final VoidCallback? onSwitched;

  @override
  State<MonthlySwitchSheet> createState() => _MonthlySwitchSheetState();
}

class _MonthlySwitchSheetState extends State<MonthlySwitchSheet> {
  bool _switching = false;
  bool _done = false;
  bool _refused = false;
  String? _error;

  Future<void> _switch() async {
    final offer = widget.issue.monthlySwitch;
    if (offer == null || _switching) return;
    OmiHaptics.medium();
    setState(() {
      _switching = true;
      _error = null;
    });
    Map<String, dynamic>? result;
    try {
      result = await (widget.apply ?? payment_api.switchPaymentIssueToMonthly)(
        priceId: offer.priceId,
        expectedAmount: offer.amount,
      );
    } catch (_) {
      result = null;
    }
    if (!mounted) return;
    final usage = context.read<UsageProvider?>();
    var switched = result != null && result['error'] != true;
    if (result == null && usage != null) {
      // No answer (timeout, server error): read the plan again before saying anything about it.
      await usage.fetchSubscription();
      if (!mounted) return;
      final sub = usage.subscription;
      switched = sub != null && sub.paymentIssue == null && sub.subscription.plan.isPaid;
    }
    final l10n = context.l10n;
    if (switched) {
      const TypedEvents().emit(const SubscriptionPaymentIssueMonthlySwitched());
      widget.onSwitched?.call();
      if (usage != null && result != null) unawaited(usage.fetchSubscription());
      setState(() {
        _switching = false;
        _done = true;
      });
      return;
    }
    final status = result?['status_code'];
    final declined = status == 402;
    final refused = status == 409 || status == 400;
    const TypedEvents().emit(SubscriptionPaymentIssueMonthlyFailed(
      reason: declined
          ? SubscriptionPaymentIssueMonthlyFailedReason.declined
          : refused
              ? SubscriptionPaymentIssueMonthlyFailedReason.refused
              : SubscriptionPaymentIssueMonthlyFailedReason.error,
    ));
    setState(() {
      _switching = false;
      _refused = refused;
      _error = declined
          ? l10n.monthlySwitchDeclined
          : refused
              ? l10n.monthlySwitchUnavailable
              : l10n.somethingWentWrong;
    });
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_switching,
      // Scrolls at large text sizes so Confirm and Cancel always stay reachable.
      child: SingleChildScrollView(
        child: AnimatedSize(
          duration: OmiMotion.of(context).standard,
          alignment: Alignment.topCenter,
          child: Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.md),
            child: _content(context),
          ),
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    final l10n = context.l10n;
    final offer = widget.issue.monthlySwitch!;
    final price = formatBillingPrice(offer.amount, offer.currency);
    if (_done) {
      return Column(
        key: const Key('monthly_switch_done'),
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: OmiSpacing.lg),
          Icon(Icons.check_circle, size: 44, color: OmiColors.success),
          const SizedBox(height: OmiSpacing.sm),
          Text(l10n.monthlySwitchDoneTitle, style: OmiType.title3, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            l10n.monthlySwitchDoneBody(price),
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const Key('monthly_switch_done_button'),
            label: l10n.done,
            expand: true,
            onPressed: () => Navigator.of(context).maybePop(),
          ),
        ],
      );
    }
    final plans = context.read<UsageProvider?>()?.subscription?.availablePlans ?? const <SubscriptionPlan>[];
    final plan = planDisplayName(widget.issue.plan, plans, l10n);
    return Column(
      key: const Key('monthly_switch_preview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        PlanSwitchFactRow(label: l10n.yearlySwitchPlanLabel, value: l10n.monthlySwitchPlanValue(plan, price)),
        Divider(height: 1, thickness: 1, color: OmiColors.border),
        PlanSwitchFactRow(
          label: l10n.yearlySwitchDueToday,
          value: price,
          valueKey: const Key('monthly_switch_due_today'),
          emphasized: true,
        ),
        Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.xxs),
          child: Text(
            l10n.monthlySwitchNote(formatBillingPrice(offer.yearlyAmount, offer.currency)),
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.md),
            child: Text(
              _error!,
              key: const Key('monthly_switch_error'),
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.danger),
            ),
          ),
        const SizedBox(height: OmiSpacing.xl),
        if (!_refused) ...[
          OmiButton(
            key: const Key('monthly_switch_confirm'),
            label: l10n.monthlySwitchTitle,
            expand: true,
            isLoading: _switching,
            onPressed: _switching ? null : _switch,
          ),
          const SizedBox(height: OmiSpacing.xs),
        ],
        OmiButton.tertiary(
          key: const Key('monthly_switch_cancel'),
          label: l10n.cancel,
          expand: true,
          onPressed: _switching ? null : () => Navigator.of(context).maybePop(),
        ),
      ],
    );
  }
}
