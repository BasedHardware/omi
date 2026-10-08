import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/env/env.dart';
import 'package:omi/mobile/native_ui/ios_native_secret.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
import 'package:omi/pages/settings/developer_api_keys_page.dart';
import 'package:omi/pages/settings/developer_mcp_page.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/services/auth_service.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Native developer credentials on Simulator: app owner keys, Developer API keys and MCP keys against
/// a loopback keys backend, with the one-time reveal on the real sensitive surface.
///
/// flutter drive --driver integration_test/native_ui_host_driver.dart \
///   --target integration_test/native_credentials_host_test.dart --flavor dev \
///   --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('app owner keys: list, one-time reveal and confirmed revoke', (tester) async {
      final backend = await _boot();
      await tester.pumpWidget(nativeHostApp(const ApiKeysWidget(appId: 'app-host', page: true),
          providers: [ChangeNotifierProvider<AddAppProvider>(create: (_) => AddAppProvider())]));
      await checkNativeHost(tester, 'native-developer-app-credentials-app-keys-dark');
      expect(backend.count('GET', '/v1/apps/app-host/keys'), 1);
      expect(nativeProjectedRow(tester, 'app_keys_create').enabled, true);

      final created = backend.next('app');
      unawaited(Future.sync(() => nativeProjectedRow(tester, 'app_keys_create').action!(null)));
      await _until(tester, () => find.byType(NativeSecretPage).evaluate().isNotEmpty);
      expect(backend.count('POST', '/v1/apps/app-host/keys'), 1);
      await _expectRevealedOnce(tester, created, 'app-keys');
      await _done(tester, created);
      await _until(tester, () => _rowIds(tester).contains('app_api_key:0'));
      expect(backend.count('GET', '/v1/apps/app-host/keys'), 2, reason: 'Creating reloads the list');

      await _revoke(tester, backend, 'app_api_key:0', 'DELETE', '/v1/apps/app-host/keys/${backend.lastId('app')}');
      await _until(tester, () => backend.count('GET', '/v1/apps/app-host/keys') == 3);
      AuthService.instance.handleAuthUserChanged('another-owner');
      await _until(tester, () => find.byType(UiKitView).evaluate().isEmpty);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('Developer API keys: native create, reveal and revoke', (tester) async {
      final backend = await _boot();
      await tester.pumpWidget(nativeHostApp(const DeveloperApiKeysPage()));
      await checkNativeHost(tester, 'native-developer-app-credentials-developer-api-dark');
      expect(backend.count('GET', '/v1/dev/keys'), 1);

      unawaited(Future.sync(() => nativeProjectedRow(tester, 'dev_keys_create').action!(null)));
      await _until(tester, () => _rowIds(tester).contains('dev_key_create'));
      expect(nativeProjectedRow(tester, 'dev_key_create').enabled, false);
      await nativeProjectedRow(tester, 'dev_key_name').action!('Host CLI');
      await nativeProjectedRow(tester, 'dev_key_scope:memories:read').action!(true);
      await tester.pump();
      final created = backend.next('dev');
      await nativeProjectedRow(tester, 'dev_key_create').action!(null);
      await _until(tester, () => find.byType(NativeSecretPage).evaluate().isNotEmpty);
      expect(backend.count('POST', '/v1/dev/keys'), 1);
      expect(backend.lastBody, {
        'name': 'Host CLI',
        'scopes': ['memories:read']
      });
      await _expectRevealedOnce(tester, created, 'developer-api');
      await _done(tester, created);

      await _until(tester, () => _rowIds(tester).contains('dev_key:0'));
      await _revoke(tester, backend, 'dev_key:0', 'DELETE', '/v1/dev/keys/${backend.lastId('dev')}');
    });

    testWidgets('MCP keys: native create, reveal, revoke, and sign-out clears the projection', (tester) async {
      final backend = await _boot();
      await tester.pumpWidget(nativeHostApp(const DeveloperMcpPage()));
      await tester.element(find.byType(DeveloperMcpPage)).read<McpProvider>().fetchKeys();
      await checkNativeHost(tester, 'native-developer-app-credentials-mcp-dark');
      expect(backend.count('GET', '/v1/mcp/keys'), 1);

      final created = backend.next('mcp');
      final presentations = _answerPresentations((_) => {
            'action': 'create',
            'values': {'mcp_key_name': 'Host Claude'},
            'reason': 'action'
          });
      unawaited(Future.sync(() => nativeProjectedRow(tester, 'mcp_create').action!(null)));
      await _until(tester, () => find.byType(NativeSecretPage).evaluate().isNotEmpty);
      expect(presentations, containsAllInOrder(['present', 'presentActivity', 'dismissPresentation']));
      expect(backend.count('POST', '/v1/mcp/keys'), 1);
      expect(backend.lastBody, {'name': 'Host Claude'});
      await _expectRevealedOnce(tester, created, 'mcp');
      await _done(tester, created);

      await _until(tester, () => _rowIds(tester).contains('mcp_key:0'));
      await _revoke(tester, backend, 'mcp_key:0', 'DELETE', '/v1/mcp/keys/${backend.lastId('mcp')}');

      AuthService.instance.handleAuthUserChanged('another-owner');
      await _until(tester, () => find.byType(UiKitView).evaluate().isEmpty);
      expect(tester.takeException(), isNull);
    });
  });
}

