import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/first_capture_controller.dart';
import 'package:omi/pages/onboarding/first_capture_page.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/onboarding/onboarding_step_telemetry.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../integration_test/visual_audit/fakes.dart' show AuditDeviceProvider;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

Widget host(Widget child, {TargetPlatform platform = TargetPlatform.iOS}) => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.light).copyWith(
          platform: platform,
          appBarTheme: buildOmiTheme(brightness: Brightness.light).appBarTheme.copyWith(
              titleTextStyle:
                  OmiType.headline.copyWith(fontFamily: platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto')),
          textTheme: buildOmiTheme(brightness: Brightness.light)
              .textTheme
              .apply(fontFamily: platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto')),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

class FakeCaptureIO implements FirstCaptureIO {
  @override
  String transcript = '';
  int starts = 0, finishes = 0, cancels = 0;
  ServerConversation? result;
  Completer<ServerConversation?>? processing;
  bool failStart = false;
  @override
  Future<void> start() async {
    starts++;
    if (failStart) throw StateError('permission');
  }

  @override
  Future<ServerConversation?> finish({bool Function()? isCurrent}) async {
    finishes++;
    if (processing != null) return await processing!.future;
    return result;
  }

  @override
  Future<void> cancel() async {
    cancels++;
  }
}

ServerConversation exampleConversation() => ServerConversation(
      id: 'first',
      createdAt: DateTime(2026, 10, 13),
      structured: Structured('Planning today’s work',
          'You’re working on the launch today. Your next step is to finish the onboarding flow and share it with your team.'),
      transcriptSegments: [
        TranscriptSegment(
            id: 'segment',
            text: 'Today I am working on the launch and preparing the onboarding flow.',
            speaker: 'SPEAKER_0',
            isUser: true,
            personId: null,
            start: 0,
            end: 30,
            translations: [])
      ],
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('phone routing, minimum duration, processing, result and capture telemetry', (tester) async {
    var now = DateTime(2026);
    final io = FakeCaptureIO()..processing = Completer<ServerConversation?>();
    final events = <RegisteredEvent>[];
    final props = <String, Object>{};
    final flow = FirstCaptureController(io, emit: events.add, now: () => now);
    var completed = false;
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () => completed = true,
        emit: events.add,
        setProperty: (k, v) => props[k] = v,
        phoneControllerFactory: () => flow)));
    expect(events.single.wireName, 'Onboarding First Capture Shown');
    await tester.tap(find.byKey(const Key('first_capture_phone')));
    await tester.pumpAndSettle();
    expect(props, {'capture_choice': 'phone', 'has_omi_device': false});
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    await tester.pump();
    now = now.add(const Duration(seconds: 5));
    await tester.pump(const Duration(seconds: 5));
    expect(flow.canFinish, isTrue);
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Finish This Recording?'), findsOneWidget);
    await tester.tap(find.text('Keep Recording'));
    await tester.pumpAndSettle();
    expect(io.finishes, 0);
    io.transcript = 'Today I am working on the launch.';
    now = now.add(const Duration(seconds: 25));
    await tester.pump(const Duration(seconds: 25));
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    await tester.pump();
    expect(flow.phase, FirstCapturePhase.processing);
    expect(completed, isFalse);
    io.processing!.complete(exampleConversation());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('first_capture_result_card')), findsOneWidget);
    final event = events.whereType<OnboardingFirstCaptureRecordingCompleted>().single;
    expect(event.properties, {'duration_s': 30, 'transcript_observed': true});
    expect(events.whereType<OnboardingFirstCaptureConversationShown>().length, 1);
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    expect(completed, isTrue);
    await tester.pumpAndSettle();
    expect(find.byType(FirstCapturePage), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('empty response offers retry and explicit skip without completing early', (tester) async {
    var now = DateTime(2026);
    final io = FakeCaptureIO()..result = (exampleConversation()..discarded = true);
    final events = <RegisteredEvent>[];
    final flow = FirstCaptureController(io, emit: events.add, now: () => now);
    var skipped = false;
    await tester.pumpWidget(host(FirstCapturePage(controller: flow, onComplete: () {}, onSkip: () => skipped = true)));
    await flow.start();
    now = now.add(const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 30));
    await flow.finish();
    await tester.pump();
    expect(find.text("I didn't catch enough speech, try again with a few sentences"), findsOneWidget);
    expect(events.whereType<OnboardingFirstCaptureEmptyResult>().length, 1);
    expect(skipped, isFalse);
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    await tester.pump();
    expect(io.starts, 2);
    await flow.leave();
    flow.phase = FirstCapturePhase.empty;
    await tester.pumpWidget(host(FirstCapturePage(controller: flow, onComplete: () {}, onSkip: () => skipped = true)));
    await tester.tap(find.byKey(const Key('first_capture_skip')));
    expect(skipped, isTrue);
    flow.dispose();
  });

  testWidgets('pair cancel returns to choices; successful pair completes; skip emits properties', (tester) async {
    var paired = false, completed = 0;
    final events = <RegisteredEvent>[];
    final props = <String, Object>{};
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () => completed++,
        emit: events.add,
        setProperty: (k, v) => props[k] = v,
        pairDevice: (_) async => paired)));
    await tester.tap(find.byKey(const Key('first_capture_omi')));
    await tester.pump();
    expect(completed, 0);
    expect(props, {'capture_choice': 'omi', 'has_omi_device': false});
    paired = true;
    await tester.tap(find.byKey(const Key('first_capture_omi')));
    await tester.pump();
    expect(completed, 1);
    expect(props['has_omi_device'], isTrue);
    await tester.tap(find.byKey(const Key('onboarding_complete_start')));
    expect(props['capture_choice'], 'skipped');
    expect(events.whereType<OnboardingFirstCaptureSkipped>().length, 1);
  });

  testWidgets('already saved Omi retains has_omi_device without a new pair', (tester) async {
    await SharedPreferencesUtil().btDeviceSet(BtDevice(id: 'saved-omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
    final props = <String, Object>{};
    await tester.pumpWidget(host(
        OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (key, value) => props[key] = value)));
    await tester.tap(find.byKey(const Key('onboarding_complete_start')));
    expect(props['has_omi_device'], isTrue);
  });

  testWidgets('Watch routes to instructions only on iOS; Back returns to choices', (tester) async {
    final events = <RegisteredEvent>[];
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () {},
        emit: events.add,
        setProperty: (_, value) {},
        watchStateProbe: () async => (paired: true, installed: false))));
    await tester.tap(find.byKey(const Key('first_capture_watch')));
    await tester.pumpAndSettle();
    expect(find.byType(FirstCaptureWatchInstructions), findsOneWidget);
    expect(events.whereType<OnboardingFirstCaptureChoiceSelected>().single.properties, {'choice': 'apple_watch'});
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('first_capture_phone')), findsOneWidget);
    await tester.pumpWidget(host(OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, value) {}),
        platform: TargetPlatform.android));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('first_capture_watch')), findsNothing);
  });

  testWidgets('automatic finish at 60 seconds; leaving cancels only owned attempt', (tester) async {
    var now = DateTime(2026);
    final io = FakeCaptureIO();
    final flow = FirstCaptureController(io, emit: (_) {}, now: () => now);
    await flow.start();
    now = now.add(const Duration(seconds: 60));
    await tester.pump(const Duration(seconds: 60));
    expect(io.finishes, 1);
    expect(flow.phase, FirstCapturePhase.delayed);
    await flow.start();
    await flow.leave();
    expect(io.cancels, 1);
    flow.dispose();
  });

  testWidgets('Back from phone capture cancels the attempt and returns to the persisted choice screen', (tester) async {
    final io = FakeCaptureIO();
    final flow = FirstCaptureController(io, emit: (_) {});
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () {}, emit: (_) {}, setProperty: (_, value) {}, phoneControllerFactory: () => flow)));
    await tester.tap(find.byKey(const Key('first_capture_phone')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('first_capture_primary')));
    await tester.pump();
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.text('Leave This Recording?'), findsOneWidget);
    await tester.tap(find.text('Keep Recording'));
    await tester.pumpAndSettle();
    expect(io.cancels, 0);
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Stop Recording'));
    await tester.pumpAndSettle();
    expect(io.cancels, 1);
    expect(find.byKey(const Key('first_capture_phone')), findsOneWidget);
  });

  testWidgets('observed speech plus missing result is delayed; start failures allow retry', (tester) async {
    var now = DateTime(2026);
    final io = FakeCaptureIO()..failStart = true;
    final events = <RegisteredEvent>[];
    final flow = FirstCaptureController(io, emit: events.add, now: () => now);
    await flow.start();
    expect(flow.phase, FirstCapturePhase.error);
    expect(events, isEmpty);
    io.failStart = false;
    await flow.start();
    io.transcript = 'My goal today is to finish the launch.';
    now = now.add(const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 30));
    await flow.finish();
    expect(flow.phase, FirstCapturePhase.delayed);
    expect(events.whereType<OnboardingFirstCaptureEmptyResult>(), isEmpty);
    flow.dispose();
  });

  testWidgets(
      'null Finish is delayed even with no transcript; late speech is observed; Back during processing never cancels',
      (tester) async {
    final io = FakeCaptureIO()..processing = Completer<ServerConversation?>();
    final events = <RegisteredEvent>[];
    final flow = FirstCaptureController(io, emit: events.add);
    await tester.pumpWidget(host(FirstCapturePage(controller: flow, onComplete: () {}, onSkip: () {})));
    await flow.start();
    final pending = flow.finish();
    await tester.pump();
    await flow.leave();
    expect(io.cancels, 0);
    io.processing!.complete(null);
    await pending;
    flow.dispose();
    final lateIO = FakeCaptureIO()..processing = Completer<ServerConversation?>();
    final late = FirstCaptureController(lateIO, emit: events.add);
    await tester.pumpWidget(host(FirstCapturePage(controller: late, onComplete: () {}, onSkip: () {})));
    await late.start();
    final finishing = late.finish();
    lateIO.transcript = 'Speech arrived during processing';
    lateIO.processing!.complete(null);
    await finishing;
    await tester.pump();
    expect(late.phase, FirstCapturePhase.delayed);
    expect(late.transcriptObserved, isTrue);
    expect(
        find.text('Your recording is taking longer to process. You can check your conversations on Home or try again.'),
        findsOneWidget);
    expect(events.whereType<OnboardingFirstCaptureEmptyResult>(), isEmpty);
    late.dispose();
  });

  testWidgets('only a terminal discarded or completed empty conversation gets insufficient-speech feedback',
      (tester) async {
    for (final discarded in [true, false]) {
      final server = exampleConversation();
      final terminal = ServerConversation(
          id: server.id,
          createdAt: server.createdAt,
          structured: server.structured,
          discarded: discarded,
          transcriptSegments: discarded ? server.transcriptSegments : []);
      final events = <RegisteredEvent>[];
      final flow = FirstCaptureController(FakeCaptureIO()..result = terminal, emit: events.add);
      await flow.start();
      await flow.finish();
      expect(flow.phase, FirstCapturePhase.empty);
      expect(events.whereType<OnboardingFirstCaptureEmptyResult>().length, 1);
      flow.dispose();
    }
    final processing = exampleConversation()..status = ConversationStatus.processing;
    final flow = FirstCaptureController(FakeCaptureIO()..result = processing, emit: (_) {});
    await flow.start();
    await flow.finish();
    expect(flow.phase, FirstCapturePhase.delayed);
    flow.dispose();
  });

  testWidgets('null Finish without speech renders delayed copy and never emits Empty Result', (tester) async {
    final events = <RegisteredEvent>[];
    final flow = FirstCaptureController(FakeCaptureIO(), emit: events.add);
    await tester.pumpWidget(host(FirstCapturePage(controller: flow, onComplete: () {}, onSkip: () {})));
    await flow.start();
    await flow.finish();
    await tester.pump();
    expect(flow.phase, FirstCapturePhase.delayed);
    expect(
        find.text('Your recording is taking longer to process. You can check your conversations on Home or try again.'),
        findsOneWidget);
    expect(events.whereType<OnboardingFirstCaptureEmptyResult>(), isEmpty);
    flow.dispose();
  });

  testWidgets('Siri tip stays hidden below its version gate or without App Shortcuts availability', (tester) async {
    for (final gate in [true, false]) {
      final flow = FirstCaptureController(FakeCaptureIO(), emit: (_) {});
      flow.phase = FirstCapturePhase.result;
      flow.conversation = exampleConversation();
      await tester.pumpWidget(host(FirstCapturePage(
          controller: flow,
          onComplete: () {},
          onSkip: () {},
          showSiriHint: gate,
          appShortcutsAvailabilityProbe: () async => false)));
      await tester.pump();
      expect(find.byKey(const Key('onboarding_siri_hint')), findsNothing);
      await tester.pumpWidget(const SizedBox());
      flow.dispose();
    }
  });

  testWidgets('result and empty actions stay at the bottom, including large text and Siri tip', (tester) async {
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final flow = FirstCaptureController(FakeCaptureIO(), emit: (_) {});
    flow.phase = FirstCapturePhase.result;
    flow.conversation = exampleConversation();
    await tester.pumpWidget(host(FirstCapturePage(
        controller: flow,
        onComplete: () {},
        onSkip: () {},
        showSiriHint: true,
        appShortcutsAvailabilityProbe: () async => true)));
    await tester.pump();
    expect(tester.getRect(find.byKey(const Key('first_capture_primary'))).bottom, greaterThan(800));
    flow.phase = FirstCapturePhase.empty;
    await tester.pumpWidget(host(MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2)),
        child: FirstCapturePage(controller: flow, onComplete: () {}, onSkip: () {}))));
    await tester.pump();
    expect(find.text("Let's try that again"), findsOneWidget);
    expect(find.byKey(const Key('first_capture_skip')).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
    flow.dispose();
  });

  test('restored tracker emits no auth exit and records the actual Back reason', () {
    final events = <RegisteredEvent>[];
    final tracker =
        MobileOnboardingStepTelemetry(emit: events.add, platform: () => OnboardingStepCompletedPlatform.ios);
    tracker.seed(9);
    tracker.enter(9);
    expect(events, isEmpty);
    tracker.exitReason = OnboardingStepCompletedExitReason.back;
    tracker.enter(6);
    expect(events.single.properties['step'], 'first_capture');
    expect(events.single.properties['exit_reason'], 'back');
  });

  testWidgets('guided capture owns info notices and restores them after disposal; Siri tip is gated', (tester) async {
    final flow = FirstCaptureController(FakeCaptureIO(), emit: (_) {});
    flow.phase = FirstCapturePhase.result;
    flow.conversation = exampleConversation();
    await tester.pumpWidget(host(FirstCapturePage(
        controller: flow,
        onComplete: () {},
        onSkip: () {},
        showSiriHint: true,
        appShortcutsAvailabilityProbe: () async => true)));
    await tester.pump();
    expect(find.byKey(const Key('onboarding_siri_hint')), findsOneWidget);
    OmiFeedback.info(tester.element(find.byType(FirstCapturePage)), 'Generic empty recording notice');
    await tester.pump();
    expect(find.byType(SnackBar), findsNothing);
    await tester.pumpWidget(host(const SizedBox()));
    await tester.pump();
    OmiFeedback.info(tester.element(find.byType(Scaffold)), 'Generic empty recording notice');
    await tester.pump();
    expect(find.byType(SnackBar), findsOneWidget);
    flow.dispose();
  });

  test('persisted completion resumes without moving indices or breaking prior saves', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    const key = 'onboarding/resumeStep/first-capture-test';
    await SharedPreferencesUtil().saveInt(key, 9);
    expect(OnboardingWrapper.resumeStepForTesting(SharedPreferencesUtil().getInt(key)), 9);
    expect(OnboardingWrapper.resumeStepForTesting(8), 8);
    expect(OnboardingWrapper.resumeStepForTesting(6), 6);
    expect(OnboardingWrapper.resumeStepForTesting(7), 9);
    expect(OnboardingWrapper.resumeStepForTesting(10), 2);
    expect(OnboardingWrapper.resumeStepForTesting(-1), 2);
  });

  test('step exits emit once, time every visit, and preserve explicit skips and Back', () {
    var ms = 0;
    final events = <RegisteredEvent>[];
    final tracker = MobileOnboardingStepTelemetry(
        emit: events.add, platform: () => OnboardingStepCompletedPlatform.ios, elapsedMs: () => ms);
    ms = 25;
    tracker.enter(1);
    tracker.enter(1);
    expect(events.length, 1);
    tracker.enter(9);
    ms = 100;
    tracker.skipped = true;
    tracker.exit();
    tracker.exit();
    expect(events.last.properties, {
      'step': 'first_capture',
      'index': 9,
      'elapsed_ms': 75,
      'skipped': true,
      'platform': 'ios',
      'exit_reason': 'skipped'
    });
    tracker.enter(6);
    tracker.enter(9);
    ms = 120;
    tracker.exit();
    expect(events.last.properties['skipped'], isFalse);
    expect(events.last.properties['elapsed_ms'], 20);
  });

  test('completion index remains resumable with both back destinations', () {
    expect(OnboardingProgressStepsForTest.completePage, 9);
    expect(OnboardingWrapper.isResumableStepForTesting(9), isTrue);
    expect(
        OnboardingWrapper.previousStepForTesting(
            currentIndex: 9, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
        6);
    expect(
        OnboardingWrapper.previousStepForTesting(
            currentIndex: 9, setupPageEnabled: true, knowledgeGraphStepEnabled: false),
        8);
    for (final step in OnboardingStepCompletedStep.values) {
      final event = OnboardingStepCompleted(
          step: step,
          index: step.index,
          elapsedMs: 23,
          skipped: true,
          platform: OnboardingStepCompletedPlatform.android,
          exitReason: OnboardingStepCompletedExitReason.skipped);
      expect(event.properties.keys.toSet(), {'step', 'index', 'elapsed_ms', 'skipped', 'platform', 'exit_reason'});
      expect(event.properties['skipped'], isTrue);
    }
  });

  testWidgets('render first-capture screens with real fonts on iOS and Android', (tester) async {
    if (Platform.environment['FIRST_CAPTURE_RENDER'] != '1') return;
    await tester.runAsync(() async {
      final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
      for (final family in manifest) {
        final loader = FontLoader(family['family'] as String);
        for (final font in family['fonts'] as List) {
          loader.addFont(rootBundle.load(font['asset'] as String));
        }
        await loader.load();
      }
    });
    await tester.runAsync(() async {
      for (final family in ['.SF UI Text', '.SF UI Display', '.SF Pro Text', 'CupertinoSystemText']) {
        final loader = FontLoader(family);
        loader.addFont(rootBundle.load('assets/fonts/SFPRODISPLAYREGULAR.OTF'));
        await loader.load();
      }
    });
    await tester.runAsync(() async {
      var dir = File(Platform.resolvedExecutable).parent;
      Directory? fonts;
      for (var i = 0; i < 8; i++) {
        final candidate = Directory('${dir.path}/material_fonts');
        if (File('${candidate.path}/Roboto-Regular.ttf').existsSync()) {
          fonts = candidate;
          break;
        }
        dir = dir.parent;
      }
      expect(fonts, isNotNull);
      final loader = FontLoader('Roboto');
      for (final weight in ['Regular', 'Medium', 'Bold']) {
        loader.addFont(Future.value(ByteData.sublistView(File('${fonts!.path}/Roboto-$weight.ttf').readAsBytesSync())));
      }
      await loader.load();
    });
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const boundary = Key('capture-render');
    for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
      debugDefaultTargetPlatformOverride = platform;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      Future<void> render(String name, Widget child, {Future<void> Function()? interact}) async {
        await tester.pumpWidget(const SizedBox());
        await tester.pump();
        await tester.pumpWidget(RepaintBoundary(key: boundary, child: host(child, platform: platform)));
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 500));
        if (interact != null) {
          await interact();
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 350));
          expect(find.byType(OmiAlertDialog), findsOneWidget, reason: name);
        }
        expect(tester.takeException(), isNull, reason: name);
        await tester.runAsync(() async {
          final image = tester.element(find.byKey(boundary)).renderObject! as RenderRepaintBoundary;
          final png = await (await image.toImage(pixelRatio: 3)).toByteData(format: ui.ImageByteFormat.png);
          const states = [
            'choice',
            'recording-5s',
            'recording-30s',
            'processing',
            'result',
            'empty',
            'omi-handoff',
            'watch-instructions'
          ];
          const extra = {'delayed': 16, 'short-warning': 18, 'back-confirmation': 20};
          final number = extra.containsKey(name)
              ? extra[name]! + (platform == TargetPlatform.android ? 1 : 0)
              : states.indexOf(name) + 1 + (platform == TargetPlatform.android ? 8 : 0);
          final ordinal = number.toString().padLeft(3, '0');
          final tag = platform == TargetPlatform.iOS ? 'mobile-ios' : 'mobile-android';
          final file = File('../.agent-artifacts/ui-evidence/onb-m-firstcapture/$ordinal-$tag-first-capture-$name.png');
          file.parent.createSync(recursive: true);
          file.writeAsBytesSync(png!.buffer.asUint8List());
        });
      }

      await render(
          'choice',
          OnboardingStepLayout(
              reserveHeader: false,
              onBack: () {},
              child: OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, value) {})));
      final flow = FirstCaptureController(FakeCaptureIO(), emit: (_) {});
      Widget page() => FirstCapturePage(
          controller: flow,
          onComplete: () {},
          onSkip: () {},
          showSiriHint: platform == TargetPlatform.iOS,
          appShortcutsAvailabilityProbe: () async => true);
      flow.phase = FirstCapturePhase.recording;
      flow.seconds = 5;
      await render('recording-5s', page());
      flow.seconds = 30;
      flow.transcript = 'Today I’m working on the launch. I want to finish onboarding and share it with my team.';
      await render('recording-30s', page());
      flow.phase = FirstCapturePhase.processing;
      await render('processing', page());
      flow.phase = FirstCapturePhase.result;
      flow.conversation = exampleConversation();
      await render('result', page());
      flow.phase = FirstCapturePhase.empty;
      await render('empty', page());
      if (platform == TargetPlatform.iOS) {
        await render(
            'watch-instructions', FirstCaptureWatchInstructions(paired: true, installed: true, onComplete: () {}));
      }
      await render(
          'omi-handoff',
          MultiProvider(providers: [
            ChangeNotifierProvider<OnboardingProvider>.value(value: _RenderPairingProvider()),
            ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
            ChangeNotifierProvider<HomeProvider>(create: (_) => _RenderHomeProvider()),
          ], child: ConnectDevicePage(onConnected: () {})));
      flow.phase = FirstCapturePhase.delayed;
      await render('delayed', page());
      flow.phase = FirstCapturePhase.recording;
      flow.seconds = 5;
      await render('short-warning', page(), interact: () => tester.tap(find.byKey(const Key('first_capture_primary'))));
      await render('back-confirmation', page(), interact: () => tester.tap(find.byType(OmiBackButton)));
      flow.dispose();
    }
    debugDefaultTargetPlatformOverride = null;
  });
}

class _RenderPairingProvider extends OnboardingProvider {
  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
  @override
  void cancelActiveScan() {}
}

class _RenderHomeProvider extends HomeProvider {
  @override
  Future<void> setupHasSpeakerProfile() async {}
}
