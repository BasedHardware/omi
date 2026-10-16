import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Variant `outline`: the soft paywall from PR #21412 (Graphite direction), on the app's real plan
/// catalog and the shared checkout. Black canvas, white accent, and "Use Free Plan" always visible,
/// so nobody is blocked. Prices come from the catalog; nothing here is hardcoded.
class OutlinePaywallPage extends StatefulWidget {
  const OutlinePaywallPage({super.key, required this.source, this.offer, this.checkout, this.onOpenPlans});

  final String source;

  /// Test seam: a fixed offer instead of the provider's catalog.
  final PaywallOffer? offer;

  /// Test seam: replaces [PaywallCheckout.start].
  final Future<PaywallCheckoutOutcome> Function(BuildContext context, PaywallPrice price, String tierId)? checkout;

  /// Test seam: replaces opening the plans sheet when the current price is missing.
  final VoidCallback? onOpenPlans;

  @override
  State<OutlinePaywallPage> createState() => _OutlinePaywallPageState();
}

class _OutlinePaywallPageState extends State<OutlinePaywallPage> with TickerProviderStateMixin {
  bool _yearly = true;
  bool _busy = false;
  bool _dismissed = false;
  String? _notice;

  @override
  void initState() {
    super.initState();
    if (widget.offer == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final usage = context.read<UsageProvider>();
        if (usage.availablePlans == null) usage.loadAvailablePlans();
      });
    }
  }

  void _dismiss() {
    if (_dismissed) return;
    _dismissed = true;
    PlatformManager.instance.analytics.upgradeModalDismissed();
    Navigator.of(context).pop(false);
  }

  Future<void> _restore() async {
    final usage = context.read<UsageProvider>();
    await usage.fetchSubscription();
    if (!mounted) return;
    final l10n = context.l10n;
    if (usage.subscription?.subscription.plan.isPaid == true) {
      OmiFeedback.confirm(context, l10n.unlimitedPlan);
      _dismissed = true;
      Navigator.of(context).pop(true);
      return;
    }
    OmiFeedback.info(context, l10n.freePlan);
  }

  Future<void> _purchase(PaywallOffer offer) async {
    final price = _yearly ? (offer.yearly ?? offer.monthly) : (offer.monthly ?? offer.yearly);
    if (price == null || _busy) return;
    setState(() => _busy = true);
    try {
      final start = widget.checkout ??
          (BuildContext context, PaywallPrice price, String tierId) => PaywallCheckout.start(
                context,
                priceId: price.priceId,
                plan: tierId,
                interval: price.interval,
                source: widget.source,
                surface: (message) {
                  if (mounted) setState(() => _notice = message);
                },
              );
      final outcome = await start(context, price, offer.tierId);
      if (!mounted) return;
      if (outcome == PaywallCheckoutOutcome.failed && _notice == null) {
        setState(() => _notice = context.l10n.anErrorOccurredTryAgain);
      }
      if (outcome == PaywallCheckoutOutcome.purchased) {
        _dismissed = true;
        Navigator.of(context).pop(true);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openPlans() async {
    final override = widget.onOpenPlans;
    if (override != null) {
      override();
      return;
    }
    if (!mounted) return;
    final wave = AnimationController(duration: const Duration(milliseconds: 18000), vsync: this);
    final notes = AnimationController(duration: const Duration(milliseconds: 36000), vsync: this);
    final arrow = AnimationController(duration: const Duration(milliseconds: 600), vsync: this);
    try {
      await showOmiSheet<void>(
        context: context,
        padding: EdgeInsets.zero,
        builder: (_) => PlansSheet(
          waveController: wave,
          notesController: notes,
          arrowController: arrow,
          arrowAnimation: arrow,
          analyticsSource: widget.source,
        ),
      );
    } finally {
      wave.dispose();
      notes.dispose();
      arrow.dispose();
    }
  }

  static String _money(int minor, String currency) =>
      NumberFormat.simpleCurrency(name: currency.toUpperCase(), decimalDigits: 2).format(minor / 100);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final top = MediaQuery.paddingOf(context).top;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _dismiss();
      },
      child: Scaffold(
        backgroundColor: _Graphite.background,
        body: Consumer<UsageProvider>(
          builder: (context, usage, _) {
            final subscription = usage.subscription?.subscription;
            final cancelPending = subscription?.cancelAtPeriodEnd == true;
            final offer = widget.offer ??
                PaywallOffer.fromCatalog(
                  usage.availablePlans,
                  cancelAtPeriodEnd: cancelPending,
                  currentPriceId: subscription?.currentPriceId,
                );
            final loading = offer == null && widget.offer == null && usage.isLoadingPlans;
            final blocked = cancelPending && widget.offer == null && !loading && offer?.resubscribe != true;
            final freeMinutes = (usage.subscription?.transcriptionSecondsLimit ?? 0) ~/ 60;
            final yearly = offer?.yearly;
            final monthly = offer?.monthly;
            final saving = offer?.yearlySavingPercent;
            return CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: 150 + top,
                    child: Stack(
                      clipBehavior: Clip.hardEdge,
                      children: [
                        const Positioned.fill(
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: RadialGradient(
                                center: Alignment(0.6, -0.2),
                                radius: 1,
                                colors: [_Graphite.surface2, _Graphite.background],
                              ),
                            ),
                          ),
                        ),
                        Positioned(
                          right: -10,
                          top: top - 10,
                          child: Image.asset(
                            'assets/images/omi-with-rope-no-padding.webp',
                            height: 190,
                            fit: BoxFit.contain,
                            errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                          ),
                        ),
                        Positioned(
                          left: 8,
                          right: 20,
                          top: top + 8,
                          child: Row(
                            children: [
                              IconButton(
                                key: const Key('outline_paywall_close'),
                                tooltip: l10n.useFreePlan,
                                onPressed: _dismiss,
                                icon: const Icon(Icons.close, color: _Graphite.text),
                              ),
                              const Spacer(),
                              TextButton(
                                key: const Key('outline_paywall_restore'),
                                onPressed: _restore,
                                child: Text(l10n.restoreAction, style: _Graphite.label(size: 14)),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 16, 24, 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(l10n.paywallOutlineHeadline, style: _Graphite.headline(30)),
                        const SizedBox(height: 10),
                        Text(
                          freeMinutes > 0 ? l10n.basicPlanDesc(freeMinutes) : l10n.unlimitedConversations,
                          style: _Graphite.body(),
                        ),
                        const SizedBox(height: 18),
                        if (loading) ...[
                          const _Skeleton(height: 74),
                          const SizedBox(height: 10),
                          const _Skeleton(height: 74),
                        ] else if (offer == null && !blocked) ...[
                          Text(l10n.unableToLoadPlans, style: _Graphite.body()),
                        ] else if (offer != null) ...[
                          if (yearly != null)
                            _PlanOption(
                              key: const Key('outline_paywall_yearly'),
                              title: l10n.billingYearly,
                              badge: saving == null ? null : l10n.savePercent(saving),
                              subtitle: _money(yearly.amountMinor, yearly.currency),
                              price: _money(yearly.perMonthMinor, yearly.currency),
                              per: l10n.perMonthLabel,
                              selected: _yearly || monthly == null,
                              onTap: () => setState(() => _yearly = true),
                            ),
                          if (yearly != null && monthly != null) const SizedBox(height: 10),
                          if (monthly != null)
                            _PlanOption(
                              key: const Key('outline_paywall_monthly'),
                              title: l10n.billingMonthly,
                              subtitle: _money(monthly.amountMinor, monthly.currency),
                              price: _money(monthly.amountMinor, monthly.currency),
                              per: l10n.perMonthLabel,
                              selected: !_yearly || yearly == null,
                              onTap: () => setState(() => _yearly = false),
                            ),
                        ],
                        const Spacer(),
                        const SizedBox(height: 16),
                        if (_notice != null) ...[
                          Text(
                            _notice!,
                            key: const Key('outline_paywall_notice'),
                            textAlign: TextAlign.center,
                            style: _Graphite.body(size: 13, color: _Graphite.text),
                          ),
                          const SizedBox(height: 12),
                        ],
                        if (blocked) ...[
                          Text(
                            l10n.resubscribeFirstToChangePlans,
                            key: const Key('outline_paywall_blocked'),
                            textAlign: TextAlign.center,
                            style: _Graphite.body(size: 14, color: _Graphite.text),
                          ),
                          const SizedBox(height: 12),
                          _Button(
                            key: const Key('outline_paywall_open_plans'),
                            label: l10n.resubscribe,
                            onPressed: _openPlans,
                          ),
                        ] else
                          _Button(
                            key: const Key('outline_paywall_cta'),
                            label: offer?.resubscribe == true ? l10n.resubscribe : l10n.upgradeToUnlimited,
                            busy: _busy,
                            onPressed: offer == null || _busy ? null : () => _purchase(offer),
                          ),
                        const SizedBox(height: 8),
                        Text(
                          l10n.paywallCancelAnytime,
                          textAlign: TextAlign.center,
                          style: _Graphite.body(size: 12, color: _Graphite.textTertiary),
                        ),
                        const SizedBox(height: 4),
                        _Button(
                          key: const Key('outline_paywall_free'),
                          label: l10n.useFreePlan,
                          kind: _ButtonKind.text,
                          onPressed: _dismiss,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Graphite tokens from the prototype: pure black, white and nothing else.
abstract final class _Graphite {
  static const background = Color(0xFF000000); // omi-ux-allow: color-literal -- fixed black design canvas
  static const surface = Color(0xFF1C1C1E); // omi-ux-allow: color-literal -- fixed black design canvas
  static const surface2 = Color(0xFF2C2C2E); // omi-ux-allow: color-literal -- fixed black design canvas
  static const border = Color(0xFF38383A); // omi-ux-allow: color-literal -- fixed black design canvas
  static const text = Color(0xFFFFFFFF); // omi-ux-allow: color-literal -- fixed black design canvas
  static const textSecondary = Color(0xFFAEAEB2); // omi-ux-allow: color-literal -- fixed black design canvas
  static const textTertiary = Color(0xFF8E8E93); // omi-ux-allow: color-literal -- fixed black design canvas
  static const accent = Color(0xFFFFFFFF); // omi-ux-allow: color-literal -- fixed black design canvas
  static const onAccent = Color(0xFF000000); // omi-ux-allow: color-literal -- fixed black design canvas
  static const success = Color(0xFF30D158); // omi-ux-allow: color-literal -- fixed black design canvas
  static const double buttonRadius = 14;

  static TextStyle headline(double size) => TextStyle(
        fontSize: size,
        height: 1.1,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.02 * size,
        color: text,
      );

  static TextStyle body({double size = 16, Color? color, double height = 1.4}) =>
      TextStyle(fontSize: size, height: height, fontWeight: FontWeight.w400, color: color ?? textSecondary);

  static TextStyle label({double size = 15, Color? color, FontWeight weight = FontWeight.w500}) =>
      TextStyle(fontSize: size, fontWeight: weight, color: color ?? text);
}

enum _ButtonKind { primary, text }

class _Button extends StatelessWidget {
  const _Button(
      {super.key, required this.label, required this.onPressed, this.kind = _ButtonKind.primary, this.busy = false});

  final String label;
  final VoidCallback? onPressed;
  final _ButtonKind kind;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final primary = kind == _ButtonKind.primary;
    final radius = BorderRadius.circular(_Graphite.buttonRadius);
    return Opacity(
      opacity: onPressed == null && !busy ? 0.35 : 1,
      child: Material(
        color: primary ? _Graphite.accent : Colors.transparent,
        borderRadius: radius,
        child: InkWell(
          borderRadius: radius,
          onTap: onPressed,
          child: SizedBox(
            height: 54,
            child: Center(
              child: busy
                  ? const OmiSpinner(size: OmiSpinnerSize.small, color: _Graphite.onAccent)
                  : Text(
                      label,
                      style: _Graphite.label(
                        size: 17,
                        color: primary ? _Graphite.onAccent : _Graphite.textSecondary,
                        weight: FontWeight.w600,
                      ),
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PlanOption extends StatelessWidget {
  const _PlanOption({
    super.key,
    required this.title,
    required this.subtitle,
    required this.price,
    required this.per,
    required this.selected,
    required this.onTap,
    this.badge,
  });

  final String title;
  final String subtitle;
  final String price;
  final String per;
  final bool selected;
  final VoidCallback onTap;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final badge = this.badge;
    return Semantics(
      selected: selected,
      button: true,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: _Graphite.surface,
            borderRadius: OmiRadius.lgAll,
            border: Border.all(color: selected ? _Graphite.accent : _Graphite.border, width: selected ? 2 : 1),
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: selected ? _Graphite.accent : Colors.transparent,
                  border: Border.all(color: selected ? _Graphite.accent : _Graphite.textTertiary, width: 1.5),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(title, style: _Graphite.label(size: 16, weight: FontWeight.w600)),
                        if (badge != null)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                            decoration: const BoxDecoration(borderRadius: OmiRadius.smAll, color: _Graphite.success),
                            child: Text(
                              badge.toUpperCase(),
                              style: _Graphite.label(size: 10, weight: FontWeight.w700, color: _Graphite.onAccent),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle, style: _Graphite.body(size: 13, height: 1.3)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(price, style: _Graphite.label(size: 16, weight: FontWeight.w600)),
                  Text(per, style: _Graphite.body(size: 12, color: _Graphite.textTertiary)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Skeleton extends StatelessWidget {
  const _Skeleton({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) => Container(
        height: height,
        decoration: const BoxDecoration(color: _Graphite.surface, borderRadius: OmiRadius.lgAll),
      );
}
