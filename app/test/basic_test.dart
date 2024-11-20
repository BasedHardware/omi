import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/main.dart' as app;

void main() {
  group('Basic App Tests', () {
    test('Basic app initialization', () {
      // Basic assertion to start with
      expect(true, isTrue);
    });

    test('Simple math operations', () {
      expect(2 + 2, equals(4));
      expect(5 - 3, equals(2));
      expect(4 * 3, equals(12));
    });

    // Example of async test
    test('Delayed operation completes', () async {
      final future = Future.delayed(
        const Duration(milliseconds: 100),
        () => 'completed',
      );

      expect(await future, equals('completed'));
    });
  });

  // Example of how to test exceptions
  group('Error Handling Tests', () {
    test('Throws exception on invalid operation', () {
      expect(
        () => [1, 2, 3].elementAt(10),
        throwsRangeError,
      );
    });
  });
}
