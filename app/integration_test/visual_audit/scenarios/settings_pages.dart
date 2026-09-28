// Settings subpages reached from the settings group pages: developer, plan and usage, account
// deletion, transcription, language, notifications, integrations, phone calls, people, payments
// and the guided voice profile.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/payments/stripe_connect_setup.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/pages/settings/language_settings_page.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/phone_call_settings_page.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/settings/widgets/leave_flow_widgets.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';

import '../harness.dart';

const _account = 'Signed-in fixture account; no device connected';

final settingsPagesScenarios = <AuditScenario>[
  AuditScenario(
    id: 'settings-developer',
    title: 'Developer settings',
    page: 'lib/pages/settings/developer.dart (DeveloperSettingsPage)',
    state: _account,
    run: (a) async {
      await a.pump(const DeveloperSettingsPage());
      await a.scrollSeries('Open Developer settings');
    },
  ),
  AuditScenario(
    id: 'settings-usage',
    title: 'Plan & Usage before the subscription loads',
    page: 'lib/pages/settings/usage_page.dart (UsagePage)',
    state: 'Signed-in fixture account; the fixture backend serves no subscription or usage',
    run: (a) async {
      await a.pump(const UsagePage());
      await a.shot('Open Plan & Usage');
    },
  ),
  AuditScenario(
    id: 'settings-plans-sheet',
    title: 'Plans sheet when plans fail to load',
    page: 'lib/pages/settings/widgets/plans_sheet.dart (PlansSheet)',
    state: 'Signed-in fixture account; the fixture backend serves no plans; opened on a neutral host',
    run: (a) async {
      await a.pumpHost(
          (context) => showOmiSheet(context: context, padding: EdgeInsets.zero, builder: (_) => _PlansHost()));
      await a.shot('Open the Plans sheet');
    },
  ),
  AuditScenario(
    id: 'settings-delete-account',
    title: 'Delete account: reason step and typed confirmation',
    page: 'lib/pages/settings/delete_account.dart (DeleteAccount)',
    state: _account,
    run: (a) async {
      await a.pump(const DeleteAccount());
      await a.shot('Open the delete-account reason step', step: 'reason');
      await a.tap(find.byType(LeaveFlowReasonTile).first);
      await a.tap(find.widgetWithText(OmiButton, 'Continue'));
      await a.tap(find.widgetWithText(OmiButton, 'Continue'));
      await a.shot('Pick a reason, skip feedback, reach the typed confirmation', step: 'confirm');
    },
  ),
  AuditScenario(
    id: 'settings-transcription',
    title: 'Transcription settings',
    page: 'lib/pages/settings/transcription_settings_page.dart (TranscriptionSettingsPage)',
    state: _account,
    run: (a) async {
      await a.pump(const TranscriptionSettingsPage());
      await a.scrollSeries('Open Transcription settings');
    },
  ),
  AuditScenario(
    id: 'settings-language',
    title: 'Language settings',
    page: 'lib/pages/settings/language_settings_page.dart (LanguageSettingsPage)',
    state: _account,
    run: (a) async {
      await a.pump(const LanguageSettingsPage());
      await a.shot('Open Language settings');
    },
  ),
  AuditScenario(
    id: 'settings-notification-preferences',
    title: 'Notification preferences',
    page: 'lib/pages/settings/notifications_settings_page.dart (NotificationsSettingsPage)',
    state: 'Signed-in fixture account; the fixture backend has no notification-settings routes, so defaults show',
    run: (a) async {
      await a.pump(const NotificationsSettingsPage());
      await a.shot('Open Notifications settings');
    },
  ),
  AuditScenario(
    id: 'settings-integration',
    title: 'Integration settings page',
    page: 'lib/pages/settings/integration_settings_page.dart (IntegrationSettingsPage)',
    state: 'A connected Asana integration with no extra settings',
    run: (a) async {
      await a.pump(IntegrationSettingsPage(appName: 'Asana', appKey: 'asana', disconnectService: () async {}));
      await a.shot('Open the Asana integration settings page');
    },
  ),
  AuditScenario(
    id: 'settings-phone-calls-empty',
    title: 'Phone call settings with no verified numbers',
    page: 'lib/pages/settings/phone_call_settings_page.dart (PhoneCallSettingsPage)',
    state: 'PhoneCallProvider loaded with no verified numbers; the call event channel is silenced',
    run: (a) async {
      const channel = 'com.omi/phone_calls/events';
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMessageHandler(channel, (_) async => const StandardMethodCodec().encodeSuccessEnvelope(null));
      addTearDown(() => messenger.setMockMessageHandler(channel, null));
      await a.pump(const PhoneCallSettingsPage(), providers: [
        ChangeNotifierProvider<PhoneCallProvider>.value(value: _NoNumbersPhoneCallProvider()),
      ]);
      await a.shot('Open Phone Call settings with no verified numbers');
    },
  ),
  AuditScenario(
    id: 'settings-people',
    title: 'People with one enrolled person',
    page: 'lib/pages/settings/people.dart (UserPeoplePage)',
    state: 'PeopleProvider holding one person (Alex) with one speech sample',
    run: (a) async {
      final people = PeopleProvider(
          loadPeople: () async => [
                Person(
                  id: 'p1',
                  name: 'Alex',
                  createdAt: DateTime.utc(2026, 9, 1),
                  updatedAt: DateTime.utc(2026, 9, 1),
                  speechSamples: const ['https://example.invalid/sample-0.wav'],
                  speechSampleTranscripts: const ['Hello there'],
                ),
              ]);
      await a.pump(const UserPeoplePage(), providers: [ChangeNotifierProvider<PeopleProvider>.value(value: people)]);
      await a.shot('Open People with one enrolled person');
    },
  ),
  AuditScenario(
    id: 'settings-payments',
    title: 'Payments with no connected payout method',
    page: 'lib/pages/payments/payments_page.dart (PaymentsPage)',
    state: 'Inert PaymentMethodProvider: nothing connected, no countries loaded',
    run: (a) async {
      await a.pump(const PaymentsPage());
      await a.shot('Open Payments');
    },
  ),
  AuditScenario(
    id: 'settings-stripe-connect',
    title: 'Stripe connect setup and its country picker',
    page: 'lib/pages/payments/stripe_connect_setup.dart (StripeConnectSetup)',
    state: 'Inert PaymentMethodProvider: nothing connected, no countries loaded',
    run: (a) async {
      await a.pump(const StripeConnectSetup());
      await a.shot('Open Stripe connect setup', step: 'setup');
      await a.tap(find.text('Select your country').first);
      await a.shot('Open the titled country picker sheet', step: 'country-picker');
    },
  ),
  AuditScenario(
    id: 'settings-voice-profile',
    title: 'Voice profile guided introduction, first prompt',
    page: 'lib/pages/onboarding/speech_profile_widget.dart (SpeechProfileWidget)',
    state: 'Guided voice controller opened from Settings with a no-op microphone and network',
    run: (a) async {
      await a.pump(_voiceProfile(GuidedVoiceController(_SilentGuidedVoiceIO(), flowSource: 'settings')),
          scaffold: false);
      await a.shot('Open Voice Profile from Settings: first prompt, progress and Start');
    },
  ),
  AuditScenario(
    id: 'settings-voice-profile-review',
    title: 'Voice profile guided introduction, review step',
    page: 'lib/pages/onboarding/speech_profile_widget.dart (SpeechProfileWidget)',
    state: 'Guided voice controller past the last prompt holding one answer and one goal',
    run: (a) async {
      final flow = GuidedVoiceController(_SilentGuidedVoiceIO(), flowSource: 'settings')
        ..promptIndex = GuidedVoiceController.promptCount
        ..answers.addAll([
          IntroductionAnswer('I live in Austin and work on developer tools.', Uint8List(0), 'answer-1'),
          IntroductionAnswer('Launch my own studio next year.', Uint8List(0), 'answer-2', isGoal: true),
        ]);
      await a.pump(_voiceProfile(flow), scaffold: false);
      await a.shot('Every prompt answered: the review lists each answer, editable, with Save & Finish');
    },
  ),
];

