import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/home/wrapper.dart';
import 'package:friend_private/pages/onboarding/device_selection.dart';
import 'package:friend_private/pages/onboarding/no_device/auth_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/clone_audience_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/clone_success_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/cloning_progress_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/social_handle_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/verify_identity_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/welcome_screen.dart';
import 'package:friend_private/providers/no_device_onboarding_provider.dart';
import 'package:provider/provider.dart';

class NoDeviceOnboardingWrapper extends StatefulWidget {
  const NoDeviceOnboardingWrapper({super.key});

  @override
  State<NoDeviceOnboardingWrapper> createState() => _NoDeviceOnboardingWrapperState();
}

class _NoDeviceOnboardingWrapperState extends State<NoDeviceOnboardingWrapper> {
  final PageController _pageController = PageController();
  final _provider = NoDeviceOnboardingProvider();
  int _currentPage = 0;

  void _goToNextPage() {
    if (_currentPage < 6) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
      setState(() {
        _currentPage++;
      });
    } else {
      _completeOnboarding();
    }
  }

  void _goToPreviousPage() {
    if (_currentPage > 0) {
      _pageController.previousPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
      setState(() {
        _currentPage--;
      });
    } else {
      // If we're on the first page, go back to device selection
      SharedPreferencesUtil().hasOmiDevice = null;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => const DeviceSelectionPage()),
      );
    }
  }

  void _completeOnboarding() {
    // Here you can use the provider data to complete the onboarding
    // For example: save the user's name to preferences or make an API call
    SharedPreferencesUtil().onboardingCompleted = true;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (context) => const HomePageWrapper()),
      (route) => false,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _provider.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _provider,
      child: PageView(
        controller: _pageController,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          NoDeviceWelcomeScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          NoDeviceAuthScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          CloneAudienceScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          SocialHandleScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          VerifyIdentityScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          CloningProgressScreen(onNext: _goToNextPage),
          CloneSuccessScreen(onNext: _completeOnboarding),
        ],
      ),
    );
  }
} 