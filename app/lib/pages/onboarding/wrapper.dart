import 'dart:async';
import 'dart:math';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/widgets/omi_device_glow.dart';
import 'package:omi/widgets/onboarding_page_transition.dart';
import 'package:omi/widgets/onboarding_progress_bar.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/omi_logo_spinner.dart';

/// Speech-profile onboarding is a clean black screen — no spinning-dots
/// backdrop on the quiet-place intro or the voice questions. Keep this in
/// lockstep with [_OnboardingWrapperState.kSpeechProfilePage].
@visibleForTesting
const int kOnboardingSpeechProfilePageIndex = 9;

/// Pages that share the spinning-dots backdrop. Speech profile is
/// intentionally absent so Get Started cannot bring the dots back.
@visibleForTesting
const Set<int> kOnboardingSpinnerBackdropPages = {
  3, // name
  4, // found omi
  5, // permissions
  6, // user-review placeholder
  10, // knowledge graph
};

@visibleForTesting
bool onboardingHidesSpinnerBackdrop(int pageIndex) => pageIndex == kOnboardingSpeechProfilePageIndex;

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key, this.forceAuthPage = false, this.forceStartAtSplash = false});

  final bool forceAuthPage;

  // Debug-only: skips the sign-in/onboarding-progress auto-routing below so
  // a fresh instance always lands on the splash page, even if Firebase still
  // has a signed-in session from earlier testing. Used by the debug "restart
  // onboarding" button, which would otherwise remount straight past splash.
  final bool forceStartAtSplash;

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  // Onboarding page indices
  static const int kSplashPage = 0; // Omi wordmark splash before sign-in
  static const int kAuthPage = 1;
  static const int kAiConsentPage = 2; // Data-and-AI disclosure with explicit consent
  static const int kNamePage = 3;
  // Primary language is set automatically to English on the Name step
  // (see its goNext) instead of asking the user to pick one.
  static const int kFoundOmiPage = 4;
  static const int kPermissionsPage = 5;
  static const int kUserReviewPage = 6; // "Loving Omi?" screen
  static const int kWelcomePage = 7;
  static const int kFindDevicesPage = 8;
  static const int kSpeechProfilePage =
      kOnboardingSpeechProfilePageIndex; // Speech profile with questions (requires device)
  static const int kKnowledgeGraphPage = 10; // Memory graph preview
  static const int kCompletePage = 11; // "You're all set" completion screen

  // Special index values used in comparisons
  static const List<int> kHiddenHeaderPages = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

  // Splash, sign-in, and data & privacy all share the same device + glow
  // backdrop (instead of each having its own background), so it never
  // fades or restarts across those three steps.
  bool get _showsDeviceBackdrop =>
      _controller!.index == kSplashPage || _controller!.index == kAuthPage || _controller!.index == kAiConsentPage;

  // Persistent spinning-dots backdrop (see build()) so it doesn't restart
  // when moving between the pages in [kOnboardingSpinnerBackdropPages].
  bool get _showsSpinnerBackdrop => kOnboardingSpinnerBackdropPages.contains(_controller!.index);

  // The spinner only starts fading in once the device backdrop has fully
  // faded out — sequential, not simultaneous — so this lags _showsSpinnerBackdrop
  // by exactly the device's fade-out duration when turning on, and drops
  // immediately when turning off.
  static const Duration _backdropFadeDuration = Duration(milliseconds: 2200);
  bool _spinnerVisible = false;
  Timer? _spinnerRevealTimer;

  TabController? _controller;
  // Plays once, exactly when leaving the splash page, so the device's glow
  // eases on for sign-in without ever being on during the splash itself.
  late final AnimationController _deviceGlowController;
  late final Animation<double> _deviceGlowAnimation;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;
  Future<void>? _knowledgeGraphPrebuildFuture;

  // Speech profile keeps a clean black screen — no spinner on the quiet-place
  // intro or the voice questions. Hold the page invisible until the spinner
  // from permissions has finished fading out.
  bool get _hidesSpinnerForSpeechProfile => onboardingHidesSpinnerBackdrop(_controller!.index);

  @override
  void initState() {
    _controller = TabController(
      length: 12,
      vsync: this,
    ); // Splash, Auth, AiConsent, Name, FoundOmi, Permissions, Review, Welcome, FindDevices, SpeechProfile, KnowledgeGraph, Complete
    _controller!.addListener(() {
      if (!mounted) return;
      setState(() {});
      if (_controller!.previousIndex == kSplashPage && _controller!.index == kAuthPage) {
        _deviceGlowController.forward();
      }
      if (_controller!.index == kSpeechProfilePage && _knowledgeGraphPrebuildFuture == null) {
        _knowledgeGraphPrebuildFuture = _prebuildKnowledgeGraph().catchError((_) {});
      }
      final showsSpinner = _showsSpinnerBackdrop;
      if (showsSpinner != _spinnerVisible) {
        _spinnerRevealTimer?.cancel();
        if (showsSpinner) {
          _spinnerRevealTimer = Timer(_backdropFadeDuration, () {
            if (mounted && _showsSpinnerBackdrop) {
              setState(() => _spinnerVisible = true);
            }
          });
        } else {
          setState(() => _spinnerVisible = false);
        }
      }
    });

    // Initialize animation controllers
    _deviceGlowController = AnimationController(duration: const Duration(milliseconds: 500), vsync: this);
    _deviceGlowAnimation = CurvedAnimation(parent: _deviceGlowController, curve: Curves.easeIn);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (widget.forceStartAtSplash) return;

      // Let's not update permissions here because of Apple's review process
      // if (mounted) {
      //   context.read<OnboardingProvider>().updatePermissions();
      // }

      bool signedIn = false;
      if (!widget.forceAuthPage) {
        try {
          signedIn = AuthService.instance.isSignedIn();
        } catch (_) {
          // Firebase not available (e.g. hermetic tests) — treat as signed out.
          signedIn = false;
        }
      }

      if (signedIn) {
        if (mounted) {
          context.read<HomeProvider>().setupHasSpeakerProfile();
          // The consent gate is checked first and is independent of the
          // server-side onboardingCompleted flag. This ensures every user
          // — including someone signing back into a previously-onboarded
          // account on a fresh install — sees the consent screen at least
          // once before any AI processing begins.
          if (!SharedPreferencesUtil().aiConsentGiven) {
            _controller!.animateTo(kAiConsentPage);
          } else if (SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _controller!.animateTo(kNamePage);
          }
        }
      }
      // If not signed in, it stays at the Splash page (index 0)
    });
    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    _deviceGlowController.dispose();
    _spinnerRevealTimer?.cancel();
    super.dispose();
  }

  Future<void> _routeWithPermissionsCheck(BuildContext context) async {
    if (!SharedPreferencesUtil().permissionsCompleted) {
      final granted = await arePermissionsGranted();
      if (!granted) {
        if (context.mounted) {
          routeToPage(context, const PermissionsInterstitialPage(), replace: true);
        }
        return;
      }
      SharedPreferencesUtil().permissionsCompleted = true;
    }
    if (context.mounted) {
      routeToPage(context, const HomePageWrapper(), replace: true);
    }
  }

  // The device + glow shared by splash, sign-in, and data & privacy —
  // rendered once outside the page-transition subtree so it never fades or
  // restarts while those three steps cross-fade their foreground content
  // over it. The glow itself still eases on via _deviceGlowAnimation.
  Widget _deviceBackground() {
    return Container(
      height: MediaQuery.of(context).size.height,
      width: double.infinity,
      color: Colors.black,
      child: Align(
        alignment: const Alignment(0, -0.45),
        child: _AnimatedDeviceGlow(animation: _deviceGlowAnimation),
      ),
    );
  }

  _goNext() {
    if (_controller!.index < _controller!.length - 1) {
      _controller!.animateTo(_controller!.index + 1);
    }
  }

  Future<void> _prebuildKnowledgeGraph() async {
    try {
      final current = await KnowledgeGraphApi.getKnowledgeGraph();
      final nodes = current['nodes'] as List<dynamic>? ?? const [];
      final hasGraph = nodes.any((node) => (node['id'] ?? '') != 'user-node');
      if (hasGraph) return;
    } catch (_) {
      // Continue to rebuild below.
    }

    await KnowledgeGraphApi.rebuildKnowledgeGraph();
    await KnowledgeGraphApi.waitForGraphStability(
      timeout: const Duration(seconds: 25),
      interval: const Duration(seconds: 2),
      stabilityChecks: 1,
    );
  }

  @override
  Widget build(BuildContext context) {
    List<Widget> pages = [
      _SplashForeground(goNext: _goNext),
      AuthComponent(
        onSignIn: () async {
          if (!mounted) return;
          PlatformManager.instance.analytics.onboardingStepCompleted('Auth');
          context.read<HomeProvider>().setupHasSpeakerProfile();
          // Refresh subscription on sign-in: AppShell only fetches it on mount,
          // so an in-session re-login would otherwise leave it null until the
          // Plan & Usage page is opened (missing Pro badge).
          context.read<UsageProvider>().fetchSubscription();
          IntercomManager.instance.loginIdentifiedUser(SharedPreferencesUtil().uid);
          // Consent is checked first regardless of server-side onboarding
          // state so a returning user signing in on a fresh install still
          // sees the consent screen before any AI processing begins.
          if (!SharedPreferencesUtil().aiConsentGiven) {
            _controller!.animateTo(kAiConsentPage);
          } else if (!widget.forceStartAtSplash && SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _controller!.animateTo(kNamePage);
          }
        },
      ),
      AiConsentWidget(
        onAgree: () async {
          if (!mounted) return;
          SharedPreferencesUtil().aiConsentGiven = true;
          PlatformManager.instance.analytics.onboardingStepCompleted('AI Consent');
          // If the server says this user already completed onboarding, jump
          // straight to home — their first-time onboarding ran in a previous
          // session and we don't want to re-run it. Debug restart
          // (forceStartAtSplash) bypasses this so the whole flow can be
          // walked end to end for testing.
          if (!widget.forceStartAtSplash && SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _controller!.animateTo(kNamePage);
          }
        },
      ),
      NameWidget(
        goNext: () {
          // Onboarding no longer asks the user to pick a language — default
          // everyone to English instead (users can still change it later
          // from Settings). Fire-and-forget so this network call never
          // blocks the onboarding flow from advancing.
          context.read<HomeProvider>().updateUserPrimaryLanguage(
                'en',
                userProvider: context.read<UserProvider>(),
              );
          _goNext(); // Go to Found Omi page
          IntercomManager.instance.updateUser(
            FirebaseAuth.instance.currentUser?.email,
            FirebaseAuth.instance.currentUser?.displayName,
            FirebaseAuth.instance.currentUser?.uid,
          );
          PlatformManager.instance.analytics.onboardingStepCompleted('Name');
        },
      ),
      FoundOmiWidget(
        goNext: () {
          _goNext(); // Go to Permissions page
          PlatformManager.instance.analytics.onboardingStepCompleted('Acquisition Source');
        },
      ),
      PermissionsWidget(
        goNext: () {
          // Go directly to Speech Profile (skip device steps - we use phone mic now).
          // The review step was removed from onboarding to comply with App Store
          // Guideline 5.6.3 (no rating prompts during onboarding).
          _controller!.animateTo(kSpeechProfilePage);
          PlatformManager.instance.analytics.onboardingStepCompleted('Permissions');
        },
      ),
      // Placeholder pages - not used in new flow but kept for index consistency
      Container(), // UserReviewPage placeholder (removed for App Store Guideline 5.6.3)
      Container(), // WelcomePage placeholder
      Container(), // FindDevicesPage placeholder
      widget.forceAuthPage
          ? const SizedBox.shrink()
          : SpeechProfileWidget(
              goNext: () {
                PlatformManager.instance.analytics.onboardingStepCompleted('Speech Profile');
                _controller!.animateTo(kKnowledgeGraphPage);
              },
              onSkip: () {
                PlatformManager.instance.analytics.onboardingStepCompleted('Speech Profile Skipped');
                _controller!.animateTo(kKnowledgeGraphPage);
              },
            ),
      OnboardingKnowledgeGraphStep(
        onContinue: () {
          PlatformManager.instance.analytics.onboardingStepCompleted('Knowledge Graph');
          _controller!.animateTo(kCompletePage);
        },
      ),
      OnboardingCompleteScreen(
        onComplete: () {
          SharedPreferencesUtil().onboardingCompleted = true;
          SharedPreferencesUtil().permissionsCompleted = true;
          updateUserOnboardingState(completed: true);
          PlatformManager.instance.analytics.onboardingCompleted();
          PaintingBinding.instance.imageCache.clear();
          routeToPage(context, const HomePageWrapper(), replace: true);
        },
      ),
    ];

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      // Debug-only: long-press any step to skip straight to the next one
      // (useful when local dev builds can't complete real sign-in, or a
      // step's Continue button is gated on a backend call that has nothing
      // to talk to locally). Compiled out of release builds via kDebugMode.
      onLongPress: kDebugMode ? _goNext : null,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: Stack(
          children: [
            // Both backdrops stay mounted for the whole onboarding flow —
            // never part of the page-transition crossfade, so they never
            // restart — and cross-fade against each other via opacity only,
            // instead of popping in/out instantly, right as data & privacy
            // hands off to the name step.
            IgnorePointer(
              child: AnimatedOpacity(
                opacity: _showsDeviceBackdrop ? 1 : 0,
                duration: _backdropFadeDuration,
                curve: Curves.easeInOut,
                child: _deviceBackground(),
              ),
            ),
            IgnorePointer(
              child: AnimatedOpacity(
                opacity: _spinnerVisible && !_hidesSpinnerForSpeechProfile ? 1 : 0,
                duration: _backdropFadeDuration,
                curve: Curves.easeInOut,
                child: OmiLogoSpinner(
                  burstTrigger: _controller!.index,
                  visible: _spinnerVisible && !_hidesSpinnerForSpeechProfile,
                ),
              ),
            ),
            OnboardingPageTransition(
              pageKey: _controller!.index,
              // Speech profile needs the spinner backdrop gone first (see
              // _hidesSpinnerForSpeechProfile) — hold this page invisible until
              // that fade-out finishes instead of cross-fading over it.
              entryDelay: _hidesSpinnerForSpeechProfile ? _backdropFadeDuration : Duration.zero,
              child: _controller!.index == kSplashPage || _controller!.index == kAuthPage
                  ? pages[_controller!.index]
                  : _controller!.index == kAiConsentPage ||
                          _controller!.index == kNamePage ||
                          _controller!.index == kFoundOmiPage ||
                          _controller!.index == kPermissionsPage ||
                          _controller!.index == kUserReviewPage ||
                          _controller!.index == kWelcomePage ||
                          _controller!.index == kSpeechProfilePage ||
                          _controller!.index == kKnowledgeGraphPage ||
                          _controller!.index == kCompletePage
                      ? pages[_controller!.index]
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
                                          animatedBackground:
                                              _controller!.index != -1 && onboardingProvider.isConnected,
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
                                      height: (_controller!.index == kFindDevicesPage ||
                                              _controller!.index == kSpeechProfilePage)
                                          ? max(
                                              MediaQuery.of(context).size.height - 500 - 10,
                                              maxHeightWithTextScale(context, _controller!.index),
                                            )
                                          : max(
                                              MediaQuery.of(context).size.height - 500 - 30,
                                              maxHeightWithTextScale(context, _controller!.index),
                                            ),
                                      child: Padding(
                                        padding:
                                            EdgeInsets.only(bottom: MediaQuery.sizeOf(context).height <= 700 ? 10 : 64),
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
                            ],
                          ),
                        ),
            ),
            // Progress bar lives outside the page-transition subtree so it
            // persists across step changes instead of being torn down and
            // re-animating from zero on every advance.
            if (_controller!.index != kSplashPage && _controller!.index != kCompletePage)
              Padding(
                padding: const EdgeInsets.fromLTRB(32, 90, 32, 0),
                child: OnboardingProgressBar(
                  currentStep: _controller!.index - 1,
                  totalSteps: _controller!.length - 1,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// The device + glow, isolated in its own widget so [AnimatedBuilder] only
/// rebuilds this small subtree on every animation tick instead of the whole
/// backdrop.
class _AnimatedDeviceGlow extends StatelessWidget {
  final Animation<double> animation;

  const _AnimatedDeviceGlow({required this.animation});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return Transform.scale(scale: 0.85, child: OmiDeviceGlow(glowIntensity: animation.value));
      },
    );
  }
}

