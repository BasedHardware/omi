import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';

class MockUser extends Mock implements User {
  @override
  String get uid => 'test-uid';

  @override
  String? get email => 'test@example.com';

  @override
  String? get displayName => 'Test User';
}

void setupAuthMocks() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Mock auth state changes
  const MethodChannel channel = MethodChannel('plugins.flutter.io/firebase_auth');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
    switch (call.method) {
      case 'Auth#authStateChanges':
        return null; // No user initially
      case 'Auth#idTokenChanges':
        return null;
      case 'Auth#getIdToken':
        return 'mock-token';
      default:
        return null;
    }
  });
}
