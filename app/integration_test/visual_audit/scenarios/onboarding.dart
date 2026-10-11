// First-run onboarding steps: AI consent, survey, name, language, permissions, progress dots and
// the device search.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';

import '../harness.dart';

final onboardingScenarios = <AuditScenario>[
  AuditScenario(
    id: 'onboarding-ai-consent',
    title: 'AI consent step',
    page: 'lib/pages/onboarding/ai_consent_widget.dart (AiConsentWidget)',
    state: 'Signed-in fixture account that has not yet agreed',
    run: (a) async {
      await a.pump(AiConsentWidget(onAgree: () {}, onUseDifferentAccount: () {}));
      await a.shot('AI consent: Agree & Continue and Use a Different Account');
    },
  ),
  AuditScenario(
    id: 'onboarding-found-omi',
    title: '"Where did you hear about Omi" survey',
    page: 'lib/pages/onboarding/found_omi/found_omi_widget.dart (FoundOmiWidget)',
    state: 'No answer chosen yet',
    run: (a) async {
      await a.pump(FoundOmiWidget(goNext: () {}));
      await a.shot('The survey with its Skip affordance');
    },
  ),
  AuditScenario(
    id: 'onboarding-name',
    title: 'Name step',
    page: 'lib/pages/onboarding/name/name_widget.dart (NameWidget)',
    state: 'Signed-in fixture account with no given name',
    run: (a) async {
      await a.pump(NameWidget(goNext: () {}));
      await a.shot('Onboarding name step');
    },
  ),
  AuditScenario(
    id: 'onboarding-language',
    title: 'Primary language step',
    page: 'lib/pages/onboarding/primary_language/primary_language_widget.dart (PrimaryLanguageWidget)',
    state: 'No primary language chosen yet',
    run: (a) async {
      await a.pump(PrimaryLanguageWidget(goNext: () {}));
      await a.shot('Onboarding primary-language step');
    },
  ),
  AuditScenario(
    id: 'onboarding-permissions',
    title: 'Permissions step, one row per permission',
    page: 'lib/pages/onboarding/permissions/permissions_widget.dart (PermissionsWidget)',
    state: 'A permissions source reporting location askable and notifications blocked',
    run: (a) async {
      await a.pump(PermissionsWidget(goNext: () {}, source: _FixedPermissionsSource()));
      await a.shot('Onboarding permissions step');
    },
  ),
  AuditScenario(
    id: 'onboarding-progress-dots',
    title: 'Onboarding progress dots',
    page: 'lib/pages/onboarding/wrapper.dart (OnboardingProgressDots)',
    state: 'Step 2 of 6',
    run: (a) async {
      await a.pump(const Center(child: OnboardingProgressDots(current: 1, total: 6)));
      await a.shot('Progress dots on step 2 of 6');
    },
  ),
  AuditScenario(
    id: 'onboarding-find-devices-none',
    title: 'Find devices: nothing found',
    page: 'lib/pages/onboarding/find_device/page.dart (FindDevicesPage)',
    state:
        'OnboardingProvider with no discovered devices and pairing instructions enabled; BLE scan and speaker-profile check are no-ops',
    run: (a) async {
      await a.pump(FindDevicesPage(goNext: () {}, includeSkip: true, isFromOnboarding: true), providers: [
        ChangeNotifierProvider<OnboardingProvider>.value(value: _NoDevicesOnboardingProvider()),
        ChangeNotifierProvider<HomeProvider>(create: (_) => _NoSpeakerCheckHomeProvider()),
      ]);
      await a.shot("The can't-find-your-device state");
    },
  ),
];

class _FixedPermissionsSource implements OnboardingPermissionsSource {
  @override
  List<OnboardingPermission> get permissions =>
      const [OnboardingPermission.location, OnboardingPermission.notifications];
  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async =>
      permission == OnboardingPermission.notifications ? OmiPermissionStatus.blocked : OmiPermissionStatus.askable;
  @override
  Future<void> request(OnboardingPermission permission) async {}
}

/// deviceList and enableInstructions are plain fields; only the BLE scan needs replacing.
class _NoDevicesOnboardingProvider extends OnboardingProvider {
  _NoDevicesOnboardingProvider() {
    deviceList = [];
    enableInstructions = true;
  }
  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
}

/// The page asks HomeProvider for the speaker profile, which reports to analytics through an
/// uninitialised Env; the answer does not change this screen.
class _NoSpeakerCheckHomeProvider extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}
