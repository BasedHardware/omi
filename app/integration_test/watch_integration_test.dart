import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:friend_private/main.dart' as app;
import 'package:friend_private/services/watch_manager.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/widgets/watch_recording_widget.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Watch Integration Tests', () {
    testWidgets('Watch recording flow', (tester) async {
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

      // Stop recording
      await tester.tap(watchWidget);
      await tester.pumpAndSettle();

      expect(captureProvider.recordingState, RecordingState.stop);
    });
  });
}
