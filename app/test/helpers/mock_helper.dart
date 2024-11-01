import 'package:firebase_core_platform_interface/firebase_core_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void setupFirebaseMocks() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Setup mock platform interface for Firebase
  final platform = TestFirebasePlatform();
  FirebasePlatform.instance = platform;

  // Mock method channels
  const MethodChannel channel = MethodChannel('plugins.flutter.io/firebase_core');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
    switch (call.method) {
      case 'Firebase#initializeCore':
        return [
          {
            'name': '[DEFAULT]',
            'options': {
              'apiKey': 'test-api-key',
              'appId': 'test-app-id',
              'messagingSenderId': 'test-sender-id',
              'projectId': 'test-project-id',
            },
          }
        ];
      case 'Firebase#initializeApp':
        return {
          'name': call.arguments['appName'],
          'options': call.arguments['options'],
        };
      default:
        return null;
    }
  });
}

class TestFirebasePlatform extends FirebasePlatform {
  @override
  FirebaseAppPlatform app([String name = defaultFirebaseAppName]) {
    return TestFirebaseAppPlatform(
      TestFirebasePlatform._testAppName,
      TestFirebasePlatform._testOptions,
    );
  }

  @override
  List<FirebaseAppPlatform> get apps => [];

  static const String _testAppName = '[DEFAULT]';
  static final FirebaseOptions _testOptions = const FirebaseOptions(
    apiKey: 'test-api-key',
    appId: 'test-app-id',
    messagingSenderId: 'test-sender-id',
    projectId: 'test-project-id',
  );
}

class TestFirebaseAppPlatform extends FirebaseAppPlatform {
  TestFirebaseAppPlatform(String name, FirebaseOptions options)
      : super(name, options);
}
