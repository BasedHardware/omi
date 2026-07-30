import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/device_audio_streaming_policy.dart';

void main() {
  group('DeviceAudioStreamingPolicy', () {
    test('legacy live audio keeps flowing while transcription reconnects', () {
      expect(
        DeviceAudioStreamingPolicy.shouldConsumeDeviceAudio(
          usesStorageAuthoritativeAudio: false,
          transcribeLaterEnabled: false,
          transcriptionServiceReady: false,
        ),
        isTrue,
      );
    });

    test('storage-authoritative live tail waits for transcription readiness', () {
      expect(
        DeviceAudioStreamingPolicy.shouldConsumeDeviceAudio(
          usesStorageAuthoritativeAudio: true,
          transcribeLaterEnabled: false,
          transcriptionServiceReady: false,
        ),
        isFalse,
      );
      expect(
        DeviceAudioStreamingPolicy.shouldConsumeDeviceAudio(
          usesStorageAuthoritativeAudio: true,
          transcribeLaterEnabled: false,
          transcriptionServiceReady: true,
        ),
        isTrue,
      );
    });

    test('Transcribe Later intentionally consumes storage audio without STT', () {
      expect(
        DeviceAudioStreamingPolicy.shouldConsumeDeviceAudio(
          usesStorageAuthoritativeAudio: true,
          transcribeLaterEnabled: true,
          transcriptionServiceReady: false,
        ),
        isTrue,
      );
    });
  });
}