Widget _voiceProfile(GuidedVoiceController flow) => Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: SpeechProfileWidget(flowSource: 'settings', controller: flow, goNext: () {}, onSkip: () {}),
    );

class _NoNumbersPhoneCallProvider extends PhoneCallProvider {
  _NoNumbersPhoneCallProvider() : super.forTesting();
  @override
  bool get numbersLoaded => true;
  @override
  List<VerifiedPhoneNumber> get verifiedNumbers => const [];
  @override
  Future<void> loadVerifiedNumbers() async {}
}

/// No microphone, network or on-device transcription behind the guided introduction.
class _SilentGuidedVoiceIO implements GuidedVoiceIO {
  @override
  bool get livePreview => false;
  @override
  Future<void> prepare() async {}
  @override
  Future<void> start(void Function(Uint8List) onAudio, VoidCallback onInterrupted) async {}
  @override
  Future<void> stop() async {}
  @override
  Future<String> transcribe(Uint8List pcm) async => '';
  @override
  Future<bool> enroll(Uint8List pcm) async => true;
  @override
  Future<bool> remember(String text) async => true;
  @override
  Future<bool> saveGoal(String text, String idempotencyKey) async => true;
  @override
  Future<void> close() async {}
}

/// PlansSheet borrows its animation controllers from the page that opens it.
class _PlansHost extends StatefulWidget {
  @override
  State<_PlansHost> createState() => _PlansHostState();
}

class _PlansHostState extends State<_PlansHost> with TickerProviderStateMixin {
  late final _wave = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
  late final _arrow = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..repeat();
  late final _notes = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  late final _arrowAnimation =
      Tween<double>(begin: 0, end: 10).animate(CurvedAnimation(parent: _arrow, curve: Curves.easeInOut));

  @override
  void dispose() {
    _wave.dispose();
    _arrow.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
      waveController: _wave, notesController: _notes, arrowController: _arrow, arrowAnimation: _arrowAnimation);
}
