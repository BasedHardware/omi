import 'dart:io';

import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'fixture_backend.dart';

/// Hermetic journey-lane bootstrap (SCA-488 / C2).
///
/// Boots the **real production page widgets and providers** with external
/// I/O faked at declared boundaries only:
///
/// | Boundary | Fake | What stays real |
/// | --- | --- | --- |
/// | Backend HTTP | [JourneyFixtureBackend] on loopback, via `Env.overrideApiBaseUrl` | the app's real HTTP client, SSE parser, controllers, UI |
/// | Firebase token I/O | synthetic [AuthTokenGateway] installed through `AuthService.installLocalHarnessTokenGateway` (debug+local_dev gated) | every AuthService decision (refresh retries, expiry, recovery) |
/// | SharedPreferences | `setMockInitialValues` seeded with the fixture principal | every provider persistence decision |
///
/// The full-stack simulator lane does **not** use this file: it boots
/// `app.main()` against the real C1 session harness (backend + Auth
/// emulator) and signs in through the real local-dev token path.
final class JourneyHermeticBoot {
  JourneyHermeticBoot._();

  static JourneyFixtureBackend? backend;

  static const String fixtureToken = 'synthetic-journey-bearer';

  /// Seeds the fixture principal and points the app at [serverBaseUrl].
  static Future<JourneyFixtureBackend> start({
    String uid = JourneyFixtureBackend.fixtureUid,
    String email = JourneyFixtureBackend.fixtureEmail,
    Map<String, Object> extraPrefs = const {},
  }) async {
    TestWidgetsFlutterBinding.ensureInitialized();

    final server = await JourneyFixtureBackend.start();
    backend = server;

    await resetAppState(uid: uid, email: email, extraPrefs: extraPrefs);
    Env.overrideApiBaseUrl(server.baseUrl);
    PlatformManager.initializeForLocalHarness();
    AuthService.installLocalHarnessTokenGateway(_SyntheticGateway(uid, email));
    return server;
  }

  /// The executable seed/reset contract of the hermetic lane: restore the
  /// fixture principal's preference state. Independent clean seed state per
  /// journey run means exactly this plus a fresh fixture backend.
  static Future<void> resetAppState({
    String uid = JourneyFixtureBackend.fixtureUid,
    String email = JourneyFixtureBackend.fixtureEmail,
    Map<String, Object> extraPrefs = const {},
  }) async {
    SharedPreferences.setMockInitialValues({
      'uid': uid,
      'email': email,
      'authToken': fixtureToken,
      'tokenExpirationTime': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
      ...extraPrefs,
    });
    await SharedPreferencesUtil.init();
  }

  static void stop() {
    Env.clearApiBaseUrlOverrideForTesting();
    JourneyFaultGate.instance.clearAll();
    backend?.clearFaults();
  }

  /// Pumps a production page inside the real app scaffolding (global
  /// navigator key, l10n, theme) with the providers that page reads. The
  /// journey then interacts through the same widget surface a user does.
  static Future<void> pumpPage(
    WidgetTester tester, {
    required Widget page,
    List<SingleChildWidget> providers = const [],
  }) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => MessageProvider()),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (_) => AppProvider()),
          ChangeNotifierProvider(create: (_) => ConversationProvider()),
          ChangeNotifierProvider(create: (_) => HomeProvider()),
          ChangeNotifierProvider(create: (_) => IntegrationProvider()),
          ChangeNotifierProvider(create: (_) => FolderProvider()),
          ChangeNotifierProvider(create: (_) => UsageProvider()),
          ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
          ...providers,
        ],
        child: MaterialApp(
          navigatorKey: globalNavigatorKey,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          theme: ThemeData(brightness: Brightness.dark, useMaterial3: false),
          home: page,
        ),
      ),
    );
    await tester.pump();
  }
}

class _SyntheticGateway implements AuthTokenGateway {
  _SyntheticGateway(this.uid, this.email);

  final String uid;
  final String email;
  AuthTokenResult? forcedResult;

  @override
  AuthUserSnapshot? get currentUser => AuthUserSnapshot(uid: uid, email: email, displayName: 'Journey Fixture');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    return RefreshedAuthToken(
      token: JourneyHermeticBoot.fixtureToken,
      expirationTime: DateTime.now().toUtc().add(const Duration(hours: 1)),
    );
  }

  @override
  Future<void> signOut() async {}
}

/// Scriptable token gateway for session-expiry journeys: the caller decides
/// what Firebase would have returned. Still pure I/O — no product logic:
/// terminal failures surface exactly the way the production gateway would,
/// as a FirebaseAuthException with a terminal code.
class ScriptableGateway implements AuthTokenGateway {
  ScriptableGateway({
    required this.user,
    this.refreshOutcome = const AuthTokenSuccess(
      token: JourneyHermeticBoot.fixtureToken,
      expirationTime: null,
    ),
  });

  AuthUserSnapshot? user;
  AuthTokenResult refreshOutcome;
  int refreshCalls = 0;
  bool signedOut = false;

  @override
  AuthUserSnapshot? get currentUser => signedOut ? null : user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    refreshCalls++;
    switch (refreshOutcome) {
      case AuthTokenSuccess(:final token, :final expirationTime):
        return RefreshedAuthToken(token: token, expirationTime: expirationTime);
      case AuthTokenTerminalFailure(:final code):
        throw FirebaseAuthException(code: code);
      case AuthTokenTransientFailure():
        // Non-terminal failures reach AuthService exactly as a real
        // Firebase network error would: an exception that is not in the
        // terminal set, classified transient by the production mapper.
        throw FirebaseAuthException(code: 'network-request-failed');
      case _:
        return null;
    }
  }

  @override
  Future<void> signOut() async {
    signedOut = true;
  }
}

/// Platform-channel mocks shared by page-level journeys (clipboard, share).
void mockCommonPlatformChannels() {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
}

/// The lane this run executes in: `hermetic` (host) or `simulator` (device).
/// Selected by the runner; the journey definitions themselves are identical.
String get journeyLane => Platform.environment['OMI_JOURNEY_LANE'] ?? 'hermetic';
