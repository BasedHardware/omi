import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Regression test for #24723: the app draft generates, the icon request fails, and the generator
// used to drop back to the prompt screen with no message. A failed icon is a failed generation
// the person must hear about.

final class _TestEnvFields implements EnvFields {
  const _TestEnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get posthogApiKey => null;
  @override
  bool? get useAuthCustomToken => false;
  @override
  bool? get useWebAuth => false;
}

/// A valid 1x1 PNG, so a successful icon response decodes like a real one.
const _onePixelPng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

/// Answers the generator's requests in memory: prompts and the draft succeed; each icon request
/// takes the next status from [iconStatuses] (500 once the script runs out).
class _GeneratorHttpOverrides extends HttpOverrides {
  _GeneratorHttpOverrides(this.requests, this.iconStatuses);

  final List<String> requests;
  final List<int> iconStatuses;

  @override
  HttpClient createHttpClient(SecurityContext? context) => _GeneratorHttpClient(requests, iconStatuses);
}

class _GeneratorHttpClient implements HttpClient {
  _GeneratorHttpClient(this.requests, this.iconStatuses);

  final List<String> requests;
  final List<int> iconStatuses;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    requests.add(url.path);
    return _GeneratorRequest(url.path, iconStatuses);
  }

  @override
  int? maxConnectionsPerHost;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  Duration? connectionTimeout;
  @override
  void close({bool force = false}) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _GeneratorRequest implements HttpClientRequest {
  _GeneratorRequest(this.path, this.iconStatuses);

  final String path;
  final List<int> iconStatuses;

  @override
  HttpHeaders get headers => _Headers();
  @override
  bool followRedirects = false;
  @override
  int maxRedirects = 5;
  @override
  bool persistentConnection = true;
  @override
  int contentLength = -1;
  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();

  @override
  Future<HttpClientResponse> close() async {
    switch (path) {
      case '/v1/app/generate-prompts':
        return _Response(HttpStatus.ok, jsonEncode({'prompts': <String>[]}));
      case '/v1/app/generate':
        return _Response(
          HttpStatus.ok,
          jsonEncode({
            'status': 'ok',
            'app': {
              'name': 'Gratitude Spinner',
              'description': 'Spins up one thing to be grateful for each morning.',
              'category': 'productivity',
              'capabilities': ['chat'],
              'chat_prompt': 'Suggest one thing to be grateful for.',
            },
          }),
        );
      case '/v1/app/generate-icon':
        final status = iconStatuses.isEmpty ? HttpStatus.internalServerError : iconStatuses.removeAt(0);
        if (status == HttpStatus.ok) {
          return _Response(
            HttpStatus.ok,
            jsonEncode({'icon_base64': _onePixelPng, 'mime_type': 'image/png', 'status': 'ok'}),
          );
        }
        return _Response(status, jsonEncode({'detail': 'icon generation unavailable'}));
    }
    return _Response(HttpStatus.notFound, '{}');
  }

  @override
  Future<HttpClientResponse> get done => close();
  @override
  void abort([Object? error, StackTrace? stackTrace]) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Response extends Stream<List<int>> implements HttpClientResponse {
  _Response(this.statusCode, String body) : _body = utf8.encode(body);

  @override
  final int statusCode;
  final List<int> _body;

  @override
  int get contentLength => _body.length;
  @override
  HttpHeaders get headers => _Headers();
  @override
  String get reasonPhrase => statusCode == HttpStatus.ok ? 'OK' : 'Error';
  @override
  bool get isRedirect => false;
  @override
  List<RedirectInfo> get redirects => const [];
  @override
  bool get persistentConnection => true;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) =>
      Stream.value(_body).listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Headers implements HttpHeaders {
  @override
  void forEach(void Function(String, List<String>) action) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Widget _harness(Widget child) {
  return ChangeNotifierProvider<AppProvider>.value(
    value: AppProvider(),
    child: MaterialApp(
      // The provider reads its error copy through the global navigator key.
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: child,
    ),
  );
}

void main() {
  final requests = <String>[];
  final iconStatuses = <int>[];
  final en = lookupAppLocalizations(const Locale('en'));

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    Env.init(const _TestEnvFields());
    // All requests are answered in memory above, without credentials or sockets.
    Env.overrideApiBaseUrl('http://generator.test/');
    PlatformManager.initializeForLocalHarness();
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _GeneratorHttpOverrides(requests, iconStatuses));
  });

  setUp(() {
    requests.clear();
    iconStatuses.clear();
  });

  tearDownAll(Env.clearApiBaseUrlOverride);

  testWidgets('a failed icon request reports the failed generation instead of silently returning to the prompt',
      (tester) async {
    iconStatuses.add(HttpStatus.internalServerError);
    await tester.pumpWidget(_harness(const AiAppGeneratorPage()));
    await tester.pump();

    await tester.enterText(find.byType(TextField), 'A playful gratitude spinner for daily positivity');
    await tester.pump();
    await tester.tap(find.byTooltip(en.send));

    // The generator paces its steps with short delays before and after each request.
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }

    expect(requests, containsAll(['/v1/app/generate', '/v1/app/generate-icon']),
        reason: 'the draft must succeed so the icon request is the only failure');
    expect(find.text(en.aiGenFailedToGenerateApp), findsOneWidget);
    expect(find.text(en.createApp), findsNothing, reason: 'no preview without an icon');
    expect(find.byType(TextField), findsOneWidget, reason: 'the prompt stays on screen for a retry');
  });

  testWidgets('a failed icon regeneration says so and keeps the generated app on screen', (tester) async {
    iconStatuses.addAll([HttpStatus.ok, HttpStatus.internalServerError]);
    await tester.pumpWidget(_harness(const AiAppGeneratorPage()));
    await tester.pump();

    await tester.enterText(find.byType(TextField), 'A playful gratitude spinner for daily positivity');
    await tester.pump();
    await tester.tap(find.byTooltip(en.send));
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.text(en.createApp), findsOneWidget, reason: 'the first icon succeeded, so the preview is up');

    await tester.tap(find.byTooltip(en.aiGenRegenerateIcon));
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }

    // The shared client retries a failed call once, so the redo shows up as two icon requests.
    expect(requests.where((path) => path == '/v1/app/generate-icon').length, greaterThanOrEqualTo(2),
        reason: 'the redo asked for a new icon and that request is the one that failed');
    expect(find.text(en.aiGenFailedToRegenerateIcon), findsOneWidget, reason: 'the failed redo is said out loud');
    expect(find.text(en.createApp), findsOneWidget, reason: 'the generated app and its previous icon stay');
    expect(find.byTooltip(en.aiGenRegenerateIcon), findsOneWidget, reason: 'and the redo can be tried again');

    // Let the error toast time out so no timer outlives the test.
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
  });
}
