import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/payment.dart' as payment_api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Monthly to yearly on the same plan, at the plan's yearly price (backend `utils/yearly_switch.py`).
/// Offered in Plans & Billing and, past the first paid month, as one quiet Home row. The confirm
/// sheet shows Stripe's preview: what is charged today, the plan and the renewal date.

enum YearlySwitchSurface { home, plans }

typedef YearlySwitchLoader = Future<wire.GeneratedYearlySwitchResponse?> Function({bool preview});

/// The plan-change endpoint's result map (`error`/`status_code` on a refusal), or null.
typedef YearlySwitchApplier = Future<Map<String, dynamic>?> Function({
  required String priceId,
  required int prorationDate,
  required int expectedAmountDue,
});

Future<Map<String, dynamic>?> _applyYearlySwitch({
  required String priceId,
  required int prorationDate,
  required int expectedAmountDue,
}) =>
    payment_api.upgradeSubscription(
      priceId: priceId,
      switchNow: true,
      prorationDate: prorationDate,
      expectedAmountDue: expectedAmountDue,
    );

bool _usablePreview(wire.GeneratedYearlySwitchResponse? offer) =>
    offer != null &&
    offer.eligible &&
    offer.priceId != null &&
    offer.amountDueToday != null &&
    offer.yearlyAmount != null &&
    offer.renewsAt != null &&
    offer.prorationDate != null;

/// A paid, renewing Stripe subscription the offer could apply to; null hides every entry point
/// (also when no [UsageProvider] is in scope).
String? yearlySwitchCandidate(UsageProvider? provider) {
  final sub = provider?.subscription?.subscription;
  if (provider == null || !provider.showSubscriptionUI || sub == null || !sub.plan.isPaid) return null;
  if (sub.status != SubscriptionStatus.active || sub.cancelAtPeriodEnd) return null;
  final id = sub.stripeSubscriptionId;
  return id == null || id.isEmpty ? null : id;
}

/// [minor] units of [currency], exact and unambiguous like every purchase surface ("US$89.97").
String yearlySwitchMoney(int minor, String? currency) => formatBillingPrice(minor, currency ?? 'usd');

void _emitShown(YearlySwitchSurface surface) => const TypedEvents()
    .emit(SubscriptionYearlySwitchShown(surface: SubscriptionYearlySwitchShownSurface.values.byName(surface.name)));

void _emitOpened(YearlySwitchSurface surface) => const TypedEvents()
    .emit(SubscriptionYearlySwitchOpened(surface: SubscriptionYearlySwitchOpenedSurface.values.byName(surface.name)));

void _emitDismissed(YearlySwitchSurface surface) => const TypedEvents().emit(
    SubscriptionYearlySwitchDismissed(surface: SubscriptionYearlySwitchDismissedSurface.values.byName(surface.name)));

void _emitFailed(YearlySwitchSurface surface, SubscriptionYearlySwitchFailedReason reason) =>
    const TypedEvents().emit(SubscriptionYearlySwitchFailed(
        surface: SubscriptionYearlySwitchFailedSurface.values.byName(surface.name), reason: reason));

/// Opens the confirm sheet; resolves true once the reader is on yearly.
Future<bool> showYearlySwitchSheet(
  BuildContext context, {
  required YearlySwitchSurface surface,
  YearlySwitchLoader? load,
  YearlySwitchApplier? apply,
}) async {
  _emitOpened(surface);
  var switched = false;
  await showOmiSheet<void>(
    context: context,
    title: context.l10n.yearlySwitchTitle,
    builder: (_) => YearlySwitchSheet(surface: surface, load: load, apply: apply, onSwitched: () => switched = true),
  );
  return switched;
}

/// The confirm step. Loads Stripe's preview, then switches at the previewed proration date for the
/// previewed amount only, so the charge is the one on screen. A declined card changes nothing: the
/// reader stays on monthly. After any failure the next tap re-previews before it charges.
class YearlySwitchSheet extends StatefulWidget {
  const YearlySwitchSheet({super.key, required this.surface, this.load, this.apply, this.onSwitched});

  final YearlySwitchSurface surface;
  final YearlySwitchLoader? load;
  final YearlySwitchApplier? apply;
  final VoidCallback? onSwitched;

  @override
  State<YearlySwitchSheet> createState() => _YearlySwitchSheetState();
}