/// Signs in the hermetic fixture owner and points the app at the shared keys backend.
Future<_KeysBackend> _boot() async {
  await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
  final backend = await _KeysBackend.shared()
    ..reset();
  Env.overrideApiBaseUrl(backend.baseUrl);
  AuthService.instance.captureSessionSnapshot();
  addTearDown(JourneyHermeticBoot.stop);
  return backend;
}

/// Pumps real frames until [condition] holds (platform views and HTTP finish outside fake time).
Future<void> _until(WidgetTester tester, bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (!condition() && DateTime.now().isBefore(deadline)) {
    await Future<void>.delayed(const Duration(milliseconds: 100));
    await tester.pump();
  }
  expect(condition(), true);
}

/// Every row the mounted surfaces dispatch, across routes.
List<NativeRow> _rows(WidgetTester tester) => [
      for (final surface
          in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface, skipOffstage: false)))
        ...IosNativeSurface.debugDispatchRows(surface),
    ];

List<String> _rowIds(WidgetTester tester) => _rows(tester).map((row) => row.id).toList();

/// The key crosses only as the single sensitive row's value; every list projection omits it.
Future<void> _expectRevealedOnce(WidgetTester tester, String secret, String screen) async {
  await _until(tester, () => _rowIds(tester).contains('secret_value'));
  final carrying = _rows(tester).where((row) => jsonEncode(row.projection).contains(secret)).toList();
  expect(carrying.map((row) => (row.id, row.kind, row.value)), [('secret_value', 'secret', secret)]);
  final sheet =
      tester.widgetList<IosNativeSurface>(find.byType(IosNativeSurface)).where((surface) => surface.sensitive);
  expect(sheet, hasLength(1));
  expect(await captureNativeHostScreenshot('native-developer-app-credentials-$screen-secret-dark'), isNotEmpty);
}

/// Done disposes the sheet, so no mounted projection holds the key any longer.
Future<void> _done(WidgetTester tester, String secret) async {
  await nativeProjectedRow(tester, 'secret_done').action!(null);
  await _until(tester, () => find.byType(NativeSecretPage).evaluate().isEmpty);
  expect(_rows(tester).where((row) => jsonEncode(row.projection).contains(secret)), isEmpty);
  await _until(tester, () => find.byType(UiKitView).evaluate().length == 1);
}

/// A declined confirmation sends nothing; a confirmed one sends exactly one DELETE.
Future<void> _revoke(WidgetTester tester, _KeysBackend backend, String row, String method, String path) async {
  var answer = 'cancel';
  final presentations = _answerPresentations((_) =>
      {'action': answer, 'values': const <String, Object?>{}, 'reason': answer == 'cancel' ? 'cancel' : 'action'});
  await nativeProjectedRow(tester, row).action!('revoke');
  await tester.pump(const Duration(seconds: 1));
  expect(presentations.where((method) => method == 'present'), hasLength(1));
  expect(backend.count(method, path), 0);
  answer = 'confirm';
  await nativeProjectedRow(tester, row).action!('revoke');
  await _until(tester, () => backend.count(method, path) == 1);
  await tester.pump(const Duration(seconds: 1));
  expect(backend.count(method, path), 1);
}

