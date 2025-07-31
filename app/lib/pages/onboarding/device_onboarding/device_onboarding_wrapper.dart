import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';

import 'device_onboarding_page.dart';

class DeviceOnboardingWrapper extends StatefulWidget {
  const DeviceOnboardingWrapper({super.key});

  @override
  State<DeviceOnboardingWrapper> createState() => _DeviceOnboardingWrapperState();
}

class _DeviceOnboardingWrapperState extends State<DeviceOnboardingWrapper> with TickerProviderStateMixin {
  late TabController _controller;
  int _currentSlide = 0;
  static const int _totalSlides = 5;

  @override
  void initState() {
    super.initState();
    _controller = TabController(length: _totalSlides, vsync: this);
    _controller.addListener(() {
      setState(() {
        _currentSlide = _controller.index;
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _goNext() {
    if (_controller.index < _controller.length - 1) {
      _controller.animateTo(_controller.index + 1);
    }
  }

  void _goBack() {
    if (_controller.index > 0) {
      _controller.animateTo(_controller.index - 1);
    }
  }

  void _completeOnboarding() {
    // Mark onboarding as completed and go to homepage
    SharedPreferencesUtil().onboardingCompleted = true;
    MixpanelManager().onboardingStepCompleted('Device Onboarding Completed');
    routeToPage(context, const HomePageWrapper(), replace: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: TabBarView(
        controller: _controller,
        physics: const NeverScrollableScrollPhysics(), // Disable swipe navigation
        children: [
          // 5 Device onboarding slides
          for (int i = 0; i < _totalSlides; i++)
            DeviceOnboardingPage(
              slideIndex: i,
              isFirstSlide: i == 0,
              isLastSlide: i == _totalSlides - 1,
              onNext: () {
                MixpanelManager().onboardingStepCompleted('Device Onboarding Slide ${i + 1}');
                if (i == _totalSlides - 1) {
                  // Last slide, complete onboarding
                  _completeOnboarding();
                } else {
                  _goNext();
                }
              },
              onBack: i > 0 ? _goBack : null,
            ),
        ],
      ),
    );
  }
}
