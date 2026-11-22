import 'dart:async';
import 'package:awesome_notifications/awesome_notifications_platform_interface.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:firebase_messaging_platform_interface/firebase_messaging_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart';

class _Messaging extends FirebaseMessagingPlatform {
  final rotations = StreamController<String>.broadcast();
  var reads = 0;
  var subscriptions = 0;
  @override
  FirebaseMessagingPlatform delegateFor({required FirebaseApp app}) => this;
  @override
  FirebaseMessagingPlatform setInitialValues({bool? isAutoInitEnabled}) => this;
  @override
  Future<RemoteMessage?> getInitialMessage() async => null;
  @override
  Future<String?> getAPNSToken() async {
    reads++;
    return null;
  }

  @override
  Future<String?> getToken({String? vapidKey}) async {
    reads++;
    return null;
  }

  @override
  Stream<String> get onTokenRefresh {
    subscriptions++;
    return rotations.stream;
  }
}

class _Gateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'alice');
  @override
  AuthUserSnapshot? get currentUser => user;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {
    user = null;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('real notification service revokes old retries and fences delayed permission admission', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp(
        options: const FirebaseOptions(
            apiKey: 'fake', appId: '1:1:ios:fake', messagingSenderId: '1', projectId: 'demo-omi-local'));
    final previousOS = AwesomeNotificationsPlatform.operatingSystem;
    AwesomeNotificationsPlatform.operatingSystem = 'ios';
    AwesomeNotificationsPlatform.resetInstance();
    addTearDown(() {
      AwesomeNotificationsPlatform.operatingSystem = previousOS;
      AwesomeNotificationsPlatform.resetInstance();
    });
    final messaging = _Messaging();
    FirebaseMessagingPlatform.instance = messaging;
    final gateway = _Gateway();
    AuthService.installLocalHarnessTokenGateway(gateway);
    AuthService.instance.markAuthenticatedUser('alice');
    Completer<bool>? permission;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('awesome_notifications'), (call) async {
      if (call.method == 'getBadgeCount') return 0;
      if (call.method.endsWith('TimeZoneIdentifier')) return 'UTC';
      if (call.method == 'isNotificationAllowed') return permission?.future ?? Future.value(true);
      return true;
    });
    final service = createNotificationService();
    addTearDown(() async {
      gateway.user = null;
      AuthService.instance.handleAuthUserChanged(null);
      WidgetsBinding.instance.removeObserver(service as WidgetsBindingObserver);
      await messaging.rotations.close();
    });
    await service.initialize();
    await service.register();
    await service.register();
    expect(messaging.subscriptions, 1, reason: 'normal entry calls must not add token listeners');
    final oldReads = messaging.reads;
    gateway.user = const AuthUserSnapshot(uid: 'bob');
    AuthService.instance.markAuthenticatedUser('bob');
    await tester.pump(const Duration(minutes: 2));
    messaging.rotations.add('late-token');
    await tester.pump();
    expect(messaging.reads, oldReads, reason: 'an auth/token event cannot admit the replacement owner');
    await service.register();
    expect(messaging.reads, oldReads + 1, reason: 'the normal authenticated entry point admits Bob');

    permission = Completer<bool>();
    final requesting = service.requestNotificationPermissions();
    await tester.pump();
    final before = messaging.reads;
    gateway.user = const AuthUserSnapshot(uid: 'carol');
    AuthService.instance.markAuthenticatedUser('carol');
    permission.complete(true);
    expect(await requesting, isTrue);
    await tester.pump();
    expect(messaging.reads, before, reason: 'Bob\'s delayed permission cannot register Carol');
    await tester.pump(const Duration(minutes: 2));
    expect(messaging.reads, before);
  });
}
