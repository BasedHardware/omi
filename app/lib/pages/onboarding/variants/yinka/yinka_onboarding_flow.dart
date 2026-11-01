import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_flow.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/onboarding_plans_sheet.dart';
import 'package:omi/pages/onboarding/variants/yinka/connect_omi_step.dart';
import 'package:omi/pages/onboarding/variants/yinka/name_widget.dart';
import 'package:omi/pages/onboarding/variants/yinka/permissions_widget.dart';
import 'package:omi/pages/onboarding/variants/yinka/primary_language_widget.dart';
import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Yinka's first-run onboarding (PR #21445) as the `yinka` arm of `onboarding-variant`: Name →
/// Permissions → Language → Connect Omi → the activation (a first real conversation, its summary
/// and to-dos, the paywall, the rating ask). Runs after sign-in and consent, like the web
/// onboarding page; the native wrapper still owns completion through [onComplete], which saves,
/// routes home and answers false when the save failed (the activation then stays, so the reader
/// can tap again).
class YinkaOnboardingFlow extends StatefulWidget {
  const YinkaOnboardingFlow({super.key, required this.onComplete});

  /// Saves onboarding as done and opens Home. [paywallShown] says the activation already offered a
  /// plan, so the end-of-onboarding paywall placement must not show a second one.
  final Future<bool> Function({required bool paywallShown}) onComplete;

  @override
  State<YinkaOnboardingFlow> createState() => _YinkaOnboardingFlowState();
}

class _YinkaOnboardingFlowState extends State<YinkaOnboardingFlow> {
  static const int kNamePage = 0;
  static const int kPermissionsPage = 1;
  static const int kPrimaryLanguagePage = 2;
  static const int kConnectOmiPage = 3;
  static const int kActivationPage = 4;

  /// The steps the progress line counts, in order. The activation is a moment, not a form: it is
  /// counted (so the line reads 4 of 5 on Connect Omi) but drawn without a line.
  static const List<int> kProgressSteps = [
    kNamePage,
    kPermissionsPage,
    kPrimaryLanguagePage,
    kConnectOmiPage,
    kActivationPage
  ];

  late int _index;
  bool _forward = true;
  bool _paywallShown = false;
  OnboardingDeviceChoice? _deviceChoice;

  /// Per-account key so a different account signing in on this phone starts at the Name step.
  static String resumeKey(String uid) => 'onboarding/yinka/resumeStep/$uid';

