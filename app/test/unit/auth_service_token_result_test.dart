import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('successful refresh returns typed token and updates cache', () async {
    final gateway = _FakeTokenGateway(
      results: [RefreshedAuthToken(token: 'fresh-token', expirationTime: DateTime.fromMillisecondsSinceEpoch(123456))],
    );
    final service = _service(gateway);

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenSuccess>());
    expect(result.tokenOrNull, 'fresh-token');
    expect(SharedPreferencesUtil().authToken, 'fresh-token');
    expect(SharedPreferencesUtil().tokenExpirationTime, 123456);
    expect(SharedPreferencesUtil().uid, 'user-1');
  });

  test('concurrent refreshes share one in-flight SDK call', () async {
    final completer = Completer<RefreshedAuthToken?>();
    final gateway = _FakeTokenGateway(refreshCompleter: completer);
    final service = _service(gateway);

    final first = service.refreshIdToken();
    final second = service.refreshIdToken();
    completer.complete(RefreshedAuthToken(token: 'shared-token', expirationTime: DateTime.now()));

    expect(await first, isA<AuthTokenSuccess>());
    expect(await second, isA<AuthTokenSuccess>());
    expect(gateway.refreshCalls, 1);
  });

  test('terminal expiration invalidates an older in-flight refresh', () async {
    SharedPreferencesUtil().authToken = 'old-token';
    SharedPreferencesUtil().uid = 'old-user';
    final completer = Completer<RefreshedAuthToken?>();
    final gateway = _FakeTokenGateway(refreshCompleter: completer);
    final service = _service(gateway);

    final refresh = service.refreshIdToken();
    await service.expireSession(
      const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.backendRejectedRefreshedToken),
    );
    completer.complete(RefreshedAuthToken(token: 'stale-new-token', expirationTime: DateTime.now()));

    expect(await refresh, isA<AuthTokenMissingUser>());
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(gateway.signOutCalls, 1);
  });

  test('account switch cannot reuse or cache the previous user refresh', () async {
    final oldRefresh = Completer<RefreshedAuthToken?>();
    final gateway = _FakeTokenGateway(refreshCompleter: oldRefresh);
    final service = _service(gateway);

    final first = service.refreshIdToken();
    gateway.user = const AuthUserSnapshot(uid: 'user-2');
    gateway.refreshCompleter = null;
    service.handleAuthUserChanged('user-2');
    final second = service.refreshIdToken();
    oldRefresh.complete(RefreshedAuthToken(token: 'user-1-token', expirationTime: DateTime.now()));

    expect(await first, isA<AuthTokenMissingUser>());
    expect((await second).tokenOrNull, 'default-token');
    expect(SharedPreferencesUtil().uid, 'user-2');
    expect(SharedPreferencesUtil().authToken, 'default-token');
    expect(gateway.refreshCalls, 2);
  });

  test('observed Firebase user events cannot unlock a terminal session', () async {
    final gateway = _FakeTokenGateway();
    final service = _service(gateway);

    await service.expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.accountDeleted));
    service.handleAuthUserChanged(null);
    service.handleAuthUserChanged('user-1');

    expect(await service.refreshIdToken(), isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 0);
    service.markAuthenticatedUser('user-1');
    expect((await service.refreshIdToken()).tokenOrNull, 'default-token');
    expect(gateway.refreshCalls, 1);
  });

  test('transient refresh is bounded and does not sign out', () async {
    final gateway = _FakeTokenGateway(error: StateError('network unavailable'));
    final delays = <Duration>[];
    final events = <_TelemetryEvent>[];
    final service = _service(
      gateway,
      refreshDelay: (delay) async => delays.add(delay),
      recordTelemetry: (name, properties) => events.add(_TelemetryEvent(name, properties)),
    );

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenTransientFailure>());
    expect(gateway.refreshCalls, 3);
    expect(delays, [const Duration(milliseconds: 200), const Duration(milliseconds: 500)]);
    expect(gateway.signOutCalls, 0);
    expect(events, hasLength(1));
    expect(events, everyElement(predicate<_TelemetryEvent>((event) => event.properties['code'] == 'transient')));
  });

  test('null token consumes bounded retries without signing out', () async {
    final gateway = _FakeTokenGateway(
      results: List<RefreshedAuthToken?>.filled(3, RefreshedAuthToken(token: null, expirationTime: DateTime.now())),
    );
    final events = <_TelemetryEvent>[];
    final service = _service(
      gateway,
      recordTelemetry: (name, properties) => events.add(_TelemetryEvent(name, properties)),
    );

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenMissingToken>());
    expect(gateway.refreshCalls, 3);
    expect(gateway.signOutCalls, 0, reason: 'an SDK null-token result is not itself a terminal session decision');
    expect(events, hasLength(1));
    expect(events, everyElement(predicate<_TelemetryEvent>((event) => event.properties['code'] == 'missing_token')));
  });

  test('one null-token SDK result can recover on the next bounded attempt', () async {
    final gateway = _FakeTokenGateway(
      results: [
        RefreshedAuthToken(token: null, expirationTime: DateTime.now()),
        RefreshedAuthToken(token: 'recovered-token', expirationTime: DateTime.now()),
      ],
    );
    final service = _service(gateway);

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenSuccess>());
    expect(result.tokenOrNull, 'recovered-token');
    expect(gateway.refreshCalls, 2);
    expect(gateway.signOutCalls, 0);
  });

  test('legacy token caller expires session only after null-token budget is exhausted', () async {
    final gateway = _FakeTokenGateway(
      results: List<RefreshedAuthToken?>.filled(3, RefreshedAuthToken(token: null, expirationTime: DateTime.now())),
    );
    final service = _service(gateway);

    final token = await service.getIdToken();

    expect(token, isNull);
    expect(gateway.refreshCalls, 3);
    expect(gateway.signOutCalls, 1);
  });

  test('missing Firebase user is distinct and clears only cached auth', () async {
    SharedPreferencesUtil().authToken = 'stale';
    SharedPreferencesUtil().tokenExpirationTime = 99;
    final gateway = _FakeTokenGateway(user: null);
    final service = _service(gateway);

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 0);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(SharedPreferencesUtil().tokenExpirationTime, 0);
  });

  test('terminal Firebase error is typed and telemetry contains only safe context', () async {
    final events = <_TelemetryEvent>[];
    final gateway = _FakeTokenGateway(error: FirebaseAuthException(code: 'user-disabled'));
    final service = _service(
      gateway,
      recordTelemetry: (name, properties) => events.add(_TelemetryEvent(name, properties)),
    );

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenTerminalFailure>());
    expect((result as AuthTokenTerminalFailure).code, 'user-disabled');
    expect(events, hasLength(1));
    expect(events.single.name, 'auth_token_refresh_failed');
    expect(events.single.properties, {
      'failure_class': 'terminal',
      'code': 'user-disabled',
      'platform': 'ios',
      'app_version': '1.2.3+456',
      'release_channel': 'testflight',
    });
    for (final forbidden in <String>['token', 'uid', 'email', 'request_body']) {
      expect(events.single.properties.containsKey(forbidden), isFalse);
    }
  });

  test('expireSession is idempotent, emits once, and clears only user display caches', () async {
    final pendingMemory = Memory(
      id: 'pending-1',
      uid: 'user-1',
      content: 'unsynced',
      category: MemoryCategory.manual,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      visibility: MemoryVisibility.private,
    );
    SharedPreferences.setMockInitialValues({
      'authToken': 'secret',
      'tokenExpirationTime': 123,
      'uid': 'user-1',
      'email': 'person@example.com',
      'givenName': 'Person',
      'familyName': 'Example',
      'cachedConversations': <String>['conversation'],
      'cachedMemories': <String>['legacy-memory'],
      'cachedMessages': <String>['message'],
      'cachedPeople': <String>['person'],
      'appsList': <String>['app'],
      'modifiedConversationDetails': 'conversation-detail',
      'cachedSingleLanguageMode': true,
      'cachedTranscriptionVocabulary': <String>['private phrase'],
      'userPrimaryLanguage': 'en',
      'hasSetPrimaryLanguage': true,
      'hasSpeakerProfile': true,
      'selectedChatAppId2': 'old-app',
      'lastUsedSummarizationAppId': 'old-summary-app',
      'preferredSummarizationAppId': 'old-preferred-app',
      'calendarEnabled': true,
      'pendingMemories': <String>[jsonEncode(pendingMemory.toJson())],
      'goals_tracker_local_goals': '[{"id":"old-goal"}]',
      'btDevice': 'preserve-device',
      'onboardingCompleted': true,
      'offlineRecordingMarker': 'preserve-recording',
    });
    await SharedPreferencesUtil.init();
    final gateway = _FakeTokenGateway();
    final service = _service(gateway);
    final events = <AuthSessionExpiredEvent>[];
    service.sessionExpiredEvents.listen(events.add);

    const event = AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.backendRejectedRefreshedToken);
    await Future.wait([service.expireSession(event), service.expireSession(event)]);

    final raw = await SharedPreferences.getInstance();
    expect(gateway.signOutCalls, 1);
    expect(events, hasLength(1));
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(SharedPreferencesUtil().email, isEmpty);
    expect(SharedPreferencesUtil().givenName, isEmpty);
    expect(SharedPreferencesUtil().familyName, isEmpty);
    expect(raw.getStringList('cachedConversations'), isEmpty);
    expect(raw.containsKey('cachedMemories'), isFalse);
    expect(raw.getStringList('cachedMessages'), isEmpty);
    expect(raw.getStringList('cachedPeople'), isEmpty);
    expect(raw.getStringList('appsList'), isEmpty);
    expect(raw.getString('modifiedConversationDetails'), isEmpty);
    expect(SharedPreferencesUtil().cachedSingleLanguageMode, isFalse);
    expect(SharedPreferencesUtil().cachedTranscriptionVocabulary, isEmpty);
    expect(SharedPreferencesUtil().userPrimaryLanguage, isEmpty);
    expect(SharedPreferencesUtil().hasSetPrimaryLanguage, isFalse);
    expect(SharedPreferencesUtil().hasSpeakerProfile, isFalse);
    expect(SharedPreferencesUtil().selectedChatAppId, 'no_selected');
    expect(SharedPreferencesUtil().lastUsedSummarizationAppId, isEmpty);
    expect(SharedPreferencesUtil().preferredSummarizationAppId, isEmpty);
    expect(SharedPreferencesUtil().calendarEnabled, isFalse);
    expect(raw.getString('btDevice'), 'preserve-device');
    expect(raw.getBool('onboardingCompleted'), isTrue);
    expect(raw.getString('offlineRecordingMarker'), 'preserve-recording');
    expect(raw.containsKey('pendingMemories'), isFalse);
    expect(raw.getStringList('pendingMemories:user-1'), hasLength(1));
    expect(raw.containsKey('goals_tracker_local_goals'), isFalse);
    expect(raw.getString('goals_tracker_local_goals:user-1'), '[{"id":"old-goal"}]');
    expect(SharedPreferencesUtil().pendingMemories, isEmpty);
    SharedPreferencesUtil().uid = 'new-user';
    expect(SharedPreferencesUtil().pendingMemories, isEmpty);
    SharedPreferencesUtil().uid = 'user-1';
    expect(SharedPreferencesUtil().pendingMemories.single.id, 'pending-1');
  });
}

