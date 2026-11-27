import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/custom_live_audio_recovery_policy.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/refactor_flag_adapter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  bool disabled({
    required bool contextAvailable,
    required bool? killSwitch,
    bool unresolvedRetryExhausted = false,
  }) =>
      shouldDisableCustomLiveAudioRecovery(
        buildEnabled: true,
        flagReadContextAvailable: contextAvailable,
        cachedKillSwitchEnabled: killSwitch,
        unresolvedRetryExhausted: unresolvedRetryExhausted,
      );

  test('a readable but unresolved kill switch blocks recovery', () {
    expect(disabled(contextAvailable: true, killSwitch: null), isTrue);
    expect(
      resolveCustomLiveAudioRecoveryGate(
        buildEnabled: true,
        flagReadContextAvailable: true,
        cachedKillSwitchEnabled: null,
      ),
      CustomLiveAudioRecoveryGate.pending,
    );
  });

  test('a missing kill switch permits recovery after its bounded lookup retry', () {
    expect(
      disabled(contextAvailable: true, killSwitch: null, unresolvedRetryExhausted: true),
      isFalse,
    );
    expect(
      resolveCustomLiveAudioRecoveryGate(
        buildEnabled: true,
        flagReadContextAvailable: true,
        cachedKillSwitchEnabled: null,
        unresolvedRetryExhausted: true,
      ),
      CustomLiveAudioRecoveryGate.enabled,
    );
  });

  test('tracking opt-out or a missing adapter preserves recovery', () {
    expect(disabled(contextAvailable: false, killSwitch: null), isFalse);
  });

  test('a known enabled kill switch blocks recovery and a known disabled switch permits it', () {
    expect(disabled(contextAvailable: true, killSwitch: true), isTrue);
    expect(disabled(contextAvailable: true, killSwitch: false), isFalse);
  });

  test('the build gate always blocks recovery', () {
    expect(
      shouldDisableCustomLiveAudioRecovery(
        buildEnabled: false,
        flagReadContextAvailable: false,
        cachedKillSwitchEnabled: null,
      ),
      isTrue,
    );
  });

  test('refresh keeps an absent kill switch unresolved only for callers that require resolution', () async {
    await setRefactorFlags({});
    addTearDown(AnalyticsManager.resetForTesting);
    await _waitForSettledIdentity();

    expect(
      await AnalyticsManager().resolvedBooleanFeatureFlag(
        'android-custom-live-audio-recovery-kill',
        refresh: true,
      ),
      isFalse,
    );
    expect(
      await AnalyticsManager().resolvedBooleanFeatureFlag(
        'android-custom-live-audio-recovery-kill',
        refresh: true,
        missingIsUnresolved: true,
      ),
      isNull,
    );
  });

  test('flag refresh reports a transient fetch failure to retry owners', () async {
    await setRefactorFlags({}, reloadFailures: 1);
    addTearDown(AnalyticsManager.resetForTesting);
    await _waitForSettledIdentity();
    var refreshFailed = false;

    expect(
      await AnalyticsManager().resolvedBooleanFeatureFlag(
        'android-custom-live-audio-recovery-kill',
        refresh: true,
        missingIsUnresolved: true,
        onRefreshFailure: () => refreshFailed = true,
      ),
      isNull,
    );
    expect(refreshFailed, isTrue);
  });

  test('a resolved multivariate arm is not enabled as a boolean kill switch', () async {
    final adapter = await setRefactorFlags({'multivariate-kill': true});
    addTearDown(AnalyticsManager.resetForTesting);
    await _waitForSettledIdentity();
    adapter.multivariateFlags.add('multivariate-kill');

    expect(
      await AnalyticsManager().resolvedBooleanFeatureFlag('multivariate-kill', refresh: true),
      isFalse,
    );
  });
}

Future<void> _waitForSettledIdentity() async {
  final identity = AnalyticsManager.settledIdentity;
  if (identity.value != null) return;

  final settled = Completer<void>();
  void onChanged() {
    if (identity.value != null && !settled.isCompleted) settled.complete();
  }

  identity.addListener(onChanged);
  try {
    onChanged();
    await settled.future.timeout(const Duration(seconds: 1));
  } finally {
    identity.removeListener(onChanged);
  }
}
