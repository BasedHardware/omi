import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_secret.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/developer_api_keys_page.dart';
import 'package:omi/pages/settings/developer_mcp_page.dart';
import 'package:omi/pages/settings/widgets/create_dev_api_key_sheet.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_created_dialog.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/mcp_config.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
const _appSecret = 'omi_app_secret_0123456789';
const _devSecret = 'omi_dev_secret_0123456789';
const _mcpSecret = 'omi_mcp_secret_0123456789';
const _baseUrl = 'https://api.omi.test/';
final _createdAt = DateTime(2026, 9, 23, 10, 43);

TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

/// Answers the config channel (presentations, activities, toasts) and records every call.
List<MethodCall> _mockConfig({Future<Object?> Function(MethodCall call)? present}) {
  final calls = <MethodCall>[];
  final activities = <Completer<Object?>>[];
  _messenger.setMockMethodCallHandler(_config, (call) async {
    calls.add(call);
    switch (call.method) {
      case 'present':
        return present?.call(call);
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
  addTearDown(() => _messenger.setMockMethodCallHandler(_config, null));
  return calls;
}

Map<String, Object?> _choose(String action, [Map<String, Object?> values = const {}]) =>
    {'action': action, 'values': values, 'reason': 'action'};

const Map<String, Object?> _cancelled = {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'};

/// Records clipboard writes.
List<String> _mockClipboard() {
  final copied = <String>[];
  OmiClipboard.debugSystemConfirmsCopy = true;
  _messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
    return null;
  });
  addTearDown(() {
    OmiClipboard.debugSystemConfirmsCopy = null;
    _messenger.setMockMethodCallHandler(SystemChannels.platform, null);
  });
  return copied;
}

/// The row [id] as the topmost mounted surface dispatches it.
NativeRow _row(WidgetTester tester, String id) =>
    IosNativeSurface.debugDispatchRows(tester.state(find.byType(IosNativeSurface).last))
        .singleWhere((row) => row.id == id);

List<NativeRow> _sectionRows(WidgetTester tester) =>
    tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last).sections.expand((s) => s.rows).toList();

/// Every snapshot the host received, the creation parameters included.
List<Map> _snapshots(WidgetTester tester, NativeTestHost host) => [
      for (final view in tester.widgetList<UiKitView>(find.byType(UiKitView))) view.creationParams as Map,
      for (final call in host.calls)
        if (call.$2.method == 'update') call.$2.arguments as Map,
    ];

Object? _decode(ByteData? reply) => const StandardMethodCodec().decodeEnvelope(reply!);

class _AppKeysOwner extends AddAppProvider {
  _AppKeysOwner(this.served);

  final Map<String, List<AppApiKey>> served;
  Completer<void>? loadGate;
  Completer<AppApiKey>? createGate;
  Completer<void>? deleteGate;
  final loads = <String>[];
  final deleted = <String>[];
  var creates = 0;

  /// Like the real provider, a failed load keeps whatever list it held.
  var failLoads = false;

  @override
  Future<void> loadApiKeys(String appId) async {
    loads.add(appId);
    await loadGate?.future;
    if (failLoads) return;
    apiKeys = List.of(served[appId] ?? const []);
    notifyListeners();
  }

  @override
  Future<AppApiKey> createApiKey(String appId) async {
    creates++;
    final key = await createGate!.future;
    served[appId] = [...?served[appId], AppApiKey(id: key.id, label: key.label, createdAt: key.createdAt)];
    await loadApiKeys(appId);
    return key;
  }

  @override
  Future<void> deleteApiKey(String appId, String keyId) async {
    deleted.add(keyId);
    await deleteGate?.future;
    served[appId]?.removeWhere((key) => key.id == keyId);
    await loadApiKeys(appId);
  }
}

class _DevKeysOwner extends DevApiKeyProvider {
  _DevKeysOwner(this.served);

  List<DevApiKey> served;
  DevApiKeyCreated? next;
  Completer<void>? createGate;
  final created = <(String, List<String>?)>[];
  final deleted = <String>[];
  String? failure;
  var failDeletes = false;

  @override
  String? get error => failure;

  @override
  List<DevApiKey> get keys => served;

  @override
  Future<void> fetchKeys({bool force = false}) async => notifyListeners();

  @override
  Future<DevApiKeyCreated?> createKey(String name, {List<String>? scopes}) async {
    created.add((name, scopes));
    await createGate?.future;
    return next;
  }

  @override
  Future<void> deleteKey(String keyId) async {
    deleted.add(keyId);
    if (failDeletes) {
      failure = 'offline';
    } else {
      served = served.where((key) => key.id != keyId).toList();
    }
    notifyListeners();
  }
}

class _McpKeysOwner extends McpProvider {
  _McpKeysOwner(this.served);

  List<McpApiKey> served;
  McpApiKeyCreated? next;
  Completer<void>? createGate;
  final created = <String>[];

  @override
  List<McpApiKey> get keys => served;

  @override
  Future<void> fetchKeys() async => notifyListeners();

  @override
  Future<McpApiKeyCreated?> createKey(String name) async {
    created.add(name);
    await createGate?.future;
    return next;
  }
}

AppApiKey _appKey(String id, {String? secret}) =>
    AppApiKey(id: id, label: 'sk_…${id.substring(id.length - 2)}', createdAt: _createdAt, secret: secret);

DevApiKey _devKey(String id, {String prefix = 'omi_dev_ab', List<String>? scopes}) =>
    DevApiKey(createdAt: _createdAt, id: id, keyPrefix: prefix, name: 'Script', scopes: scopes);

Future<void> _pumpAppKeys(WidgetTester tester, _AppKeysOwner owner, {String appId = 'app-a'}) async {
  await tester.pumpWidget(NativeTestHost.app(
      ChangeNotifierProvider<AddAppProvider>.value(value: owner, child: ApiKeysWidget(appId: appId, page: true))));
  await NativeTestHost.settle(tester);
}

void main() {
  group('app owner keys', () {
    testWidgets('rows carry only labels and dates under index ids, never a secret', (tester) async {
      final host = NativeTestHost.install();
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-01', secret: _appSecret), _appKey('key-02')]
      });
      await _pumpAppKeys(tester, owner);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(_sectionRows(tester).map((row) => row.id), ['app_api_key:0', 'app_api_key:1']);
      final snapshots = _snapshots(tester, host);
      expect(snapshots, isNotEmpty);
      for (final snapshot in snapshots) {
        final json = jsonEncode(snapshot);
        expect(json, isNot(contains(_appSecret)));
        expect(json, isNot(contains('key-01')), reason: 'Backend ids stay in Dart');
      }
      expect(_row(tester, 'app_api_key:0').subtitle,
          OmiDateFormat.of(tester.element(find.byType(UiKitView))).dateTime(_createdAt));
    });

    testWidgets('the revoke menu accepts only revoke, and revokes after confirmation', (tester) async {
      final host = NativeTestHost.install();
      final presents = _mockConfig(present: (_) async => _choose('confirm'));
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-01'), _appKey('key-02')]
      });
      await _pumpAppKeys(tester, owner);
      final row = _row(tester, 'app_api_key:1');
      expect(row.accepts('revoke'), true);
      for (final forged in [null, 'delete', 'key-02', true]) {
        expect(row.accepts(forged), false, reason: '$forged');
      }
      final view = host.created.single;
      final refused =
          await host.sendFromNative(view, const MethodCall('action', {'id': 'app_api_key:1', 'value': 'delete'}));
      expect(() => _decode(refused), throwsA(isA<PlatformException>()));
      expect(owner.deleted, isEmpty);
      _decode(await host.sendFromNative(view, const MethodCall('action', {'id': 'app_api_key:1', 'value': 'revoke'})));
      await tester.pump();
      expect(presents.where((call) => call.method == 'present'), hasLength(1), reason: 'Revoking is confirmed first');
      expect(owner.deleted, ['key-02']);
    });

    testWidgets('a revoke in flight shows native progress until it finishes', (tester) async {
      final host = NativeTestHost.install();
      _mockConfig(present: (_) async => _choose('confirm'));
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-01')]
      })
        ..deleteGate = Completer<void>();
      await _pumpAppKeys(tester, owner);
      expect(tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).loading, false);
      _decode(await host.sendFromNative(
          host.created.single, const MethodCall('action', {'id': 'app_api_key:0', 'value': 'revoke'})));
      await tester.pump();
      expect(owner.deleted, ['key-01']);
      final busy = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(busy.loading, true);
      expect(busy.loadingLabel, 'Deleting…');
      expect(_row(tester, 'app_api_key:0').enabled, false);
      owner.deleteGate!.complete();
      await NativeTestHost.settle(tester);
      final idle = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(idle.loading, false);
      expect(idle.loadingLabel, isNull);
      expect(_sectionRows(tester), isEmpty);
    });

    testWidgets('a declined confirmation keeps the key', (tester) async {
      final host = NativeTestHost.install();
      _mockConfig(present: (_) async => _cancelled);
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-01')]
      });
      await _pumpAppKeys(tester, owner);
      _decode(await host.sendFromNative(
          host.created.single, const MethodCall('action', {'id': 'app_api_key:0', 'value': 'revoke'})));
      expect(owner.deleted, isEmpty);
    });

    testWidgets('keys are projected only after a load for this app completes', (tester) async {
      NativeTestHost.install();
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-0a')],
        'app-b': [_appKey('key-0b'), _appKey('key-1b')],
      })
        ..apiKeys = [_appKey('key-0b'), _appKey('key-1b')]
        ..loadGate = Completer<void>();
      await _pumpAppKeys(tester, owner);
      expect(owner.loads, ['app-a']);
      expect(_sectionRows(tester), isEmpty, reason: "Another app's keys are never shown while this app loads");
      expect(tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).loading, true);
      owner.loadGate!.complete();
      await NativeTestHost.settle(tester);
      expect(_sectionRows(tester).map((row) => row.title), ['sk_…0a']);
    });

    testWidgets("a failed load shows the error, never the previous app's keys", (tester) async {
      NativeTestHost.install();
      final owner = _AppKeysOwner({'app-a': []})
        ..apiKeys = [_appKey('key-0b')]
        ..failLoads = true;
      await _pumpAppKeys(tester, owner);
      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(_sectionRows(tester), isEmpty);
      expect(surface.failed, true);
      expect(surface.loading, false);
      owner.failLoads = false;
      await surface.onRefresh!(null);
      await NativeTestHost.settle(tester);
      expect(tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).failed, false);
    });

    testWidgets('keys loaded for a previous session are never projected', (tester) async {
      NativeTestHost.install();
      final owner = _AppKeysOwner({
        'app-a': [_appKey('key-0a')]
      })
        ..loadGate = Completer<void>();
      await _pumpAppKeys(tester, owner);
      AuthService.instance.handleAuthUserChanged('another-owner');
      owner.loadGate!.complete();
      await NativeTestHost.settle(tester);
      expect(_sectionRows(tester), isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a key created before a session change is never presented', (tester) async {
      final host = NativeTestHost.install();
      final owner = _AppKeysOwner({'app-a': []})..createGate = Completer<AppApiKey>();
      await _pumpAppKeys(tester, owner);
      unawaited(host.sendFromNative(host.created.single, const MethodCall('action', {'id': 'app_keys_create'})));
      await tester.pump();
      expect(owner.creates, 1);
      AuthService.instance.handleAuthUserChanged('another-owner');
      owner.createGate!.complete(_appKey('key-new', secret: _appSecret));
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.textContaining(_appSecret), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a created key is revealed once in the secret sheet and gone after Done', (tester) async {
      final host = NativeTestHost.install();
      final copied = _mockClipboard();
      final owner = _AppKeysOwner({'app-a': []})..createGate = Completer<AppApiKey>();
      await _pumpAppKeys(tester, owner);
      expect(_row(tester, 'app_keys_create').enabled, true);
      unawaited(host.sendFromNative(host.created.single, const MethodCall('action', {'id': 'app_keys_create'})));
      await tester.pump();
      expect(_row(tester, 'app_keys_create').enabled, false, reason: 'One create at a time');
      owner.createGate!.complete(_appKey('key-new', secret: _appSecret));
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsOneWidget);
      expect(find.text(_appSecret), findsOneWidget);
      await tester.tap(find.text('Copy to clipboard'));
      await tester.pump();
      expect(copied, [_appSecret]);
      for (final snapshot in _snapshots(tester, host)) {
        expect(jsonEncode(snapshot), isNot(contains(_appSecret)), reason: 'The list never carries the key');
      }
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text(_appSecret), findsNothing);
      expect(_sectionRows(tester).single.title, 'sk_…ew');
    });

    testWidgets('a key the secret row cannot carry keeps the classic dialog', (tester) async {
      final host = NativeTestHost.install();
      const unbridgeable = 'omi key with spaces';
      final owner = _AppKeysOwner({'app-a': []})..createGate = Completer<AppApiKey>();
      await _pumpAppKeys(tester, owner);
      unawaited(host.sendFromNative(host.created.single, const MethodCall('action', {'id': 'app_keys_create'})));
      await tester.pump();
      owner.createGate!.complete(_appKey('key-new', secret: unbridgeable));
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.descendant(of: find.byType(OmiAlertDialog), matching: find.text(unbridgeable)), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text(unbridgeable), findsNothing);
    });

    testWidgets('the info button opens the API keys explanation', (tester) async {
      NativeTestHost.install();
      final presents = _mockConfig(present: (_) async => _cancelled);
      await _pumpAppKeys(tester, _AppKeysOwner({'app-a': []}));
      await _row(tester, 'app_keys_info').action!(null);
      final snapshot = (presents.single.arguments as Map)['snapshot'] as Map;
      expect(snapshot['title'], 'Omi API Keys');
    });

    testWidgets('flag off keeps the complete Flutter page', (tester) async {
      await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider<AddAppProvider>.value(
          value: _AppKeysOwner({'app-a': []}), child: const ApiKeysWidget(appId: 'app-a', page: true))));
      await tester.pumpAndSettle();
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(find.byType(AppBar), findsOneWidget);
    });
  });

  group('developer API keys', () {
    testWidgets('rows show the prefix, date and scope summary under index ids', (tester) async {
      final host = NativeTestHost.install();
      final owner = _DevKeysOwner([
        _devKey('dev-1'),
        _devKey('dev-2', scopes: const ['memories:read', 'goals:write']),
      ]);
      await tester.pumpWidget(NativeTestHost.app(DeveloperApiKeysPage(provider: owner)));
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsOneWidget);
      final date = OmiDateFormat.of(tester.element(find.byType(UiKitView))).date(_createdAt);
      expect(_row(tester, 'dev_key:0').subtitle, 'omi_dev_ab*** · $date · Read Only');
      expect(_row(tester, 'dev_key:1').subtitle, 'omi_dev_ab*** · $date · Read, Write');
      expect(_row(tester, 'dev_key:1').options.keys, ['revoke']);
      for (final snapshot in _snapshots(tester, host)) {
        expect(jsonEncode(snapshot), isNot(contains('dev-1')));
      }
    });

    test('the scope summary is shared with the Flutter chips', () {
      final l10n = lookupAppLocalizations(const Locale('en'));
      expect(devKeyScopeSummary(l10n, null), ['Read Only']);
      expect(devKeyScopeSummary(l10n, const ['memories:read']), ['Read']);
      expect(
          devKeyScopeSummary(l10n, [
            for (final resource in devApiKeyScopeResources) ...['$resource:read', '$resource:write']
          ]),
          ['Full Access']);
    });

    testWidgets('a key whose metadata fails validation keeps the complete Flutter page', (tester) async {
      final host = NativeTestHost.install();
      for (final key in [
        _devKey('dev-1', prefix: 'omi dev'),
        _devKey(''),
        DevApiKey(createdAt: _createdAt, id: 'dev-1', keyPrefix: 'omi_dev_ab', name: 'n' * 1001),
      ]) {
        await tester
            .pumpWidget(NativeTestHost.app(DeveloperApiKeysPage(key: UniqueKey(), provider: _DevKeysOwner([key]))));
        await NativeTestHost.settle(tester);
        expect(find.byType(UiKitView), findsNothing);
        expect(find.byType(DeveloperApiKeysContent), findsOneWidget);
      }
      expect(host.created, isEmpty);
    });

    testWidgets('revoking asks first and then deletes through the owner', (tester) async {
      NativeTestHost.install();
      _mockConfig(present: (_) async => _choose('confirm'));
      final owner = _DevKeysOwner([_devKey('dev-1')]);
      await tester.pumpWidget(NativeTestHost.app(DeveloperApiKeysPage(provider: owner)));
      await NativeTestHost.settle(tester);
      await _row(tester, 'dev_key:0').action!('revoke');
      await tester.pump();
      expect(owner.deleted, ['dev-1']);
    });
  });

  testWidgets('a revoke the owner could not apply is reported, a declined one is not', (tester) async {
    NativeTestHost.install();
    var answer = _cancelled;
    _mockConfig(present: (_) async => answer);
    final owner = _DevKeysOwner([_devKey('dev-1')])
      ..failDeletes = true
      ..failure = 'stale';
    await tester.pumpWidget(NativeTestHost.app(DeveloperApiKeysPage(provider: owner)));
    await NativeTestHost.settle(tester);
    await _row(tester, 'dev_key:0').action!('revoke');
    await tester.pump();
    expect(find.textContaining('Failed to revoke API key'), findsNothing);
    answer = _choose('confirm');
    await _row(tester, 'dev_key:0').action!('revoke');
    await tester.pump();
    expect(owner.deleted, ['dev-1']);
    expect(find.text('Failed to revoke API key: offline'), findsOneWidget);
  });

  group('create developer key sheet', () {
    Future<Future<DevApiKeyCreated?>> open(WidgetTester tester, _DevKeysOwner owner) async {
      late Future<DevApiKeyCreated?> result;
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => result = Navigator.of(context).push<DevApiKeyCreated>(MaterialPageRoute(
                  builder: (_) => ChangeNotifierProvider<DevApiKeyProvider>.value(
                      value: owner, child: const Material(child: CreateDevApiKeySheet(native: true))))),
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(UiKitView), findsOneWidget, reason: 'The sheet is drawn natively, not by its fallback');
      return result;
    }

    testWidgets('scope toggles and presets change only the allowlisted scopes', (tester) async {
      final host = NativeTestHost.install();
      await open(tester, _DevKeysOwner([]));
      final toggles = _sectionRows(tester).where((row) => row.kind == 'toggle').map((row) => row.id);
      expect(toggles, [
        for (final resource in devApiKeyScopeResources) ...[
          'dev_key_scope:$resource:read',
          'dev_key_scope:$resource:write',
        ]
      ]);
      await _row(tester, 'dev_key_scope:memories:write').action!(true);
      await tester.pump();
      expect(_row(tester, 'dev_key_scope:memories:write').value, true);
      expect(_row(tester, 'dev_key_preset:read_only').symbol, 'circle');
      await _row(tester, 'dev_key_preset:read_only').action!(null);
      await tester.pump();
      expect(_row(tester, 'dev_key_preset:read_only').symbol, 'checkmark.circle.fill');
      expect(_row(tester, 'dev_key_scope:memories:write').value, false);
      expect(_row(tester, 'dev_key_scope:goals:read').value, true);
      await _row(tester, 'dev_key_preset:full_access').action!(null);
      await tester.pump();
      expect(_sectionRows(tester).where((row) => row.kind == 'toggle').every((row) => row.value == true), true);
      final view = host.created.last;
      final forged = await host.sendFromNative(
          view, const MethodCall('action', {'id': 'dev_key_scope:billing:write', 'value': true}));
      expect(() => _decode(forged), throwsA(isA<PlatformException>()));
    });

    testWidgets('Create needs a name and sends null scopes when none are selected', (tester) async {
      NativeTestHost.install();
      final owner = _DevKeysOwner([])
        ..next = DevApiKeyCreated(
            createdAt: _createdAt, id: 'dev-new', key: _devSecret, keyPrefix: 'omi_dev_ne', name: 'CLI');
      final result = await open(tester, owner);
      expect(_row(tester, 'dev_key_create').enabled, false);
      await _row(tester, 'dev_key_name').action!('   ');
      await tester.pump();
      expect(_row(tester, 'dev_key_create').enabled, false);
      expect(_row(tester, 'dev_key_name').maximumLength, 100);
      await _row(tester, 'dev_key_name').action!('  CLI ');
      await tester.pump();
      expect(_row(tester, 'dev_key_create').enabled, true);
      await _row(tester, 'dev_key_create').action!(null);
      await tester.pumpAndSettle();
      expect(owner.created, [('CLI', null)]);
      expect((await result)?.key, _devSecret, reason: 'The sheet closes with the key for the page to reveal');
      expect(find.text(_devSecret), findsNothing);
    });

    testWidgets('a key created before a session change closes the sheet without it', (tester) async {
      NativeTestHost.install();
      final owner = _DevKeysOwner([])
        ..createGate = Completer<void>()
        ..next = DevApiKeyCreated(
            createdAt: _createdAt, id: 'dev-new', key: _devSecret, keyPrefix: 'omi_dev_ne', name: 'CLI');
      final result = await open(tester, owner);
      await _row(tester, 'dev_key_name').action!('CLI');
      await tester.pump();
      unawaited(Future.sync(() => _row(tester, 'dev_key_create').action!(null)));
      await tester.pump();
      expect(owner.created, hasLength(1));
      final busy = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(busy.loading, true, reason: 'The native sheet shows progress while the key is created');
      expect(busy.loadingLabel, 'Creating…');
      AuthService.instance.handleAuthUserChanged('another-owner');
      owner.createGate!.complete();
      await tester.pumpAndSettle();
      expect(await result, isNull);
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.textContaining(_devSecret), findsNothing);
    });

    testWidgets('selected scopes are sent as the allowlisted list', (tester) async {
      NativeTestHost.install();
      final owner = _DevKeysOwner([])
        ..next = DevApiKeyCreated(
            createdAt: _createdAt, id: 'dev-new', key: _devSecret, keyPrefix: 'omi_dev_ne', name: 'Reader');
      await open(tester, owner);
      await _row(tester, 'dev_key_name').action!('Reader');
      await _row(tester, 'dev_key_scope:goals:read').action!(true);
      await tester.pump();
      await _row(tester, 'dev_key_create').action!(null);
      await tester.pumpAndSettle();
      expect(owner.created.single.$1, 'Reader');
      expect(owner.created.single.$2, ['goals:read']);
    });

    testWidgets('Cancel with edits asks before discarding', (tester) async {
      NativeTestHost.install();
      var answer = _cancelled;
      _mockConfig(present: (_) async => answer);
      await open(tester, _DevKeysOwner([]));
      await _row(tester, 'dev_key_name').action!('Draft');
      await tester.pump();
      await _row(tester, 'dev_key_cancel').action!(null);
      await tester.pumpAndSettle();
      expect(find.byType(CreateDevApiKeySheet), findsOneWidget);
      answer = _choose('confirm');
      await _row(tester, 'dev_key_cancel').action!(null);
      await tester.pumpAndSettle();
      expect(find.byType(CreateDevApiKeySheet), findsNothing);
    });
  });

  group('created developer key', () {
    Future<void> reveal(WidgetTester tester) async {
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => DevApiKeyCreatedSheet.show(
                  context,
                  DevApiKeyCreated(
                      createdAt: _createdAt, id: 'dev-new', key: _devSecret, keyPrefix: 'omi_dev_ne', name: 'CLI')),
              child: const Text('reveal')))));
      await tester.tap(find.text('reveal'));
      await tester.pumpAndSettle();
    }

    testWidgets('unsupported hosts keep the existing sheet', (tester) async {
      await reveal(tester);
      expect(find.byType(DevApiKeyCreatedSheet), findsOneWidget);
      expect(find.byType(NativeSecretPage), findsNothing);
    });

    testWidgets('the secret sheet shows the key exactly once and copies through OmiClipboard', (tester) async {
      NativeTestHost.install();
      final copied = _mockClipboard();
      await reveal(tester);
      expect(find.byType(NativeSecretPage), findsOneWidget);
      expect(find.byType(DevApiKeyCreatedSheet), findsNothing);
      expect(find.text(_devSecret), findsOneWidget);
      await tester.tap(find.text('Copy Key'));
      await tester.pump();
      expect(copied, [_devSecret]);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text(_devSecret), findsNothing);
    });
  });

  group('MCP', () {
    setUp(() => Env.overrideApiBaseUrl(_baseUrl));
    tearDown(Env.clearApiBaseUrlOverrideForTesting);

    Future<_McpKeysOwner> pumpMcp(WidgetTester tester, {List<McpApiKey> keys = const []}) async {
      final owner = _McpKeysOwner(keys);
      await tester.pumpWidget(
          NativeTestHost.app(ChangeNotifierProvider<McpProvider>.value(value: owner, child: const DeveloperMcpPage())));
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'The page is drawn natively, not by its fallback');
      return owner;
    }

    testWidgets('copy rows copy the exact config, URL and client ID', (tester) async {
      NativeTestHost.install();
      final copied = _mockClipboard();
      await pumpMcp(tester);
      final url = hostedMcpUrl(_baseUrl);
      final config = _row(tester, 'mcp_config_json');
      expect(config.kind, 'rich_text');
      expect(config.blocks, [
        {'kind': 'code', 'text': hostedMcpConfigJson(url), 'indent': 0, 'prefix': ''}
      ]);
      for (final id in ['mcp_copy_config', 'mcp_desktop_url', 'mcp_server_url', 'mcp_client_id']) {
        await _row(tester, id).action!(null);
        await tester.pump();
      }
      expect(copied, [hostedMcpConfigJson(url), url, url, kMcpOAuthClientId]);
      expect(_row(tester, 'mcp_auth_header').subtitle, 'Authorization: Bearer <key>');
    });

    testWidgets('key rows carry the name, masked prefix and date only', (tester) async {
      final host = NativeTestHost.install();
      await pumpMcp(tester,
          keys: [McpApiKey(createdAt: _createdAt, id: 'mcp-1', keyPrefix: 'omi_mcp_ab', name: 'Claude')]);
      final row = _row(tester, 'mcp_key:0');
      expect(row.title, 'Claude');
      expect(row.subtitle, startsWith('omi_mcp_ab*** · '));
      expect(row.options.keys, ['revoke']);
      for (final snapshot in _snapshots(tester, host)) {
        expect(jsonEncode(snapshot), isNot(contains('mcp-1')));
      }
    });

    testWidgets('a blank name is asked again with a hint and never reaches createKey', (tester) async {
      NativeTestHost.install();
      var presented = 0;
      final calls =
          _mockConfig(present: (_) async => presented++ == 0 ? _choose('create', {'mcp_key_name': '   '}) : _cancelled);
      final owner = await pumpMcp(tester);
      await _row(tester, 'mcp_create').action!(null);
      await tester.pumpAndSettle();
      final presents = calls.where((call) => call.method == 'present').toList();
      expect(presents, hasLength(2));
      List<Object?> ids(MethodCall call) => [
            for (final section in ((call.arguments as Map)['snapshot'] as Map)['sections'] as List)
              for (final row in (section as Map)['rows'] as List) (row as Map)['id']
          ];
      expect(ids(presents[0]), ['mcp_key_name']);
      expect(ids(presents[1]), ['mcp_key_name', 'mcp_key_name_required']);
      expect((presents[0].arguments as Map)['guardEdits'], true);
      expect(owner.created, isEmpty);
    });

    testWidgets('a second Create while the first is pending starts nothing', (tester) async {
      NativeTestHost.install();
      final answer = Completer<Object?>();
      final calls = _mockConfig(present: (_) => answer.future);
      await pumpMcp(tester);
      final create = _row(tester, 'mcp_create');
      unawaited(Future.sync(() => create.action!(null)));
      unawaited(Future.sync(() => create.action!(null)));
      await tester.pump();
      expect(_row(tester, 'mcp_create').enabled, false);
      expect(calls.where((call) => call.method == 'present'), hasLength(1));
      answer.complete(_cancelled);
      await tester.pumpAndSettle();
      expect(calls.where((call) => call.method == 'present'), hasLength(1));
      expect(_row(tester, 'mcp_create').enabled, true);
    });

    testWidgets('create shows an activity, dismisses it, then reveals the key once', (tester) async {
      NativeTestHost.install();
      final calls = _mockConfig(present: (_) async => _choose('create', {'mcp_key_name': ' Claude '}));
      final owner = await pumpMcp(tester)
        ..next = McpApiKeyCreated(
            createdAt: _createdAt, id: 'mcp-new', key: _mcpSecret, keyPrefix: 'omi_mcp_ne', name: 'Claude');
      unawaited(Future.sync(() => _row(tester, 'mcp_create').action!(null)));
      await tester.pumpAndSettle();
      expect(owner.created, ['Claude']);
      expect(
          calls.map((call) => call.method), containsAllInOrder(['present', 'presentActivity', 'dismissPresentation']));
      expect(find.byType(NativeSecretPage), findsOneWidget);
      expect(find.text(_mcpSecret), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text(_mcpSecret), findsNothing);
    });

    testWidgets('a session change during create presents nothing', (tester) async {
      NativeTestHost.install();
      _mockConfig(present: (_) async => _choose('create', {'mcp_key_name': 'Claude'}));
      final owner = await pumpMcp(tester)
        ..createGate = Completer<void>()
        ..next = McpApiKeyCreated(
            createdAt: _createdAt, id: 'mcp-new', key: _mcpSecret, keyPrefix: 'omi_mcp_ne', name: 'Claude');
      unawaited(Future.sync(() => _row(tester, 'mcp_create').action!(null)));
      await tester.pump();
      await tester.pump();
      expect(owner.created, ['Claude']);
      AuthService.instance.handleAuthUserChanged('another-owner');
      owner.createGate!.complete();
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.textContaining(_mcpSecret), findsNothing);
    });
  });

  group('debug log chooser', () {
    final files = [File('/logs/omi-1.log'), File('/logs/omi-2.log'), File('/logs/omi-3.log')];

    Future<BuildContext> caller(WidgetTester tester) async {
      await tester.pumpWidget(NativeTestHost.app(const SizedBox(key: ValueKey('caller'))));
      return tester.element(find.byKey(const ValueKey('caller')));
    }

    testWidgets('a chosen action maps to the file at its index', (tester) async {
      NativeTestHost.install();
      final calls = _mockConfig(present: (_) async => _choose('log_file_1'));
      final chosen = await chooseDebugLogFileNatively(await caller(tester), files);
      expect(chosen!.file, same(files[1]));
      final toolbar = ((calls.single.arguments as Map)['snapshot'] as Map)['toolbar'] as List;
      expect(toolbar.map((row) => (row as Map)['id']), ['cancel', 'log_file_0', 'log_file_1', 'log_file_2']);
      expect(toolbar.map((row) => (row as Map)['title']).skip(1), ['omi-1.log', 'omi-2.log', 'omi-3.log']);
    });

    testWidgets('a host that refuses the alert keeps the Flutter sheet', (tester) async {
      NativeTestHost.install();
      _mockConfig(present: (_) async => throw PlatformException(code: 'invalid_native_presentation'));
      expect(await chooseDebugLogFileNatively(await caller(tester), files), isNull);
    });

    testWidgets('cancel chooses nothing', (tester) async {
      NativeTestHost.install();
      _mockConfig(present: (_) async => _cancelled);
      final cancelled = await chooseDebugLogFileNatively(await caller(tester), files);
      expect(cancelled, isNotNull);
      expect(cancelled!.file, isNull);
    });

    testWidgets('flag off answers null so the existing sheet opens', (tester) async {
      expect(await chooseDebugLogFileNatively(await caller(tester), files), isNull);
    });
  });
}
