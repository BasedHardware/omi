import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/variants/pocket/pocket_pairing_step.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The `pocket` arm of `onboarding-variant`: the native steps in Pocket's order. After the sign-up
/// paywall (and its 30-day upsell, both owned by the wrapper): permissions, pairing that starts by
/// itself, the device walkthrough when an Omi connected, how did you find us, language, and the
/// name only when sign-in did not provide one. No voice intro, no capture-choice screen. The
/// wrapper still owns completion through [onComplete].
class PocketOnboardingFlow extends StatefulWidget {
  const PocketOnboardingFlow({super.key, required this.onComplete});

  final Future<bool> Function({required bool paywallShown}) onComplete;

  @override
  State<PocketOnboardingFlow> createState() => _PocketOnboardingFlowState();
}

class _PocketOnboardingFlowState extends State<PocketOnboardingFlow> {
  static const int kPermissionsPage = 0;
  static const int kPairingPage = 1;
  static const int kFoundOmiPage = 2;
  static const int kPrimaryLanguagePage = 3;
  static const int kNamePage = 4;

  late int _index;
  bool _finishing = false;

  static String resumeKey(String uid) => 'onboarding/pocket/resumeStep/$uid';

  @override
  void initState() {
    super.initState();
    final saved =
        SharedPreferencesUtil().getInt(resumeKey(SharedPreferencesUtil().uid), defaultValue: kPermissionsPage);
    _index = saved >= kPermissionsPage && saved <= kNamePage ? saved : kPermissionsPage;
  }

  void _show(int index) {
    if (!mounted) return;
    setState(() => _index = index);
    SharedPreferencesUtil().saveInt(resumeKey(SharedPreferencesUtil().uid), index);
  }

  void _step(String name, int next) {
    PlatformManager.instance.analytics.onboardingStepCompleted(name);
    if (next > kNamePage) {
      unawaited(_finish());
    } else {
      _show(next);
    }
  }

  bool _needsDeviceTutorial() {
    if (SharedPreferencesUtil().deviceOnboardingCompleted) return false;
    final devices = context.read<DeviceProvider>();
    final device = devices.connectedDevice;
    if (device == null || device.type != DeviceType.omi) return false;
    return DeviceUtils.isOmiCv1(modelNumber: devices.pairedDevice?.modelNumber, deviceName: device.name);
  }

  Future<void> _leavePairing(bool connected) async {
    PlatformManager.instance.analytics.onboardingStepCompleted('Pairing');
    if (connected && _needsDeviceTutorial()) {
      await routeToPage(context, const InteractiveDeviceOnboardingWrapper());
      if (!mounted) return;
    }
    _show(kFoundOmiPage);
  }

  /// Sign-in usually brings a name; the name step only runs when it did not.
  int get _afterLanguage => SharedPreferencesUtil().givenName.trim().isEmpty ? kNamePage : kNamePage + 1;

  Future<void> _finish() async {
    if (_finishing) return;
    _finishing = true;
    final usage = context.read<UsageProvider>();
    if (usage.subscription?.subscription.plan.isPaid != true) {
      SharedPreferencesUtil().homeTrialSheetPending = true;
    }
    // The first conversation should be on Home when it opens; a slow or failed seed never holds
    // onboarding.
    await seedOnboardingConversation().timeout(const Duration(seconds: 4), onTimeout: () => false);
    if (!mounted) return;
    final saved = await widget.onComplete(paywallShown: false);
    if (saved) SharedPreferencesUtil().remove(resumeKey(SharedPreferencesUtil().uid));
    _finishing = false;
  }

  String _background(int index) {
    switch (index) {
      case kPermissionsPage:
        return Assets.images.onboardingBg3.path;
      case kPrimaryLanguagePage:
        return Assets.images.onboardingBg4.path;
      default:
        return Assets.images.onboardingBg1.path;
    }
  }

  Widget _page(int index) {
    switch (index) {
      case kPermissionsPage:
        return PermissionsWidget(goNext: () => _step('Permissions', kPairingPage));
      case kPairingPage:
        return PocketPairingStep(onDone: _leavePairing);
      case kFoundOmiPage:
        return FoundOmiWidget(goNext: () => _step('Found Omi', kPrimaryLanguagePage));
      case kPrimaryLanguagePage:
        return PrimaryLanguageWidget(goNext: () => _step('Primary Language', _afterLanguage));
      default:
        return NameWidget(goNext: () => _step('Name', kNamePage + 1));
    }
  }

  /// System back and the iOS swipe step back one page and never leave the flow. Pairing owns its
  /// own back (the same guarded skip as its visible button); permissions has nowhere to go.
  void _systemBack() {
    switch (_index) {
      case kFoundOmiPage:
        _show(kPairingPage);
      case kPrimaryLanguagePage:
        _show(kFoundOmiPage);
      case kNamePage:
        _show(kPrimaryLanguagePage);
      default:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _systemBack();
      },
      child: _index == kPairingPage ? _page(_index) : _stepPage(context),
    );
  }

  Widget _stepPage(BuildContext context) {
    final media = MediaQuery.of(context);
    return Scaffold(
      body: Stack(
        children: [
          Container(
            height: media.size.height,
            decoration: BoxDecoration(
              image: DecorationImage(
                image: ResizeImage(
                  AssetImage(_background(_index)),
                  width: (media.size.width * media.devicePixelRatio).round(),
                  height: (media.size.height * media.devicePixelRatio).round(),
                ),
                fit: BoxFit.cover,
              ),
            ),
          ),
          KeyedSubtree(key: ValueKey(_index), child: _page(_index)),
        ],
      ),
    );
  }
}
