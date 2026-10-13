import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// W4 may call this from its 100% choice; W6 does not own held-content decisions.
/// Also serves MCP cap and screen-context gates when those mobile surfaces exist.
Future<bool> openContextualPlans(
  BuildContext context, {
  required String source,
  String trigger = '',
  PlanStorefront? storefront,
}) async {
  final provider = context.read<UsageProvider>();
  if (!provider.showSubscriptionUI || !await PlanStorefrontGate.sheetEnabled()) return false;
  if (!context.mounted || !provider.showSubscriptionUI) return false;
  PlatformManager.instance.analytics
      .paywallOpened(source, currentPlan: provider.subscription?.subscription.plan.wireName ?? 'unknown');
  await showOmiSheet(
      context: context,
      padding: EdgeInsets.zero,
      title: context.l10n.plansAndBilling,
      builder: (_) => _ContextualPlansHost(source: source, trigger: trigger, storefront: storefront));
  return true;
}

class _ContextualPlansHost extends StatefulWidget {
  const _ContextualPlansHost({required this.source, this.trigger = '', this.storefront});
  final String source;
  final String trigger;
  final PlanStorefront? storefront;
  @override
  State<_ContextualPlansHost> createState() => _ContextualPlansHostState();
}

class _ContextualPlansHostState extends State<_ContextualPlansHost> with TickerProviderStateMixin {
  late final _wave = AnimationController(vsync: this, duration: const Duration(seconds: 1));
  late final _notes = AnimationController(vsync: this, duration: const Duration(seconds: 1));
  late final _arrow = AnimationController(vsync: this, duration: const Duration(seconds: 1));
  @override
  void dispose() {
    _wave.dispose();
    _notes.dispose();
    _arrow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
      waveController: _wave,
      notesController: _notes,
      arrowController: _arrow,
      arrowAnimation: _arrow,
      analyticsSource: widget.source,
      storefrontTrigger: widget.trigger,
      initialStorefront: widget.storefront);
}

/// Returns true only when the server explicitly gates this action and a sheet was shown.
/// Existing legacy access is never inferred from a canonical tier name.
Future<bool> showProGateUpsell(BuildContext context, {required String feature, required String source}) async {
  final provider = context.read<UsageProvider>();
  if (!provider.showSubscriptionUI || !await PlanStorefrontGate.contextualEnabled()) {
    return false;
  }
  if (!context.mounted || !provider.showSubscriptionUI) return false;
  final result = await PlanStorefrontApi().load(source: source, trigger: feature, locale: context.l10n.localeName);
  if (!context.mounted || !provider.showSubscriptionUI || result is! ApiSuccess<PlanStorefront>) {
    return false;
  }
  final data = result.data;
  if (!data.shouldGate(feature)) return false;
  return openContextualPlans(context, source: source, trigger: feature, storefront: data);
}

/// Local presentation preference; the backend period, not a client date, resets it.
abstract final class BudgetNudgeDismissal {
  static String get _key => 'budget_nudge_dismissed_period_${SharedPreferencesUtil().uid}';
  static bool isDismissed(String? period) =>
      period != null && period.isNotEmpty && SharedPreferencesUtil().getString(_key) == period;
  static Future<void> dismiss(String? period) async {
    if (period != null && period.isNotEmpty) await SharedPreferencesUtil().saveString(_key, period);
  }
}

/// Nonblocking; absent flags/visibility/payload/usage keep the page exactly as before.
class BudgetUpsellBanner extends StatefulWidget {
  const BudgetUpsellBanner({super.key});
  @override
  State<BudgetUpsellBanner> createState() => _BudgetUpsellBannerState();
}

