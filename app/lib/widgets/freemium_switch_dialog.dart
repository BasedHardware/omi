import 'package:flutter/material.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/backend/schema/gen/budget_choice_wire.g.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/backend/http/budget_choice_api.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/on_device/on_device_at_cap_sheet.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/freemium_threshold_tracker.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';

/// Prompt id of the plans sheet offered when the Plus meter runs low.
const String kFreemiumPlansPromptId = 'freemium-plans';

/// Handler for freemium transcription switching
/// Decides when to offer the plans sheet; the sheet itself goes through [PromptQueue].
class FreemiumSwitchHandler {
  FreemiumSwitchHandler({PromptQueue? queue}) : _queue = queue ?? PromptQueue.instance;

  final FreemiumTranscriptionService _freemiumService = FreemiumTranscriptionService();
  final PromptQueue _queue;
  bool _wasEligible = false;

  FreemiumTranscriptionService get service => _freemiumService;

  /// Whether the Plus meter warning applies right now.
  bool _eligible(BuildContext context, CaptureProvider captureProvider) {
    if (!context.mounted) return false;
    final usage = context.read<UsageProvider>();
    if (!usage.showSubscriptionUI) return false;
    if (OnDeviceTranscriptionController.instance.isActive && usage.isOutOfCredits) return true;
    return FreemiumThresholdTracker.shouldShowPlusMeterPaywall(
      reached: captureProvider.freemiumThresholdReached,
      requiresUserAction: captureProvider.freemiumRequiresUserAction,
      plan: usage.subscription?.subscription.plan,
    );
  }

  /// Call on every capture change. Offers the plans sheet once per session, only when the meter
  /// actually crosses the threshold (not on every capture notification), and never over a recording:
  /// the sheet is queued, and [PromptQueue] holds it until capture stops. Returns true when it was
  /// queued.
  bool checkAndShowPaywall(BuildContext context, CaptureProvider captureProvider) {
    final eligible = _eligible(context, captureProvider);
    final crossed = eligible && !_wasEligible;
    _wasEligible = eligible;
    if (!crossed || _freemiumService.dialogShownThisSession) return false;

    _freemiumService.markDialogShown();
    return _queue.enqueue(
      kFreemiumPlansPromptId,
      PromptPriority.low,
      // Still relevant when it is finally shown (the plan may have changed meanwhile).
      canShowNow: () => _eligible(context, captureProvider),
      show: (promptContext) async {
        if (await _offerOnDevice(promptContext)) return;
        if (!promptContext.mounted) return;
        if (await PaywallRouter.openVariant(promptContext, source: 'freemium_switch')) return;
        if (!promptContext.mounted) return;
        final plan = promptContext.read<UsageProvider>().subscription?.subscription.plan.wireName ?? 'unknown';
        PlatformManager.instance.analytics.paywallOpened('freemium_switch', currentPlan: plan);
        final title = await plansSheetTitle(promptContext);
        if (!promptContext.mounted) return;
        return showOmiSheet<void>(
          context: promptContext,
          title: title,
          padding: EdgeInsets.zero,
          builder: (_) => const _PlansSheetWrapper(),
        );
      },
    );
  }

  /// With the on-device flag on and this month's usage limit reached, offers transcribing on this phone before
  /// the plans sheet. Returns true when it handled the prompt.
  Future<bool> _offerOnDevice(BuildContext context) async {
    if (!context.read<UsageProvider>().isOutOfCredits || !await OnDeviceOverflowGate.read()) return false;
    if (!context.mounted) return false;
    final controller = OnDeviceTranscriptionController.instance;
    await controller.ensureLoaded();
    if (!context.mounted) return false;
    final storefront = await PlanStorefrontApi()
        .load(source: 'on_device_at_cap', trigger: 'usage_budget', locale: context.l10n.localeName);
    if (!context.mounted) return true;
    final data = storefront is ApiSuccess<PlanStorefront> ? storefront.data : null;
    final copy = data?.atCap;
    final api = BudgetChoiceApi();
    final record = copy == null ? null : await api.load();
    if (!context.mounted) return true;
    if (copy != null && record is! ApiSuccess<GeneratedBudgetChoiceResponse>) {
      return true;
    } // Hold, retry later; no local entitlement guess.
    if (record is ApiSuccess<GeneratedBudgetChoiceResponse> && !record.data.ask) {
      if (record.data.state == 'on_device') {
        await controller.updateSettings(controller.settings.copyWith(enabled: true));
      }
      return true;
    }
    var dontAskAgain = false;
    var current = record;
    OnDeviceAtCapChoice? choice;
    for (var ask = 0; ask < 2; ask++) {
      dontAskAgain = false;
      choice = await showOnDeviceAtCapSheet(context,
          liveHoursReturnOn: onDeviceUsageResetsOn(DateTime.now()),
          copy: copy,
          onDontAskAgain: (value) => dontAskAgain = value);
      if (!context.mounted || choice == null) return true;
      if (copy == null || current is! ApiSuccess<GeneratedBudgetChoiceResponse>) break;
      final saved = await api.save(
          current.data.period, choice == OnDeviceAtCapChoice.upgrade ? 'upgrade' : 'on_device', dontAskAgain);
      if (!context.mounted) return true;
      if (saved is ApiSuccess) break;
      if (!budgetPeriodChanged(saved) || ask == 1) return true;
      final reloaded = await api.load();
      if (!context.mounted || reloaded is! ApiSuccess<GeneratedBudgetChoiceResponse>) return true;
      current = reloaded;
      if (!reloaded.data.ask) {
        if (reloaded.data.state == 'on_device') {
          await controller.updateSettings(controller.settings.copyWith(enabled: true));
        }
        return true;
      }
    }
    if (choice == null) return true;
    switch (choice) {
      case OnDeviceAtCapChoice.transcribeOnPhone:
        await controller.updateSettings(controller.settings.copyWith(enabled: true));
        if (context.mounted && !controller.model.status.isInstalled) {
          await openOnDeviceSetup(context);
        }
      case OnDeviceAtCapChoice.upgrade:
        if (copy != null) {
          await openContextualPlans(context, source: 'on_device_at_cap', trigger: 'usage_budget', storefront: data);
        } else {
          openOnDeviceUpgrade(context);
        }
    }
    return true;
  }

  /// Legacy method name for backward compatibility
  bool checkAndShowDialog(BuildContext context, CaptureProvider captureProvider) {
    return checkAndShowPaywall(context, captureProvider);
  }

  /// Clean up resources
  void dispose() {
    _freemiumService.onAutoSwitch = null;
    _queue.remove(kFreemiumPlansPromptId);
  }

  /// Reset for new session (call when recording starts)
  void resetSession() {
    _freemiumService.resetDialogShownFlag();
    _freemiumService.reset();
  }

  /// Reset just the dialog shown flag
  void resetDialogFlag() {
    _freemiumService.resetDialogShownFlag();
  }
}

/// Wrapper widget to create animation controllers for PlansSheet
class _PlansSheetWrapper extends StatefulWidget {
  const _PlansSheetWrapper();

  @override
  State<_PlansSheetWrapper> createState() => _PlansSheetWrapperState();
}

class _PlansSheetWrapperState extends State<_PlansSheetWrapper> with TickerProviderStateMixin {
  late AnimationController _waveController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(duration: const Duration(milliseconds: 18000), vsync: this)..repeat();

    _arrowController = AnimationController(duration: const Duration(milliseconds: 800), vsync: this)
      ..repeat(reverse: true);

    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 3,
    ).animate(CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _waveController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
      analyticsSource: 'freemium_switch',
    );
  }
}
