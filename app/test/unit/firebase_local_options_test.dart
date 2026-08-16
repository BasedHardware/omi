import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/firebase_options_local.dart';

// Firebase's native SDKs format-validate these fields at Firebase.initializeApp()
// time, before any network call and before Auth is routed to the local emulator —
// so a syntactically invalid placeholder crashes the app on launch even though the
// values are never used to reach a real backend. Measured directly from the iOS
// crash text: "API Key length must be 39 characters, API Key must start with `A`"
// and an EXC_BREAKPOINT inside native Firebase config validation for a malformed
// GOOGLE_APP_ID. These regexes pin the constraints that broke, so a future edit
// can't reintroduce a human-readable placeholder like "omi-dev-local" in either
// field.
final _apiKeyPattern = RegExp(r'^A.{38}$');
final _appIdPattern = RegExp(r'^\d+:\d+:(ios|android|web):[0-9a-fA-F]+$');

void main() {
  group('firebase_options_local placeholders are format-valid', () {
    for (final entry in {
      'android': DefaultFirebaseOptions.android,
      'ios': DefaultFirebaseOptions.ios,
      'macos': DefaultFirebaseOptions.macos,
      'web': DefaultFirebaseOptions.web,
    }.entries) {
      test('${entry.key} apiKey and appId are format-valid', () {
        final options = entry.value;
        expect(options.apiKey, matches(_apiKeyPattern), reason: 'apiKey for ${entry.key}');
        expect(options.appId, matches(_appIdPattern), reason: 'appId for ${entry.key}');
      });
    }
  });

  group('setup/prebuilt Firebase config sources stay in sync', () {
    test('GoogleService-Info-Local.plist API_KEY and GOOGLE_APP_ID are format-valid', () {
      final plist = File('setup/prebuilt/GoogleService-Info-Local.plist').readAsStringSync();
      final apiKey = RegExp(r'<key>API_KEY</key>\s*<string>([^<]+)</string>').firstMatch(plist)!.group(1)!;
      final appId = RegExp(r'<key>GOOGLE_APP_ID</key>\s*<string>([^<]+)</string>').firstMatch(plist)!.group(1)!;
      expect(apiKey, matches(_apiKeyPattern));
      expect(appId, matches(_appIdPattern));
    });

    test('google-services-local.json api_key and mobilesdk_app_id are format-valid', () {
      final json = jsonDecode(File('setup/prebuilt/google-services-local.json').readAsStringSync());
      final client = json['client'][0];
      final apiKey = client['api_key'][0]['current_key'] as String;
      final appId = client['client_info']['mobilesdk_app_id'] as String;
      expect(apiKey, matches(_apiKeyPattern));
      expect(appId, matches(_appIdPattern));
    });
  });
}
