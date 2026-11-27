import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/custom_live_audio_recovery_policy.dart';

void main() {
  test(
    'recovery fails closed when the cached kill switch context is unavailable',
    () {
      expect(
        shouldDisableCustomLiveAudioRecovery(
          buildEnabled: true,
          analyticsTrackingEnabled: false,
          identitySettled: false,
          cachedKillSwitchEnabled: false,
        ),
        isTrue,
      );
      expect(
        shouldDisableCustomLiveAudioRecovery(
          buildEnabled: true,
          analyticsTrackingEnabled: true,
          identitySettled: false,
          cachedKillSwitchEnabled: false,
        ),
        isTrue,
      );
    },
  );

  test(
    'the resolved cached kill switch disables recovery and an available off flag permits it',
    () {
      bool disabled({required bool cachedKillSwitchEnabled}) => shouldDisableCustomLiveAudioRecovery(
            buildEnabled: true,
            analyticsTrackingEnabled: true,
            identitySettled: true,
            cachedKillSwitchEnabled: cachedKillSwitchEnabled,
          );

      expect(disabled(cachedKillSwitchEnabled: true), isTrue);
      expect(disabled(cachedKillSwitchEnabled: false), isFalse);
    },
  );
}
