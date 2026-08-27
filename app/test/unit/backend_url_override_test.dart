import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/backend_url_override.dart';
import 'package:omi/env/env.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  group('BackendUrlOverride', () {
    test('normalizes HTTPS endpoints with a trailing slash', () {
      expect(BackendUrlOverride.parse(' https://omi.example.test/api ').url, 'https://omi.example.test/api/');
    });

    test('allows cleartext only for local, private, and CGNAT hosts', () {
      for (final url in [
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        'http://10.0.0.8:8000',
        'http://172.31.0.8:8000',
        'http://192.168.1.8:8000',
        'http://100.64.0.8:8000',
      ]) {
        expect(BackendUrlOverride.parse(url).url, endsWith('/'), reason: url);
      }
    });

    test('rejects public cleartext, credentials, fragments, and unsupported schemes', () {
      for (final url in [
        'http://8.8.8.8:8000',
        'http://user:pass@127.0.0.1:8000',
        'https://example.test/#secret',
        'ftp://127.0.0.1/files',
      ]) {
        expect(() => BackendUrlOverride.parse(url), throwsFormatException, reason: url);
      }
    });
  });

  test('persisted override restores at startup and clearing it removes the override', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().customBackendUrl = 'https://omi.example.test/api/';
    await SharedPreferencesUtil.reload();

    BackendUrlOverride.restore(SharedPreferencesUtil().customBackendUrl);
    expect(Env.apiBaseUrl, 'https://omi.example.test/api/');

    BackendUrlOverride.restore('');
    expect(Env.hasApiBaseUrlOverride, isFalse);
  });

  test('an invalid persisted override cannot break startup', () {
    expect(BackendUrlOverride.restore('http://public.example.test'), isFalse);
    expect(Env.hasApiBaseUrlOverride, isFalse);
  });

  test('release-mode restoration fails closed to the flavor backend', () {
    expect(
      BackendUrlOverride.restore('https://omi.example.test/api/', runtimeAllowed: false),
      isFalse,
    );
    expect(Env.hasApiBaseUrlOverride, isFalse);
  });

  group('backend auth isolation', () {
    test('Omi credentials remain attached to official API hosts', () {
      expect(shouldAttachOmiCredentials('https://api.omi.me/v1/users/me'), isTrue);
      expect(shouldAttachOmiCredentials('wss://api.omi.me/v4/listen'), isTrue);
      expect(shouldAttachOmiCredentials('https://api.omiapi.com/v1/users/me'), isTrue);
    });

    test('custom backends never receive Omi credentials', () {
      expect(shouldAttachOmiCredentials('https://self-hosted.example.test/v1/users/me'), isFalse);
      expect(shouldAttachOmiCredentials('ws://100.64.0.8:8000/v4/listen'), isFalse);
      expect(shouldAttachOmiCredentials('https://api.omi.me.attacker.example/v1/users/me'), isFalse);
    });

    test('unconditional legacy callers are still isolated under an override', () {
      expect(shouldHonorRequestedOmiAuth(requested: false, customBackendActive: true), isFalse);
      expect(shouldHonorRequestedOmiAuth(requested: true, customBackendActive: true), isFalse);
      expect(
        shouldHonorRequestedOmiAuth(
          requested: true,
          customBackendActive: true,
          url: 'https://self-hosted.example.test/v1/users/me',
        ),
        isFalse,
      );
      expect(
        shouldHonorRequestedOmiAuth(
          requested: true,
          customBackendActive: true,
          url: 'https://api.omi.me/v1/agents',
        ),
        isTrue,
      );
    });
  });
}
