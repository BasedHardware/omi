import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/custom_live_audio_recovery_policy.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

import '../../support/refactor_flag_adapter.dart';

void main() {
  bool disabled({required bool contextAvailable, required bool? killSwitch}) => shouldDisableCustomLiveAudioRecovery(
        buildEnabled: true,
        flagReadContextAvailable: contextAvailable,
        cachedKillSwitchEnabled: killSwitch,
      );

  test('a readable but unresolved kill switch blocks recovery', () {
    expect(disabled(contextAvailable: true, killSwitch: null), isTrue);
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

  test('refresh keeps an absent kill switch unresolved instead of reporting it off', () async {
    await setRefactorFlags({});
    addTearDown(AnalyticsManager.resetForTesting);

    expect(
      await AnalyticsManager().resolvedBooleanFeatureFlag(
        'android-custom-live-audio-recovery-kill',
        refresh: true,
      ),
      isNull,
    );
  });
}
