// First-run onboarding steps: AI consent, survey, name, language, permissions, progress dots and
// the device search.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/onboarding/pick_device_step.dart';
import 'package:omi/pages/capture/connect.dart';
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
    id: 'onboarding-welcome',
    title: 'Welcome, then Sign in',
    page: 'lib/pages/onboarding/auth.dart (AuthComponent)',
    state: 'Signed out; first launch',
    run: (a) async {
      await a.pump(AuthComponent(onSignIn: () {}));
      await a.shot('Welcome: pendant, headline, Get Started', step: 'welcome');
      await a.tap(find.byKey(const Key('auth_get_started')));
      await a.shot('Sign in: Apple and Google', step: 'sign-in');
    },
  ),
  AuditScenario(
    id: 'onboarding-complete',
    title: 'You are all set',
    page: 'lib/pages/onboarding/complete_screen.dart (OnboardingCompleteScreen)',
    state: 'Every onboarding step done',
    run: (a) async {
      await a.pump(OnboardingCompleteScreen(onComplete: () {}));
      await a.shot('Complete: pendant and Start Using Omi');
    },
  ),
  AuditScenario(
    id: 'onboarding-knows',
    title: 'Here is what I know about you: the sample map',
    page: 'lib/pages/onboarding/knowledge_graph_step.dart (OnboardingKnowledgeGraphStep)',
    state: 'A new account named Ashwin: no memories yet, so the step shows a sample map',
    prefs: const {'givenName': 'Ashwin'},
    run: (a) async {
      await a.pump(OnboardingKnowledgeGraphStep(onContinue: () {}));
      await a.shot('Knows: the reader at the centre, four topics, Continue');
    },
  ),
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
    id: 'onboarding-pick-device',
    title: 'What will you wear? (the first question)',
    page: 'lib/pages/onboarding/pick_device_step.dart (OnboardingPickDeviceStep)',
    state: 'Signed in, consent given; nothing paired',
    run: (a) async {
      await a.pump(Scaffold(body: OnboardingPickDeviceStep(goNext: () {})));
      await a.scrollSeries('Open the device question');
    },
  ),
  AuditScenario(
    id: 'onboarding-connect',
    title: 'Connect in onboarding: three steps, Continue and Set up later',
    page: 'lib/pages/capture/connect.dart (ConnectDevicePage)',
    state: 'OnboardingProvider reporting a connected device with Bluetooth allowed; no words heard yet',
    run: (a) async {
      await a.pump(ConnectDevicePage(onDone: () {}), providers: [
        ChangeNotifierProvider<OnboardingProvider>.value(value: _ConnectedOnboardingProvider()),
        ChangeNotifierProvider<HomeProvider>(create: (_) => _NoSpeakerCheckHomeProvider()),
      ]);
      await a.shot('Connected: steps 1 and 2 ticked, the live test waiting for words');
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
class _ConnectedOnboardingProvider extends OnboardingProvider {
  _ConnectedOnboardingProvider() {
    deviceList = [];
    isConnected = true;
    hasBluetoothPermission = true;
  }
  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
}

class _NoSpeakerCheckHomeProvider extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}
