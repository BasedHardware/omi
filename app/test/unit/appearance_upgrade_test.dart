import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
// Exercise unsuccessful platform writes, which the legacy mock API cannot model.
// ignore: depend_on_referenced_packages
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/startup/boot_recovery.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('fresh install stays Light after onboarding and subsequent launches', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(SharedPreferencesUtil.appearanceModeKey), 'light');

    await prefs.setBool('onboardingCompleted', true);
    await prefs.setString('lastKnownAppVersion', '1.0.553+1000');
    await BootRecovery(prefs).fullBootSucceeded();
    await prefs.reload();
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().appearanceMode, 'light');
  });

  test('fresh Light default survives sign out without being mistaken for a legacy install', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboardingCompleted', true);
    await prefs.setString('lastKnownAppVersion', '1.0.553+1000');

    await clearPreferencesForSignOut();
    await prefs.reload();
    expect(prefs.getBool('onboardingCompleted'), isNull);
    expect(prefs.getString('lastKnownAppVersion'), isNotEmpty);
    expect(prefs.getString(SharedPreferencesUtil.appearanceModeKey), 'light');
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().appearanceMode, 'light');
  });

  for (final previousInstall in <String, Map<String, Object>>{
    'onboarded user': {'onboardingCompleted': true},
    'signed-out user with a previous version': {
      'onboardingCompleted': false,
      'lastKnownAppVersion': '1.0.550+997',
    },
    'previous successful boot before onboarding': {BootRecovery.schemaKey: BootRecovery.schemaVersion},
  }.entries) {
    test('${previousInstall.key} without an appearance choice keeps System across launches', () async {
      SharedPreferences.setMockInitialValues(previousInstall.value);
      await SharedPreferencesUtil.init();
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString(SharedPreferencesUtil.appearanceModeKey), 'system');

      await prefs.reload();
      await SharedPreferencesUtil.init();
      final provider = AppearanceProvider();
      addTearDown(provider.dispose);
      expect(provider.mode, ThemeMode.system);
      expect(resolveAppearanceBrightness(provider.mode, Brightness.dark), Brightness.dark);
      expect(resolveAppearanceBrightness(provider.mode, Brightness.light), Brightness.light);
    });
  }

  for (final mode in ThemeMode.values) {
    test('upgrade preserves explicit ${mode.name}', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'onboardingCompleted': true,
        SharedPreferencesUtil.appearanceModeKey: mode.name,
        SharedPreferencesUtil.appearanceDefaultMigrationKey: mode == ThemeMode.light ? 'system' : 'light',
      });
      await SharedPreferencesUtil.init();
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().appearanceMode, mode.name);
    });
  }

  test('a later user choice survives initialization and signing out', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{'onboardingCompleted': true});
    await SharedPreferencesUtil.init();
    final provider = AppearanceProvider();
    addTearDown(provider.dispose);
    await provider.setMode(ThemeMode.dark);
    final prefs = await SharedPreferences.getInstance();
    await clearPreferencesForSignOut();
    await prefs.reload();
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().appearanceMode, 'dark');
  });

  test('first-boot diagnostics and malformed history do not imply an existing install', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'onboardingCompleted': 'true',
      'lastKnownAppVersion': 123,
      BootRecovery.schemaKey: '1',
      'boot.failure_count': 1,
      'boot.failure_stage': 'firebase_init',
    });
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().appearanceMode, 'light');
  });

  for (final badValue in <Object>['unexpected', 123]) {
    test('invalid appearance $badValue retains the Light fallback across launches', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'onboardingCompleted': true,
        SharedPreferencesUtil.appearanceModeKey: badValue,
        SharedPreferencesUtil.appearanceDefaultMigrationKey: 'system',
      });
      await SharedPreferencesUtil.init();
      expect(AppearanceProvider.parse(SharedPreferencesUtil().appearanceMode), ThemeMode.light);
      final prefs = await SharedPreferences.getInstance();
      if (badValue is! String) {
        expect(prefs.getKeys().any((key) => key.startsWith('appearanceMode.corrupt-')), isTrue);
      }
      await prefs.reload();
      await SharedPreferencesUtil.init();

      expect(AppearanceProvider.parse(SharedPreferencesUtil().appearanceMode), ThemeMode.light);
    });
  }

  for (final badDefault in <Object>['dark', true, 123]) {
    for (final existingInstall in <bool>[false, true]) {
      test('invalid migration decision $badDefault uses the original install classification $existingInstall',
          () async {
        SharedPreferences.setMockInitialValues(<String, Object>{
          if (existingInstall) 'onboardingCompleted': true,
          SharedPreferencesUtil.appearanceDefaultMigrationKey: badDefault,
        });
        await SharedPreferencesUtil.init();

        expect(SharedPreferencesUtil().appearanceMode, existingInstall ? 'system' : 'light');
      });
    }
  }

  for (final throwsOnWrite in <bool>[false, true]) {
    test('failed migration ${throwsOnWrite ? 'exception' : 'result'} keeps System and retries', () async {
      final store = _AppearancePreferencesStore(throwsOnWrite: throwsOnWrite);
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().appearanceMode, 'system');
      expect(store.data.containsKey('flutter.appearanceMode'), isFalse);

      store.failAppearanceWrite = false;
      SharedPreferences.resetStatic();
      await SharedPreferencesUtil.init();

      expect(store.data['flutter.appearanceMode'], 'system');
      expect(store.appearanceWrites, 2);
    });

    for (final initialValues in <String, Map<String, Object>>{
      'fresh install': {},
      'quarantined appearance': {'onboardingCompleted': true, SharedPreferencesUtil.appearanceModeKey: 123},
    }.entries) {
      test('${initialValues.key} keeps Light after a failed ${throwsOnWrite ? 'throwing' : 'false'} write', () async {
        final store = _AppearancePreferencesStore(throwsOnWrite: throwsOnWrite, initialValues: initialValues.value);
        SharedPreferences.resetStatic();
        SharedPreferencesStorePlatform.instance = store;
        await SharedPreferencesUtil.init();
        final prefs = await SharedPreferences.getInstance();

        expect(SharedPreferencesUtil().appearanceMode, 'light');
        expect(store.data.containsKey('flutter.appearanceMode'), isFalse);
        // These are written later in a successful first boot. None should turn
        // a retry of the original Light decision into an upgrade to System.
        await BootRecovery(prefs).fullBootSucceeded();
        await prefs.setBool('onboardingCompleted', true);
        await prefs.setString('lastKnownAppVersion', '1.0.553+1000');

        store.failAppearanceWrite = false;
        SharedPreferences.resetStatic();
        await SharedPreferencesUtil.init();

        expect(store.data['flutter.appearanceMode'], 'light');
        expect(SharedPreferencesUtil().appearanceMode, 'light');
      });
    }

    test('pending Light decision survives sign out after a failed ${throwsOnWrite ? 'throwing' : 'false'} write',
        () async {
      final store = _AppearancePreferencesStore(throwsOnWrite: throwsOnWrite, initialValues: {});
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      await SharedPreferencesUtil.init();
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('lastKnownAppVersion', '1.0.553+1000');

      if (throwsOnWrite) {
        // Sign-out currently propagates a failed restoration. Its pending
        // appearance decision must already be safe before that write occurs.
        await expectLater(clearPreferencesForSignOut(), throwsStateError);
      } else {
        await clearPreferencesForSignOut();
      }
      expect(store.data['flutter.${SharedPreferencesUtil.appearanceDefaultMigrationKey}'], 'light');
      expect(store.data.containsKey('flutter.appearanceMode'), isFalse);

      store.failAppearanceWrite = false;
      SharedPreferences.resetStatic();
      await SharedPreferencesUtil.init();

      expect(store.data['flutter.appearanceMode'], 'light');
    });

    test('failed decision ${throwsOnWrite ? 'exception' : 'result'} still attempts and saves appearance', () async {
      final store = _AppearancePreferencesStore(
        throwsOnWrite: throwsOnWrite,
        initialValues: {},
        failAppearanceWrite: false,
        failMigrationWrite: true,
      );
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      await SharedPreferencesUtil.init();
      final prefs = await SharedPreferences.getInstance();
      await BootRecovery(prefs).fullBootSucceeded();

      expect(store.data.containsKey('flutter.${SharedPreferencesUtil.appearanceDefaultMigrationKey}'), isFalse);
      expect(store.data['flutter.appearanceMode'], 'light');
      SharedPreferences.resetStatic();
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().appearanceMode, 'light');
    });

    test('failure of both ${throwsOnWrite ? 'throwing' : 'false'} writes leaves this boot usable', () async {
      final store = _AppearancePreferencesStore(
        throwsOnWrite: throwsOnWrite,
        initialValues: {},
        failMigrationWrite: true,
      );
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().appearanceMode, 'light');
      expect(store.data.containsKey('flutter.${SharedPreferencesUtil.appearanceDefaultMigrationKey}'), isFalse);
      expect(store.data.containsKey('flutter.appearanceMode'), isFalse);
      expect(store.appearanceWrites, 1);
    });
  }
}

