import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/webhook_only_socket_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('WebhookOnlySocketService', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('should batch audio bytes for 60 seconds before sending', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://test.webhook.com/audio';
      SharedPreferencesUtil().webhookAudioBytesDelay = '60';

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      // Act
      await service.start();
      service.send([1, 2, 3, 4]); // First frame

      // Assert: Should buffer, not send immediately
      expect(service.getPendingBufferSize(), equals(4));
    });

    test('should send batched audio after 60 seconds', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://test.webhook.com/audio';
      SharedPreferencesUtil().webhookAudioBytesDelay = '60';

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      bool webhookCalled = false;
      service.onWebhookCalled = () => webhookCalled = true;

      // Act
      await service.start();
      service.send([1, 2, 3, 4]);

      // Wait for batch timer (use shorter time in test)
      await Future.delayed(const Duration(milliseconds: 100));

      // Assert
      expect(webhookCalled, isTrue);
    });

    test('should never connect to Omi servers', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://test.webhook.com/audio';

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      // Act
      await service.start();

      // Assert: No WebSocket connection URL should contain Omi domain
      expect(service.getConnectionUrl(), isNull);
      expect(service.state, equals(SocketServiceState.connected)); // "Connected" but to webhook, not WS
    });

    test('should fail gracefully if webhook URL is empty', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = ''; // Empty

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      // Act & Assert
      expect(() async => await service.start(), throwsException);
    });

    test('should include codec metadata in webhook payload', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://test.webhook.com/audio';

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      Map<String, dynamic>? capturedPayload;
      service.onWebhookPayloadCapture = (payload) => capturedPayload = payload;

      // Act
      await service.start();
      service.send([1, 2, 3, 4]);
      await service.flushImmediately(); // Force send

      // Assert
      expect(capturedPayload, isNotNull);
      expect(capturedPayload!['codec'], equals('pcm16'));
      expect(capturedPayload!['sample_rate'], equals(16000));
      expect(capturedPayload!['language'], equals('en'));
    });

    test('should trigger notification on webhook failure', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://invalid.webhook.test/fail';

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      bool errorCallbackCalled = false;
      service.onWebhookError = (error) => errorCallbackCalled = true;

      // Act
      await service.start();
      service.send([1, 2, 3]);
      await service.flushImmediately();

      // Assert
      expect(errorCallbackCalled, isTrue);
    });

    test('should respect battery optimization level for keep-alive', () async {
      // Arrange
      SharedPreferencesUtil().webhookAudioBytes = 'https://test.webhook.com/audio';
      SharedPreferencesUtil().batteryOptimizationLevel = 2; // Aggressive

      final service = WebhookOnlySocketService.create(
        16000,
        BleAudioCodec.pcm16,
        'en',
      );

      // Act
      await service.start();

      // Assert: Keep-alive should be 30 seconds for level 2
      expect(service.getKeepAliveInterval(), equals(30));
    });
  });
}
