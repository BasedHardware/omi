import 'dart:async';

import 'package:omi/services/onboarding_sync_runtime.dart';
import 'onboarding_step_telemetry.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
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
import 'package:omi/pages/onboarding/variants/pocket/pocket_onboarding_flow.dart';
import 'package:omi/pages/onboarding/variants/yinka/yinka_onboarding_flow.dart';
import 'package:omi/pages/paywall/trial_upsell_sheet.dart';
import 'package:omi/pages/onboarding/web_onboarding_page.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/pages/onboarding/setup_page.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/guided_voice_io.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/experiments/onboarding_setup_rating_prompt.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
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

  /// The step helpers live on the private state class. Tests call them through the public widget.
  @visibleForTesting
  static bool isResumableStepForTesting(int index) => _OnboardingWrapperState.isResumableStepForTesting(index);

  @visibleForTesting
  static int? previousStepForTesting({
    required int currentIndex,
    required bool setupPageEnabled,
    required bool knowledgeGraphStepEnabled,
  }) =>
      _OnboardingWrapperState.previousStepForTesting(
        currentIndex: currentIndex,
        setupPageEnabled: setupPageEnabled,
        knowledgeGraphStepEnabled: knowledgeGraphStepEnabled,
      );

  @visibleForTesting
  static int resumeStepForTesting(int saved) => _OnboardingWrapperState.resolveResumeStep(saved);

  /// Debug builds with `--dart-define=OMI_ONBOARDING_RERUN=1` walk onboarding again on a
  /// signed-in account; startup routing honours it so the reader lands in the wrapper.
  static bool get rerunForTesting => _OnboardingWrapperState._rerunForTesting;

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
  static const int kSetupPage = 8; // "Setting up your Omi" + rating pre-prompt; flag-gated, else skipped
  static const int kCompletePage = 9; // Capture choice; keep persisted index stable.
  static const int kPageCount = 10;

  /// The steps the progress dots count, in order. Auth, consent and the completion screen are not
  /// steps: they are shown without dots.
  /// The Knowledge Graph preview is hidden from the first run for now (Oct 2026: the step does not
  /// work well enough yet). The page stays in the TabController so indices are stable; nothing
  /// navigates to it while this is false.
  static const bool kKnowledgeGraphStepEnabled = false;

  /// Debug-build override to walk first-run onboarding again on a signed-in account (for
  /// exercising onboarding variants): `--dart-define=OMI_ONBOARDING_RERUN=1`. `kDebugMode`
  /// excludes every store build.
  static const _debugRerun = String.fromEnvironment('OMI_ONBOARDING_RERUN');
  static bool get _rerunForTesting => kDebugMode && _debugRerun == '1';

  static const List<int> kProgressSteps = [
    kNamePage,
    kPrimaryLanguagePage,
    kFoundOmiPage,
    kPermissionsPage,
    kSpeechProfilePage,
    if (kKnowledgeGraphStepEnabled) kKnowledgeGraphPage,
  ];

  TabController? _controller;
  late AnimationController _backgroundAnimationController;
  late Animation<double> _backgroundFadeAnimation;
  String _currentBackgroundImage = Assets.images.onboardingBg2.path;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;
  Future<void>? _knowledgeGraphPrebuildFuture;
  Future<bool>? _setupPageEnabled;
  bool? _setupPageEnabledResolved;
  ProductAttempt? _onboardingAttempt;
  bool _finishing = false;
  bool _signupPaywallShown = false;
  late final _stepTelemetry = MobileOnboardingStepTelemetry(
    emit: const TypedEvents().emit,
    platform: () => switch (Theme.of(context).platform) {
      TargetPlatform.iOS => OnboardingStepCompletedPlatform.ios,
      TargetPlatform.android => OnboardingStepCompletedPlatform.android,
      _ => OnboardingStepCompletedPlatform.other,
    },
  );
  GuidedVoiceController? _voiceController;

  GuidedVoiceController _getVoiceController() {
    return _voiceController ??= GuidedVoiceController(
      DeviceGuidedVoiceIO(),
      flowSource: 'first_run',
      accountUid: SharedPreferencesUtil().uid,
    );
  }

  @override
  void initState() {
    super.initState();
    if (!widget.forceAuthPage && !SharedPreferencesUtil().onboardingCompleted) {
      _onboardingAttempt = ProductTelemetry.instance.start(
        ProductJourney.onboarding,
        surface: ProductSurface.onboarding,
      );
    }
    final signedIn = !widget.forceAuthPage && AuthService.instance.isSignedIn();
    final initialIndex =
        signedIn ? (!SharedPreferencesUtil().aiConsentGiven ? kAiConsentPage : _resumeStep()) : kAuthPage;
    _stepTelemetry.seed(initialIndex);
    // Auth, AiConsent, Name, Lang, FoundOmi, Permissions, SpeechProfile, KnowledgeGraph, Setup, Complete
    _controller = TabController(length: kPageCount, initialIndex: initialIndex, vsync: this);
    _controller!.addListener(() {
      if (!mounted) return;
      _stepTelemetry.enter(_controller!.index);
      setState(() {});
      _rememberStep(_controller!.index);
      // Update background image when page changes
      _updateBackgroundImage(_controller!.index);
      // Precache next image for smoother transitions
      _precacheNextImage(_controller!.index);
      if (_controller!.index == kSpeechProfilePage && _knowledgeGraphPrebuildFuture == null) {
        _knowledgeGraphPrebuildFuture = _prebuildKnowledgeGraph().catchError((_) {});
      }
      // Read the flag two steps ahead so the decision is ready when the reader taps Continue.
      if (_controller!.index == kSpeechProfilePage) {
        _ensureSetupPageFlag();
      }
    });

    // Initialize animation controllers
    _backgroundAnimationController = AnimationController(duration: const Duration(milliseconds: 500), vsync: this);

    // Initialize animations
    _backgroundFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _backgroundAnimationController, curve: Curves.easeInOut));

    _currentBackgroundImage = _getBackgroundImageForIndex(initialIndex) ?? _currentBackgroundImage;
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
            OnboardingVariantGate.warm();
            _controller!.animateTo(kAiConsentPage);
          } else if (SharedPreferencesUtil().onboardingCompleted && !_rerunForTesting) {
            await _routeWithPermissionsCheck(context);
          } else {
            _enterSteps();
          }
        }
      }
      // If not signed in, it stays at the Auth page (index 0)
    });
  }

  @override
  void dispose() {
    _onboardingAttempt?.complete(ProductOutcome.unobserved, failure: ProductFailure.incomplete);
    _voiceController?.dispose();
    _controller?.dispose();
    _backgroundAnimationController.dispose();
    super.dispose();
  }

  void _completeOnboardingTelemetry() {
    _onboardingAttempt?.complete(ProductOutcome.success);
    _onboardingAttempt = null;
  }

  Future<void> _routeWithPermissionsCheck(BuildContext context) async {
    _stepTelemetry.exit();
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

  /// Marks first-run onboarding complete and routes home. Shared by the native completion screen,
  /// the web onboarding page and Yinka's flow, so only the wrapper ever owns completion. False when
  /// the save failed (the step stays, so the reader can tap again). [paywallShown] skips the
  /// end-of-onboarding paywall placement when the arm already offered a plan.
  Future<bool> _finishOnboarding({bool paywallShown = false}) async {
    if (_finishing) return false;
    _finishing = true;
    final saved = await OnboardingSyncRuntime.enqueue(completed: true);
    _finishing = false;
    if (!mounted || !context.mounted) return false;
    if (!saved) {
      OmiFeedback.error(context, context.l10n.somethingWentWrong);
      return false;
    }
    SharedPreferencesUtil().onboardingCompleted = true;
    SharedPreferencesUtil().permissionsCompleted = true;
    SharedPreferencesUtil().remove(_resumeKey);
    _stepTelemetry.exit();
    _completeOnboardingTelemetry();
    PlatformManager.instance.analytics.onboardingCompleted();
    PaintingBinding.instance.imageCache.clear();
    if (!paywallShown) await _maybeShowOnboardingPaywall();
    if (!mounted) return true;
    // Sign-in happened inside onboarding, after the app shell's launch-time fetch, so Home and
    // Settings (Upgrade row, first-tap trial paywall) would otherwise have no subscription.
    unawaited(context.read<UsageProvider>().fetchSubscription());
    routeToPage(context, const HomePageWrapper(), replace: true);
    return true;
  }

  /// The experiment's end-of-onboarding placement: only arms whose payload asks for it, never
  /// control, and never when subscription UI is hidden (the router checks that). The `trial` arm
  /// has its placement right after sign-up instead ([_maybeShowSignupPaywall]).
  Future<void> _maybeShowOnboardingPaywall() async {
    final config = await PaywallExperiment.resolve();
    if (!mounted || config.isControl || !config.onboardingPaywall) return;
    if (config.variant == PaywallVariant.trial) return;
    await PaywallRouter.openVariant(context, source: 'onboarding', config: config);
  }

  /// The `trial` arm's placement: once, right after sign-up and consent, before the first step.
  /// Dismissing it (close button) just continues onboarding.
  bool _signupPaywallPurchased = false;

  Future<void> _maybeShowSignupPaywall() async {
    if (_signupPaywallShown) return;
    final config = await PaywallExperiment.resolve();
    if (!mounted || config.variant != PaywallVariant.trial || !config.onboardingPaywall) return;
    _signupPaywallShown = true;
    // The router needs the subscription (trial eligibility) that sign-in only started fetching.
    final usage = context.read<UsageProvider>();
    if (usage.subscription == null) await usage.fetchSubscription();
    if (!mounted) return;
    await PaywallRouter.openVariant(
      context,
      source: 'onboarding',
      config: config,
      onResult: (result) => _signupPaywallPurchased = result == true,
    );
  }

  /// Enters the steps after sign-in and consent: the arm of `onboarding-variant` for this reader
  /// (Reid's web page, Yinka's flow) or the native step the reader left off at. A web page that
  /// falls back lands on that same native step.
  Future<void> _enterSteps() async {
    await _maybeShowSignupPaywall();
    if (!mounted) return;
    final arm = await OnboardingVariantGate.resolve();
    if (!mounted) return;
    PlatformManager.instance.analytics.track('Onboarding Variant Shown', properties: {
      'variant': arm.variant.wireName,
      '\$feature/${OnboardingVariantGate.enabledFlag}': arm.variant.wireName,
    });
    switch (arm.variant) {
      case OnboardingVariant.pocket:
        // Closing the sign-up trial paywall earns the 30-day downsell, once.
        if (_signupPaywallShown && !_signupPaywallPurchased) {
          await TrialUpsellSheet.show(context, source: 'onboarding');
          if (!mounted) return;
        }
        // The flow offers no plan itself: skip the end placement only when sign-up already showed one.
        await routeToPage(
          context,
          PocketOnboardingFlow(
              onComplete: ({required bool paywallShown}) =>
                  _finishOnboarding(paywallShown: paywallShown || _signupPaywallShown)),
        );
        return;
      case OnboardingVariant.yinka:
        await routeToPage(context, YinkaOnboardingFlow(onComplete: _finishOnboarding));
        return;
      case OnboardingVariant.reid:
        const TypedEvents().emit(const OnboardingWebviewShown());
        final result = await routeToPage(context, WebOnboardingPage(url: arm.webUrl!));
        if (!mounted) return;
        if (result == WebOnboardingResult.completed) {
          const TypedEvents().emit(const OnboardingWebviewCompleted());
          await _finishOnboarding();
          return;
        }
      case OnboardingVariant.control:
        break;
    }
    _controller!.animateTo(_resumeStep());
  }

  void _goNext() {
    if (_controller!.index < _controller!.length - 1) {
      _controller!.animateTo(_controller!.index + 1);
    }
  }

  /// After the knowledge graph: the setup page when its flag is on, otherwise straight to the
  /// completion screen exactly as before the page existed.
  static int stepAfterKnowledgeGraph({required bool setupPageEnabled}) => setupPageEnabled ? kSetupPage : kCompletePage;

  Future<void> _leaveKnowledgeGraph() async {
    PlatformManager.instance.analytics.onboardingStepCompleted('Knowledge Graph');
    await _continueAfterKnowledgeGraph();
  }

  /// Setup page when the flag allows it, otherwise the completion screen. Used by the Knowledge
  /// Graph step's Continue and, while that step is hidden, straight from the speech profile.
  void _ensureSetupPageFlag() {
    _setupPageEnabled ??= OnboardingSetupRatingPromptGate.isEnabled().then((enabled) {
      _setupPageEnabledResolved = enabled;
      if (mounted) setState(() {});
      return enabled;
    });
  }

  Future<void> _continueAfterKnowledgeGraph() async {
    _ensureSetupPageFlag();
    final enabled = await _setupPageEnabled!;
    _setupPageEnabledResolved = enabled;
    if (!mounted) return;
    _controller!.animateTo(stepAfterKnowledgeGraph(setupPageEnabled: enabled));
  }

  void _leaveSpeechProfile() {
    if (kKnowledgeGraphStepEnabled) {
      _controller!.animateTo(kKnowledgeGraphPage);
    } else {
      _continueAfterKnowledgeGraph();
    }
  }

  // ---- Resume and back ----------------------------------------------------------------------

  /// Per-account key so a different account signing in on this phone starts at the Name step.
  String get _resumeKey => 'onboarding/resumeStep/${SharedPreferencesUtil().uid}';

  bool _isResumableStep(int index) => index >= kNamePage && index <= kCompletePage;

  void _rememberStep(int index) {
    if (widget.forceAuthPage || !_isResumableStep(index)) return;
    SharedPreferencesUtil().saveInt(_resumeKey, index);
  }

  /// The step to reopen after the app was killed mid-onboarding: the last step the reader reached,
  /// or Name.
  int _resumeStep() {
    final saved = SharedPreferencesUtil().getInt(_resumeKey, defaultValue: kNamePage);
    return resolveResumeStep(saved);
  }

  static int resolveResumeStep(int saved) {
    if (!isResumableStepForTesting(saved)) return kNamePage;
    if (!kKnowledgeGraphStepEnabled && saved == kKnowledgeGraphPage) {
      return stepAfterKnowledgeGraph(setupPageEnabled: false);
    }
    return saved;
  }

  /// The step before the current one, or null when there is nothing to go back to (Auth, consent,
  /// Name).
  int? get _previousStep {
    final current = _controller!.index;
    if (current == kCompletePage) {
      return _setupPageEnabledResolved == true
          ? kSetupPage
          : (kKnowledgeGraphStepEnabled ? kKnowledgeGraphPage : kSpeechProfilePage);
    }
    if (current == kSetupPage) {
      return kKnowledgeGraphStepEnabled ? kKnowledgeGraphPage : kSpeechProfilePage;
    }
    if (current == kKnowledgeGraphPage) {
      return kSpeechProfilePage;
    }
    final position = kProgressSteps.indexOf(current);
    if (position <= 0) return null;
    return kProgressSteps[position - 1];
  }

  @visibleForTesting
  static bool isResumableStepForTesting(int index) => index >= kNamePage && index <= kCompletePage;

  @visibleForTesting
  static int? previousStepForTesting({
    required int currentIndex,
    required bool setupPageEnabled,
    required bool knowledgeGraphStepEnabled,
  }) {
    if (currentIndex == kCompletePage) {
      return setupPageEnabled ? kSetupPage : (knowledgeGraphStepEnabled ? kKnowledgeGraphPage : kSpeechProfilePage);
    }
    if (currentIndex == kSetupPage) {
      return knowledgeGraphStepEnabled ? kKnowledgeGraphPage : kSpeechProfilePage;
    }
    if (currentIndex == kKnowledgeGraphPage) {
      return kSpeechProfilePage;
    }
    final steps = [
      kNamePage,
      kPrimaryLanguagePage,
      kFoundOmiPage,
      kPermissionsPage,
      kSpeechProfilePage,
      if (knowledgeGraphStepEnabled) kKnowledgeGraphPage,
    ];
    final position = steps.indexOf(currentIndex);
    if (position <= 0) return null;
    return steps[position - 1];
  }

  bool _speechStepBusy = false;

  /// Back — the on-screen control, Android system back and the iOS swipe all land here.
  void _goBack() {
    final previous = _previousStep;
    if (previous == null) return;
    // Never leave while the introduction is saving; its own PopScope blocks too.
    if (_controller!.index == kSpeechProfilePage && _speechStepBusy) return;
    OmiHaptics.selection();
    _stepTelemetry.skipped = false;
    _stepTelemetry.exitReason = OnboardingStepCompletedExitReason.back;
    _controller!.animateTo(previous);
  }

  /// "Use a Different Account" on the consent step: sign out and start again from the beginning.
  Future<void> _useDifferentAccount() async {
    OnboardingVariantGate.invalidate();
    _voiceController?.dispose();
    _voiceController = null;
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
      // Canonical graphs are derived on read, even when no relationships exist.
      // Do not schedule the legacy mutation rejected by the canonical fence.
      if (current['canonical'] == true) return;
      final nodes = current['nodes'] as List<dynamic>? ?? const [];
      final hasGraph = nodes.any((node) => (node['id'] ?? '') != 'user-node');
      if (hasGraph) return;
    } catch (_) {
      // Continue to rebuild below.
    }

    final rebuildResult = await KnowledgeGraphApi.rebuildKnowledgeGraph();
    final status = rebuildResult['status'];
    // 'canonical_up_to_date' is the synthetic client status returned on HTTP 409.
    if (status == 'canonical_up_to_date') {
      return;
    }
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
      case kSetupPage:
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
            OnboardingVariantGate.warm();
            _controller!.animateTo(kAiConsentPage);
          } else if (SharedPreferencesUtil().onboardingCompleted) {
            await _routeWithPermissionsCheck(context);
          } else {
            _enterSteps();
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
            _enterSteps();
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
              controller: _getVoiceController(),
              onBusyChanged: (busy) => _speechStepBusy = busy,
              goNext: () {
                // All Done is not enroll success (#12765). Upload/embedding
                // events fire only from the guided I/O upload receipt.
                PlatformManager.instance.analytics.speechProfileContinued();
                _leaveSpeechProfile();
              },
              onSkip: () {
                PlatformManager.instance.analytics.speechProfileSkipped();
                _stepTelemetry.skipped = true;
                _leaveSpeechProfile();
              },
            ),
      OnboardingKnowledgeGraphStep(onContinue: _leaveKnowledgeGraph),
      OnboardingSetupPage(
        pendingWork: _knowledgeGraphPrebuildFuture,
        onFinished: () {
          PlatformManager.instance.analytics.onboardingStepCompleted('Setup');
          _controller!.animateTo(kCompletePage);
        },
      ),
      OnboardingCompleteScreen(
        onSkipped: () => _stepTelemetry.skipped = true,
        onComplete: _finishOnboarding,
      ),
    ];

    // The speech step draws the Omi device with a mic-level glow instead of a background image,
    // matching the Settings redo page; the setup and completion screens draw their own.
    final showBackground = index != kCompletePage && index != kSetupPage && index != kSpeechProfilePage;
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
              OnboardingStepLayout(
                reserveHeader: index == kSpeechProfilePage,
                onBack: previous == null ? null : _goBack,
                progress: kProgressSteps.contains(index)
                    ? OnboardingProgressDots(current: kProgressSteps.indexOf(index), total: kProgressSteps.length)
                    : null,
                child: pages[index],
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
  static int get setupPage => _OnboardingWrapperState.kSetupPage;
  static int get completePage => _OnboardingWrapperState.kCompletePage;
  static int get knowledgeGraphPage => _OnboardingWrapperState.kKnowledgeGraphPage;
  static bool get knowledgeGraphStepEnabled => _OnboardingWrapperState.kKnowledgeGraphStepEnabled;
  static int stepAfterKnowledgeGraph({required bool setupPageEnabled}) =>
      _OnboardingWrapperState.stepAfterKnowledgeGraph(setupPageEnabled: setupPageEnabled);
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
