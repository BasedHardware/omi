import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

const _launcher = MethodChannel('plugins.flutter.io/url_launcher');
const _links = EventChannel('com.llfbandit.app_links/events');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() => Env.init(_BrowserEnvironment()));

  for (final provider in ['google', 'apple']) {
    test('$provider linking binds the browser return and exchanges only a provider credential', () async {
      Env.overrideApiBaseUrl('http://127.0.0.1:9471/');
      addTearDown(Env.clearApiBaseUrlOverrideForTesting);
      final launched = Completer<Uri>();
      final listening = Completer<MockStreamHandlerEventSink>();
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_launcher, (call) async {
        expect(call.method, 'launch');
        launched.complete(Uri.parse(call.arguments['url'] as String));
        return true;
      });
      messenger.setMockStreamHandler(_links, MockStreamHandler.inline(onListen: (_, events) {
        listening.complete(events);
      }));

      final user = _OwnerUser();
      final gateway = _OwnerGateway();
      final service = AuthService.forTesting(tokenGateway: gateway, firebaseAuth: _Firebase(user));
      final snapshot = service.captureSessionSnapshot(expectedUid: user.uid)!;
      final authorization = ProviderLinkAuthorization();
      addTearDown(authorization.dispose);
      final link = provider == 'apple' ? service.linkWithApple : service.linkWithGoogle;
      final exchanged = <http.Request>[];
      final pending = http.runWithClient(
        () => link(expectedOwnerUid: user.uid, authorization: authorization),
        () => MockClient((request) async {
          exchanged.add(request);
          return http.Response(jsonEncode({'provider': provider, 'id_token': 'fixture-$provider'}), 200);
        }),
      );
      final refused = expectLater(pending.timeout(const Duration(seconds: 5)), throwsA(isA<ProviderLinkConflict>()));

      final authorize = await launched.future.timeout(const Duration(seconds: 5));
      final events = await listening.future.timeout(const Duration(seconds: 5));
      expect(authorize.origin, 'http://127.0.0.1:9471');
      expect(authorize.path, '/v1/auth/authorize');
      final query = authorize.queryParameters;
      expect(query['provider'], provider);
      expect(query['redirect_uri'], Env.authRedirectUri);
      expect(query['code_challenge_method'], 'S256');
      expect(query['select_account'], provider == 'google' ? 'true' : null);

      Uri callback(String state, String code) =>
          Uri.parse(Env.authRedirectUri).replace(queryParameters: {'state': state, 'code': code});
      events.success(callback('unrelated-state', 'ignored-code').toString());
      await Future<void>.delayed(Duration.zero);
      expect(exchanged, isEmpty);
      expect(user.credentials, isEmpty);
      events.success(callback(query['state']!, 'fixture-code').toString());
      await refused;

      final exchange = exchanged.single;
      expect(exchange.method, 'POST');
      expect(exchange.url, Uri.parse('http://127.0.0.1:9471/v1/auth/token'));
      final form = exchange.bodyFields;
      expect(form['grant_type'], 'authorization_code');
      expect(form['code'], 'fixture-code');
      expect(form['redirect_uri'], query['redirect_uri']);
      expect(form['use_custom_token'], 'false');
      final boundChallenge = base64Url.encode(sha256.convert(utf8.encode(form['code_verifier']!)).bytes);
      expect(query['code_challenge'], boundChallenge.replaceAll('=', ''));
      final credential = user.credentials.single as OAuthCredential;
      expect(credential.providerId, '$provider.com');
      expect(credential.idToken, 'fixture-$provider');
      expect(gateway.signOutCalls, 0);
      expect(service.isSessionSnapshotCurrent(snapshot), isTrue);
    });
  }
}

class _BrowserEnvironment implements EnvFields {
  @override
  bool get useWebAuth => true;

  @override
  bool get useAuthCustomToken => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Firebase implements FirebaseAuth {
  _Firebase(this.currentUser);

  @override
  final User currentUser;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _OwnerUser implements User {
  final credentials = <AuthCredential>[];

  @override
  String get uid => 'owner';

  @override
  bool get isAnonymous => false;

  @override
  Future<UserCredential> linkWithCredential(AuthCredential credential) async {
    credentials.add(credential);
    throw FirebaseAuthException(code: 'credential-already-in-use');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _OwnerGateway implements AuthTokenGateway {
  int signOutCalls = 0;

  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: 'owner');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => throw StateError('An existing session should not refresh');

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}