class _YearlySwitchSheetState extends State<YearlySwitchSheet> {
  wire.GeneratedYearlySwitchResponse? _offer;
  bool _loading = true;
  bool _unavailable = false;
  bool _switching = false;
  bool _done = false;
  // The last attempt failed: its preview (and the idempotency key bound to it) is spent.
  bool _stale = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final offer = await (widget.load ?? payment_api.getYearlySwitch)(preview: true);
    if (!mounted) return;
    final usable = _usablePreview(offer);
    final refused = offer != null && !offer.eligible && offer.reason != 'unavailable';
    if (!usable) {
      _emitFailed(
        widget.surface,
        refused
            ? SubscriptionYearlySwitchFailedReason.refused
            : SubscriptionYearlySwitchFailedReason.previewUnavailable,
      );
    }
    setState(() {
      _loading = false;
      _offer = usable ? offer : null;
      _unavailable = refused;
    });
  }

  Future<void> _switch() async {
    var offer = _offer;
    if (offer == null || _switching) return;
    HapticFeedback.mediumImpact();
    const TypedEvents().emit(SubscriptionYearlySwitchConfirmed(
        surface: SubscriptionYearlySwitchConfirmedSurface.values.byName(widget.surface.name)));
    setState(() {
      _switching = true;
      _error = null;
    });
    final load = widget.load ?? payment_api.getYearlySwitch;
    if (_stale) {
      // A retry charges only a fresh preview. If the amount moved, show it and wait for another tap.
      final fresh = await load(preview: true);
      if (!mounted) return;
      if (!_usablePreview(fresh)) {
        _emitFailed(widget.surface, SubscriptionYearlySwitchFailedReason.previewUnavailable);
        setState(() {
          _switching = false;
          _error = context.l10n.yearlySwitchPreviewFailed;
        });
        return;
      }
      final moved = fresh!.amountDueToday != offer.amountDueToday;
      setState(() {
        _offer = fresh;
        _stale = false;
        if (moved) _switching = false;
      });
      if (moved) return;
      offer = fresh;
    }
    Map<String, dynamic>? result;
    try {
      result = await (widget.apply ?? _applyYearlySwitch)(
        priceId: offer.priceId!,
        prorationDate: offer.prorationDate!,
        expectedAmountDue: offer.amountDueToday!,
      );
    } catch (_) {
      result = null;
    }
    if (!mounted) return;
    var outcome = result == null
        ? _Outcome.unknown
        : result['error'] != true
            ? _Outcome.switched
            : result['status_code'] is int
                ? _Outcome.failed
                : _Outcome.unknown;
    if (outcome == _Outcome.unknown) {
      // No answer (timeout, server error): read Stripe again before saying anything about the plan.
      final after = await load(preview: false);
      if (!mounted) return;
      outcome = after?.eligible == true
          ? _Outcome.failed
          : after?.reason == 'not_monthly'
              ? _Outcome.switched
              : _Outcome.unknown;
    }
    final l10n = context.l10n;
    if (outcome == _Outcome.switched) {
      const TypedEvents().emit(SubscriptionYearlySwitchSucceeded(
          surface: SubscriptionYearlySwitchSucceededSurface.values.byName(widget.surface.name)));
      widget.onSwitched?.call();
      final usage = context.read<UsageProvider?>();
      if (usage != null) {
        unawaited(usage.fetchSubscription());
        unawaited(usage.loadAvailablePlans());
      }
      setState(() {
        _switching = false;
        _done = true;
      });
      return;
    }
    final status = result?['status_code'];
    final declined = status == 402;
    _emitFailed(
      widget.surface,
      declined
          ? SubscriptionYearlySwitchFailedReason.declined
          : (status == 400 || status == 409)
              ? SubscriptionYearlySwitchFailedReason.refused
              : SubscriptionYearlySwitchFailedReason.error,
    );
    setState(() {
      _switching = false;
      _stale = true;
      _error = declined
          ? l10n.yearlySwitchDeclined
          : outcome == _Outcome.unknown
              ? l10n.somethingWentWrong
              : l10n.yearlySwitchFailed;
    });
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_switching,
      child: AnimatedSize(
        duration: OmiMotion.of(context).standard,
        alignment: Alignment.topCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: OmiSpacing.md),
          child: _content(context),
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    final l10n = context.l10n;
    if (_loading) {
      return const SizedBox(key: Key('yearly_switch_loading'), height: 240, child: Center(child: OmiSpinner()));
    }
    final offer = _offer;
    if (offer == null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.lg),
        child: OmiErrorState(
          message: _unavailable ? l10n.yearlySwitchUnavailable : l10n.yearlySwitchPreviewFailed,
          onRetry: _unavailable ? null : _load,
        ),
      );
    }
    final currency = offer.currency;
    final dueToday = yearlySwitchMoney(offer.amountDueToday!, currency);
    final renews = OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(offer.renewsAt! * 1000));
    if (_done) {
      return Column(
        key: const Key('yearly_switch_done'),
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: OmiSpacing.lg),
          Icon(Icons.check_circle, size: 44, color: OmiColors.success),
          const SizedBox(height: OmiSpacing.sm),
          Text(l10n.yearlySwitchDoneTitle, style: OmiType.title3, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            l10n.yearlySwitchDoneBody(dueToday, renews),
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const Key('yearly_switch_done_button'),
            label: l10n.done,
            expand: true,
            onPressed: () => Navigator.of(context).maybePop(),
          ),
        ],
      );
    }
    final usage = context.read<UsageProvider?>()?.subscription;
    final plan = planDisplayName(PlanType.fromWire(offer.planId ?? ''), usage?.availablePlans ?? const [], l10n);
    return Column(
      key: const Key('yearly_switch_preview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FactRow(
          label: l10n.yearlySwitchPlanLabel,
          value: l10n.yearlySwitchPlanValue(plan, yearlySwitchMoney(offer.yearlyAmount!, currency)),
        ),
        Divider(height: 1, thickness: 1, color: OmiColors.border),
        _FactRow(
          label: l10n.yearlySwitchDueToday,
          value: dueToday,
          valueKey: const Key('yearly_switch_due_today'),
          emphasized: true,
        ),
        Divider(height: 1, thickness: 1, color: OmiColors.border),
        _FactRow(label: l10n.yearlySwitchRenews, value: renews),
        if (offer.amountDueToday! < offer.yearlyAmount!)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.xxs),
            child: Text(l10n.yearlySwitchCreditNote, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.md),
            child: Text(
              _error!,
              key: const Key('yearly_switch_error'),
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.danger),
            ),
          ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          key: const Key('yearly_switch_confirm'),
          label: l10n.yearlySwitchTitle,
          expand: true,
          isLoading: _switching,
          onPressed: _switching ? null : _switch,
        ),
        const SizedBox(height: OmiSpacing.xs),
        OmiButton.tertiary(
          key: const Key('yearly_switch_cancel'),
          label: l10n.cancel,
          expand: true,
          onPressed: _switching ? null : () => Navigator.of(context).maybePop(),
        ),
      ],
    );
  }
}

