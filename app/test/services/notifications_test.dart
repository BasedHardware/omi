import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:firebase_core/firebase_core.dart';
import '../helpers/mock_helper.dart';

@GenerateMocks([NotificationService])
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    setupFirebaseMocks();
  });

  group('NotificationService Tests', () {
    setUp(() async {
      await Firebase.initializeApp();
    });

    test('Service initialization', () async {
      await Future.delayed(const Duration(milliseconds: 100)); // Wait for initialization
      expect(() => NotificationService.instance, returnsNormally);
    });
  });
}
