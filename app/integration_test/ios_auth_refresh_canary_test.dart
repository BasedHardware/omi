import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/main.dart' as app;
import 'package:omi/services/auth_service.dart';

/// Signed-iOS auth canary for release candidates.
///
/// Preconditions: install the release candidate on an iPhone, sign in and
/// complete onboarding once, then force-quit the app so Firebase must restore
/// the persisted session on this run.
///
/// Run with `flutter test integration_test/ios_auth_refresh_canary_test.dart
/// --flavor prod -d <physical-ios-device>` using the normal signed iOS setup.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('persisted session refreshes and authorizes conversations', (
    tester,
  ) async {
    expect(
      Platform.isIOS,
      isTrue,
      reason: 'This release canary must run on signed iOS',
    );

    app.main();
    for (var i = 0; i < 100; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(
      AuthService.instance.isSignedIn(),
      isTrue,
      reason: 'The persisted Firebase session was not restored',
    );

    final token = await AuthService.instance.getIdToken();
    expect(token, isNotNull, reason: 'Forced Firebase ID-token refresh failed');
    expect(
      token,
      isNotEmpty,
      reason: 'Forced Firebase ID-token refresh returned an empty token',
    );

    final conversations = await getConversationsResult(
      limit: 1,
      includeDiscarded: false,
    );
    expect(
      conversations.ok,
      isTrue,
      reason: 'The refreshed session could not access /v1/conversations',
    );
  });
}