/// Answers the config channel in Dart for the rest of the test, so a confirmation or name prompt
/// needs no tap: [answer] replies to 'present', an activity ends when it is dismissed, and every
/// surface keeps its real UIKit view. Records each method.
List<String> _answerPresentations(Map<String, Object?> Function(MethodCall call) answer) {
  final methods = <String>[];
  final activities = <Completer<Object?>>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const config = MethodChannel('com.omi.native_ui/config');
  messenger.setMockMethodCallHandler(config, (call) async {
    methods.add(call.method);
    switch (call.method) {
      case 'isSupported':
        return true;
      case 'present':
        return answer(call);
      case 'presentActivity':
        final activity = Completer<Object?>();
        activities.add(activity);
        return activity.future;
      case 'dismissPresentation':
        for (final activity in activities) {
          if (!activity.isCompleted) activity.complete({'reason': 'programmatic'});
        }
    }
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(config, null));
  return methods;
}

/// Loopback stand-in for the three key routes, counting every request. One server serves the whole
/// suite, because the developer and MCP API clients resolve their base URL once per process.
class _KeysBackend {
  _KeysBackend._(this._server);

  static Future<_KeysBackend>? _instance;
  static Future<_KeysBackend> shared() => _instance ??= () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        return _KeysBackend._(server).._listen();
      }();

  final HttpServer _server;
  final _counts = <String, int>{};
  final _keys = <String, List<Map<String, Object?>>>{};
  final _lastIds = <String, String>{};
  final _secrets = <String, String>{};
  Object? lastBody;
  var _serial = 0;

  String get baseUrl => 'http://127.0.0.1:${_server.port}/';

  int count(String method, String path) => _counts['$method $path'] ?? 0;

  String lastId(String kind) => _lastIds[kind]!;

  /// The secret the next create of [kind] ('app', 'dev' or 'mcp') returns.
  String next(String kind) => _secrets[kind] = 'omi_${kind}_host_${++_serial}_0123456789abcdef';

  void reset() {
    _counts.clear();
    _keys.clear();
    _lastIds.clear();
    lastBody = null;
  }

  void _listen() => _server.listen((request) async {
        final method = request.method.toUpperCase();
        final path = request.uri.path;
        _counts['$method $path'] = (_counts['$method $path'] ?? 0) + 1;
        final body = await utf8.decoder.bind(request).join();
        final segments = request.uri.pathSegments;
        final (kind, collection, keyId) = switch (segments) {
          ['v1', 'apps', final app, 'keys'] => ('app', app, null),
          ['v1', 'apps', final app, 'keys', final key] => ('app', app, key),
          ['v1', 'dev' || 'mcp', 'keys'] => (segments[1], segments[1], null),
          ['v1', 'dev' || 'mcp', 'keys', final key] => (segments[1], segments[1], key),
          _ => ('', '', null),
        };
        final keys = _keys.putIfAbsent(collection, () => []);
        var status = 200;
        Object? reply;
        if (kind.isEmpty) {
          status = 404;
          reply = {'detail': 'not found'};
        } else if (method == 'GET' && keyId == null) {
          reply = keys;
        } else if (method == 'POST' && keyId == null) {
          lastBody = body.isEmpty ? null : jsonDecode(body);
          final id = '$kind-key-${++_serial}';
          final created = DateTime.utc(2026, 9, 23, 10, 43).toIso8601String();
          final secret = _secrets[kind] ?? next(kind);
          final record = kind == 'app'
              ? {'id': id, 'label': 'sk_…${id.substring(id.length - 2)}', 'created_at': created}
              : {
                  'id': id,
                  'name': (lastBody as Map?)?['name'] ?? '',
                  'key_prefix': secret.substring(0, 8),
                  'created_at': created,
                  'scopes': (lastBody as Map?)?['scopes'],
                };
          keys.insert(0, record);
          _lastIds[kind] = id;
          reply = {...record, kind == 'app' ? 'secret' : 'key': secret};
        } else if (method == 'DELETE' && keyId != null) {
          keys.removeWhere((key) => key['id'] == keyId);
          status = kind == 'app' ? 200 : 204;
          reply = kind == 'app' ? {'status': 'ok'} : null;
        } else {
          status = 405;
          reply = {'detail': 'method not allowed'};
        }
        request.response.statusCode = status;
        if (reply != null) {
          request.response.headers.contentType = ContentType.json;
          request.response.write(jsonEncode(reply));
        }
        await request.response.close();
      });
}
