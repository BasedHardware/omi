import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';

import '../support/on_device_fakes.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final previous = OmiColors.active;
    OmiColors.active = OmiPalette.light;
    addTearDown(() => OmiColors.active = previous);
  });

  const recordings = [
    HeldAudioRecording(id: 'newer', startedAt: 200, seconds: 90),
    HeldAudioRecording(id: 'older', startedAt: 100, seconds: 30),
  ];

  HeldAudioSummary summary({int seconds = 120, int count = 2}) => HeldAudioSummary(
        state: 'paused',
        seconds: seconds,
        resetAt: 0,
        retainLive: true,
        count: count,
        recordings: recordings,
      );

  OnDeviceTranscriptionController phone({
    bool enabled = false,
    OnDeviceModelPhase phase = OnDeviceModelPhase.installed,
  }) {
    return OnDeviceTranscriptionController(
      model: FakeOnDeviceModel(OnDeviceModelStatus(phase: phase)),
      power: FakePhonePowerSource(),
      manageNativeCustody: false,
    )..debugActivate(settings: OnDeviceSettings(enabled: enabled));
  }

  Future<void> pump(WidgetTester tester, Widget child) async {
    await tester.pumpWidget(MaterialApp(
      locale: const Locale('en'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildOmiTheme(brightness: Brightness.light),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ));
    await tester.pump();
  }

  test('waiting recordings become locked rows, and a running release shows none', () {
    expect(lockedHeldRecordings(null, null), isEmpty);
    expect(lockedHeldRecordings(summary(seconds: 0), null), isEmpty);
    expect(lockedHeldRecordings(summary(), null), recordings);
    expect(lockedHeldRecordings(summary(), const ProcessingBacklog(state: 'capped')), recordings);
    expect(lockedHeldRecordings(summary(), const ProcessingBacklog(state: 'waiting_choice')), recordings);
    expect(lockedHeldRecordings(summary(), const ProcessingBacklog(state: 'processing')), isEmpty);
  });

  testWidgets('a locked row names the recording and acts when tapped', (tester) async {
    var pressed = 0;
    await pump(tester, HeldRecordingLockedRow(recording: recordings.first, onPressed: () => pressed++));
    expect(find.byKey(const Key('held_recording_locked_newer')), findsOneWidget);
    expect(find.byKey(const Key('held_audio_more')), findsNothing);
    await tester.tap(find.text('Upgrade'));
    await tester.pump();
    expect(pressed, 1);
  });

  testWidgets('the last row says how many more the server did not list', (tester) async {
    await pump(tester, HeldRecordingLockedRow(recording: recordings.last, more: 3, onPressed: () {}));
    expect(find.byKey(const Key('held_audio_more')), findsOneWidget);
  });

  testWidgets('phone choice is offered only when this phone can run the engine and is not already on', (tester) async {
    expect(heldAudioPhoneEligible(phone()), isTrue);
    expect(heldAudioPhoneEligible(phone(phase: OnDeviceModelPhase.unsupported)), isFalse);
  });

  testWidgets('save-live-hours stays for a paid owner on a capable phone', (tester) async {
    await pump(tester, SaveLiveHoursRow(controller: phone(), paid: true, onChanged: (_) {}));
    expect(find.byKey(const Key('held_audio_usage_toggle')), findsOneWidget);
  });

  testWidgets('save-live-hours stays hidden for an unpaid owner', (tester) async {
    await pump(tester, SaveLiveHoursRow(controller: phone(), paid: false, onChanged: (_) {}));
    expect(find.byKey(const Key('held_audio_usage_toggle')), findsNothing);
  });
}
