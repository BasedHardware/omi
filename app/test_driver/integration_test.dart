import 'package:integration_test/integration_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/main.dart' as app;
import 'package:friend_private/services/watch_manager.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/widgets/watch_recording_widget.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Watch Integration Tests', () {
    testWidgets('Watch discovery and connection', (tester) async {
      await app.main();
      await tester.pumpAndSettle();

      final deviceService = DeviceService();
      await deviceService.discover();
      await tester.pumpAndSettle();

      // Check if watch is discovered when available
      final watchManager = WatchManager();
      if (await watchManager.isWatchAvailable()) {
        final devices = deviceService.devices;
        expect(
          devices.any((d) => d.type == DeviceType.watch),
          true,
          reason: 'Watch should be discovered when available',
        );

        // Test connection
        final connection = await deviceService.ensureConnection('apple_watch');
        expect(connection, isNotNull);
        expect(connection?.status, DeviceConnectionState.connected);
      }
    });

    testWidgets('Watch recording flow with audio', (tester) async {
      await app.main();
      await tester.pumpAndSettle();

      final watchWidget = find.byType(WatchRecordingWidget);
      expect(watchWidget, findsOneWidget);

      // Start recording
      await tester.tap(watchWidget);
      await tester.pumpAndSettle();

      final context = tester.element(watchWidget);
      final captureProvider = CaptureProvider.of(context);

      expect(captureProvider.recordingSource, RecordingSource.watch);
      expect(captureProvider.recordingState, RecordingState.record);

      // Simulate audio data
      final watchManager = WatchManager();
      await watchManager.handleAudioData(Uint8List.fromList([1, 2, 3]));
      await tester.pumpAndSettle();

      // Stop recording
      await tester.tap(watchWidget);
      await tester.pumpAndSettle();

      expect(captureProvider.recordingState, RecordingState.stop);
    });

    testWidgets('Watch connection loss handling', (tester) async {
      await app.main();
      await tester.pumpAndSettle();

      final watchManager = WatchManager();
      if (await watchManager.isWatchAvailable()) {
        // Start recording
        await watchManager.startRecording();
        expect(watchManager.isRecording, true);

        // Simulate connection loss
        await watchManager.handleWatchConnectionChanged(false);
        expect(watchManager.isRecording, false);
      }
    });
  });
}
