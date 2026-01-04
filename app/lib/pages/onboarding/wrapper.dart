import 'dart:math';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/user_review_page.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:provider/provider.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key});

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  // Onboarding page indices
  static const int kAuthPage = 0;
  static const int kNamePage = 1;
  static const int kPrimaryLanguagePage = 2;
  static const int kPermissionsPage = 3;
  static const int kUserReviewPage = 4; // "Loving Omi?" screen
  static const int kWelcomePage = 5;
  static const int kFindDevicesPage = 6;
  static const int kSpeechProfilePage = 7; // Speech profile with questions (requires device)

  // Special index values used in comparisons
  static const List<int> kHiddenHeaderPages = [-1, 0, 1, 2, 3, 4, 5, 6, 7];

  TabController? _controller;
  late AnimationController _backgroundAnimationController;
  late Animation<double> _backgroundFadeAnimation;
  String _currentBackgroundImage = Assets.images.onboardingBg2.path;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;
  SpeechProfileProvider? _speechProfileProvider;

  @override
  void initState() {
    _speechProfileProvider = SpeechProfileProvider();
    _controller = TabController(
        length: 8, vsync: this); // Auth, Name, Lang, Permissions, Review, Welcome, FindDevices, SpeechProfile
    _controller!.addListener(() {
      setState(() {});
      // Update background image when page changes
      _updateBackgroundImage(_controller!.index);
      // Precache next image for smoother transitions
      _precacheNextImage(_controller!.index);
    });

    // Initialize animation controllers
    _backgroundAnimationController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );

    // Initialize animations
    _backgroundFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _backgroundAnimationController,
      curve: Curves.easeInOut,
    ));

    // Start initial animations
    _backgroundAnimationController.forward();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Let's not update permissions here because of Apple's review process
      // if (mounted) {
      //   context.read<OnboardingProvider>().updatePermissions();
      // }

      if (AuthService.instance.isSignedIn()) {
        // && !SharedPreferencesUtil().onboardingCompleted
        if (mounted) {
          context.read<HomeProvider>().setupHasSpeakerProfile();
          if (SharedPreferencesUtil().onboardingCompleted) {
            routeToPage(context, const HomePageWrapper(), replace: true);
          } else {
            _controller!.animateTo(kNamePage);
          }
        }
      }
      // If not signed in, it stays at the Auth page (index 0)
    });
    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    _backgroundAnimationController.dispose();
    _speechProfileProvider?.dispose();
    super.dispose();
  }

  _goNext() {
    if (_controller!.index < _controller!.length - 1) {
      _controller!.animateTo(_controller!.index + 1);
    }
  }

  void _updateBackgroundImage(int pageIndex) {
    String newImage = _currentBackgroundImage;

    switch (pageIndex) {
      case kAuthPage:
        newImage = Assets.images.onboardingBg2.path;
        break;
      case kNamePage:
        newImage = Assets.images.onboardingBg1.path;
        break;
      case kPrimaryLanguagePage:
        newImage = Assets.images.onboardingBg4.path;
        break;
      case kPermissionsPage:
        newImage = Assets.images.onboardingBg3.path;
        break;
      case kUserReviewPage:
        newImage = Assets.images.onboardingBg6.path;
        break;
      default:
        newImage = Assets.images.onboardingBg1.path;
        break;
    }

    if (_currentBackgroundImage != newImage) {
      setState(() {
        _currentBackgroundImage = newImage;
      });
      _backgroundAnimationController.reset();
      _backgroundAnimationController.forward();
    }
  }

  void _precacheNextImage(int currentIndex) {
    // Get the next background image path
    String? nextImagePath = _getBackgroundImageForIndex(currentIndex + 1);
    if (nextImagePath != null && mounted) {
      // Precache the next image
      precacheImage(
        ResizeImage(
          AssetImage(nextImagePath),
          width: (MediaQuery.of(context).size.width * MediaQuery.of(context).devicePixelRatio).round(),
          height: (MediaQuery.of(context).size.height * MediaQuery.of(context).devicePixelRatio).round(),
        ),
        context,
      );
    }
  }

  String? _getBackgroundImageForIndex(int pageIndex) {
    switch (pageIndex) {
      case kAuthPage:
        return Assets.images.onboardingBg2.path;
      case kNamePage:
        return Assets.images.onboardingBg1.path;
      case kPrimaryLanguagePage:
        return Assets.images.onboardingBg4.path;
      case kPermissionsPage:
        return Assets.images.onboardingBg3.path;
      case kUserReviewPage:
        return Assets.images.onboardingBg6.path;
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    List<Widget> pages = [
      AuthComponent(
        onSignIn: () {
          SharedPreferencesUtil().hasOmiDevice = true;
          SharedPreferencesUtil().verifiedPersonaId = null;
          MixpanelManager().onboardingStepCompleted('Auth');
          context.read<HomeProvider>().setupHasSpeakerProfile();
          IntercomManager.instance.loginIdentifiedUser(SharedPreferencesUtil().uid);
          if (SharedPreferencesUtil().onboardingCompleted) {
            routeToPage(context, const HomePageWrapper(), replace: true);
          } else {
            _goNext(); // Go to Name page
          }
        },
      ),
      NameWidget(goNext: () {
        _goNext(); // Go to Primary Language page
        IntercomManager.instance.updateUser(
          FirebaseAuth.instance.currentUser!.email,
          FirebaseAuth.instance.currentUser!.displayName,
          FirebaseAuth.instance.currentUser!.uid,
        );
        MixpanelManager().onboardingStepCompleted('Name');
      }),
      PrimaryLanguageWidget(goNext: () {
        _goNext(); // Go to Permissions page
        MixpanelManager().onboardingStepCompleted('Primary Language');
      }),
      PermissionsWidget(
        goNext: () {
          _goNext(); // Go to User Review page
          MixpanelManager().onboardingStepCompleted('Permissions');
        },
      ),
      UserReviewPage(
        goNext: () {
          // Go directly to Speech Profile (skip device steps - we use phone mic now)
          _controller!.animateTo(kSpeechProfilePage);
          MixpanelManager().onboardingStepCompleted('User Review');
        },
      ),
      // Placeholder pages - not used in new flow but kept for index consistency
      Container(), // WelcomePage placeholder
      Container(), // FindDevicesPage placeholder
      ChangeNotifierProvider.value(
        value: _speechProfileProvider!,
        child: SpeechProfileWidget(
          goNext: () {
            // Speech profile complete, finish onboarding
            SharedPreferencesUtil().onboardingCompleted = true;
            MixpanelManager().onboardingStepCompleted('Speech Profile');
            PaintingBinding.instance.imageCache.clear();
            routeToPage(context, const HomePageWrapper(), replace: true);
          },
          onSkip: () {
            // Skip speech profile, finish onboarding
            SharedPreferencesUtil().onboardingCompleted = true;
            MixpanelManager().onboardingStepCompleted('Speech Profile Skipped');
            PaintingBinding.instance.imageCache.clear();
            routeToPage(context, const HomePageWrapper(), replace: true);
          },
        ),
      ),
    ];

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: _controller!.index == kAuthPage
            ? Stack(
                children: [
                  // Animated background image for auth page
                  FadeTransition(
                    opacity: _backgroundFadeAnimation,
                    child: Container(
                      height: MediaQuery.of(context).size.height,
                      decoration: BoxDecoration(
                        image: DecorationImage(
                          image: ResizeImage(
                            AssetImage(_currentBackgroundImage),
                            width:
                                (MediaQuery.of(context).size.width * MediaQuery.of(context).devicePixelRatio).round(),
                            height:
                                (MediaQuery.of(context).size.height * MediaQuery.of(context).devicePixelRatio).round(),
                          ),
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  ),
                  // Auth component (no transition for content)
                  pages[kAuthPage],
                ],
              )
            : _controller!.index == kNamePage ||
                    _controller!.index == kPrimaryLanguagePage ||
                    _controller!.index == kPermissionsPage ||
                    _controller!.index == kUserReviewPage ||
                    _controller!.index == kWelcomePage
                ? Stack(
                    children: [
                      // Animated background image for name, language, permissions, and user review pages (not welcome page)
                      if (_controller!.index != kWelcomePage)
                        FadeTransition(
                          opacity: _backgroundFadeAnimation,
                          child: Container(
                            height: MediaQuery.of(context).size.height,
                            decoration: BoxDecoration(
                              image: DecorationImage(
                                image: ResizeImage(
                                  AssetImage(_currentBackgroundImage),
                                  width: (MediaQuery.of(context).size.width * MediaQuery.of(context).devicePixelRatio)
                                      .round(),
                                  height: (MediaQuery.of(context).size.height * MediaQuery.of(context).devicePixelRatio)
                                      .round(),
                                ),
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                        ),
                      // Page component (no transition for content)
                      pages[_controller!.index],
                      // Progress dots for name, language, permissions, user review, and welcome pages
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 56, 16, 0),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: List.generate(
                            7,
                            (index) {
                              int pageIndex = index + 1; // Name=1, Lang=2, ..., Speech=7
                              return Container(
                                margin: const EdgeInsets.symmetric(horizontal: 4.0),
                                width: pageIndex == _controller!.index ? 12.0 : 8.0,
                                height: pageIndex == _controller!.index ? 12.0 : 8.0,
                                decoration: BoxDecoration(
                                  color: pageIndex <= _controller!.index
                                      ? Theme.of(context).colorScheme.secondary
                                      : Colors.grey.shade400,
                                  shape: BoxShape.circle,
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                      // Back button for language and permissions pages
                      if (_controller!.index > kNamePage)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 40, 0, 0),
                          child: Align(
                            alignment: Alignment.topLeft,
                            child: Container(
                              width: 36,
                              height: 36,
                              margin: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: Colors.grey.withOpacity(0.3),
                                shape: BoxShape.circle,
                              ),
                              child: IconButton(
                                padding: EdgeInsets.zero,
                                onPressed: () {
                                  if (_controller!.index > kNamePage) {
                                    _controller!.animateTo(_controller!.index - 1);
                                  }
                                },
                                icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
                              ),
                            ),
                          ),
                        ),
                    ],
                  )
                : SingleChildScrollView(
                    child: Stack(
                      children: [
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: ListView(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            children: [
                              Consumer<OnboardingProvider>(
                                builder: (context, onboardingProvider, child) {
                                  return DeviceAnimationWidget(
                                    animatedBackground: _controller!.index != -1 && onboardingProvider.isConnected,
                                    isConnected: onboardingProvider.isConnected,
                                    deviceName: onboardingProvider.deviceName,
                                  );
                                },
                              ),
                              const SizedBox(height: 24),
                              kHiddenHeaderPages.contains(_controller?.index)
                                  ? const SizedBox.shrink()
                                  : Padding(
                                      padding: const EdgeInsets.symmetric(horizontal: 16),
                                      child: Text(
                                        context.l10n.personalGrowthJourney,
                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 24),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                              SizedBox(
                                height:
                                    (_controller!.index == kFindDevicesPage || _controller!.index == kSpeechProfilePage)
                                        ? max(MediaQuery.of(context).size.height - 500 - 10,
                                            maxHeightWithTextScale(context, _controller!.index))
                                        : max(MediaQuery.of(context).size.height - 500 - 30,
                                            maxHeightWithTextScale(context, _controller!.index)),
                                child: Padding(
                                  padding: EdgeInsets.only(bottom: MediaQuery.sizeOf(context).height <= 700 ? 10 : 64),
                                  child: TabBarView(
                                    controller: _controller,
                                    physics: const NeverScrollableScrollPhysics(),
                                    children: pages,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (_controller!.index > kNamePage)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 40, 0, 0),
                            child: Align(
                              alignment: Alignment.topLeft,
                              child: Container(
                                width: 36,
                                height: 36,
                                margin: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: Colors.grey.withOpacity(0.3),
                                  shape: BoxShape.circle,
                                ),
                                child: IconButton(
                                  padding: EdgeInsets.zero,
                                  onPressed: () {
                                    if (_controller!.index == kSpeechProfilePage) {
                                      _speechProfileProvider?.close();
                                      _controller!.animateTo(kUserReviewPage);
                                    } else if (_controller!.index > kNamePage) {
                                      _controller!.animateTo(_controller!.index - 1);
                                    }
                                  },
                                  icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
                                ),
                              ),
                            ),
                          ),
                        if (_controller!.index != kAuthPage)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 56, 16, 0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: List.generate(
                                6,
                                (index) {
                                  int pageIndex = index + 1; // Name=1, Lang=2, ..., Speech=6
                                  return Container(
                                    margin: const EdgeInsets.symmetric(horizontal: 4.0),
                                    width: pageIndex == _controller!.index ? 12.0 : 8.0,
                                    height: pageIndex == _controller!.index ? 12.0 : 8.0,
                                    decoration: BoxDecoration(
                                      color: pageIndex <= _controller!.index
                                          ? Theme.of(context).colorScheme.secondary
                                          : Colors.grey.shade400,
                                      shape: BoxShape.circle,
                                    ),
                                  );
                                },
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
      ),
    );
  }
}

double maxHeightWithTextScale(BuildContext context, int index) {
  double textScaleFactor = MediaQuery.of(context).textScaleFactor;
  if (textScaleFactor > 1.0) {
    if (index == _OnboardingWrapperState.kAuthPage) {
      return 200;
    } else {
      return 405;
    }
  } else {
    return 305;
  }
}
