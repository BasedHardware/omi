import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/capture/live_held_audio_state.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';

import '../support/on_device_fakes.dart';

class _HeldCaptureProvider extends ChangeNotifier implements CaptureProvider {
  @override
  final liveHeldAudio = LiveHeldAudioState();

  void receipt(int seconds, int resetAt, {bool paused = true}) {
    liveHeldAudio.apply(SttCapLiveHeldEvent(
      sessionId: 'socket-1',
      heldSeconds: seconds,
      paused: paused,
      resetAt: resetAt,
    ));
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _EmptyHeldUsageProvider extends ChangeNotifier implements UsageProvider {
  @override
  UserSubscriptionResponse? get subscription => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final previous = OmiColors.active;
    OmiColors.active = OmiPalette.light;
    addTearDown(() => OmiColors.active = previous);
  });

  final resetAt = DateTime.utc(2026, 11, 1).millisecondsSinceEpoch ~/ 1000;

  HeldAudioSummary summary({
    String state = 'paused',
    int seconds = 120,
    bool retainLive = true,
    int count = 0,
    List<HeldAudioRecording>? recordings,
  }) {
    return HeldAudioSummary(
      state: state,
      seconds: seconds,
      resetAt: resetAt,
      retainLive: retainLive,
      count: count,
      recordings: recordings ??
          [
            const HeldAudioRecording(id: 'newer', startedAt: 200, seconds: 90),
            const HeldAudioRecording(id: 'older', startedAt: 100, seconds: 30),
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

  testWidgets('live receipt appears without subscription summary and updates server counter', (tester) async {
    final capture = _HeldCaptureProvider();
    final usage = _EmptyHeldUsageProvider();
    addTearDown(capture.dispose);
    addTearDown(usage.dispose);
    await pump(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: capture),
            ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ],
          child: HeldAudioLiveBanner(controller: phone(), gate: true),
        ));
    expect(find.byKey(const Key('held_audio_live_banner')), findsNothing);
    capture.receipt(61, resetAt);
    await tester.pump();
    expect(find.text('Processing paused. You\'ve reached this month\'s limit.'), findsOneWidget);
    expect(find.text('2 min recorded since the limit'), findsOneWidget);
    expect(find.text('Waiting for processing'), findsOneWidget);
    capture.receipt(181, resetAt);
    await tester.pump();
    expect(find.text('4 min recorded since the limit'), findsOneWidget);
    capture.receipt(181, resetAt, paused: false);
    await tester.pump();
    expect(find.byKey(const Key('held_audio_live_banner')), findsNothing);
    expect(find.byKey(const Key('held_audio_live_placeholder')), findsNothing);
  });