/// Splash's foreground content only (wordmark, tagline, Get Started) — the
/// device itself is rendered by the wrapper's persistent device backdrop so
/// it doesn't restart when this cross-fades into sign-in.
class _SplashForeground extends StatefulWidget {
  final VoidCallback goNext;

  const _SplashForeground({required this.goNext});

  @override
  State<_SplashForeground> createState() => _SplashForegroundState();
}

class _SplashForegroundState extends State<_SplashForeground> with TickerProviderStateMixin {
  late final AnimationController _entrance;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(duration: const Duration(milliseconds: 1100), vsync: this)..forward();
  }

  @override
  void dispose() {
    _entrance.dispose();
    super.dispose();
  }

  Animation<double> _stagger(double start, double end) {
    return CurvedAnimation(parent: _entrance, curve: Interval(start, end, curve: Curves.easeOutCubic));
  }

  Widget _reveal(Animation<double> animation, {double dy = 18, required Widget child}) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return Opacity(
          opacity: animation.value,
          child: Transform.translate(offset: Offset(0, dy * (1 - animation.value)), child: child),
        );
      },
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    final titleReveal = _stagger(0.35, 0.75);
    final taglineReveal = _stagger(0.45, 0.85);
    final buttonReveal = _stagger(0.6, 1.0);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          children: [
            const Spacer(flex: 2),
            // Empty space matching the device's footprint — the device
            // itself is drawn by the wrapper's persistent backdrop, behind
            // this content.
            const SizedBox(width: 320, height: 320),
            const SizedBox(height: 32),
            _reveal(
              titleReveal,
              child: const Text(
                'Omi',
                style: TextStyle(color: Colors.white, fontSize: 40, fontWeight: FontWeight.bold, fontFamily: 'Manrope'),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 8),
            _reveal(
              taglineReveal,
              child: Text(
                context.l10n.onboardingSplashTagline,
                style: const TextStyle(color: Colors.white70, fontSize: 18, fontFamily: 'Manrope'),
                textAlign: TextAlign.center,
              ),
            ),
            const Spacer(flex: 4),
            _reveal(
              buttonReveal,
              child: SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: widget.goNext,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                    elevation: 0,
                  ),
                  child: Text(
                    context.l10n.getStarted,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],
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
