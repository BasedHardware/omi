import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
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
      builder: (_) => _ContextualPlansHost(source: source, storefront: storefront));
  return true;
}

class _ContextualPlansHost extends StatefulWidget {
  const _ContextualPlansHost({required this.source, this.storefront});
  final String source;
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
      initialStorefront: widget.storefront);
}

/// Returns true only when the server explicitly gates this action and a sheet was shown.
/// Existing legacy access is never inferred from a canonical tier name.
Future<bool> showProGateUpsell(BuildContext context, {required String feature, required String source}) async {
  final provider = context.read<UsageProvider>();
  if (!provider.showSubscriptionUI ||
      !await PlanStorefrontGate.upsellsEnabled() ||
      !await PlanStorefrontGate.sheetEnabled()) {
    return false;
  }
  if (!context.mounted || !provider.showSubscriptionUI) return false;
  final result = await PlanStorefrontApi().load(source: source, locale: context.l10n.localeName);
  if (!context.mounted || !provider.showSubscriptionUI || result is! ApiSuccess<PlanStorefront>) {
    return false;
  }
  final data = result.data;
  if (!data.shouldGate(feature)) return false;
  return openContextualPlans(context, source: source, storefront: data);
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
    if (!provider.showSubscriptionUI ||
        !await PlanStorefrontGate.upsellsEnabled() ||
        !await PlanStorefrontGate.sheetEnabled()) {
      return;
    }
    if (!mounted || generation != _generation || !provider.showSubscriptionUI) return;
    final result = await PlanStorefrontApi().load(source: 'budget_80_percent', locale: context.l10n.localeName);
    if (mounted && generation == _generation && result is ApiSuccess<PlanStorefront>) {
      setState(() => _data = result.data);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    if (!context.watch<UsageProvider>().showSubscriptionUI || data == null) return const SizedBox.shrink();
    return BudgetUpsellCard(
        data: data,
        onOpen: () async {
          await openContextualPlans(context, source: 'budget_80_percent', storefront: data);
        });
  }
}

/// Pure banner presentation; eligibility is from the backend budget snapshot.
class BudgetUpsellCard extends StatelessWidget {
  const BudgetUpsellCard({super.key, required this.data, required this.onOpen});
  final PlanStorefront data;
  final Future<void> Function() onOpen;
  @override
  Widget build(BuildContext context) {
    if (!data.showBudgetNudge) {
      return const SizedBox.shrink();
    }
    return Container(
      key: const Key('budget_80_percent_banner'),
      margin: const EdgeInsets.only(top: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(data.usageContext!.message, style: OmiType.subhead),
        OmiButton.tertiary(label: context.l10n.managePlan, onPressed: onOpen),
      ]),
    );
  }
}
