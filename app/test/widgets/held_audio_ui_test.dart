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

  final resetAt = DateTime.utc(2026, 11, 1).millisecondsSinceEpoch ~/ 1000;

  HeldAudioSummary summary({int seconds = 120, bool retainLive = true, List<HeldAudioRecording>? recordings}) {
    return HeldAudioSummary(
      seconds: seconds,
      resetAt: resetAt,
      retainLive: retainLive,
      recordings: recordings ??
          [
            HeldAudioRecording(id: 'newer', startedAt: 200, seconds: 90),
            HeldAudioRecording(id: 'older', startedAt: 100, seconds: 30),
          ],
    );
  }

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

  testWidgets('home card lists waiting recordings and both actions', (tester) async {
    var upgrades = 0;
    var phones = 0;
    await pump(
      tester,
      HeldAudioHomeSection(
        controller: phone(),
        gate: true,
        summary: summary(),
        onUpgrade: () => upgrades++,
        onPhone: () => phones++,
      ),
    );

    expect(find.byKey(const Key('held_audio_card')), findsOneWidget);
    expect(find.text('2m waiting to transcribe'), findsOneWidget);
    expect(find.textContaining('Your recordings are saved and will be transcribed on Nov 1, 2026'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_row_newer')), findsOneWidget);
    expect(find.byKey(const Key('held_audio_row_older')), findsOneWidget);
    expect(find.text('1m 30s · Waiting to transcribe'), findsOneWidget);
    expect(find.text('30s · Waiting to transcribe'), findsOneWidget);

    await tester.tap(find.byKey(const Key('held_audio_upgrade')));
    await tester.tap(find.byKey(const Key('held_audio_on_phone')));
    expect(upgrades, 1);
    expect(phones, 1);
  });

  testWidgets('choosing the phone switches new recordings and says the backlog stays waiting', (tester) async {
    final controller = phone();
    await pump(tester, HeldAudioHomeSection(controller: controller, gate: true, summary: summary()));

    await tester.tap(find.byKey(const Key('held_audio_on_phone')));
    await tester.pump();
    await tester.pump();

    expect(controller.settings.enabled, isTrue);
    expect(find.textContaining('New recordings will transcribe on this phone'), findsOneWidget);
    expect(find.textContaining('Waiting recordings transcribe on Nov 1, 2026'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_on_phone')), findsNothing);
    expect(find.byKey(const Key('held_audio_upgrade')), findsOneWidget);
  });

  testWidgets('phone action stays hidden when this phone cannot run the engine', (tester) async {
    await pump(
      tester,
      HeldAudioHomeSection(
        controller: phone(phase: OnDeviceModelPhase.unsupported),
        gate: true,
        summary: summary(),
        onUpgrade: () {},
        onPhone: () {},
      ),
    );
    expect(find.byKey(const Key('held_audio_on_phone')), findsNothing);
    expect(find.byKey(const Key('held_audio_upgrade')), findsOneWidget);
  });

  testWidgets('flag off leaves the conversations list unchanged', (tester) async {
    await pump(
      tester,
      HeldAudioHomeSection(controller: phone(), gate: false, summary: summary(), onUpgrade: () {}, onPhone: () {}),
    );
    expect(find.byKey(const Key('held_audio_card')), findsNothing);
    expect(find.byKey(const Key('held_audio_row_newer')), findsNothing);
    expect(find.textContaining('waiting to transcribe'), findsNothing);
  });

  testWidgets('live banner and transcript placeholder', (tester) async {
    var upgrades = 0;
    await pump(
      tester,
      HeldAudioLiveBanner(
        controller: phone(),
        gate: true,
        summary: summary(),
        recordedSeconds: 61,
        onUpgrade: () => upgrades++,
        onPhone: () {},
      ),
    );
    expect(find.byKey(const Key('held_audio_live_banner')), findsOneWidget);
    expect(find.text('Cloud transcription paused'), findsOneWidget);
    expect(find.textContaining('Omi keeps recording'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_live_on_phone')), findsOneWidget);
    expect(find.text('2 min recorded since the limit'), findsOneWidget);
    expect(find.text('Transcribes on Nov 1, 2026'), findsOneWidget);
    await tester.tap(find.byKey(const Key('held_audio_live_upgrade')));
    expect(upgrades, 1);
  });

  testWidgets('live placeholder stays hidden once the phone is transcribing', (tester) async {
    await pump(
      tester,
      HeldAudioLiveBanner(
        controller: phone(enabled: true),
        gate: true,
        summary: summary(),
        recordedSeconds: 61,
        onUpgrade: () {},
        onPhone: () {},
      ),
    );
    expect(find.byKey(const Key('held_audio_live_banner')), findsOneWidget);
    expect(find.byKey(const Key('held_audio_live_placeholder')), findsNothing);
    expect(find.byKey(const Key('held_audio_live_on_phone')), findsNothing);
  });

  testWidgets('flag off leaves the live transcript unchanged', (tester) async {
    await pump(
      tester,
      HeldAudioLiveBanner(
        controller: phone(),
        gate: false,
        summary: summary(),
        recordedSeconds: 61,
        onUpgrade: () {},
        onPhone: () {},
      ),
    );
    expect(find.byKey(const Key('held_audio_live_banner')), findsNothing);
    expect(find.text('Cloud transcription paused'), findsNothing);
  });

  testWidgets('usage row sits with the phone toggle and plans', (tester) async {
    var plans = 0;
    bool? saved;
    await pump(
      tester,
      HeldAudioUsageSection(
        controller: phone(),
        gate: true,
        summary: summary(retainLive: false),
        paid: true,
        onUpgrade: () => plans++,
        onSaveLiveHours: (value) => saved = value,
      ),
    );
    expect(find.byKey(const Key('held_audio_usage_waiting')), findsOneWidget);
    expect(find.text('2m waiting'), findsOneWidget);
    expect(find.text('Transcribed automatically on Nov 1, 2026'), findsOneWidget);
    expect(find.text('Always transcribe on this phone'), findsOneWidget);
    expect(find.text('See plans'), findsOneWidget);
    await tester.tap(find.byKey(const Key('held_audio_usage_plans')));
    await tester.tap(find.byKey(const Key('held_audio_usage_toggle')));
    expect(plans, 1);
    expect(saved, isTrue);
  });

  testWidgets('unpaid usage omits the always-on-phone toggle', (tester) async {
    await pump(
      tester,
      HeldAudioUsageSection(
        controller: phone(),
        gate: true,
        summary: summary(),
        paid: false,
        onUpgrade: () {},
      ),
    );
    expect(find.byKey(const Key('held_audio_usage_waiting')), findsOneWidget);
    expect(find.byKey(const Key('held_audio_usage_toggle')), findsNothing);
    expect(find.byKey(const Key('held_audio_usage_plans')), findsOneWidget);
  });

  testWidgets('flag off leaves usage unchanged', (tester) async {
    await pump(
      tester,
      HeldAudioUsageSection(controller: phone(), gate: false, summary: summary(), paid: true, onUpgrade: () {}),
    );
    expect(find.byKey(const Key('held_audio_usage_waiting')), findsNothing);
    expect(find.text('See plans'), findsNothing);
  });
}
