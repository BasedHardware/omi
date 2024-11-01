import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

@GenerateMocks([CaptureProvider])
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CaptureProvider Tests', () {
    late CaptureProvider provider;

    setUp(() {
      provider = CaptureProvider();
    });

    test('Initial state', () {
      expect(provider, isNotNull);
    });

    tearDown(() {
      provider.dispose();
    });
  });
}
