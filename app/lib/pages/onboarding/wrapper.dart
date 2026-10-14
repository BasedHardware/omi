import 'dart:async';

import 'package:omi/utils/logger.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/home_tab_switcher.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/services/onboarding_sync_runtime.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_hero_film.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/activation/activation_flow.dart';
import 'package:omi/pages/onboarding/activation/onboarding_plans_sheet.dart';
import 'package:omi/pages/onboarding/connect_omi/connect_omi_step.dart';
import 'package:omi/services/superwall_pilot.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/web_onboarding_page.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/services/experiments/onboarding_webview_gate.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/pages/onboarding/setup_page.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/guided_voice_io.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/experiments/onboarding_activation_flow.dart';
import 'package:omi/services/experiments/onboarding_setup_rating_prompt.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/clear_user_state.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key, this.forceAuthPage = false});

  final bool forceAuthPage;

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
  static const int kPermissionsPage = 3;
  static const int kPrimaryLanguagePage = 4;
  static const int kConnectOmiPage = 5; // Finds the reader's Omi (search starts after sign-in)
  // The ending after Connect Omi, A/B by OnboardingActivationExperiment: the guided voice
  // introduction (control) or the activation (treatment: Omi at work, the first conversation,
  // congrats).
  static const int kSpeechProfilePage = 6;
  static const int kActivationPage = kSpeechProfilePage;
  static const int kKnowledgeGraphPage = 7; // Memory graph preview
  static const int kSetupPage = 8; // "Setting up your Omi" + rating pre-prompt; flag-gated, else skipped
  static const int kCompletePage = 9; // "You're all set" completion screen
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
    kPermissionsPage,
    kPrimaryLanguagePage,
    kConnectOmiPage,
    kSpeechProfilePage,
    if (kKnowledgeGraphStepEnabled) kKnowledgeGraphPage,
  ];

  TabController? _controller;
  late AnimationController _backgroundAnimationController;
  late Animation<double> _backgroundFadeAnimation;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;
  Future<void>? _knowledgeGraphPrebuildFuture;
  Future<bool>? _setupPageEnabled;
  ProductAttempt? _onboardingAttempt;
  bool _finishing = false;
  GuidedVoiceController? _voiceController;

  GuidedVoiceController _getVoiceController() {
    return _voiceController ??= GuidedVoiceController(
      DeviceGuidedVoiceIO(),
      flowSource: 'first_run',
      accountUid: SharedPreferencesUtil().uid,
    );
  }

  /// Which ending this reader gets; null until the flag has been read.
  OnboardingEnding? _ending;
  Future<OnboardingEnding>? _endingFuture;

  /// The step on screen and which way the reader last moved, for the step transition.
  int _shownIndex = 0;
  bool _forward = true;

  @override
  void initState() {
    super.initState();
    if (!widget.forceAuthPage && !SharedPreferencesUtil().onboardingCompleted) {
      _onboardingAttempt = ProductTelemetry.instance.start(
        ProductJourney.onboarding,
        surface: ProductSurface.onboarding,
      );
    }
    // Auth, AiConsent, Name, Permissions, Lang, ConnectOmi, SpeechProfile, KnowledgeGraph, Setup, Complete
    _controller = TabController(length: kPageCount, vsync: this);
    _controller!.addListener(() {
      if (!mounted) return;
      setState(() {
        _forward = _controller!.index >= _shownIndex;
        _shownIndex = _controller!.index;
      });
      _rememberStep(_controller!.index);
      // Read the ending's flag from Connect Omi on, so it is decided when the reader leaves it.
      if (_controller!.index >= kConnectOmiPage) unawaited(_resolveEnding());
      // Control, as before the activation: start the memory graph and read the setup page's flag
      // while the reader does the voice introduction, so the setup page has them ready.
      if (_controller!.index == kSpeechProfilePage && _ending == OnboardingEnding.voiceIntro) {
        _knowledgeGraphPrebuildFuture ??= _prebuildKnowledgeGraph().catchError((_) {});
        _setupPageEnabled ??= OnboardingSetupRatingPromptGate.isEnabled();
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
          } else if (SharedPreferencesUtil().onboardingCompleted && !_rerunForTesting) {
            await _routeWithPermissionsCheck(context);
          } else {
            _startDeviceSearch();
            _enterSteps();
          }
        }
      }
      // If not signed in, it stays at the Auth page (index 0): the app's first screen. It records the
      // welcome and asks for Bluetooth shortly after it appears, so the search for the reader's Omi
      // can start right after sign-in (the separate "Get Started" welcome screen is gone).
      if (!widget.forceAuthPage && !AuthService.instance.isSignedIn()) {
        PlatformManager.instance.analytics.onboardingWelcomeShown();
        await Future<void>.delayed(const Duration(milliseconds: 800));
        if (!mounted) return;
        await context.read<OnboardingProvider>().askForBluetoothAtLaunch();
      }
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

  /// Starts looking for the reader's Omi in the background so "Connect your Omi" can show it at once.
  void _startDeviceSearch() {
    if (widget.forceAuthPage) return;
    unawaited(context.read<OnboardingProvider>().startQuietDeviceScan());
  }

  /// The paywall experiment's end-of-onboarding placement: only arms whose payload asks for it,
  /// never control, never when subscription UI is hidden (the router checks that), and never when
  /// the activation already offered a plan.
  Future<void> _maybeShowOnboardingPaywall() async {
    if (SuperwallPilot.instance.offeredDuringOnboarding) return;
    final config = await PaywallExperiment.resolve();
    if (!mounted || config.isControl || !config.onboardingPaywall) return;
    await PaywallRouter.openVariant(context, source: 'onboarding', config: config);
  }

  /// Enters the steps after sign-in and consent: the web onboarding page when its flag names one,
  /// otherwise the native step the reader left off at. A page that falls back lands on that same
  /// native step.
  Future<void> _enterSteps() async {
    final url = await OnboardingWebviewGate.resolve();
    if (!mounted) return;
    if (url != null) {
      const TypedEvents().emit(const OnboardingWebviewShown());
      final result = await routeToPage(context, WebOnboardingPage(url: url));
      if (!mounted) return;
      if (result == WebOnboardingResult.completed) {
        const TypedEvents().emit(const OnboardingWebviewCompleted());
        await _completeOnboarding();
        return;
      }
    }
    _controller!.animateTo(_resumeStep());
  }

  /// Leaving "Connect your Omi". A device connected here skips the post-onboarding device
  /// tutorial (it stays in device settings).
  OnboardingDeviceChoice? _deviceChoice;

  /// The paywall inside the activation, between the celebration and the rating ask.
  Future<void> _showPaywall() async {
    SuperwallPilot.instance.offeredDuringOnboarding = true;
    unawaited(context.read<UsageProvider>().fetchSubscription());
    if (await SuperwallPilot.instance.showPlacementAndWait(SuperwallPilot.deviceSetupCompletePlacement)) return;
    if (!mounted) return;
    // The paywall experiment's arm when the reader is in one; control keeps the onboarding sheet.
    if (await PaywallRouter.openVariant(context, source: 'onboarding')) return;
    if (!mounted) return;
    await showOmiSheet<void>(context: context, padding: EdgeInsets.zero, builder: (_) => const OnboardingPlansSheet());
  }

  /// Saves onboarding as done and opens Home. False when the save failed (the step stays, so the
  /// reader can tap again).
  Future<bool> _completeOnboarding() async {
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
    unawaited(_addStarterTasks(context.l10n));
    SharedPreferencesUtil().remove(_resumeKey);
    OnboardingActivationExperiment.forget(SharedPreferencesUtil().uid);
    _completeOnboardingTelemetry();
    PlatformManager.instance.analytics.onboardingCompleted();
    PaintingBinding.instance.imageCache.clear();
    await _maybeShowOnboardingPaywall();
    if (!mounted) return true;
    routeToPage(context, const HomePageWrapper(), replace: true);
    return true;
  }

  /// An empty Tasks tab teaches nothing: when onboarding produced no to-dos, add three starter tasks
  /// that walk the person through Omi (once per account; never on a failed read, so nobody gets
  /// them on top of real tasks).
  static Future<void> _addStarterTasks(AppLocalizations l10n) async {
    final key = 'onboarding/starterTasks/${SharedPreferencesUtil().uid}';
    if (SharedPreferencesUtil().getBool(key)) return;
    // The activation already showed real to-dos (they may still be saving): no starter tasks.
    if (NewTasksDot.showing) {
      SharedPreferencesUtil().saveBool(key, true);
      return;
    }
    try {
      final existing = await tryGetActionItems(limit: 1);
      if (existing == null) return;
      SharedPreferencesUtil().saveBool(key, true);
      if (existing.actionItems.isNotEmpty) return;
      for (final description in [
        l10n.onboardingStarterTaskAsk,
        l10n.onboardingStarterTaskRecord,
        l10n.onboardingStarterTaskCheck,
      ]) {
        await createActionItem(description: description);
      }
      NewTasksDot.show();
    } catch (e) {
      Logger.debug('Starter tasks not added: $e');
    }
  }

  Future<void> _leaveConnectOmi(OnboardingDeviceChoice choice) async {
    _deviceChoice = choice;
    PlatformManager.instance.analytics.onboardingStepCompleted('Connect Omi');
    // A reader who just connected an Omi learns its button now, before trying it; the tutorial
    // marks itself done, so Home won't show it again.
    if (choice == OnboardingDeviceChoice.connected && _needsDeviceTutorial()) {
      await routeToPage(context, const InteractiveDeviceOnboardingWrapper(duringSetup: true));
      if (!mounted) return;
    }
    unawaited(_enterEnding());
  }

  bool _needsDeviceTutorial() {
    if (SharedPreferencesUtil().deviceOnboardingCompleted) return false;
    final devices = context.read<DeviceProvider>();
    final device = devices.connectedDevice;
    if (device == null || device.type != DeviceType.omi) return false;
    return DeviceUtils.isOmiCv1(modelNumber: devices.pairedDevice?.modelNumber, deviceName: device.name);
  }

  // ---- The ending: voice introduction (control) or activation (treatment) ------------------

  /// The ending for this account: the one it already started, else the flag's answer (control on
  /// any doubt). Read once per onboarding.
  Future<OnboardingEnding> _resolveEnding() {
    return _endingFuture ??= () async {
      final uid = SharedPreferencesUtil().uid;
      final ending = OnboardingActivationExperiment.remembered(uid) ?? await OnboardingActivationExperiment.resolve();
      if (mounted) setState(() => _ending = ending);
      return ending;
    }();
  }

  /// Leaves Connect Omi once the ending is decided, and keeps it for this account so a reader who
  /// comes back later finishes the same ending.
  Future<void> _enterEnding() async {
    final ending = await _resolveEnding();
    if (!mounted) return;
    OnboardingActivationExperiment.remember(SharedPreferencesUtil().uid, ending);
    // The arm the reader actually sees (a slow flag read falls back to control while PostHog may
    // still log the flag call as treatment): compare arms on this, not on the flag exposure.
    PlatformManager.instance.analytics.track(
      'Onboarding Ending Shown',
      properties: {'ending': ending.wireName, ...OnboardingActivationExperiment.exposureProperties()},
    );
    PlatformManager.instance.analytics.setUserProperty('Onboarding Ending', ending.wireName);
    _controller!.animateTo(kSpeechProfilePage);
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

  /// Control: after the voice introduction, the knowledge graph when shown, otherwise the setup
  /// page or the completion screen, exactly as before the activation existed.
  void _leaveSpeechProfile() {
    if (kKnowledgeGraphStepEnabled) {
      _controller!.animateTo(kKnowledgeGraphPage);
    } else {
      _continueAfterKnowledgeGraph();
    }
  }

  Widget _endingPage() {
    if (widget.forceAuthPage) return const SizedBox.shrink();
    switch (_ending) {
      case null:
        return const SizedBox.shrink();
      case OnboardingEnding.voiceIntro:
        // The guided introduction owns its transcription-only session and reviews statements
        // before explicitly saving them as memories.
        return SpeechProfileWidget(
          flowSource: 'first_run',
          controller: _getVoiceController(),
          goNext: () {
            // All Done is not enroll success (#12765). Upload/embedding events fire only from the
            // guided I/O upload receipt.
            PlatformManager.instance.analytics.speechProfileContinued();
            _leaveSpeechProfile();
          },
          onSkip: () {
            PlatformManager.instance.analytics.speechProfileSkipped();
            _leaveSpeechProfile();
          },
        );
      case OnboardingEnding.activation:
        return ActivationFlow(
          hasDevice: _deviceChoice == OnboardingDeviceChoice.connected ||
              context.read<DeviceProvider>().isConnected ||
              DemoActivationCapture.pretendsDevice,
          showPaywall: _showPaywall,
          onFinished: () {
            PlatformManager.instance.analytics.onboardingStepCompleted('Activation');
            return _completeOnboarding();
          },
        );
    }
  }

  /// The activation is a moment, not a form: no progress line and no way back. The voice
  /// introduction keeps its progress line.
  bool get _onActivation => _controller!.index == kActivationPage && _ending != OnboardingEnding.voiceIntro;

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
  Future<void> _continueAfterKnowledgeGraph() async {
    final enabled = await (_setupPageEnabled ?? OnboardingSetupRatingPromptGate.isEnabled());
    if (!mounted) return;
    _controller!.animateTo(stepAfterKnowledgeGraph(setupPageEnabled: enabled));
  }

  // ---- Resume and back ----------------------------------------------------------------------

  /// Per-account key so a different account signing in on this phone starts at the Name step.
  /// v2: the redesign renumbered the steps, so a step saved by an older build is not reused.
  String get _resumeKey => 'onboarding/resumeStep.v2/${SharedPreferencesUtil().uid}';

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
    // Connect Omi is the threshold into the experience: no way back into the setup questions
    // (language and permissions can be changed later in Settings).
    // The ending that follows (activation or voice introduction) is not a form: no back either.
    if (_controller!.index == kConnectOmiPage || _controller!.index == kActivationPage) return null;
    final position = kProgressSteps.indexOf(_controller!.index);
    if (position <= 0) return null;
    return kProgressSteps[position - 1];
  }

  /// Back — the on-screen control, Android system back and the iOS swipe all land here.
  void _goBack() {
    final previous = _previousStep;
    if (previous == null) return;
    OmiHaptics.selection();
    _controller!.animateTo(previous);
  }

  /// "Use a Different Account" on the consent step: sign out and start again from the beginning.
  Future<void> _useDifferentAccount() async {
    final navigator = Navigator.of(context, rootNavigator: true);
    _voiceController?.dispose();
    _voiceController = null;
    final rootContext = globalNavigatorKey.currentContext;
    if (rootContext != null && rootContext.mounted) clearAllUserState(rootContext);
    await SharedPreferencesUtil().clear();
    await AuthService.instance.signOut();
    navigator.pushAndRemoveUntil(omiPageRoute(builder: (_) => const AppShell()), (_) => false);
  }

  /// Sign-in and the data & privacy consent: the Omi pendant at the top, on the same light surface
  /// as the rest of onboarding (no photo).
  Widget _background() {
    final media = MediaQuery.of(context);
    return FadeTransition(
      opacity: _backgroundFadeAnimation,
      child: Align(
        alignment: Alignment.topCenter,
        // The cord runs off the top edge, so the pendant hangs into view.
        child: ExcludeSemantics(
          child: Assets.images.omiPendantGlow.image(
            key: const Key('onboarding_pendant_hero'),
            width: media.size.width,
            height: media.size.height * 0.6,
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
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
            _startDeviceSearch();
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
            _startDeviceSearch();
            _enterSteps();
          }
        },
        onUseDifferentAccount: _useDifferentAccount,
      ),
      NameWidget(
        goNext: () {
          _goNext(); // Go to Permissions page
          IntercomManager.instance.updateUser(
            FirebaseAuth.instance.currentUser!.email,
            FirebaseAuth.instance.currentUser!.displayName,
            FirebaseAuth.instance.currentUser!.uid,
          );
          PlatformManager.instance.analytics.onboardingStepCompleted('Name');
        },
      ),
      PermissionsWidget(
        goNext: () {
          _goNext(); // Go to Primary Language page
          PlatformManager.instance.analytics.onboardingStepCompleted('Permissions');
        },
      ),
      PrimaryLanguageWidget(
        goNext: () {
          _goNext(); // Go to Connect Omi page
          PlatformManager.instance.analytics.onboardingStepCompleted('Primary Language');
        },
      ),
      widget.forceAuthPage ? const SizedBox.shrink() : ConnectOmiStep(onDone: _leaveConnectOmi),
      _endingPage(),
      OnboardingKnowledgeGraphStep(onContinue: _leaveKnowledgeGraph),
      OnboardingSetupPage(
        pendingWork: _knowledgeGraphPrebuildFuture,
        onFinished: () {
          PlatformManager.instance.analytics.onboardingStepCompleted('Setup');
          _controller!.animateTo(kCompletePage);
        },
      ),
      OnboardingCompleteScreen(onComplete: () => unawaited(_completeOnboarding())),
    ];

    // The speech step draws the Omi device with a mic-level glow instead of a background image,
    // matching the Settings redo page; the setup and completion screens draw their own.
    // Name, permissions, language and connect sit on the plain surface, without artwork.
    final showBackground = index == kAuthPage || index == kAiConsentPage;
    final previous = _previousStep;

    return PopScope(
      // System back and the iOS swipe step back one step, like the on-screen back button. On the
      // first step (and Auth / consent) back leaves onboarding as usual.
      canPop: previous == null &&
          index != kConnectOmiPage &&
          index != kActivationPage &&
          // Control's last screens: Android back must not drop the reader out of onboarding.
          index != kSetupPage &&
          index != kCompletePage,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goBack();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: OmiColors.surface0,
          body: Stack(
            children: [
              if (showBackground) OnboardingHero.video ? const OnboardingHeroFilm() : _background(),
              OnboardingStepLayout(
                reserveHeader: index == kConnectOmiPage,
                onBack: previous == null ? null : _goBack,
                // The activation is a moment, not a form: no progress line over it.
                progress: kProgressSteps.contains(index) && !_onActivation
                    ? OnboardingProgressLine(current: kProgressSteps.indexOf(index), total: kProgressSteps.length)
                    : null,
                child: _StepTransition(
                  index: index,
                  forward: _forward,
                  // Arriving at Connect Omi is a moment, not another form: a plain cross-fade lets the
                  // step's own entrance carry it.
                  fadeOnly: index == kConnectOmiPage,
                  // Sign-in and consent share their photo: the consent card rises over it, so it
                  // reads as part of signing in rather than a new page.
                  rise: index == kAiConsentPage || (index == kAuthPage && !_forward),
                  child: pages[index],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Moves between steps: the new step slides in from the side the reader is heading and fades up,
/// the old one drifts the other way and fades out. Instant under Reduce Motion.
class _StepTransition extends StatelessWidget {
  const _StepTransition({
    required this.index,
    required this.forward,
    required this.child,
    this.fadeOnly = false,
    this.rise = false,
  });

  final int index;
  final bool forward;
  final bool fadeOnly;

  /// The incoming step rises from the bottom edge (a sheet over the same background); the
  /// outgoing one sinks back down when going the other way.
  final bool rise;
  final Widget child;

  static const double _shift = 0.08;

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return AnimatedSwitcher(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 420),
      reverseDuration: reduce ? Duration.zero : const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      layoutBuilder: (current, previous) => Stack(
        fit: StackFit.expand,
        children: [...previous, if (current != null) current],
      ),
      transitionBuilder: (child, animation) {
        final incoming = child.key == ValueKey(index);
        // An outgoing child runs its animation backwards, ending at its begin offset.
        final from = fadeOnly || rise ? 0.0 : ((incoming == forward) ? _shift : -_shift);
        final Offset begin = rise ? Offset(0, incoming == forward ? 0.35 : 0) : Offset(from, 0);
        return IgnorePointer(
          ignoring: !incoming,
          child: FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween<Offset>(begin: begin, end: Offset.zero).animate(animation),
              child: child,
            ),
          ),
        );
      },
      child: KeyedSubtree(key: ValueKey(index), child: child),
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

/// The first-run progress: one thin line that fills as the reader moves through the real steps,
/// with a spoken "Step N of M".
class OnboardingProgressLine extends StatelessWidget {
  const OnboardingProgressLine({super.key, required this.current, required this.total});

  /// Zero-based position of the current step.
  final int current;
  final int total;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    final fraction = total <= 0 ? 0.0 : ((current + 1) / total).clamp(0.0, 1.0);
    return Semantics(
      label: context.l10n.onboardingStepOf(current + 1, total),
      excludeSemantics: true,
      child: SizedBox(
        height: kOmiMinTapTarget,
        child: Center(
          child: Padding(
            // Clear of the back button on the left, balanced on the right.
            padding: const EdgeInsets.symmetric(horizontal: kOmiMinTapTarget + OmiSpacing.md),
            child: ClipRRect(
              borderRadius: OmiRadius.pillAll,
              child: SizedBox(
                width: double.infinity,
                height: 3,
                child: Stack(
                  children: [
                    Positioned.fill(child: ColoredBox(color: OmiColors.surface2)),
                    TweenAnimationBuilder<double>(
                      tween: Tween(end: fraction),
                      duration: motion.standard,
                      curve: Curves.easeOutCubic,
                      builder: (context, value, _) => FractionallySizedBox(
                        widthFactor: value,
                        heightFactor: 1,
                        alignment: Alignment.centerLeft,
                        child: ColoredBox(color: OmiColors.textPrimary),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
