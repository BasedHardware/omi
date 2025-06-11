import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/desktop/pages/desktop_home_page.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_welcome_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_name_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_language_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_permissions_screen.dart';
import 'package:omi/desktop/pages/onboarding/screens/desktop_complete_screen.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Beautiful desktop onboarding wrapper with fully responsive UI
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

  final List<OnboardingStep> _steps = [
    OnboardingStep(
      id: 'welcome',
      title: 'Welcome',
      description: 'Get started with Omi',
      icon: Icons.waving_hand_rounded,
    ),
    OnboardingStep(
      id: 'name',
      title: 'Your Name',
      description: 'Tell us about yourself',
      icon: Icons.person_rounded,
    ),
    OnboardingStep(
      id: 'language',
      title: 'Language',
      description: 'Choose your preference',
      icon: Icons.language_rounded,
    ),
    OnboardingStep(
      id: 'permissions',
      title: 'Permissions',
      description: 'Grant required access',
      icon: Icons.security_rounded,
    ),
    OnboardingStep(
      id: 'complete',
      title: 'Complete',
      description: 'You\'re all set',
      icon: Icons.check_circle_rounded,
    ),
  ];

  List<Widget> get _screens => [
        DesktopWelcomeScreen(onNext: _nextStep),
        DesktopNameScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopLanguageScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopPermissionsScreen(onNext: _nextStep, onBack: _previousStep),
        DesktopCompleteScreen(onComplete: _completeOnboarding),
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
    if (_currentStep < _steps.length - 1) {
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

  void _completeOnboarding() {
    SharedPreferencesUtil().onboardingCompleted = true;
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
        child: Row(
          children: [
            // Premium Left Sidebar
            Container(
              width: responsive.sidebarWidth(),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
                border: Border(
                  right: BorderSide(
                    color: ResponsiveHelper.backgroundTertiary,
                    width: 1,
                  ),
                ),
              ),
              child: Column(
                children: [
                  // Header with Logo
                  Container(
                    padding: responsive.sidebarPadding(),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(height: responsive.spacing(baseSpacing: 20)),
                        // Premium Logo Section
                        Row(
                          children: [
                            Container(
                              width: responsive.iconSize(baseSize: 48),
                              height: responsive.iconSize(baseSize: 48),
                              decoration: BoxDecoration(
                                gradient: responsive.purpleGradient,
                                borderRadius: BorderRadius.circular(responsive.radiusMedium),
                                boxShadow: responsive.glowShadow,
                              ),
                              child: Icon(
                                Icons.psychology_rounded,
                                color: Colors.white,
                                size: responsive.iconSize(baseSize: 28),
                              ),
                            ),
                            SizedBox(width: responsive.spacing(baseSpacing: 12)),
                            Text(
                              'Omi',
                              style: responsive.headlineMedium.copyWith(
                                fontWeight: FontWeight.w800,
                                letterSpacing: -0.5,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: responsive.spacing(baseSpacing: 40)),
                        // Subtitle
                        Text(
                          'Setup your AI companion',
                          style: responsive.bodyLarge.copyWith(
                            color: ResponsiveHelper.textTertiary,
                          ),
                        ),
                        SizedBox(height: responsive.spacing(baseSpacing: 32)),
                      ],
                    ),
                  ),

                  // Steps List
                  Expanded(
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: responsive.spacing(baseSpacing: 24),
                      ),
                      child: Column(
                        children: [
                          ...List.generate(_steps.length, (index) {
                            final step = _steps[index];
                            final isActive = index == _currentStep;
                            final isCompleted = index < _currentStep;

                            return AnimatedContainer(
                              duration: const Duration(milliseconds: 300),
                              margin: EdgeInsets.only(
                                bottom: responsive.spacing(baseSpacing: 16),
                              ),
                              child: _buildStepItem(
                                step: step,
                                index: index,
                                isActive: isActive,
                                isCompleted: isCompleted,
                                responsive: responsive,
                              ),
                            );
                          }),
                        ],
                      ),
                    ),
                  ),

                  // Progress Section
                  Container(
                    padding: responsive.sidebarPadding(),
                    child: Column(
                      children: [
                        // Progress Bar
                        Container(
                          width: double.infinity,
                          height: responsive.spacing(baseSpacing: 8),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundTertiary,
                            borderRadius: BorderRadius.circular(responsive.radiusSmall),
                          ),
                          child: FractionallySizedBox(
                            alignment: Alignment.centerLeft,
                            widthFactor: (_currentStep + 1) / _steps.length,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: responsive.purpleGradient,
                                borderRadius: BorderRadius.circular(responsive.radiusSmall),
                                boxShadow: responsive.glowShadow,
                              ),
                            ),
                          ),
                        ),
                        SizedBox(height: responsive.spacing(baseSpacing: 16)),
                        // Progress Text
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Step ${_currentStep + 1} of ${_steps.length}',
                              style: responsive.bodySmall.copyWith(
                                color: ResponsiveHelper.textTertiary,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            Text(
                              '${((_currentStep + 1) / _steps.length * 100).round()}%',
                              style: responsive.bodySmall.copyWith(
                                color: ResponsiveHelper.purplePrimary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Main Content Area
            Expanded(
              child: AnimatedBuilder(
                animation: Listenable.merge([_fadeAnimation, _slideAnimation]),
                builder: (context, child) {
                  return FadeTransition(
                    opacity: _fadeAnimation,
                    child: SlideTransition(
                      position: _slideAnimation,
                      child: Container(
                        width: double.infinity,
                        height: double.infinity,
                        padding: responsive.contentPadding(),
                        child: Column(
                          children: [
                            // Content Area
                            Expanded(
                              child: PageView.builder(
                                controller: _pageController,
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

                            // Navigation Buttons
                            // _buildNavigationButtons(responsive),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStepItem({
    required OnboardingStep step,
    required int index,
    required bool isActive,
    required bool isCompleted,
    required ResponsiveHelper responsive,
  }) {
    return InkWell(
      onTap: () {
        if (index <= _currentStep) {
          setState(() {
            _currentStep = index;
          });
          _pageController.animateToPage(
            index,
            duration: const Duration(milliseconds: 400),
            curve: Curves.easeInOutCubic,
          );
          _animateTransition();
        }
      },
      borderRadius: BorderRadius.circular(responsive.radiusMedium),
      child: Container(
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
        decoration: BoxDecoration(
          color: isActive
              ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
              : isCompleted
                  ? ResponsiveHelper.backgroundTertiary
                  : Colors.transparent,
          borderRadius: BorderRadius.circular(responsive.radiusMedium),
          border: Border.all(
            color: isActive ? ResponsiveHelper.purplePrimary.withOpacity(0.3) : Colors.transparent,
            width: 1,
          ),
        ),
        child: Row(
          children: [
            // Step Icon
            Container(
              width: responsive.iconSize(baseSize: 40),
              height: responsive.iconSize(baseSize: 40),
              decoration: BoxDecoration(
                color: isCompleted
                    ? ResponsiveHelper.purplePrimary
                    : isActive
                        ? ResponsiveHelper.purplePrimary.withOpacity(0.2)
                        : ResponsiveHelper.backgroundQuaternary,
                borderRadius: BorderRadius.circular(responsive.radiusSmall),
                boxShadow: isActive ? responsive.softShadow : null,
              ),
              child: Icon(
                isCompleted ? Icons.check_rounded : step.icon,
                color: isCompleted || isActive ? Colors.white : ResponsiveHelper.textQuaternary,
                size: responsive.iconSize(baseSize: 20),
              ),
            ),
            SizedBox(width: responsive.spacing(baseSpacing: 12)),
            // Step Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    step.title,
                    style: responsive.titleMedium.copyWith(
                      color: isActive
                          ? ResponsiveHelper.textPrimary
                          : isCompleted
                              ? ResponsiveHelper.textSecondary
                              : ResponsiveHelper.textTertiary,
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 2)),
                  Text(
                    step.description,
                    style: responsive.bodySmall.copyWith(
                      color: isActive ? ResponsiveHelper.textSecondary : ResponsiveHelper.textQuaternary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNavigationButtons(ResponsiveHelper responsive) {
    return Container(
      padding: EdgeInsets.only(
        top: responsive.spacing(baseSpacing: 24),
      ),
      child: Row(
        children: [
          // Back Button
          if (_currentStep > 0)
            Container(
              margin: EdgeInsets.only(
                right: responsive.spacing(baseSpacing: 16),
              ),
              child: OutlinedButton.icon(
                onPressed: _previousStep,
                icon: Icon(
                  Icons.arrow_back_rounded,
                  size: responsive.iconSize(baseSize: 20),
                ),
                label: Text(
                  'Back',
                  style: responsive.labelMedium,
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: ResponsiveHelper.textSecondary,
                  side: BorderSide(
                    color: ResponsiveHelper.backgroundTertiary,
                    width: 1,
                  ),
                  backgroundColor: ResponsiveHelper.backgroundSecondary,
                  padding: EdgeInsets.symmetric(
                    horizontal: responsive.spacing(baseSpacing: 24),
                    vertical: responsive.spacing(baseSpacing: 12),
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(responsive.radiusMedium),
                  ),
                  minimumSize: Size(
                    responsive.responsiveWidth(baseWidth: 120),
                    responsive.buttonHeight(),
                  ),
                ),
              ),
            ),

          const Spacer(),

          // Next/Continue Button
          Container(
            decoration: BoxDecoration(
              gradient: responsive.purpleGradient,
              borderRadius: BorderRadius.circular(responsive.radiusMedium),
              boxShadow: responsive.mediumShadow,
            ),
            child: ElevatedButton.icon(
              onPressed: _nextStep,
              icon: _currentStep == _steps.length - 1
                  ? Icon(
                      Icons.check_rounded,
                      size: responsive.iconSize(baseSize: 20),
                    )
                  : Icon(
                      Icons.arrow_forward_rounded,
                      size: responsive.iconSize(baseSize: 20),
                    ),
              label: Text(
                _currentStep == _steps.length - 1 ? 'Complete' : 'Continue',
                style: responsive.labelMedium.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.transparent,
                foregroundColor: Colors.white,
                shadowColor: Colors.transparent,
                padding: EdgeInsets.symmetric(
                  horizontal: responsive.spacing(baseSpacing: 32),
                  vertical: responsive.spacing(baseSpacing: 12),
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(responsive.radiusMedium),
                ),
                minimumSize: Size(
                  responsive.responsiveWidth(baseWidth: 160),
                  responsive.buttonHeight(),
                ),
              ),
            ),
          ),
        ],
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
