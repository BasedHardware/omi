import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

@GenerateMocks([NotificationService])
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('NotificationService Tests', () {
    test('Instance is singleton', () {
      final instance1 = NotificationService.instance;
      final instance2 = NotificationService.instance;
      expect(identical(instance1, instance2), isTrue);
    });
  });
}
