import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/desktop/pages/desktop_home_page.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_auth_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_complete_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_language_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_name_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_permissions_screen.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopOnboardingWrapper extends StatefulWidget {
  const DesktopOnboardingWrapper({super.key});

  @override
  State<DesktopOnboardingWrapper> createState() => _DesktopOnboardingWrapperState();
}

class _DesktopOnboardingWrapperState extends State<DesktopOnboardingWrapper> with TickerProviderStateMixin {
  int _currentStep = 0;
  final PageController _pageController = PageController();
  late AnimationController _fadeController;
  late AnimationController _slideController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  List<OnboardingStep> _getSteps(AppLocalizations l10n) => [
        OnboardingStep(
          id: 'auth',
          title: l10n.onboardingSignIn,
          description: l10n.onboardingWelcomeToOmi,
          icon: Icons.login_rounded,
        ),
        OnboardingStep(
          id: 'name',
          title: l10n.onboardingYourName,
          description: l10n.onboardingTellUsAboutYourself,
          icon: Icons.person_rounded,
        ),
        OnboardingStep(
          id: 'language',
          title: l10n.onboardingLanguage,
          description: l10n.onboardingChooseYourPreference,
          icon: Icons.language_rounded,
        ),
        OnboardingStep(
          id: 'permissions',
          title: l10n.onboardingPermissions,
          description: l10n.onboardingGrantRequiredAccess,
          icon: Icons.shield_rounded,
        ),
        OnboardingStep(
          id: 'complete',
          title: l10n.onboardingComplete,
          description: l10n.onboardingYoureAllSet,
          icon: Icons.check_circle_rounded,
        ),
      ];

  List<Widget> get _screens => [
        DesktopAuthScreen(onSignIn: _handleSignIn),
        DesktopNameScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopLanguageScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopPermissionsScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopCompleteScreen(onComplete: _completeOnboarding, onBack: _previousStep),
      ];

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeInOut),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0.05, 0),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _fadeController.forward();
    _slideController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _slideController.dispose();
    _pageController.dispose();
    super.dispose();
  }

  void _nextStep() {
    if (_currentStep < _screens.length - 1) {
      setState(() {
        _currentStep++;
      });
      _pageController.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOutCubic,
      );
      _animateTransition();
    }
  }

  void _previousStep() {
    if (_currentStep > 0) {
      setState(() {
        _currentStep--;
      });
      _pageController.previousPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOutCubic,
      );
      _animateTransition();
    }
  }

  void _animateTransition() {
    _fadeController.reset();
    _slideController.reset();
    _fadeController.forward();
    _slideController.forward();
  }

  void _handleSignIn() {
    SharedPreferencesUtil().hasOmiDevice = true;
    SharedPreferencesUtil().verifiedPersonaId = null;
    MixpanelManager().onboardingStepCompleted('Auth');
    if (context.mounted) {
      context.read<HomeProvider>().setupHasSpeakerProfile();
    }
    IntercomManager.instance.loginIdentifiedUser(SharedPreferencesUtil().uid);
    IntercomManager.instance.updateUser(
      FirebaseAuth.instance.currentUser!.email,
      FirebaseAuth.instance.currentUser!.displayName,
      FirebaseAuth.instance.currentUser!.uid,
    );
    _nextStep();
  }

  void _completeOnboarding() {
    SharedPreferencesUtil().onboardingCompleted = true;
    updateUserOnboardingState(completed: true);
    routeToPage(context, const DesktopHomePage(), replace: true);
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      body: Container(
        decoration: BoxDecoration(
          gradient: responsive.backgroundGradient,
        ),
        child: SafeArea(
          child: AnimatedBuilder(
            animation: Listenable.merge([_fadeAnimation, _slideAnimation]),
            builder: (context, child) {
              return FadeTransition(
                opacity: _fadeAnimation,
                child: SlideTransition(
                  position: _slideAnimation,
                  child: PageView.builder(
                    controller: _pageController,
                    physics: const NeverScrollableScrollPhysics(),
                    onPageChanged: (index) {
                      setState(() {
                        _currentStep = index;
                      });
                    },
                    itemCount: _screens.length,
                    itemBuilder: (context, index) {
                      return _screens[index];
                    },
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class OnboardingStep {
  final String id;
  final String title;
  final String description;
  final IconData icon;

  OnboardingStep({
    required this.id,
    required this.title,
    required this.description,
    required this.icon,
  });
}
