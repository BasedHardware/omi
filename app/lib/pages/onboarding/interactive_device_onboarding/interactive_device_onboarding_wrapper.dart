import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/transcription_demo_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/single_press_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/power_cycle_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/double_press_config_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_intro_screen.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class InteractiveDeviceOnboardingWrapper extends StatefulWidget {
  // True when re-opened from Settings → Device Tutorial. The flow is always
  // dismissible (a hardware/BLE hiccup mid-tutorial must never soft-lock the
  // app); leaving on the first run persists completion so it doesn't re-fire,
  // and the tutorial stays reachable from device settings.
  final bool allowExit;

  const InteractiveDeviceOnboardingWrapper({super.key, this.allowExit = false});

  @override
  State<InteractiveDeviceOnboardingWrapper> createState() => _InteractiveDeviceOnboardingWrapperState();
}

class _InteractiveDeviceOnboardingWrapperState extends State<InteractiveDeviceOnboardingWrapper> {
  late DeviceOnboardingProvider _onboardingProvider;
  CaptureProvider? _captureProvider;
  bool _showIntro = true;
  bool _started = false;
  bool _completed = false;

  @override
  void initState() {
    super.initState();
    _onboardingProvider = DeviceOnboardingProvider();

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      _captureProvider = context.read<CaptureProvider>();
      _captureProvider!.deviceOnboardingProvider = _onboardingProvider;
      await _captureProvider!.suspendBatchModeForOnboarding();
      if (!mounted) return;
      _started = true;
      AnalyticsManager().deviceOnboardingStarted(source: widget.allowExit ? 'settings' : 'auto');
    });
  }

  void _startTutorial() {
    setState(() => _showIntro = false);
    _onboardingProvider.startOnboarding();
  }

  @override
  void dispose() {
    if (_started && !_completed) {
      AnalyticsManager().deviceOnboardingAbandoned(_onboardingProvider.currentStep);
    }
    _captureProvider?.restoreBatchModeAfterOnboarding();
    _captureProvider?.deviceOnboardingProvider = null;
    _onboardingProvider.dispose();
    super.dispose();
  }

  void _onStepComplete(String stepName) {
    AnalyticsManager().deviceOnboardingStepCompleted(stepName);

    if (_onboardingProvider.currentStep < DeviceOnboardingProvider.totalSteps - 1) {
      // advanceStep() notifies; the Consumer below rebuilds and the AnimatedSwitcher
      // swaps to the next step (keyed by currentStep) with a fade + small slide.
      _onboardingProvider.advanceStep();
    } else {
      _completeOnboarding();
    }
  }

  Widget _buildStep(int step) {
    switch (step) {
      case 0:
        return TranscriptionDemoStep(key: const ValueKey(0), onComplete: () => _onStepComplete('transcription_demo'));
      case 1:
        return SinglePressStep(key: const ValueKey(1), onComplete: () => _onStepComplete('single_press_ask_question'));
      case 2:
        return PowerCycleStep(key: const ValueKey(2), onComplete: () => _onStepComplete('power_cycle'));
      default:
        return DoublePressConfigStep(key: const ValueKey(3), onComplete: () => _onStepComplete('double_press_config'));
    }
  }

  void _completeOnboarding() {
    _completed = true;
    AnalyticsManager().deviceOnboardingCompleted();
    AnalyticsManager().deviceOnboardingDoubleTapConfigured(_onboardingProvider.selectedDoubleTapAction);
    _onboardingProvider.completeOnboarding();
    SharedPreferencesUtil().deviceOnboardingCompleted = true;
    updateUserOnboardingState(deviceOnboardingCompleted: true);
    Navigator.of(context).pop();
  }

  /// Leave the tutorial from any point. Persists completion so the forced
  /// first-run never re-fires (redo anytime via Settings → Device Tutorial);
  /// dispose() records the abandoned step for analytics.
  void _skipOnboarding() {
    SharedPreferencesUtil().deviceOnboardingCompleted = true;
    updateUserOnboardingState(deviceOnboardingCompleted: true);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _onboardingProvider,
      child: PopScope(
        // Intercept system back so leaving mid-tutorial persists completion —
        // otherwise the forced flow re-fires on next launch. _completeOnboarding
        // and _skipOnboarding pop directly (didPop == true) and skip this path.
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (didPop) return;
          _skipOnboarding();
        },
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFF2A2342), Colors.black],
              ),
            ),
            child: SafeArea(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 320),
                child: _showIntro
                    ? OnboardingIntroScreen(
                        key: const ValueKey('intro'),
                        onStart: _startTutorial,
                        onSkip: _skipOnboarding,
                      )
                    : Column(
                        key: const ValueKey('steps'),
                        children: [
                          // Always dismissible: a stuck step (e.g. the mic-test
                          // waiting on a response) must never trap the user.
                          SizedBox(
                            height: 48,
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: IconButton(
                                icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
                                onPressed: _skipOnboarding,
                              ),
                            ),
                          ),
                          // Persistent progress indicator — stays fixed and animates the
                          // active dot in place while only the content below transitions.
                          Consumer<DeviceOnboardingProvider>(
                            builder: (_, provider, __) => OnboardingProgressDots(currentStep: provider.currentStep),
                          ),
                          Expanded(
                            child: Consumer<DeviceOnboardingProvider>(
                              builder: (context, provider, _) => AnimatedSwitcher(
                                duration: const Duration(milliseconds: 320),
                                switchInCurve: Curves.easeOutCubic,
                                switchOutCurve: Curves.easeInCubic,
                                layoutBuilder: (currentChild, previousChildren) => Stack(
                                  alignment: Alignment.topCenter,
                                  children: [...previousChildren, if (currentChild != null) currentChild],
                                ),
                                transitionBuilder: (child, animation) {
                                  final slide = Tween<Offset>(
                                    begin: const Offset(0.08, 0),
                                    end: Offset.zero,
                                  ).animate(animation);
                                  return FadeTransition(
                                    opacity: animation,
                                    child: SlideTransition(position: slide, child: child),
                                  );
                                },
                                child: _buildStep(provider.currentStep),
                              ),
                            ),
                          ),
                        ],
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
