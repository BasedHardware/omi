import 'package:firebase_core_platform_interface/firebase_core_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:firebase_auth_platform_interface/firebase_auth_platform_interface.dart';

void setupFirebaseMocks() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Setup mock platform interface for Firebase Core
  FirebasePlatform.instance = MockFirebasePlatform();

  // Mock Firebase Core method channel
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

  // Mock Firebase Auth Pigeon API
  const pigeonChannel = BinaryMessenger.setMockMessageHandler(
    'dev.flutter.pigeon.FirebaseAuthHostApi.registerIdTokenListener',
    (ByteData? message) async => null,
  );

  // Mock other required Pigeon channels
  BinaryMessenger.setMockMessageHandler(
    'dev.flutter.pigeon.FirebaseAuthHostApi.registerAuthStateListener',
    (ByteData? message) async => null,
  );
}

class MockFirebasePlatform extends FirebasePlatform {
  @override
  FirebaseAppPlatform app([String name = defaultFirebaseAppName]) {
    return TestFirebaseAppPlatform(name, _testOptions);
  }

  @override
  List<FirebaseAppPlatform> get apps => [];

  static const FirebaseOptions _testOptions = FirebaseOptions(
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