AuthService _service(
  _FakeTokenGateway gateway, {
  AuthRefreshDelay? refreshDelay,
  AuthTelemetryRecorder? recordTelemetry,
}) =>
    AuthService.forTesting(
      tokenGateway: gateway,
      refreshDelay: refreshDelay ?? (_) async {},
      recordTelemetry: recordTelemetry,
      telemetryContextProvider: () => const {
        'platform': 'ios',
        'app_version': '1.2.3+456',
        'release_channel': 'testflight',
      },
    );

final class _FakeTokenGateway implements AuthTokenGateway {
  _FakeTokenGateway({
    this.user = const AuthUserSnapshot(uid: 'user-1', email: 'person@example.com', displayName: 'Person Example'),
    this.results = const [],
    this.error,
    this.refreshCompleter,
  });

  AuthUserSnapshot? user;
  final List<RefreshedAuthToken?> results;
  final Object? error;
  Completer<RefreshedAuthToken?>? refreshCompleter;
  int refreshCalls = 0;
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    refreshCalls++;
    if (error != null) throw error!;
    final pendingRefresh = refreshCompleter;
    if (pendingRefresh != null) return pendingRefresh.future;
    if (results.isEmpty) {
      return RefreshedAuthToken(token: 'default-token', expirationTime: DateTime.now());
    }
    final index = refreshCalls <= results.length ? refreshCalls - 1 : results.length - 1;
    return results[index];
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

final class _TelemetryEvent {
  const _TelemetryEvent(this.name, this.properties);

  final String name;
  final Map<String, dynamic> properties;
}
