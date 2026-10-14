import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/on_device/on_device_at_cap_sheet.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_provenance_section.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

import '../support/on_device_fakes.dart';

final l10n = lookupAppLocalizations(const Locale('en'));

Future<void> _pump(WidgetTester tester, Widget child, {bool page = false}) async {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: page ? child : Scaffold(body: SingleChildScrollView(child: child)),
  ));
  await tester.pump();
}

/// Content is taller than the viewport with the test font; scroll a target in before tapping it.
Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
}

OnDeviceTranscriptionController _controller({
  OnDeviceModelStatus status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed),
  OnDeviceSettings settings = const OnDeviceSettings(enabled: true),
  PhonePowerSource power = const UnknownPhonePowerSource(),
  bool active = true,
}) {
  final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(status), power: power);
  if (active) controller.debugActivate(settings: settings);
  return controller;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('at-cap sheet', () {
    testWidgets('defaults to the phone, says when hours return, and reports the choice', (tester) async {
      final choices = <OnDeviceAtCapChoice>[];
      await _pump(tester, OnDeviceAtCapSheet(onContinue: choices.add, liveHoursReturnOn: DateTime(2026, 11, 1)));

      expect(find.text(l10n.onDeviceAtCapTitle), findsOneWidget);
      expect(find.textContaining(l10n.onDeviceLiveHoursReturn('Nov 1, 2026')), findsOneWidget);
      expect(find.text(l10n.onDeviceIncluded), findsOneWidget);

      await tester.tap(find.byKey(const Key('on_device_at_cap_continue')));
      expect(choices, [OnDeviceAtCapChoice.transcribeOnPhone]);

      await tester.tap(find.byKey(const Key('on_device_at_cap_upgrade')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('on_device_at_cap_continue')));
      expect(choices.last, OnDeviceAtCapChoice.upgrade);
    });

    testWidgets('leaves out the return date when unknown', (tester) async {
      await _pump(tester, OnDeviceAtCapSheet(onContinue: (_) {}));
      expect(find.text(l10n.onDeviceAtCapBody), findsOneWidget);
    });
  });

  group('queue banner', () {
    Future<void> pumpBanner(WidgetTester tester, OnDeviceTranscriptionController controller,
        {int pendingSeconds = 3900, bool atCap = true, VoidCallback? onSetUp, VoidCallback? onUpgrade}) {
      return _pump(
        tester,
        OnDeviceQueueBannerView(
          controller: controller,
          pendingSeconds: pendingSeconds,
          atCap: atCap,
          onSetUp: onSetUp ?? () {},
          onGetMoreLiveHours: onUpgrade ?? () {},
        ),
      );
    }

    testWidgets('renders nothing with the flag off', (tester) async {
      await pumpBanner(tester, _controller(active: false));
      expect(find.byType(Container), findsNothing);
    });

    testWidgets('renders nothing with nothing waiting', (tester) async {
      await pumpBanner(tester, _controller(), pendingSeconds: 0);
      expect(find.byKey(const Key('on_device_queue_banner')), findsNothing);
    });

    testWidgets('waiting: amount, why, and Transcribe Now asks the policy', (tester) async {
      final controller = _controller(power: FakePhonePowerSource(const PhonePowerState(isCharging: false)));
      await pumpBanner(tester, controller);

      expect(find.text(l10n.onDeviceQueueWaiting('1h 5m')), findsOneWidget);
      expect(find.text(l10n.onDeviceQueueChargingBody), findsOneWidget);
      await tester.tap(find.byKey(const Key('on_device_transcribe_now')));
      await tester.pump();
      expect(controller.decision, const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
    });

    testWidgets('while transcribing shows progress instead of the button', (tester) async {
      final controller = _controller()..markRun(running: true);
      await pumpBanner(tester, controller);
      expect(find.text(l10n.onDeviceTranscribing), findsOneWidget);
      expect(find.byKey(const Key('on_device_transcribe_now')), findsNothing);
    });

    testWidgets('no model yet: finish setup, with download and upgrade', (tester) async {
      var setUps = 0;
      var upgrades = 0;
      await pumpBanner(
        tester,
        _controller(status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded)),
        onSetUp: () => setUps++,
        onUpgrade: () => upgrades++,
      );
      expect(find.text(l10n.onDeviceFinishSetupTitle), findsOneWidget);
      await tester.tap(find.byKey(const Key('on_device_finish_setup_download')));
      await tester.tap(find.byKey(const Key('on_device_finish_setup_upgrade')));
      expect((setUps, upgrades), (1, 1));
    });

    testWidgets('no model and not chosen: only shown once live hours are used', (tester) async {
      final controller = _controller(
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded),
        settings: const OnDeviceSettings(),
      );
      await pumpBanner(tester, controller, atCap: false);
      expect(find.byKey(const Key('on_device_finish_setup_banner')), findsNothing);
      await pumpBanner(tester, controller, atCap: true);
      expect(find.byKey(const Key('on_device_finish_setup_banner')), findsOneWidget);
    });

    testWidgets('unsupported phone: only at cap, offering more live hours', (tester) async {
      final controller = _controller(status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported));
      await pumpBanner(tester, controller, atCap: false);
      expect(find.byKey(const Key('on_device_unsupported_banner')), findsNothing);
      await pumpBanner(tester, controller, atCap: true);
      expect(find.text(l10n.onDeviceUnsupportedBody), findsOneWidget);
    });
  });

  group('recording chip', () {
    Future<Widget?> chip(WidgetTester tester, OnDeviceTranscriptionController controller, {bool atCap = false}) async {
      Widget? result;
      await _pump(tester, Builder(builder: (context) {
        result = onDeviceRecordingChip(context, controller, atCap: atCap);
        return const SizedBox.shrink();
      }));
      return result;
    }

    testWidgets('none with the flag off or the feature unused', (tester) async {
      expect(await chip(tester, _controller(active: false)), isNull);
      expect(await chip(tester, _controller(settings: const OnDeviceSettings())), isNull);
    });

    testWidgets('names what the recording waits for', (tester) async {
      final charging = await chip(tester, _controller());
      expect((charging! as OnDeviceStatusChip).label, l10n.onDeviceWaitingForCharger);
      final hours = await chip(tester,
          _controller(settings: const OnDeviceSettings(enabled: true, schedule: OnDeviceSchedule.everyFewHours)));
      expect((hours! as OnDeviceStatusChip).label, l10n.onDeviceWaitingToTranscribe);
      final setup = await chip(
        tester,
        _controller(
            status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded),
            settings: const OnDeviceSettings()),
        atCap: true,
      );
      expect((setup! as OnDeviceStatusChip).label, l10n.onDeviceWaitingForSetup);
    });
  });

  group('provenance', () {
    tearDown(() => debugDefaultTargetPlatformOverride = null);

    testWidgets('nothing for a conversation Omi Cloud transcribed', (tester) async {
      await _pump(tester, OnDeviceProvenanceSection(conversationId: 'c1', controller: _controller()));
      expect(find.byKey(const Key('on_device_provenance_section')), findsNothing);
    });

    testWidgets('summarized on the iPhone: one badge, why, Redo', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      final controller = _controller()
        ..recordProvenance(
            'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.phone, reason: OnDeviceReason.liveHoursUsed));
      var redos = 0;
      await _pump(
          tester, OnDeviceProvenanceSection(conversationId: 'c1', controller: controller, onRedo: () => redos++));

      expect(find.text(l10n.onDeviceTranscribedSummarizedOnIphone), findsOneWidget);
      expect(find.text(l10n.onDeviceSummarizedByCloud), findsNothing);
      expect(find.text(l10n.onDeviceWhyPhoneTitle), findsOneWidget);
      expect(find.text('${l10n.onDeviceWhyLiveHoursUsed} ${l10n.onDeviceWhySummaryOnPhone}'), findsOneWidget);
      await tester.tap(find.byKey(const Key('on_device_redo_with_cloud')));
      expect(redos, 1);
      debugDefaultTargetPlatformOverride = null;
    });

    testWidgets('summarized by Omi Cloud: both badges, why, and keep-everything switch', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      final controller = _controller()
        ..recordProvenance('c1',
            const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.cloud, reason: OnDeviceReason.savingLiveHours));
      await _pump(tester, OnDeviceProvenanceSection(conversationId: 'c1', controller: controller));

      expect(find.text(l10n.onDeviceTranscribedOnPhone), findsOneWidget);
      expect(find.text(l10n.onDeviceSummarizedByCloud), findsOneWidget);
      expect(find.text(l10n.onDeviceWhyCloudPhone), findsOneWidget);
      expect(find.byKey(const Key('on_device_redo_with_cloud')), findsNothing);
      await tester.tap(find.text(l10n.onDeviceKeepEverything));
      await tester.pump();
      expect(controller.settings.keepEverythingOnDevice, isTrue);
      debugDefaultTargetPlatformOverride = null;
    });

    testWidgets('list chip appears only for on-device conversations', (tester) async {
      final controller = _controller()
        ..recordProvenance(
            'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.none, reason: OnDeviceReason.liveHoursUsed));
      await _pump(
        tester,
        Column(children: [
          OnDeviceProvenanceChip(conversationId: 'c1', controller: controller),
          OnDeviceProvenanceChip(conversationId: 'c2', controller: controller),
        ]),
      );
      expect(find.text(l10n.onDeviceTranscribedOnPhone), findsOneWidget);
    });
  });

  group('setup and schedule', () {
    testWidgets('setup downloads with the Wi-Fi choice', (tester) async {
      final controller = _controller(status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded));
      await _pump(tester, OnDeviceSetupPage(controller: controller), page: true);
      await _tap(tester, find.text(l10n.onDeviceWifiOnly));
      await tester.pump();
      await _tap(tester, find.byKey(const Key('on_device_model_download')));
      final model = controller.model as FakeOnDeviceModel;
      expect(model.downloads, 1);
      expect(model.lastWifiOnly, isFalse);
    });

    testWidgets('setup shows progress and cancels', (tester) async {
      final controller = _controller(
          status: const OnDeviceModelStatus(
              phase: OnDeviceModelPhase.downloading, progress: 0.62, timeLeft: Duration(minutes: 4)));
      await _pump(tester, OnDeviceSetupPage(controller: controller), page: true);
      expect(find.text(l10n.onDeviceDownloadingWifi(62)), findsOneWidget);
      expect(find.text(l10n.onDeviceTimeLeft('4m')), findsOneWidget);
      await _tap(tester, find.byKey(const Key('on_device_model_cancel')));
      expect((controller.model as FakeOnDeviceModel).cancels, 1);
    });

    testWidgets('schedule applies the choice and Done turns the feature on', (tester) async {
      final controller = _controller(settings: const OnDeviceSettings());
      await _pump(tester, OnDeviceSchedulePage(controller: controller, step: 2), page: true);
      expect(find.text(l10n.onDeviceStepOf(2, 2)), findsOneWidget);
      await _tap(tester, find.byKey(const Key('on_device_schedule_as_you_talk')));
      await tester.pump();
      expect(controller.settings.schedule, OnDeviceSchedule.asYouTalk);
      await _tap(tester, find.byKey(const Key('on_device_schedule_done')));
      await tester.pumpAndSettle();
      expect(controller.settings.enabled, isTrue);
    });
  });

  group('settings', () {
    Future<OnDeviceTranscriptionController> pumpSettings(WidgetTester tester,
        {OnDeviceSettings settings = const OnDeviceSettings(enabled: true)}) async {
      final controller = _controller(settings: settings);
      await _pump(
        tester,
        OnDeviceSettingsView(
          controller: controller,
          liveHours: OnDeviceLiveHours(usedSeconds: 360000, limitSeconds: 360000, resetsOn: DateTime(2026, 11, 1)),
          showSaveLiveHours: true,
          pendingSeconds: 12000,
          pendingBytes: 180 * 1024 * 1024,
          onGetMoreLiveHours: () {},
        ),
        page: true,
      );
      return controller;
    }

    testWidgets('shows the meter, schedule, model and waiting audio', (tester) async {
      await pumpSettings(tester);
      expect(find.text(l10n.onDeviceLiveHoursUsed('100', '100')), findsOneWidget);
      expect(find.text(l10n.onDeviceResets('Nov 1, 2026')), findsOneWidget);
      expect(find.text(l10n.onDeviceScheduleCharging), findsOneWidget);
      expect(find.text(l10n.onDeviceSummariesCloud), findsOneWidget);
      await tester.scrollUntilVisible(find.text(l10n.onDeviceMegabytes('180')), 200);
      expect(find.text('3h 20m'), findsOneWidget);
      expect(find.text(l10n.onDeviceMegabytes('180')), findsOneWidget);
    });

    testWidgets('schedule rows hide while the feature is off', (tester) async {
      final controller = await pumpSettings(tester, settings: const OnDeviceSettings());
      expect(find.byKey(const Key('on_device_settings_when')), findsNothing);
      await _tap(tester, find.byKey(const Key('on_device_settings_enabled')));
      await tester.pump();
      expect(controller.settings.enabled, isTrue);
      expect(find.byKey(const Key('on_device_settings_when')), findsOneWidget);
    });

    testWidgets('removing the model confirms first', (tester) async {
      final controller = await pumpSettings(tester);
      await tester.scrollUntilVisible(find.byKey(const Key('on_device_settings_remove')), 200);
      await _tap(tester, find.byKey(const Key('on_device_settings_remove')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.onDeviceRemoveModelTitle), findsOneWidget);
      await _tap(tester, find.text(l10n.onDeviceRemove));
      await tester.pumpAndSettle();
      expect((controller.model as FakeOnDeviceModel).removals, 1);
      expect(find.byKey(const Key('on_device_settings_remove')), findsNothing);
    });
  });
}
