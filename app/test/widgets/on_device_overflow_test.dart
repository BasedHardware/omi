import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/on_device/on_device_at_cap_sheet.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_provenance_section.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

import '../support/on_device_fakes.dart';
import 'storefront_plans_content_test.dart' as renders;

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
    testWidgets('ladder cap renders backend strings and records the monthly preference', (tester) async {
      final copy = GeneratedStorefrontCapChoice.fromJson(
          jsonDecode(File('../backend/tests/fixtures/ladder_v1_at_cap.json').readAsStringSync()));
      var dontAsk = false;
      await renders.pumpSheet(tester,
          title: null,
          content: Padding(
              padding: const EdgeInsets.all(20),
              child: OnDeviceAtCapSheet(copy: copy, onDontAskAgain: (value) => dontAsk = value, onContinue: (_) {})));
      expect(find.text(copy.title), findsOneWidget);
      expect(copy.title, "Processing paused. You've reached this month's limit.");
      expect(find.text(copy.body), findsOneWidget);
      expect(find.text(copy.onDeviceUpgradeLine), findsOneWidget);
      await _tap(tester, find.byType(CheckboxListTile));
      await tester.pumpAndSettle();
      expect(dontAsk, true);
      await renders.capture(tester, '018-mobile-integrated-at-cap.png');
    });
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

    testWidgets('a non-english device keeps the backend at-cap title', (tester) async {
      final copy = GeneratedStorefrontCapChoice.fromJson(
          jsonDecode(File('../backend/tests/fixtures/ladder_v1_at_cap.json').readAsStringSync()));
      final spanish = lookupAppLocalizations(const Locale('es'));
      await tester.pumpWidget(MaterialApp(
        locale: const Locale('es'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: OnDeviceAtCapSheet(copy: copy, onContinue: (_) {})),
      ));
      await tester.pump();
      expect(find.text(copy.title), findsOneWidget);
      expect(find.text(spanish.onDeviceAtCapTitle), findsNothing);
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
          moreLabel: 'Get more usage',
          onGetMoreUsage: onUpgrade ?? () {},
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

    testWidgets('OS-managed asset install is progress only', (tester) async {
      final model = FakeOnDeviceModel(
        const OnDeviceModelStatus(phase: OnDeviceModelPhase.downloading, progress: 0.4),
        'speech_analyzer',
      );
      final controller = OnDeviceTranscriptionController(model: model, power: const UnknownPhonePowerSource())
        ..debugActivate();
      await pumpBanner(tester, controller);
      expect(find.byKey(const Key('on_device_asset_progress')), findsOneWidget);
      expect(find.text(l10n.onDeviceFinishSetupBody), findsNothing);
      expect(find.text(l10n.onDeviceDownloadingPercent(40)), findsOneWidget);
      expect(find.byKey(const Key('on_device_finish_setup_banner')), findsNothing);
    });

    testWidgets('unsupported phone: only at cap, offering more usage', (tester) async {
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
          usage: const StorefrontUsage(
            kind: 'usage_budget',
            percent: 80,
            resetLabel: 'resets Nov 1',
            meterLine: '80% used · about 3 hours of recording left · resets Nov 1',
            hoursLeft: 3,
            moreLabel: 'Get more usage',
          ),
          showSaveUsage: true,
          pendingSeconds: 12000,
          pendingBytes: 180 * 1024 * 1024,
          plansSheetAvailable: true,
          onGetMoreUsage: () {},
        ),
        page: true,
      );
      return controller;
    }

    testWidgets('shows the meter, schedule, model and waiting audio', (tester) async {
      await pumpSettings(tester);
      expect(find.text('80% used · about 3 hours of recording left · resets Nov 1'), findsOneWidget);
      expect(find.text('Get more usage'), findsOneWidget);
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

    testWidgets('hides the speech model row when the engine is OS-managed', (tester) async {
      final controller = OnDeviceTranscriptionController(
        model: FakeOnDeviceModel(const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed), 'speech_analyzer'),
        power: const UnknownPhonePowerSource(),
      )..debugActivate(settings: const OnDeviceSettings(enabled: true));
      await _pump(
        tester,
        OnDeviceSettingsView(
          controller: controller,
          usage: const StorefrontUsage(kind: 'usage_budget', percent: 40, meterLine: '40% used · resets Nov 1'),
          plansSheetAvailable: true,
          showSaveUsage: true,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () {},
        ),
        page: true,
      );
      expect(find.byKey(const Key('on_device_settings_model')), findsNothing);
      expect(find.byKey(const Key('on_device_settings_remove')), findsNothing);
      expect(find.text(l10n.onDeviceSaveLiveHours), findsOneWidget);
    });

    testWidgets('hides get more usage unless the plans sheet is available', (tester) async {
      final controller = _controller();
      await _pump(
        tester,
        OnDeviceSettingsView(
          controller: controller,
          usage: const StorefrontUsage(
            kind: 'usage_budget',
            percent: 80,
            meterLine: '80% used · resets Nov 1',
            moreLabel: 'Get more usage',
          ),
          plansSheetAvailable: false,
          showSaveUsage: false,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () => fail('legacy usage page must not open from this row'),
        ),
        page: true,
      );
      expect(find.byKey(const Key('on_device_settings_more_usage')), findsNothing);
    });

    testWidgets('get more usage does not open the legacy usage page', (tester) async {
      final usage = UsageProvider()
        ..debugSetSubscription(UserSubscriptionResponse(
          subscription: Subscription(plan: PlanType.unlimited, status: SubscriptionStatus.active),
          transcriptionSecondsUsed: 0,
          transcriptionSecondsLimit: 0,
          wordsTranscribedUsed: 0,
          wordsTranscribedLimit: 0,
          insightsGainedUsed: 0,
          insightsGainedLimit: 0,
          showSubscriptionUi: false,
        ));
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () => openOnDeviceUsagePlans(context),
              child: const Text('more'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('more'));
      await tester.pumpAndSettle();
      expect(find.byType(UsagePage), findsNothing);
    });

    testWidgets('unknown engine hides model rows and does not open Parakeet setup', (tester) async {
      final model = FakeOnDeviceModel(const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded), null, false);
      model.beforeRefresh = () async {
        model.engine = 'speech_analyzer';
      };
      final controller = OnDeviceTranscriptionController(model: model, power: const UnknownPhonePowerSource())
        ..debugActivate(settings: const OnDeviceSettings(enabled: true));
      await _pump(
        tester,
        OnDeviceSettingsView(
          controller: controller,
          usage: null,
          plansSheetAvailable: false,
          showSaveUsage: false,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () {},
        ),
        page: true,
      );
      expect(find.byKey(const Key('on_device_settings_model')), findsNothing);

      await _pump(
        tester,
        Builder(
          builder: (context) => TextButton(
            onPressed: () => openOnDeviceSetup(context, controller: controller),
            child: const Text('setup'),
          ),
        ),
        page: true,
      );
      await _tap(tester, find.text('setup'));
      await tester.pumpAndSettle();
      expect(find.byType(OnDeviceSetupPage), findsNothing);
      expect(model.engine, 'speech_analyzer');
      expect(model.downloads, 1);
    });

    testWidgets('a spanish device shows the backend meter and get more usage', (tester) async {
      final controller = _controller();
      await tester.pumpWidget(MaterialApp(
        locale: const Locale('es'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: OnDeviceSettingsView(
          controller: controller,
          usage: const StorefrontUsage(
            kind: 'usage_budget',
            percent: 80,
            resetLabel: 'resets Nov 1',
            meterLine: '80% used · about 3 hours of recording left · resets Nov 1',
            hoursLeft: 3,
            moreLabel: 'Get more usage',
          ),
          plansSheetAvailable: true,
          showSaveUsage: false,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () {},
        ),
      ));
      await tester.pump();
      expect(find.text('80% used · about 3 hours of recording left · resets Nov 1'), findsOneWidget);
      expect(find.text('Get more usage'), findsOneWidget);
    });

    testWidgets('detection failure offers retry and hides the speech model', (tester) async {
      final model =
          FakeOnDeviceModel(const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported), null, true, true);
      var refreshes = 0;
      model.beforeRefresh = () async => refreshes++;
      final controller = OnDeviceTranscriptionController(model: model, power: const UnknownPhonePowerSource())
        ..debugActivate(settings: const OnDeviceSettings(enabled: true));
      await _pump(
        tester,
        OnDeviceSettingsView(
          controller: controller,
          usage: null,
          plansSheetAvailable: false,
          showSaveUsage: false,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () {},
        ),
        page: true,
      );
      expect(find.byKey(const Key('on_device_settings_model')), findsNothing);
      await _tap(tester, find.byKey(const Key('on_device_settings_engine_unavailable')));
      expect(refreshes, 1);
    });
  });

  group('engine detection', () {
    Future<void> mockChannel(Future<dynamic> Function(MethodCall call) handler) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(AppleOnDeviceModel.channel, handler);
      addTearDown(() {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(AppleOnDeviceModel.channel, null);
      });
    }

    testWidgets('a platform failure never opens Parakeet setup', (tester) async {
      await mockChannel((call) async {
        if (call.method == 'status') throw PlatformException(code: 'UNAVAILABLE', message: 'down');
        return null;
      });
      final model = AppleOnDeviceModel(detectionTimeout: const Duration(seconds: 1));
      final controller = OnDeviceTranscriptionController(
        model: model,
        power: const UnknownPhonePowerSource(),
        readGate: () async => true,
        manageNativeCustody: false,
      );
      await _pump(
        tester,
        Builder(
          builder: (context) => TextButton(
            onPressed: () => openOnDeviceSetup(context, controller: controller),
            child: const Text('setup'),
          ),
        ),
        page: true,
      );
      await _tap(tester, find.text('setup'));
      await tester.pumpAndSettle();
      expect(model.detectionFailed, isTrue);
      expect(model.engine, isNull);
      expect(model.engineResolved, isTrue);
      expect(find.byType(OnDeviceSetupPage), findsNothing);
    });

    testWidgets('a stalled status call becomes unavailable instead of hiding the banner', (tester) async {
      await mockChannel((call) async {
        if (call.method == 'status') await Completer<void>().future;
        return null;
      });
      final model = AppleOnDeviceModel(detectionTimeout: const Duration(milliseconds: 40));
      final controller = OnDeviceTranscriptionController(
        model: model,
        power: const UnknownPhonePowerSource(),
        readGate: () async => true,
        manageNativeCustody: false,
      );
      final loaded = controller.ensureLoaded();
      await tester.pump(const Duration(milliseconds: 100));
      await loaded;
      expect(controller.isActive, isTrue);
      expect(model.detectionFailed, isTrue);
      expect(model.engine, isNull);
      await _pump(
        tester,
        OnDeviceQueueBannerView(
          controller: controller,
          pendingSeconds: 120,
          atCap: true,
          onSetUp: () {},
          moreLabel: 'Get more usage',
          onGetMoreUsage: () {},
        ),
      );
      expect(find.byKey(const Key('on_device_engine_unavailable')), findsOneWidget);
      expect(find.byKey(const Key('on_device_finish_setup_banner')), findsNothing);
      expect(find.text(l10n.tryAgain), findsOneWidget);
    });

    testWidgets('Parakeet setup opens only after that engine is detected', (tester) async {
      await mockChannel((call) async {
        if (call.method == 'status') {
          return {'engine': 'parakeet_v2', 'phase': 'notDownloaded', 'progress': 0, 'sizeBytes': 100};
        }
        return null;
      });
      final model = AppleOnDeviceModel(detectionTimeout: const Duration(seconds: 1));
      final controller = OnDeviceTranscriptionController(
        model: model,
        power: const UnknownPhonePowerSource(),
        readGate: () async => true,
        manageNativeCustody: false,
      );
      await _pump(
        tester,
        Builder(
          builder: (context) => TextButton(
            onPressed: () => openOnDeviceSetup(context, controller: controller),
            child: const Text('setup'),
          ),
        ),
        page: true,
      );
      await _tap(tester, find.text('setup'));
      await tester.pumpAndSettle();
      expect(model.engine, 'parakeet_v2');
      expect(model.detectionFailed, isFalse);
      expect(find.byType(OnDeviceSetupPage), findsOneWidget);
    });
  });

  group('queue banner plans sheet', () {
    test('get more usage stays hidden unless the plans sheet can open', () {
      expect(
        onDeviceMoreUsageTitle(
          plansSheetAvailable: false,
          moreLabel: 'Get more usage',
        ),
        isNull,
      );
      expect(
        onDeviceMoreUsageTitle(
          plansSheetAvailable: true,
          moreLabel: 'Get more usage',
        ),
        'Get more usage',
      );
      expect(
        onDeviceMoreUsageTitle(
          plansSheetAvailable: true,
          moreLabel: 'Obtén más uso',
        ),
        'Obtén más uso',
      );
    });

    testWidgets('finish setup hides get more usage when the sheet label is withheld', (tester) async {
      final controller = _controller(status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded));
      await _pump(
        tester,
        OnDeviceQueueBannerView(
          controller: controller,
          pendingSeconds: 120,
          atCap: true,
          onSetUp: () {},
          moreLabel: onDeviceMoreUsageTitle(
            plansSheetAvailable: false,
            moreLabel: 'Get more usage',
          ),
          onGetMoreUsage: () {},
        ),
      );
      expect(find.byKey(const Key('on_device_finish_setup_download')), findsOneWidget);
      expect(find.byKey(const Key('on_device_finish_setup_upgrade')), findsNothing);
    });

    testWidgets('upgrade from the banner does not open the legacy usage page', (tester) async {
      final usage = UsageProvider()
        ..debugSetSubscription(UserSubscriptionResponse(
          subscription: Subscription(plan: PlanType.unlimited, status: SubscriptionStatus.active),
          transcriptionSecondsUsed: 0,
          transcriptionSecondsLimit: 0,
          wordsTranscribedUsed: 0,
          wordsTranscribedLimit: 0,
          insightsGainedUsed: 0,
          insightsGainedLimit: 0,
          showSubscriptionUi: false,
        ));
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () => openOnDeviceUpgrade(context),
              child: const Text('more'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('more'));
      await tester.pumpAndSettle();
      expect(find.byType(UsagePage), findsNothing);
    });
  });
}
