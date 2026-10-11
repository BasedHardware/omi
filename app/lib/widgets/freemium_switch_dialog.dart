import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/freemium_threshold_tracker.dart';
import 'package:omi/services/freemium_transcription_service.dart';
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
      show: (promptContext) => showOmiSheet<void>(
        context: promptContext,
        padding: EdgeInsets.zero,
        builder: (_) => _PlansSheetWrapper(),
      ),
    );
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
    );
  }
}
