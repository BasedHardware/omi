import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'dart:typed_data';
import 'package:friend_private/services/watch_manager.dart';
import 'package:friend_private/providers/capture_provider.dart' show CaptureProvider;
import 'package:friend_private/utils/enums.dart' hide RecordingSource;
import '../mocks/mocks.mocks.dart';

void main() {
  late WatchManager watchManager;
  late MockMethodChannel methodChannel;
  late MockCaptureProvider captureProvider;

  setUp(() {
    methodChannel = MockMethodChannel();
    captureProvider = MockCaptureProvider();
    watchManager = WatchManager();
    watchManager.setCaptureProvider(captureProvider);
  });

  group('WatchManager Tests', () {
    test('isWatchAvailable returns true when watch is available', () async {
      when(methodChannel.invokeMethod<bool>('isWatchAvailable'))
          .thenAnswer((_) async => true);

      final result = await watchManager.isWatchAvailable();
      expect(result, true);
    });

    test('handles recording state changes', () async {
      watchManager.startRecording();

      verify(captureProvider.updateRecordingState(RecordingState.record));
      verify(captureProvider.updateRecordingSource(RecordingSource.watch));
    });

    test('processes audio data correctly', () async {
      final audioData = Uint8List.fromList([1, 2, 3]);
      when(captureProvider.transcriptServiceReady).thenReturn(true);
      when(captureProvider.isWalSupported).thenReturn(true);

      await watchManager.handleAudioData(audioData);

      verify(captureProvider.processRawAudioData(audioData)).called(1);
    });
  });
}
