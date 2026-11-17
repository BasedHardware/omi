import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

/// A free plan's choice to transcribe on this phone, made at the monthly cloud cap.
///
/// The choice is permanent (David, 2026-11-16): it stays after the monthly reset until the reader
/// switches back in Settings › Transcription, and only a paid plan releases it automatically. It is
/// stored as the persisted on-device Custom STT config plus a pin naming exactly that config, so a
/// later release never touches a Custom STT the reader set up themselves.
abstract final class PhoneTranscriptionChoice {
  /// True when the persisted STT config is the pinned free-plan phone choice.
  static bool isPinned(SharedPreferencesUtil p) {
    final pin = p.paywallOnDeviceSttConfigId;
    if (pin.isEmpty) return false;
    final config = p.customSttConfig;
    return config.provider == SttProvider.onDeviceWhisper && config.sttConfigId == pin;
  }

  /// Persists [config] as the phone choice and pins it. Raw audio stays on the phone.
  static Future<CustomSttConfig> adopt(CustomSttConfig config, SharedPreferencesUtil p) async {
    final persisted = CustomSttConfig.fromJson(config.copyWith(sendRawAudioToOmi: false).toJson());
    await p.saveCustomSttConfig(persisted);
    p.paywallOnDeviceSttConfigId = persisted.sttConfigId;
    return persisted;
  }

  /// Returns to Omi's cloud transcription when the pinned choice is still the persisted config.
  /// Returns true when the persisted config changed.
  static Future<bool> release(SharedPreferencesUtil p) async {
    final changed = isPinned(p);
    if (changed) await p.saveCustomSttConfig(CustomSttConfig.defaultConfig);
    if (p.paywallOnDeviceSttConfigId.isNotEmpty) p.paywallOnDeviceSttConfigId = '';
    return changed;
  }
}