/// What a switch attempt did: [unknown] when neither the response nor a re-read of Stripe says.
enum _Outcome { switched, failed, unknown }

/// One line of the preview: what it is on the left, its value on the right, aligned with the title.
class _FactRow extends StatelessWidget {
  const _FactRow({required this.label, required this.value, this.valueKey, this.emphasized = false});

  final String label;
  final String value;
  final Key? valueKey;

  /// The charge today: the line the reader is deciding on.
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
          child: Row(
            children: [
              Text(label, style: OmiType.body.copyWith(color: OmiColors.textPrimary)),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Text(
                  value,
                  key: valueKey,
                  textAlign: TextAlign.end,
                  style: emphasized
                      ? OmiType.body.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w600)
                      : OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The offer row: an icon tile, the saving and one quiet line, like a Home conversation row.
class YearlySwitchRow extends StatelessWidget {
  const YearlySwitchRow({
    super.key,
    required this.title,
    required this.subtitle,
    required this.onTap,
    required this.color,
    required this.tileColor,
    this.onDismiss,
  });

  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color color;
  final Color tileColor;

  /// Draws a close X instead of the chevron.
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color,
      borderRadius: OmiRadius.xlAll,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsetsDirectional.fromSTEB(14, 14, onDismiss == null ? 14 : 4, 14),
          child: Row(
            children: [
              ExcludeSemantics(
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(color: tileColor, borderRadius: OmiRadius.mdAll),
                  child: Icon(Icons.event_repeat_outlined, size: 20, color: OmiColors.textPrimary),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Semantics(
                  button: true,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 3),
                      Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                    ],
                  ),
                ),
              ),
              if (onDismiss != null)
                OmiIconButton(
                  key: const Key('yearly_switch_dismiss'),
                  icon: const Icon(Icons.close, size: 20),
                  label: context.l10n.dismiss,
                  color: OmiColors.textTertiary,
                  onPressed: onDismiss,
                )
              else
                ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Plans & Billing: "Switch to yearly · Save $89.97 a year" for an eligible monthly subscriber.
class YearlySwitchPlansRow extends StatefulWidget {
  const YearlySwitchPlansRow({super.key, this.load, this.apply});

  final YearlySwitchLoader? load;
  final YearlySwitchApplier? apply;

  @override
  State<YearlySwitchPlansRow> createState() => _YearlySwitchPlansRowState();
}

class _YearlySwitchPlansRowState extends State<YearlySwitchPlansRow> {
  wire.GeneratedYearlySwitchResponse? _offer;
  String? _loadedFor;
  bool _switched = false;

  Future<void> _load(String candidate) async {
    final offer = await (widget.load ?? payment_api.getYearlySwitch)(preview: false);
    if (!mounted || _loadedFor != candidate || offer == null || !offer.eligible || offer.savingsAmount == null) return;
    setState(() => _offer = offer);
    _emitShown(YearlySwitchSurface.plans);
  }

  Future<void> _open() async {
    final switched = await showYearlySwitchSheet(
      context,
      surface: YearlySwitchSurface.plans,
      load: widget.load,
      apply: widget.apply,
    );
    if (switched && mounted) setState(() => _switched = true);
  }

  @override
  Widget build(BuildContext context) {
    final candidate = context.select<UsageProvider?, String?>(yearlySwitchCandidate);
    if (candidate == null || _switched) return const SizedBox.shrink();
    if (_loadedFor != candidate) {
      _loadedFor = candidate;
      _offer = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) unawaited(_load(candidate));
      });
    }
    final offer = _offer;
    if (offer == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.lg),
      child: YearlySwitchRow(
        key: const Key('yearly_switch_plans_row'),
        title: l10n.yearlySwitchTitle,
        subtitle: l10n.yearlySwitchRowSavings(yearlySwitchMoney(offer.savingsAmount!, offer.currency)),
        color: OmiColors.surface2,
        tileColor: OmiColors.surface3,
        onTap: _open,
      ),
    );
  }
}