class _AppearancePreferencesStore extends SharedPreferencesStorePlatform {
  _AppearancePreferencesStore({
    required this.throwsOnWrite,
    Map<String, Object> initialValues = const {'onboardingCompleted': true},
    this.failAppearanceWrite = true,
    this.failMigrationWrite = false,
  }) : data = {for (final entry in initialValues.entries) 'flutter.${entry.key}': entry.value};

  final bool throwsOnWrite;
  final Map<String, Object> data;
  bool failAppearanceWrite;
  bool failMigrationWrite;
  int appearanceWrites = 0;

  @override
  Future<Map<String, Object>> getAll() async => Map<String, Object>.from(data);

  @override
  Future<bool> setValue(String valueType, String key, Object value) async {
    if (key == 'flutter.${SharedPreferencesUtil.appearanceDefaultMigrationKey}' && failMigrationWrite) {
      if (throwsOnWrite) throw StateError('Appearance migration storage unavailable');
      return false;
    }
    if (key == 'flutter.appearanceMode') {
      appearanceWrites++;
      if (failAppearanceWrite) {
        if (throwsOnWrite) throw StateError('Appearance storage unavailable');
        return false;
      }
    }
    data[key] = value;
    return true;
  }

  @override
  Future<bool> remove(String key) async {
    data.remove(key);
    return true;
  }

  @override
  Future<bool> clear() async {
    data.clear();
    return true;
  }
}
