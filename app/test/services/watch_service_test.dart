import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:friend_private/services/watch_service.dart';
import 'package:friend_private/services/watch_manager.dart';
import 'package:friend_private/utils/errors.dart';
import '../mocks/mocks.mocks.dart';

void main() {
  late WatchService watchService;
  late MockWatchManager mockManager;

  setUp(() {
    watchService = WatchService();
    mockManager = MockWatchManager();
  });

  group('WatchService Tests', () {
    test('checkAvailability returns false when watch is not available', () async {
      when(mockManager.isWatchAvailable()).thenAnswer((_) async => false);

      final result = await watchService.checkAvailability();
      expect(result, false);
    });

    test('startRecording throws when watch is not available', () async {
      when(mockManager.isWatchAvailable()).thenAnswer((_) async => false);

      expect(
        () => watchService.startRecording(),
        throwsA(isA<WatchConnectionError>()),
      );
    });

    test('stopRecording stops recording successfully', () async {
      when(mockManager.stopRecording()).thenAnswer((_) async {});

      await watchService.stopRecording();
      verify(mockManager.stopRecording()).called(1);
    });
  });
}