class _BudgetUpsellBannerState extends State<BudgetUpsellBanner> {
  PlanStorefront? _data;
  Object? _subscription;
  bool _initialized = false;
  int _generation = 0;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final subscription = context.watch<UsageProvider>().subscription;
    if (!_initialized || !identical(subscription, _subscription)) {
      _initialized = true;
      _subscription = subscription;
      _data = null;
      final generation = ++_generation;
      WidgetsBinding.instance.addPostFrameCallback((_) => _load(generation));
    }
  }

  Future<void> _load(int generation) async {
    if (!mounted || generation != _generation) return;
    final provider = context.read<UsageProvider>();
    if (!provider.showSubscriptionUI || !await PlanStorefrontGate.contextualEnabled()) {
      return;
    }
    if (!mounted || generation != _generation || !provider.showSubscriptionUI) return;
    final result =
        await PlanStorefrontApi().load(source: 'budget_80', trigger: 'budget_80', locale: context.l10n.localeName);
    if (mounted && generation == _generation && result is ApiSuccess<PlanStorefront>) {
      setState(() => _data = result.data);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    if (!context.watch<UsageProvider>().showSubscriptionUI || data == null) return const SizedBox.shrink();
    final period = data.usage?.periodId;
    final dismissed = BudgetNudgeDismissal.isDismissed(period);
    final meterLine = data.usage?.meterLine;
    final showMeter = meterLine != null && meterLine.isNotEmpty;
    final showNudge = !dismissed && data.showBudgetNudge;
    if (!showMeter && !showNudge) return const SizedBox.shrink();
    return Column(mainAxisSize: MainAxisSize.min, children: [
      if (showMeter) StorefrontUsageMeter(usage: data.usage!),
      if (showNudge)
        BudgetUpsellCard(
            data: data,
            onDismiss: () => BudgetNudgeDismissal.dismiss(period),
            onOpen: () async {
              await openContextualPlans(context, source: 'budget_80', trigger: 'budget_80', storefront: data);
            }),
    ]);
  }
}

/// Usage-screen meter. The line is the backend string; there is no separate title.
class StorefrontUsageMeter extends StatelessWidget {
  const StorefrontUsageMeter({super.key, required this.usage});
  final StorefrontUsage usage;

  @override
  Widget build(BuildContext context) {
    final line = usage.meterLine;
    if (line == null || line.isEmpty) return const SizedBox.shrink();
    final percent = usage.percent;
    return Container(
      key: const Key('storefront_usage_meter'),
      margin: const EdgeInsets.only(top: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(line, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        if (percent != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          LinearProgressIndicator(
            key: const Key('storefront_usage_meter_bar'),
            value: (percent / 100).clamp(0.0, 1.0),
            minHeight: 4,
            color: OmiColors.accent,
            backgroundColor: OmiColors.surface3,
            borderRadius: OmiRadius.pillAll,
          ),
        ],
      ]),
    );
  }
}

/// Pure banner presentation; eligibility is from the backend budget snapshot.
class BudgetUpsellCard extends StatefulWidget {
  const BudgetUpsellCard({super.key, required this.data, required this.onOpen, this.onDismiss});
  final PlanStorefront data;
  final Future<void> Function() onOpen;
  final Future<void> Function()? onDismiss;
  @override
  State<BudgetUpsellCard> createState() => _BudgetUpsellCardState();
}

class _BudgetUpsellCardState extends State<BudgetUpsellCard> {
  bool _dismissed = false;
  @override
  void didUpdateWidget(BudgetUpsellCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.data.usage?.periodId != widget.data.usage?.periodId) _dismissed = false;
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    if (_dismissed || !data.showBudgetNudge) {
      return const SizedBox.shrink();
    }
    final nudge = data.usage?.nudgeLine;
    if (nudge == null || nudge.isEmpty) return const SizedBox.shrink();
    return Container(
      key: const Key('budget_80'),
      margin: const EdgeInsets.only(top: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(nudge, style: OmiType.subhead),
        const SizedBox(height: OmiSpacing.xs),
        Row(children: [
          Expanded(
              child: OmiButton(
            key: const Key('budget_nudge_compare'),
            label: context.l10n.paywallComparePlans,
            size: OmiButtonSize.compact,
            onPressed: widget.onOpen,
          )),
          OmiButton.tertiary(
            key: const Key('budget_nudge_dismiss'),
            label: context.l10n.paywallNotNow,
            size: OmiButtonSize.compact,
            onPressed: () async {
              setState(() => _dismissed = true);
              await widget.onDismiss?.call();
            },
          ),
        ]),
      ]),
    );
  }
}
