/// Owns the registry-visible kill key for Android Limitless Custom Live recovery.
/// Keep the controller's runtime read on this constant so the registry scan
/// can verify that the declared kill switch has a code reader.
class CustomLiveAudioRecoveryFlag {
  static const killSwitchFlag = 'android-custom-live-audio-recovery-kill';
}
