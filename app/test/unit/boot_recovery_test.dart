import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/startup/boot_journal.dart';
import 'package:omi/startup/boot_recovery.dart';
import 'package:omi/startup/boot_recovery_app.dart';
import 'package:omi/startup_failure_app.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late BootRecovery recovery;
  var now = DateTime.utc(2026, 9, 28);
  setUp(() async {
    now = DateTime.utc(2026, 9, 28);
    BootRecovery.safeModeActive = false;
    SharedPreferences.setMockInitialValues({});
    recovery = BootRecovery(await SharedPreferences.getInstance(), now: () => now);
  });
  tearDown(() => BootRecovery.safeModeActive = false);

  test('third same-stage failure enters recovery and full success resets it', () async {
    expect(recovery.needsMigration, isTrue);
    expect(await recovery.failed('resolve_auth'), 1);
    expect(recovery.shouldRecover, isFalse);
    expect(await recovery.failed('resolve_auth'), 2);
    expect(recovery.shouldRecover, isFalse);
    expect(await recovery.failed('resolve_auth'), 3);
    expect(recovery.shouldRecover, isTrue);
    await recovery.fullBootSucceeded();
    expect(recovery.count, 0);
    expect(recovery.previousSchema, BootRecovery.schemaVersion);
    expect(recovery.needsMigration, isFalse);
    expect(recovery.shouldRecover, isFalse);
  });

  test('a different stage or expired window starts a new streak', () async {
    await recovery.failed('resolve_auth');
    expect(await recovery.failed('bind_owner'), 1);
    now = now.add(BootRecovery.window + const Duration(seconds: 1));
    expect(await recovery.failed('bind_owner'), 1);
    expect(recovery.shouldRecover, isFalse);
  });

  test('build configuration errors do not enter the retry circuit', () {
    expect(BootRecovery.countsFailure(const StartupConfigurationError('bad build')), isFalse);
    expect(BootRecovery.countsFailure(StateError('recoverable stage')), isTrue);
  });

  test('only the explicit derivative stages are skipped', () async {
    BootRecovery.safeModeActive = true;
    for (final stage in BootRecovery.skippedStages) {
      expect(BootRecovery.skipStage(stage), isTrue);
    }
    for (final stage in ['firebase_init', 'shared_preferences', 'resolve_auth', 'crash_reporter']) {
      expect(BootRecovery.skipStage(stage), isFalse);
    }
    BootRecovery.safeModeActive = false;
    expect(BootRecovery.skipStage('ble_setup'), isFalse);
  });

  test('interrupted stage is counted on next launch', () async {
    final directory = await Directory.systemTemp.createTemp('boot-recovery-');
    try {
      final journal = BootJournal(documents: () async => directory);
      await journal.record('service_manager_start', 'begin');
      await recovery.countInterruptedBoot(journal);
      expect(recovery.failingStage, 'service_manager_start');
      expect(recovery.count, 1);
      await recovery.countInterruptedBoot(journal);
      expect(recovery.count, 1);
    } finally {
      await directory.delete(recursive: true);
    }
  });

  testWidgets('recovery screen shows banner and full-startup retry', (tester) async {
    var retries = 0;
    await tester.pumpWidget(BootRecoveryApp(onRetry: () async {
      retries++;
    }));
    expect(find.text('Recovery mode — some features paused; tap to retry full startup'), findsOneWidget);
    await tester.tap(find.byKey(const Key('boot_recovery_retry')));
    expect(retries, 1);
  });
}
