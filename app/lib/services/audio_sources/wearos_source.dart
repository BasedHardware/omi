import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';

/// Audio source for WearOS watch via Wear Data Layer.
///
/// The watch sends Opus-encoded audio chunks through the native
/// WearOsListenerService → WearOsAudioBridge → Flutter EventChannel.
///
/// Audio data arrives already in Limitless .bin format:
///   [4-byte LE length prefix][raw Opus frame][4-byte LE length prefix][raw Opus frame]...
///
/// Unlike [BleDeviceSource], there is no 3-byte BLE header to strip —
/// the data is pure Opus. Each processBytes call wraps the incoming
/// bytes into a [WalFrame] with a monotonic index sync key (like
/// [PhoneMicSource]).
class WearOsSource implements AudioSource {
  @override
  BleAudioCodec get codec => BleAudioCodec.opus;

  @override
  final String deviceId;

  @override
  final String deviceModel;

  int _frameIndex = 0;

  WearOsSource({
    this.deviceId = 'wearos-watch',
    this.deviceModel = 'WearOS Watch',
  });

  @override
  List<WalFrame> processBytes(List<int> rawBytes) {
    if (rawBytes.isEmpty) return [];

    // The incoming bytes are already Opus in Limitless .bin format
    // (4-byte LE length prefix per frame). Wrap as a single WalFrame.
    final frame = WalFrame(
      payload: rawBytes,
      syncKey: FrameSyncKey.fromIndex(_frameIndex),
    );
    _frameIndex = (_frameIndex + 1) & 0xFF;

    return [frame];
  }

  @override
  List<int> getSocketPayload(List<int> rawBytes) {
    // Already pure Opus data — return as-is for WebSocket streaming.
    return rawBytes;
  }

  @override
  List<WalFrame> flush() => [];
}
