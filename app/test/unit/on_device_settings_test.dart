import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

import '../support/on_device_fakes.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('OnDeviceSettings', () {
    test('defaults: off, while charging, Wi-Fi only, summaries allowed', () {
      final settings = OnDeviceSettingsStore().load();
      expect(settings, const OnDeviceSettings());
      expect(settings.enabled, isFalse);
      expect(settings.saveLiveHours, isFalse);
      expect(settings.schedule, OnDeviceSchedule.whileCharging);
      expect(settings.wifiOnlyDownload, isTrue);
      expect(settings.keepEverythingOnDevice, isFalse);
    });

    test('round-trips every field through prefs', () async {
      const saved = OnDeviceSettings(
        enabled: true,
        saveLiveHours: true,
        schedule: OnDeviceSchedule.asYouTalk,
        wifiOnlyDownload: false,
        keepEverythingOnDevice: true,
      );
      await OnDeviceSettingsStore().save(saved);
      expect(OnDeviceSettingsStore().load(), saved);
    });

    test('an unknown stored schedule falls back to while charging', () async {
      await SharedPreferencesUtil().saveString(OnDeviceSettingsStore.scheduleKey, 'hourly_v0');
      expect(OnDeviceSettingsStore().load().schedule, OnDeviceSchedule.whileCharging);
    });

    test('schedule storage ids are stable', () {
      expect(OnDeviceSchedule.values.map((s) => s.storageId), ['while_charging', 'every_few_hours', 'as_you_talk']);
    });
  });

  group('OnDeviceOverflowGate', () {
    test('reads the PostHog key and fails closed', () async {
      String? asked;
      expect(
          await OnDeviceOverflowGate.read(readFlag: (key) async {
            asked = key;
            return true;
          }),
          isTrue);
      expect(asked, 'mobile-on-device-overflow');
      expect(await OnDeviceOverflowGate.read(readFlag: (_) async => throw StateError('offline')), isFalse);
      expect(await OnDeviceOverflowGate.read(readFlag: (_) async => false), isFalse);
    });
  });

  group('OnDeviceTranscriptionController', () {
    test('stays inactive with the flag off and does not touch settings', () async {
      await OnDeviceSettingsStore().save(const OnDeviceSettings(enabled: true));
      final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), readGate: () async => false);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      expect(controller.isActive, isFalse);
      expect(controller.settings, const OnDeviceSettings());
      controller.recordProvenance(
          'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.cloud, reason: OnDeviceReason.liveHoursUsed));
      expect(controller.provenanceFor('c1'), isNull);
    });

    test('loads saved settings once the flag is on, and reads the gate once', () async {
      await OnDeviceSettingsStore()
          .save(const OnDeviceSettings(enabled: true, schedule: OnDeviceSchedule.everyFewHours));
      var reads = 0;
      final controller = OnDeviceTranscriptionController(
        model: FakeOnDeviceModel(),
        readGate: () async {
          reads++;
          return true;
        },
      );
      addTearDown(controller.dispose);
      await Future.wait([controller.ensureLoaded(), controller.ensureLoaded()]);
      expect(reads, 1);
      expect(controller.isActive, isTrue);
      expect(controller.settings.schedule, OnDeviceSchedule.everyFewHours);
    });

    test('updateSettings persists and notifies', () async {
      final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), readGate: () async => true);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      var notified = 0;
      controller.addListener(() => notified++);
      await controller.updateSettings(controller.settings.copyWith(keepEverythingOnDevice: true));
      expect(notified, 1);
      expect(OnDeviceSettingsStore().load().keepEverythingOnDevice, isTrue);
    });

    test('evaluate feeds power, schedule and the last run into the policy', () async {
      final power = FakePhonePowerSource(const PhonePowerState(isCharging: false, batteryPercent: 90));
      var now = DateTime(2026, 10, 14, 9);
      final controller = OnDeviceTranscriptionController(
        model: FakeOnDeviceModel(),
        power: power,
        readGate: () async => true,
        clock: () => now,
      );
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      const pending = Duration(minutes: 40);

      expect((await controller.evaluate(pendingAudio: pending)).reason, OnDeviceRunReason.waitingForCharger);
      expect((await controller.evaluate(pendingAudio: pending, transcribeNow: true)).reason,
          OnDeviceRunReason.userRequested);

      power.state = const PhonePowerState(isCharging: true, batteryPercent: 90);
      expect((await controller.evaluate(pendingAudio: pending)).reason, OnDeviceRunReason.charging);

      power.state = const PhonePowerState(isCharging: false, batteryPercent: 90);
      await controller.updateSettings(controller.settings.copyWith(schedule: OnDeviceSchedule.everyFewHours));
      controller.markRun(running: true);
      controller.markRun(running: false);
      now = now.add(const Duration(hours: 1));
      final decision = await controller.evaluate(pendingAudio: pending);
      expect(decision.reason, OnDeviceRunReason.waitingForInterval);
      expect(decision.retryAt, DateTime(2026, 10, 14, 12));
      expect(controller.decision, decision);
    });
  });
}
