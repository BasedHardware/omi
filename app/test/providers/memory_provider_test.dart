import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

@GenerateMocks([MemoryProvider])
void main() {
  setUp(() {
    // Initialize service manager before tests
    ServiceManager.init();
  });

  group('MemoryProvider Tests', () {
    test('Initial state', () {
      final provider = MemoryProvider();
      expect(provider.memories, isEmpty);
    });
  });
}
