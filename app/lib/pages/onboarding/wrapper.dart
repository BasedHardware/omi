import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/clear_user_state.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key, this.forceAuthPage = false});

  final bool forceAuthPage;

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  // Onboarding page indices
  static const int kAuthPage = 0;
  static const int kAiConsentPage = 1; // Data-and-AI disclosure with explicit consent
  static const int kNamePage = 2;
  static const int kPrimaryLanguagePage = 3;
  static const int kFoundOmiPage = 4;
  static const int kPermissionsPage = 5;
  static const int kSpeechProfilePage = 6; // Guided voice introduction
  static const int kKnowledgeGraphPage = 7; // Memory graph preview
  static const int kCompletePage = 8; // "You're all set" completion screen
  static const int kPageCount = 9;

  /// The steps the progress dots count, in order. Auth, consent and the completion screen are not
  /// steps: they are shown without dots.
  static const List<int> kProgressSteps = [
    kNamePage,
    kPrimaryLanguagePage,
    kFoundOmiPage,
    kPermissionsPage,
    kSpeechProfilePage,
    kKnowledgeGraphPage,
  ];

  TabController? _controller;
  late AnimationController _backgroundAnimationController;
  late Animation<double> _backgroundFadeAnimation;
  String _currentBackgroundImage = Assets.images.onboardingBg2.path;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;
  Future<void>? _knowledgeGraphPrebuildFuture;
  ProductAttempt? _onboardingAttempt;

  @override
  void initState() {
    super.initState();
    if (!widget.forceAuthPage && !SharedPreferencesUtil().onboardingCompleted) {
      _onboardingAttempt = ProductTelemetry.instance.start(
        ProductJourney.onboarding,
        surface: ProductSurface.onboarding,
      );
    }
    // Auth, AiConsent, Name, Lang, FoundOmi, Permissions, SpeechProfile, KnowledgeGraph, Complete
    _controller = TabController(length: kPageCount, vsync: this);
    _controller!.addListener(() {
      if (!mounted) return;
      setState(() {});
      _rememberStep(_controller!.index);
      // Update background image when page changes
      _updateBackgroundImage(_controller!.index);
      // Precache next image for smoother transitions
      _precacheNextImage(_controller!.index);
      if (_controller!.index == kSpeechProfilePage && _knowledgeGraphPrebuildFuture == null) {
        _knowledgeGraphPrebuildFuture = _prebuildKnowledgeGraph().catchError((_) {});
      }
    });

    // Initialize animation controllers
    _backgroundAnimationController = AnimationController(duration: const Duration(milliseconds: 500), vsync: this);

    // Initialize animations
    _backgroundFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _backgroundAnimationController, curve: Curves.easeInOut));

    // Start initial animations
    _backgroundAnimationController.forward();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Let's not update permissions here because of Apple's review process
      // if (mounted) {
      //   context.read<OnboardingProvider>().updatePermissions();
      // }

      if (!widget.forceAuthPage && AuthService.instance.isSignedIn()) {
        // && !SharedPreferencesUtil().onboardingCompleted
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
            _controller!.animateTo(_resumeStep());
          }
        }
      }
      // If not signed in, it stays at the Auth page (index 0)
    });
  }

  @override
  void dispose() {
    _onboardingAttempt?.complete(ProductOutcome.unobserved, failure: ProductFailure.incomplete);
    _controller?.dispose();
    _backgroundAnimationController.dispose();
    super.dispose();
  }

  void _completeOnboardingTelemetry() {
    _onboardingAttempt?.complete(ProductOutcome.success);
    _onboardingAttempt = null;
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

  void _goNext() {
    if (_controller!.index < _controller!.length - 1) {
      _controller!.animateTo(_controller!.index + 1);
    }
  }

  // ---- Resume and back ----------------------------------------------------------------------

  /// Per-account key so a different account signing in on this phone starts at the Name step.
  String get _resumeKey => 'onboarding/resumeStep/${SharedPreferencesUtil().uid}';

  void _rememberStep(int index) {
    if (widget.forceAuthPage || !kProgressSteps.contains(index)) return;
    SharedPreferencesUtil().saveInt(_resumeKey, index);
  }

  /// The step to reopen after the app was killed mid-onboarding: the last step the reader reached,
  /// or Name.
  int _resumeStep() {
    final saved = SharedPreferencesUtil().getInt(_resumeKey, defaultValue: kNamePage);
    return kProgressSteps.contains(saved) ? saved : kNamePage;
  }

  /// The step before the current one, or null when there is nothing to go back to (Auth, consent,
  /// Name, completion).
  int? get _previousStep {
    final position = kProgressSteps.indexOf(_controller!.index);
    if (position <= 0) return null;
    return kProgressSteps[position - 1];
  }

  bool _speechStepBusy = false;

  /// Back — the on-screen control, Android system back and the iOS swipe all land here.
  void _goBack() {
    final previous = _previousStep;
    if (previous == null) return;
    // Never leave while the introduction is saving; its own PopScope blocks too.
    if (_controller!.index == kSpeechProfilePage && _speechStepBusy) return;
    OmiHaptics.selection();
    _controller!.animateTo(previous);
  }

  /// "Use a Different Account" on the consent step: sign out and start again from the beginning.
  Future<void> _useDifferentAccount() async {
    final navigator = Navigator.of(context, rootNavigator: true);
    final rootContext = globalNavigatorKey.currentContext;
    if (rootContext != null && rootContext.mounted) clearAllUserState(rootContext);
    await SharedPreferencesUtil().clear();
    await AuthService.instance.signOut();
    navigator.pushAndRemoveUntil(omiPageRoute(builder: (_) => const AppShell()), (_) => false);
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

  void _updateBackgroundImage(int pageIndex) {
    final newImage = _getBackgroundImageForIndex(pageIndex) ?? Assets.images.onboardingBg1.path;
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
      case kAiConsentPage:
        return Assets.images.onboardingBg2.path;
      case kNamePage:
      case kFoundOmiPage:
        return Assets.images.onboardingBg1.path;
      case kPrimaryLanguagePage:
        return Assets.images.onboardingBg4.path;
      case kPermissionsPage:
      case kSpeechProfilePage:
        return Assets.images.onboardingBg3.path;
      case kKnowledgeGraphPage:
      case kCompletePage:
        return Assets.images.onboardingBg6.path;
      default:
        return null;
    }
  }

  Widget _background() {
    final media = MediaQuery.of(context);
    return FadeTransition(
      opacity: _backgroundFadeAnimation,
      child: Container(
        height: media.size.height,
        decoration: BoxDecoration(
          image: DecorationImage(
            image: ResizeImage(
              AssetImage(_currentBackgroundImage),
              width: (media.size.width * media.devicePixelRatio).round(),
              height: (media.size.height * media.devicePixelRatio).round(),
            ),
            fit: BoxFit.cover,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final index = _controller!.index;
    List<Widget> pages = [
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
          } else if (SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _controller!.animateTo(_resumeStep());
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
          // session and we don't want to re-run it.
          if (SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _controller!.animateTo(_resumeStep());
          }
        },
        onUseDifferentAccount: _useDifferentAccount,
      ),
      NameWidget(
        goNext: () {
          _goNext(); // Go to Primary Language page
          IntercomManager.instance.updateUser(
            FirebaseAuth.instance.currentUser!.email,
            FirebaseAuth.instance.currentUser!.displayName,
            FirebaseAuth.instance.currentUser!.uid,
          );
          PlatformManager.instance.analytics.onboardingStepCompleted('Name');
        },
      ),
      PrimaryLanguageWidget(
        goNext: () {
          _goNext(); // Go to Found Omi page
          PlatformManager.instance.analytics.onboardingStepCompleted('Primary Language');
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
          // Straight to the voice introduction (phone mic; no device step). The review step was
          // removed from onboarding to comply with App Store Guideline 5.6.3 (no rating prompts
          // during onboarding).
          _goNext();
          PlatformManager.instance.analytics.onboardingStepCompleted('Permissions');
        },
      ),
      widget.forceAuthPage
          ? const SizedBox.shrink()
          // The guided introduction owns its transcription-only session and
          // reviews statements before explicitly saving them as memories.
          : SpeechProfileWidget(
              flowSource: 'first_run',
              onBusyChanged: (busy) => _speechStepBusy = busy,
              goNext: () {
                // All Done is not enroll success (#12765). Upload/embedding
                // events fire only from the guided I/O upload receipt.
                PlatformManager.instance.analytics.speechProfileContinued();
                _controller!.animateTo(kKnowledgeGraphPage);
              },
              onSkip: () {
                PlatformManager.instance.analytics.speechProfileSkipped();
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
          SharedPreferencesUtil().remove(_resumeKey);
          _completeOnboardingTelemetry();
          updateUserOnboardingState(completed: true);
          PlatformManager.instance.analytics.onboardingCompleted();
          PaintingBinding.instance.imageCache.clear();
          routeToPage(context, const HomePageWrapper(), replace: true);
        },
      ),
    ];

    // The speech step draws the Omi device with a mic-level glow instead of a background image,
    // matching the Settings redo page; the completion screen draws its own.
    final showBackground = index != kCompletePage && index != kSpeechProfilePage;
    final previous = _previousStep;

    return PopScope(
      // System back and the iOS swipe step back one step, like the on-screen back button. On the
      // first step (and Auth / consent) back leaves onboarding as usual.
      canPop: previous == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goBack();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: OmiColors.surface0,
          body: Stack(
            children: [
              if (index == kAuthPage || showBackground) _background(),
              // Page component (no transition for content)
              pages[index],
              if (kProgressSteps.contains(index))
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.only(top: OmiSpacing.md),
                    child: OnboardingProgressDots(
                      current: kProgressSteps.indexOf(index),
                      total: kProgressSteps.length,
                    ),
                  ),
                ),
              if (previous != null)
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.only(left: OmiSpacing.xs, top: OmiSpacing.xxs),
                    child: Align(
                      alignment: Alignment.topLeft,
                      child: OmiBackButton.circled(key: const Key('onboarding_back'), onPressed: _goBack),
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

/// Exposes the counted steps to tests without widening the wrapper's state class.
@visibleForTesting
abstract final class OnboardingProgressStepsForTest {
  static List<int> get steps => _OnboardingWrapperState.kProgressSteps;
}

/// The first-run progress: one dot per real step, the current one larger, with a spoken
/// "Step N of M".
class OnboardingProgressDots extends StatelessWidget {
  const OnboardingProgressDots({super.key, required this.current, required this.total});

  /// Zero-based position of the current step.
  final int current;
  final int total;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    return Semantics(
      label: context.l10n.onboardingStepOf(current + 1, total),
      excludeSemantics: true,
      child: SizedBox(
        height: kOmiMinTapTarget,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(total, (i) {
            final isCurrent = i == current;
            return AnimatedContainer(
              duration: motion.quick,
              margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
              width: isCurrent ? 12.0 : 8.0,
              height: isCurrent ? 12.0 : 8.0,
              decoration: BoxDecoration(
                color: i <= current ? OmiColors.textPrimary : OmiColors.textTertiary,
                shape: BoxShape.circle,
              ),
            );
          }),
        ),
      ),
    );
  }
}