  testWidgets('paused receipt overrides stale recovering summary and uses event reset date', (tester) async {
    final capture = _HeldCaptureProvider();
    addTearDown(capture.dispose);
    final eventReset = DateTime.utc(2026, 12, 1).millisecondsSinceEpoch ~/ 1000;
    capture.receipt(61, eventReset);
    await pump(
        tester,
        ChangeNotifierProvider<CaptureProvider>.value(
          value: capture,
          child: HeldAudioLiveBanner(
              controller: phone(), gate: true, summary: summary(state: 'recovering', retainLive: false)),
        ));
    expect(find.text('Processing paused. You\'ve reached this month\'s limit.'), findsOneWidget);
    expect(find.text('Transcribing your waiting recordings'), findsNothing);
    expect(find.text('Waiting for processing'), findsOneWidget);
    capture.receipt(61, eventReset, paused: false);
    await tester.pump();
    expect(find.text('Processing paused. You\'ve reached this month\'s limit.'), findsNothing);
    expect(find.text('Transcribing your waiting recordings'), findsNothing);
  });

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
    expect(find.text('2m waiting'), findsOneWidget);
    expect(
      find.textContaining('Your recordings and transcripts are saved.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('held_audio_row_newer')), findsOneWidget);
    expect(find.byKey(const Key('held_audio_row_older')), findsOneWidget);
    expect(find.text('1m 30s · Waiting for processing'), findsOneWidget);
    expect(find.text('30s · Waiting for processing'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_more')), findsNothing);

    await tester.tap(find.byKey(const Key('held_audio_upgrade')));
    await tester.tap(find.byKey(const Key('held_audio_on_phone')));
    expect(upgrades, 1);
    expect(phones, 1);
  });

  testWidgets('a truncated hold page says how many more exist', (tester) async {
    await pump(tester, HeldAudioHomeSection(controller: phone(), gate: true, summary: summary(count: 22)));
    expect(find.text('and 20 more'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_more')), findsOneWidget);
  });

  testWidgets('choosing the phone switches new recordings and says the backlog stays waiting', (tester) async {
    final controller = phone();
    await pump(tester, HeldAudioHomeSection(controller: controller, gate: true, summary: summary()));

    await tester.tap(find.byKey(const Key('held_audio_on_phone')));
    await tester.pump();
    await tester.pump();

    expect(controller.settings.enabled, isTrue);
    expect(find.textContaining('Your recordings and transcripts are saved.'), findsOneWidget);
    expect(
      find.textContaining('Waiting recordings stay waiting until you choose to process them.'),
      findsOneWidget,
    );
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

  testWidgets('inactive surfaces do not require a subscription provider', (tester) async {
    final controller = OnDeviceTranscriptionController(
      model: FakeOnDeviceModel(const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed)),
      power: FakePhonePowerSource(),
      manageNativeCustody: false,
    );
    addTearDown(controller.dispose);
    for (final surface in <Widget>[
      HeldAudioHomeSection(controller: controller),
      HeldAudioLiveBanner(controller: controller),
      HeldAudioUsageSection(controller: controller),
    ]) {
      await pump(tester, surface);
      expect(tester.takeException(), isNull);
      expect(find.byType(ProcessingBacklogView), findsNothing);
    }
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
    expect(find.text('Processing paused. You\'ve reached this month\'s limit.'), findsOneWidget);
    expect(find.textContaining('Your recordings and transcripts are saved.'), findsOneWidget);
    expect(find.byKey(const Key('held_audio_live_on_phone')), findsOneWidget);
    expect(find.text('2 min recorded since the limit'), findsOneWidget);
    expect(find.text('Waiting for processing'), findsOneWidget);
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
    expect(find.text('Processing paused. You\'ve reached this month\'s limit.'), findsNothing);
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
    expect(find.text('Waiting for processing'), findsOneWidget);
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
  testWidgets('legacy recovering never supplies automatic processing choice', (tester) async {
    final held = summary(state: 'recovering', retainLive: false);
    await pump(tester, HeldAudioHomeSection(controller: phone(), gate: true, summary: held));
    expect(find.textContaining('resets'), findsNothing);
    expect(find.text('Transcribing your waiting recordings'), findsNothing);
    expect(find.byKey(const Key('held_audio_upgrade')), findsOneWidget);
    await pump(tester, HeldAudioLiveBanner(controller: phone(), gate: true, summary: held, recordedSeconds: 61));
    expect(find.byKey(const Key('held_audio_live_banner')), findsNothing);
  });

  ProcessingBacklog backlog(String state, {bool exceeds = false}) => ProcessingBacklog(
        state: state,
        heldAudioSeconds: 7200,
        heldAudioCount: 2,
        deferredConversations: 1,
        estimatedUnits: 25,
        estimatedHours: 2.5,
        estimatedPercent: 12.5,
        remainingUnits: exceeds ? 10 : 100,
        exceedsRemaining: exceeds,
      );

  for (final state in ['capped', 'waiting_choice', 'processing', 'none']) {
    for (final surface in ['a', 'b', 'c']) {
      testWidgets('$surface hides processing card for $state and retains neighbors', (tester) async {
        var toggleCalls = 0;
        final value = backlog(state);
        final controller = phone(enabled: true);
        final Widget child = switch (surface) {
          'a' => HeldAudioHomeSection(controller: controller, gate: true, summary: summary(), backlog: value),
          'b' => HeldAudioLiveBanner(controller: controller, gate: true, recordedSeconds: 60, backlog: value),
          _ => HeldAudioUsageSection(
              controller: controller, gate: true, backlog: value, paid: true, onSaveLiveHours: (_) => toggleCalls++),
        };
        await pump(tester, child);
        expect(find.byKey(Key('processing_backlog_$surface')), findsNothing);
        expect(find.textContaining('Process now uses about'), findsNothing);
        expect(find.text('Process waiting recordings'), findsNothing);
        expect(find.byKey(Key('processing_backlog_upgrade_$surface')), findsNothing);
        if (surface == 'a' && state != 'none') {
          expect(find.byKey(const Key('held_audio_row_newer')), findsOneWidget);
          expect(find.byKey(const Key('held_audio_row_older')), findsOneWidget);
        }
        if (surface == 'c' && state != 'none') {
          expect(find.byKey(const Key('held_audio_usage_toggle')), findsOneWidget);
          await tester.tap(find.byType(Switch));
          await tester.pump();
          expect(toggleCalls, 1);
        }
      });
    }
  }
}