/// Home: one quiet row for a monthly payer past their first paid month, at most once every 30 days.
class YearlySwitchHomeRow extends StatefulWidget {
  const YearlySwitchHomeRow({super.key, this.load, this.apply, this.now});

  final YearlySwitchLoader? load;
  final YearlySwitchApplier? apply;
  final DateTime Function()? now;

  static const quietPeriod = Duration(days: 30);

  @override
  State<YearlySwitchHomeRow> createState() => _YearlySwitchHomeRowState();
}

class _YearlySwitchHomeRowState extends State<YearlySwitchHomeRow> {
  static const _monthAhead = Duration(days: 32);
  wire.GeneratedYearlySwitchResponse? _offer;
  String? _loadedFor;
  bool _hidden = false;

  Future<void> _load(String candidate) async {
    final prefs = SharedPreferencesUtil();
    final now = (widget.now ?? DateTime.now)();
    // A yearly plan renews months from now: no lookup (it would only answer not_monthly on every launch).
    final periodEnd = context.read<UsageProvider?>()?.subscription?.subscription.currentPeriodEnd;
    if (periodEnd != null && DateTime.fromMillisecondsSinceEpoch(periodEnd * 1000).isAfter(now.add(_monthAhead))) {
      return;
    }
    final lastShown = prefs.yearlySwitchHomeShownAt;
    if (lastShown > 0 &&
        now.difference(DateTime.fromMillisecondsSinceEpoch(lastShown)) < YearlySwitchHomeRow.quietPeriod) {
      return;
    }
    final offer = await (widget.load ?? payment_api.getYearlySwitch)(preview: false);
    if (!mounted || _loadedFor != candidate || offer == null || !offer.eligible) return;
    // The first paid month is still the reader's decision; the row waits for the second.
    if (offer.firstBillingPeriod != false || offer.savingsAmount == null) return;
    prefs.yearlySwitchHomeShownAt = now.millisecondsSinceEpoch;
    setState(() => _offer = offer);
    _emitShown(YearlySwitchSurface.home);
  }

  Future<void> _open() async {
    final switched = await showYearlySwitchSheet(
      context,
      surface: YearlySwitchSurface.home,
      load: widget.load,
      apply: widget.apply,
    );
    if (switched && mounted) setState(() => _hidden = true);
  }

  void _dismiss() {
    _emitDismissed(YearlySwitchSurface.home);
    setState(() => _hidden = true);
  }

  @override
  Widget build(BuildContext context) {
    final candidate = context.select<UsageProvider?, String?>(yearlySwitchCandidate);
    if (candidate == null || _hidden) return const SizedBox.shrink();
    if (_loadedFor != candidate) {
      _loadedFor = candidate;
      _offer = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) unawaited(_load(candidate));
      });
    }
    final offer = _offer;
    if (offer == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: YearlySwitchRow(
        key: const Key('yearly_switch_home_row'),
        title: l10n.yearlySwitchHomeTitle(yearlySwitchMoney(offer.savingsAmount!, offer.currency)),
        subtitle: l10n.yearlySwitchHomeSubtitle,
        color: OmiColors.surface1,
        tileColor: OmiColors.surface2,
        onTap: _open,
        onDismiss: _dismiss,
      ),
    );
  }
}