  @override
  void initState() {
    super.initState();
    final saved = SharedPreferencesUtil().getInt(resumeKey(SharedPreferencesUtil().uid), defaultValue: kNamePage);
    // The activation listens afresh: a reader killed there comes back to Connect Omi.
    _index = saved >= kNamePage && saved <= kConnectOmiPage ? saved : kNamePage;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Start looking for the reader's Omi now, so "Connect your Omi" can show it at once.
      unawaited(context.read<OnboardingProvider>().startQuietDeviceScan());
    });
  }

  void _show(int index) {
    if (!mounted) return;
    setState(() {
      _forward = index >= _index;
      _index = index;
    });
    if (index <= kConnectOmiPage) SharedPreferencesUtil().saveInt(resumeKey(SharedPreferencesUtil().uid), index);
  }

  void _goNext() => _show(_index + 1);

  /// The step before the current one, or null when there is nothing to go back to. Connect Omi is
  /// the threshold into the experience: no way back into the setup questions (language and
  /// permissions can be changed later in Settings); the activation is not a form either.
  int? get _previousStep {
    if (_index == kConnectOmiPage || _index == kActivationPage) return null;
    final position = kProgressSteps.indexOf(_index);
    if (position <= 0) return null;
    return kProgressSteps[position - 1];
  }

  void _goBack() {
    final previous = _previousStep;
    if (previous == null) return;
    OmiHaptics.selection();
    _show(previous);
  }

  Future<void> _leaveConnectOmi(OnboardingDeviceChoice choice) async {
    _deviceChoice = choice;
    PlatformManager.instance.analytics.onboardingStepCompleted('Connect Omi');
    // A reader who just connected an Omi learns its button now, before trying it; the tutorial
    // marks itself done, so Home won't show it again.
    if (choice == OnboardingDeviceChoice.connected && _needsDeviceTutorial()) {
      await routeToPage(context, const InteractiveDeviceOnboardingWrapper());
      if (!mounted) return;
    }
    PlatformManager.instance.analytics.track('Onboarding Ending Shown', properties: {'ending': 'activation'});
    _show(kActivationPage);
  }

  bool _needsDeviceTutorial() {
    if (SharedPreferencesUtil().deviceOnboardingCompleted) return false;
    final devices = context.read<DeviceProvider>();
    final device = devices.connectedDevice;
    if (device == null || device.type != DeviceType.omi) return false;
    return DeviceUtils.isOmiCv1(modelNumber: devices.pairedDevice?.modelNumber, deviceName: device.name);
  }

  /// The paywall inside the activation, between the celebration and the rating ask: the paywall
  /// experiment's arm when the reader is in one; control keeps the onboarding sheet.
  Future<void> _showPaywall() async {
    _paywallShown = true;
    unawaited(context.read<UsageProvider>().fetchSubscription());
    if (await PaywallRouter.openVariant(context, source: 'onboarding')) return;
    if (!mounted) return;
    await showOmiSheet<void>(context: context, padding: EdgeInsets.zero, builder: (_) => const OnboardingPlansSheet());
  }

  Future<bool> _finish() async {
    PlatformManager.instance.analytics.onboardingStepCompleted('Activation');
    final saved = await widget.onComplete(paywallShown: _paywallShown);
    if (saved) SharedPreferencesUtil().remove(resumeKey(SharedPreferencesUtil().uid));
    return saved;
  }

  Widget _page(int index) {
    switch (index) {
      case kNamePage:
        return NameWidget(
          goNext: () {
            _goNext();
            IntercomManager.instance.updateUser(
              FirebaseAuth.instance.currentUser!.email,
              FirebaseAuth.instance.currentUser!.displayName,
              FirebaseAuth.instance.currentUser!.uid,
            );
            PlatformManager.instance.analytics.onboardingStepCompleted('Name');
          },
        );
      case kPermissionsPage:
        return PermissionsWidget(
          goNext: () {
            _goNext();
            PlatformManager.instance.analytics.onboardingStepCompleted('Permissions');
          },
        );
      case kPrimaryLanguagePage:
        return PrimaryLanguageWidget(
          goNext: () {
            _goNext();
            PlatformManager.instance.analytics.onboardingStepCompleted('Primary Language');
          },
        );
      case kConnectOmiPage:
        return ConnectOmiStep(onDone: _leaveConnectOmi);
      default:
        return ActivationFlow(
          hasDevice: _deviceChoice == OnboardingDeviceChoice.connected || context.read<DeviceProvider>().isConnected,
          showPaywall: _showPaywall,
          onFinished: _finish,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final previous = _previousStep;
    final onActivation = _index == kActivationPage;
    return PopScope(
      // The flow owns onboarding: system back and the iOS swipe step back one step, never out.
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goBack();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: OmiColors.surface0,
          body: OnboardingStepLayout(
            reserveHeader: _index == kConnectOmiPage,
            onBack: previous == null ? null : _goBack,
            // The activation is a moment, not a form: no progress line over it.
            progress: onActivation
                ? null
                : OnboardingProgressLine(current: kProgressSteps.indexOf(_index), total: kProgressSteps.length),
            child: _StepTransition(
              index: _index,
              forward: _forward,
              // Arriving at Connect Omi is a moment, not another form: a plain cross-fade lets the
              // step's own entrance carry it.
              fadeOnly: _index == kConnectOmiPage,
              child: _page(_index),
            ),
          ),
        ),
      ),
    );
  }
}

/// Moves between steps: the new step slides in from the side the reader is heading and fades up,
/// the old one drifts the other way and fades out. Instant under Reduce Motion.
class _StepTransition extends StatelessWidget {
  const _StepTransition({required this.index, required this.forward, required this.child, this.fadeOnly = false});

  final int index;
  final bool forward;
  final bool fadeOnly;
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
        final from = fadeOnly ? 0.0 : ((incoming == forward) ? _shift : -_shift);
        return IgnorePointer(
          ignoring: !incoming,
          child: FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween<Offset>(begin: Offset(from, 0), end: Offset.zero).animate(animation),
              child: child,
            ),
          ),
        );
      },
      child: KeyedSubtree(key: ValueKey(index), child: child),
    );
  }
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
