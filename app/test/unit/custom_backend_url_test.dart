import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/custom_backend_url_dialog.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    Env.clearApiBaseUrlOverrideForTesting();
  });

  tearDown(() {
    Env.clearApiBaseUrlOverrideForTesting();
  });

  group('Custom Backend URL preferences', () {
    test('defaults to empty string', () {
      expect(SharedPreferencesUtil().customBackendUrl, '');
      expect(Env.isApiBaseUrlOverridden, isFalse);
    });

    test('persists and trims custom URL', () {
      final prefs = SharedPreferencesUtil();
      prefs.customBackendUrl = '   https://selfhosted.example.com:8000   ';
      expect(prefs.customBackendUrl, 'https://selfhosted.example.com:8000');
    });

    test('setting empty string clears preference', () {
      final prefs = SharedPreferencesUtil();
      prefs.customBackendUrl = 'https://selfhosted.example.com:8000';
      expect(prefs.customBackendUrl, 'https://selfhosted.example.com:8000');
      prefs.customBackendUrl = '';
      expect(prefs.customBackendUrl, '');
    });
  });

  group('Env.overrideApiBaseUrl normalization', () {
    test('normalizes URL without trailing slash', () {
      Env.overrideApiBaseUrl('http://192.168.1.50:8000');
      expect(Env.apiBaseUrl, 'http://192.168.1.50:8000/');
      expect(Env.isApiBaseUrlOverridden, isTrue);
    });

    test('preserves URL with trailing slash', () {
      Env.overrideApiBaseUrl('https://my-backend.domain.org/');
      expect(Env.apiBaseUrl, 'https://my-backend.domain.org/');
      expect(Env.isApiBaseUrlOverridden, isTrue);
    });

    test('trims surrounding whitespace', () {
      Env.overrideApiBaseUrl('   https://my-backend.domain.org   ');
      expect(Env.apiBaseUrl, 'https://my-backend.domain.org/');
    });

    test('null or empty clears override', () {
      Env.overrideApiBaseUrl('https://my-backend.domain.org/');
      expect(Env.isApiBaseUrlOverridden, isTrue);
      Env.overrideApiBaseUrl('');
      expect(Env.isApiBaseUrlOverridden, isFalse);
      expect(Env.apiBaseUrl, Env.defaultApiBaseUrl);

      Env.overrideApiBaseUrl('https://my-backend.domain.org/');
      Env.overrideApiBaseUrl(null);
      expect(Env.isApiBaseUrlOverridden, isFalse);
    });

    test('resetApiBaseUrlOverride clears override', () {
      Env.overrideApiBaseUrl('https://my-backend.domain.org/');
      expect(Env.isApiBaseUrlOverridden, isTrue);
      Env.resetApiBaseUrlOverride();
      expect(Env.isApiBaseUrlOverridden, isFalse);
      expect(Env.apiBaseUrl, Env.defaultApiBaseUrl);
    });
  });

  group('CustomBackendUrlDialog widget', () {
    Widget buildTestWidget() {
      return const MaterialApp(
        home: Scaffold(
          body: CustomBackendUrlDialog(),
        ),
      );
    }

    testWidgets('renders dialog elements and default URL', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Custom Backend URL'), findsOneWidget);
      expect(find.text('Default Backend:'), findsOneWidget);
      expect(find.text(Env.defaultApiBaseUrl), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('Save'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
      // Reset button is only visible when custom is active
      expect(find.text('Reset'), findsNothing);
    });

    testWidgets('rejects invalid URL format', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'not_a_valid_url');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(find.text('Please enter a valid HTTP or HTTPS URL'), findsOneWidget);
      expect(Env.isApiBaseUrlOverridden, isFalse);
      expect(SharedPreferencesUtil().customBackendUrl, '');
    });

    testWidgets('saves valid URL and updates preferences and Env', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'http://192.168.1.100:8000');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(SharedPreferencesUtil().customBackendUrl, 'http://192.168.1.100:8000/');
      expect(Env.apiBaseUrl, 'http://192.168.1.100:8000/');
      expect(Env.isApiBaseUrlOverridden, isTrue);
    });

    testWidgets('shows reset button when custom URL is set and resets on tap', (tester) async {
      SharedPreferencesUtil().customBackendUrl = 'https://custom.backend.org/';
      Env.overrideApiBaseUrl('https://custom.backend.org/');

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Reset'), findsOneWidget);
      await tester.tap(find.text('Reset'));
      await tester.pumpAndSettle();

      expect(SharedPreferencesUtil().customBackendUrl, '');
      expect(Env.isApiBaseUrlOverridden, isFalse);
      expect(Env.apiBaseUrl, Env.defaultApiBaseUrl);
    });
  });
}
