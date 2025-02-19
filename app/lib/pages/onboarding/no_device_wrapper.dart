import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/home/wrapper.dart';
import 'package:friend_private/pages/onboarding/device_selection.dart';
import 'package:friend_private/pages/onboarding/no_device/auth_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/clone_success_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/social_handle_screen.dart';
import 'package:friend_private/pages/onboarding/no_device/verify_identity_screen.dart';
import 'package:friend_private/providers/no_device_onboarding_provider.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/pages/no_device_chat/chat.dart';

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
    if (_currentPage < 3) {  // Updated for 4 screens (0-3)
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
    // Save onboarding completion status
    SharedPreferencesUtil().onboardingCompleted = true;
    
    // Save the twitter handle to preferences if not already saved
    if (SharedPreferencesUtil().verifiedTwitterHandle.isEmpty) {
      SharedPreferencesUtil().verifiedTwitterHandle = _provider.twitterHandle;
    }

    // Navigate to chat screen with provider
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(
        builder: (context) => ChangeNotifierProvider.value(
          value: _provider,
          child: const NoDeviceChatScreen(),
        ),
      ),
      (route) => false,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
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
          SocialHandleScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          VerifyIdentityScreen(onNext: _goToNextPage, onBack: _goToPreviousPage),
          CloneSuccessScreen(onNext: _completeOnboarding),
          NoDeviceAuthScreen(onNext: _completeOnboarding, onBack: _goToPreviousPage),
        ],
      ),
    );
  }
} 