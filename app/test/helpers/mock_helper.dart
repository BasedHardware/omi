import 'package:firebase_core_platform_interface/firebase_core_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class MockFirebasePlatform extends FirebasePlatform {
  @override
  FirebaseAppPlatform app([String name = defaultFirebaseAppName]) {
    return MockFirebaseApp(
      options: const FirebaseOptions(
        apiKey: 'test-api-key',
        appId: 'test-app-id',
        messagingSenderId: 'test-sender-id',
        projectId: 'test-project-id',
      ),
    );
  }

  @override
  List<FirebaseAppPlatform> get apps => [];
}

class MockFirebaseApp extends FirebaseAppPlatform {
  MockFirebaseApp({required FirebaseOptions options})
      : super(defaultFirebaseAppName, options);

  @override
  Future<void> delete() async {}

  @override
  bool get isAutomaticDataCollectionEnabled => false;
}

void setupFirebaseMocks() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Setup mock platform
  FirebasePlatform.instance = MockFirebasePlatform();

  // Mock method channels
  const MethodChannel('plugins.flutter.io/firebase_core')
    .setMockMethodCallHandler((call) async {
      switch (call.method) {
        case 'Firebase#initializeCore':
          return [
            {
              'name': defaultFirebaseAppName,
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

  // Mock auth channel
  const MethodChannel('plugins.flutter.io/firebase_auth')
    .setMockMethodCallHandler((call) async {
      switch (call.method) {
        case 'Auth#authStateChanges':
          return null;
        default:
          return null;
      }
    });
}
