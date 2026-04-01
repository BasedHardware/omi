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
import 'package:omi/utils/analytics/mixpanel.dart';

class InteractiveDeviceOnboardingWrapper extends StatefulWidget {
  const InteractiveDeviceOnboardingWrapper({super.key});

  @override
  State<InteractiveDeviceOnboardingWrapper> createState() => _InteractiveDeviceOnboardingWrapperState();
}

class _InteractiveDeviceOnboardingWrapperState extends State<InteractiveDeviceOnboardingWrapper> {
  late DeviceOnboardingProvider _onboardingProvider;
  late PageController _pageController;
  CaptureProvider? _captureProvider;

  @override
  void initState() {
    super.initState();
    _onboardingProvider = DeviceOnboardingProvider();
    _pageController = PageController();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _captureProvider = context.read<CaptureProvider>();
      _captureProvider!.deviceOnboardingProvider = _onboardingProvider;
      _onboardingProvider.startOnboarding();
      MixpanelManager().deviceOnboardingStarted();
    });
  }

  @override
  void dispose() {
    _captureProvider?.deviceOnboardingProvider = null;
    _onboardingProvider.dispose();
    _pageController.dispose();
    super.dispose();
  }

  void _onStepComplete(String stepName) {
    MixpanelManager().deviceOnboardingStepCompleted(stepName);

    if (_onboardingProvider.currentStep < DeviceOnboardingProvider.totalSteps - 1) {
      _onboardingProvider.advanceStep();
      _pageController.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
    } else {
      _completeOnboarding();
    }
  }

  void _completeOnboarding() {
    MixpanelManager().deviceOnboardingCompleted();
    MixpanelManager().deviceOnboardingDoubleTapConfigured(_onboardingProvider.selectedDoubleTapAction);
    _onboardingProvider.completeOnboarding();
    SharedPreferencesUtil().deviceOnboardingCompleted = true;
    updateUserOnboardingState(deviceOnboardingCompleted: true);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _onboardingProvider,
      child: PopScope(
        canPop: false,
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFF1A0033), Colors.black],
              ),
            ),
            child: PageView(
              controller: _pageController,
              physics: const NeverScrollableScrollPhysics(),
              children: [
                TranscriptionDemoStep(onComplete: () => _onStepComplete('transcription_demo')),
                SinglePressStep(onComplete: () => _onStepComplete('single_press_ask_question')),
                PowerCycleStep(onComplete: () => _onStepComplete('power_cycle')),
                DoublePressConfigStep(onComplete: () => _onStepComplete('double_press_config')),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
