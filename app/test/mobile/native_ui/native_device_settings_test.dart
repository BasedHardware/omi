import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:device_info_plus_platform_interface/device_info_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../../support/recording_analytics.dart';
import 'native_test_host.dart';

// Device Settings.

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({required this.device, this.connected = true});

  final BtDevice device;
  bool connected;
  bool paired = true;

  @override
  bool get isConnected => connected;
  @override
  BtDevice? get connectedDevice => connected ? device : null;
  @override
  BtDevice? get pairedDevice => paired ? device : null;
  @override
  int get batteryLevel => 0;
  @override
  bool get isCharging => false;
  @override
  bool get havingNewFirmware => false;
  @override
  String get latestStableFirmwareVersion => '';
  @override
  Future<void> getDeviceInfo() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// An Omi with LED dimming and mic gain that records every write.
class _FakeOmiConnection implements DeviceConnection {
  final dimWrites = <int>[];
  final gainWrites = <int>[];

  @override
  Future<int> getFeatures() async => OmiFeatures.ledDimming | OmiFeatures.micGain;
  @override
  Future<int?> getLedDimRatio() async => 50;
  @override
  Future<int?> getMicGain() async => 5;
  @override
  Future<void> setLedDimRatio(int ratio) async => dimWrites.add(ratio);
  @override
  Future<void> setMicGain(int gain) async => gainWrites.add(gain);
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeRayBanConnection implements RayBanMetaDeviceConnection {
  @override
  Future<int> getFeatures() async => 0;
  @override
  Future<String> getCameraPermissionStatus() async => 'granted';
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _omi = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
final _rayBan = BtDevice(id: 'rayban-1', name: 'Ray-Ban Meta', type: DeviceType.raybanMeta, rssi: -40);

Future<void> _pumpSettings(WidgetTester tester, _StubDeviceProvider provider, DeviceConnection connection) async {
  await tester.pumpWidget(ChangeNotifierProvider<DeviceProvider>.value(
    value: provider,
    child: NativeTestHost.app(DeviceSettings(connectionForTest: (_) async => connection)),
  ));
  await NativeTestHost.settle(tester);
}

/// The rows the mounted Device Settings surface projects, by id.
Map<String, NativeRow> _rows(WidgetTester tester) => {
      for (final row in IosNativeSurface.debugDispatchRows(tester.state(find.byType(IosNativeSurface)))) row.id: row,
    };

/// Sends a native command without awaiting the owner, which may wait on later frames.
void _send(NativeTestHost host, String id, Object? value) =>
    unawaited(host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value})));

// Diagnostics: canned platform and HTTP answers, as in device_diagnostics_send_support_test.dart.

class _NoConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

class _TestDeviceInfoPlatform extends DeviceInfoPlatform {
  @override
  Future<BaseDeviceInfo> deviceInfo() async => BaseDeviceInfo(const {
        'model': 'Pixel Test',
        'version': {'sdkInt': 34, 'release': '14', 'incremental': 'test', 'codename': 'REL'},
        'board': 'test',
        'bootloader': 'test',
        'brand': 'test',
        'device': 'test',
        'display': 'test',
        'fingerprint': 'test',
        'hardware': 'test',
        'host': 'test',
        'id': 'test',
        'manufacturer': 'test',
        'product': 'test',
        'tags': 'test',
        'type': 'test',
        'isPhysicalDevice': true,
        'isLowRamDevice': false,
        'freeDiskSize': 1,
        'totalDiskSize': 1,
        'physicalRamSize': 1,
        'availableRamSize': 1,
        'serialNumber': 'test',
      });
}

/// Scripted replies for the support-upload HTTP call. The canned client
/// completes entirely in microtasks, so it works inside the widget-test fake
/// async zone where real sockets cannot be awaited.
class _CannedUpload {
  static int status = 500;
  static String body = '{}';
  static int requests = 0;
}

class _CannedHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _CannedHttpClient();
}

class _CannedHttpClient implements HttpClient {
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async => _CannedRequest();

  // Set by HttpPoolManager's constructor.
  @override
  int? maxConnectionsPerHost = 15;

  @override
  Duration idleTimeout = const Duration(seconds: 15);

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned client does not implement ${invocation.memberName}');
}

class _CannedRequest implements HttpClientRequest {
  @override
  HttpHeaders get headers => _CannedHttpHeaders();

  @override
  bool followRedirects = false;

  @override
  int maxRedirects = 5;

  @override
  bool persistentConnection = true;

  @override
  int contentLength = -1;

  @override
  Future<void> addStream(Stream<List<int>> stream) async {
    await stream.drain<void>();
    _CannedUpload.requests++;
  }

  @override
  Future<HttpClientResponse> close() async => _CannedResponse(_CannedUpload.status, _CannedUpload.body);

  @override
  Future<HttpClientResponse> get done => close();

  @override
  void abort([Object? error, StackTrace? stackTrace]) {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned request does not implement ${invocation.memberName}');
}

class _CannedResponse extends Stream<List<int>> implements HttpClientResponse {
  _CannedResponse(this.statusCode, this.body);

  @override
  final int statusCode;

  final String body;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> data)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([utf8.encode(body)])
        .listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }

  @override
  HttpHeaders get headers => _CannedHttpHeaders();

  @override
  String get reasonPhrase => '';

  @override
  bool get isRedirect => false;

  @override
  List<RedirectInfo> get redirects => const [];

  @override
  bool get persistentConnection => true;

  @override
  int get contentLength => utf8.encode(body).length;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned response does not implement ${invocation.memberName}');
}

class _CannedHttpHeaders implements HttpHeaders {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Signed-in synthetic principal so authenticated uploads leave the app with a
/// bearer token instead of failing Firebase user lookup on the test host.
class _SyntheticGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'diag-test-user', email: 'diag@local.test');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => RefreshedAuthToken(
        token: 'synthetic-bearer',
        expirationTime: DateTime.now().toUtc().add(const Duration(hours: 1)),
      );

  @override
  Future<void> signOut() async {}
}

BleDeviceDiagnostics _diagnostics(int reconnectionCount) {
  final now = DateTime.now().millisecondsSinceEpoch;
  return BleDeviceDiagnostics(
    disconnectHistory: [
      BleDisconnectEvent(
        timestamp: now - 1000,
        reason: 'connection_timeout',
        reasonCode: 8,
        isManual: false,
        eventType: 'disconnect',
        lastRssi: -80,
        connectionDurationMs: 60000,
        appState: 'background',
        timeToReconnectMs: 5000,
        rssiTrend: 'sudden',
      ),
    ],
    reconnectionCount: reconnectionCount,
    connectedAt: now - 60000,
    failToConnectCount: 0,
    nativeBackgroundBytesConsumed: 0,
    nativeBackgroundPacketsConsumed: 0,
  );
}

String _extendedDiagnostics() {
  final now = DateTime.now().millisecondsSinceEpoch;
  return jsonEncode({
    'counters_since': now - 86400 * 1000,
    'disconnect_history_v2': [
      {
        'timestamp': now - 1000,
        'reason': 'connection_timeout',
        'reasonCode': 8,
        'isManual': false,
        'eventType': 'disconnect',
        'lastRssi': -80,
        'lastRssiAgeMs': 400,
        'connectionDurationMs': 60000,
        'appState': 'background',
        'timeToReconnectMs': 5000,
        'rssiTrend': 'sudden',
      },
    ],
  });
}

const _config = MethodChannel('com.omi.native_ui/config');

/// Answers every native presentation with the next reply in [replies].
List<MethodCall> _presenter(List<Map<String, Object?>> replies) {
  final calls = <MethodCall>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    calls.add(call);
    return call.method == 'present' ? replies.removeAt(0) : null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return calls;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Device Settings', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({'doubleTapAction': 1});
      await SharedPreferencesUtil.init();
    });

    testWidgets('a paired Ray-Ban Meta stays native with its camera readiness', (tester) async {
      NativeTestHost.install();
      final provider = _StubDeviceProvider(device: _rayBan);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, _FakeRayBanConnection());

      // The camera row used to be a FutureBuilder, which kept the whole page classic.
      expect(find.byType(UiKitView), findsOneWidget);
      final camera = _rows(tester).values.singleWhere((row) => row.title == 'Camera');
      expect(camera.subtitle, 'Image capture ready');
      expect(camera.valid, isTrue);
    });

    testWidgets('a burst of LED changes writes the final value once, after the debounce', (tester) async {
      final host = NativeTestHost.install();
      final connection = _FakeOmiConnection();
      final provider = _StubDeviceProvider(device: _omi);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, connection);

      final led = _rows(tester)['device_led']!;
      expect((led.kind, led.value, led.maximumValue, led.step, led.subtitle), ('level', 50.0, 100.0, 1.0, '50%'));
      for (final value in [20.0, 35.0, 64.0]) {
        _send(host, 'device_led', value);
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(connection.dimWrites, isEmpty);
      expect(_rows(tester)['device_led']!.subtitle, '64%');

      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(seconds: 1));
      expect(connection.dimWrites, [64]);
    });

    testWidgets('leaving the page writes a pending level at once', (tester) async {
      final host = NativeTestHost.install();
      final connection = _FakeOmiConnection();
      final provider = _StubDeviceProvider(device: _omi);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, connection);

      _send(host, 'device_mic_gain', 7.0);
      await tester.pump();
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(connection.gainWrites, [7]);
    });

    testWidgets('a pending level is dropped once its device is no longer paired', (tester) async {
      final host = NativeTestHost.install();
      final connection = _FakeOmiConnection();
      final provider = _StubDeviceProvider(device: _omi);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, connection);

      _send(host, 'device_led', 10.0);
      await tester.pump();
      // Forget Device clears the pairing, then leaves the page before the debounce ends.
      provider.paired = false;
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 1));
      expect(connection.dimWrites, isEmpty);
    });

    testWidgets('the double-tap choice persists options and rejects anything else', (tester) async {
      final host = NativeTestHost.install();
      final provider = _StubDeviceProvider(device: _omi);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, _FakeOmiConnection());

      final choice = _rows(tester)['device_double_tap']!;
      expect((choice.kind, choice.value), ('choice', '1'));
      expect(choice.options.keys, ['0', '1', '2']);
      expect(choice.accepts('3'), isFalse);
      expect(choice.accepts(2), isFalse);

      _send(host, 'device_double_tap', '3');
      await tester.pump();
      expect(SharedPreferencesUtil().doubleTapAction, 1);

      _send(host, 'device_double_tap', '2');
      await tester.pump();
      expect(SharedPreferencesUtil().doubleTapAction, 2);
      expect(_rows(tester)['device_double_tap']!.value, '2');
    });

    testWidgets('mic gain presets write Quiet 2, Normal 4 and High 6', (tester) async {
      final host = NativeTestHost.install();
      final connection = _FakeOmiConnection();
      final provider = _StubDeviceProvider(device: _omi);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, connection);

      final gain = _rows(tester)['device_mic_gain']!;
      expect((gain.kind, gain.value, gain.maximumValue), ('level', 5.0, 8.0));
      for (final preset in ['device_mic_gain_quiet', 'device_mic_gain_normal', 'device_mic_gain_high']) {
        _send(host, preset, null);
        await tester.pump();
      }
      expect(connection.gainWrites, [2, 4, 6]);

      // A preset replaces a drag that is still waiting to be written.
      _send(host, 'device_mic_gain', 7.0);
      await tester.pump();
      _send(host, 'device_mic_gain_quiet', null);
      await tester.pump(const Duration(seconds: 1));
      expect(connection.gainWrites, [2, 4, 6, 2]);
      expect(_rows(tester)['device_mic_gain_quiet']!.symbol, 'checkmark');
      expect(_rows(tester)['device_mic_gain_high']!.symbol, isNull);
    });

    testWidgets('the disconnected explanation appears only while disconnected', (tester) async {
      NativeTestHost.install();
      final provider = _StubDeviceProvider(device: _omi, connected: false);
      addTearDown(provider.dispose);
      await _pumpSettings(tester, provider, _FakeOmiConnection());

      final disconnected = _rows(tester)['device_disconnected'];
      expect(disconnected?.title, 'Device Not Connected');
      expect(disconnected?.kind, 'label');

      provider
        ..connected = true
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(_rows(tester).containsKey('device_disconnected'), isFalse);
    });
  });

  group('Device diagnostics send to support', () {
    final mockedChannels = <String>{};
    late RecordingAnalytics analytics;

    void mockBleHostApi(String method, Object? reply) {
      final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
      mockedChannels.add(channel);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
        channel,
        (ByteData? message) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[reply]),
      );
    }

    setUpAll(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      ConnectivityPlatform.instance = _NoConnectivityPlatform();
      DeviceInfoPlatform.instance = _TestDeviceInfoPlatform();
      PackageInfo.setMockInitialValues(
          appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
      try {
        await ServiceManager.init();
      } catch (_) {
        // Ignore if already initialized by another test.
      }
    });

    setUp(() async {
      SharedPreferences.setMockInitialValues({
        'authToken': 'synthetic-bearer',
        'tokenExpirationTime': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
      });
      await SharedPreferencesUtil.init();
      mockBleHostApi('getDeviceDiagnostics', _diagnostics(3));
      mockBleHostApi('getExtendedDeviceDiagnostics', _extendedDiagnostics());
      mockBleHostApi('getBatteryHistory', <Object?>[]);
      mockBleHostApi('startRssiStreaming', null);
      mockBleHostApi('stopRssiStreaming', null);
      _CannedUpload.status = 201;
      _CannedUpload.body = '{"ticket": "OMI-TKT-42"}';
      _CannedUpload.requests = 0;
      Env.overrideApiBaseUrl('http://diagnostics-support.test/');
      HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _CannedHttpOverrides());
      PlatformManager.initializeForLocalHarness();
      analytics = RecordingAnalytics();
      AnalyticsManager.configure(analytics.adapter);
      await AnalyticsManager.init();
    });

    tearDown(() async {
      Env.clearApiBaseUrlOverrideForTesting();
      for (final channel in mockedChannels) {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(channel, null);
      }
      mockedChannels.clear();
      AnalyticsManager.resetForTesting();
    });

    /// Mounts the native diagnostics page and asks it to send to support.
    Future<void> sendToSupport(WidgetTester tester) async {
      final host = NativeTestHost.install();
      // The upload authenticates as a synthetic principal; settle its session before mounting.
      final previous = AuthService.installLocalHarnessTokenGateway(_SyntheticGateway());
      addTearDown(() => AuthService.installLocalHarnessTokenGateway(previous));
      AuthService.instance.captureSessionSnapshot();
      final provider = DeviceProvider();
      addTearDown(provider.dispose);
      await tester.pumpWidget(ChangeNotifierProvider.value(
        value: provider,
        child: NativeTestHost.app(const DeviceDiagnostics(deviceId: 'AA:BB:CC:DD:EE:FF')),
      ));
      for (var frame = 0; frame < 10; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(find.byType(UiKitView), findsOneWidget);
      _send(host, 'diagnostics_support', null);
      for (var frame = 0; frame < 20; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
    }

    testWidgets('Send uploads once and shows the ticket natively', (tester) async {
      final presented = _presenter([
        {'action': 'send', 'values': <String, Object?>{}, 'reason': 'action'},
        {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'},
      ]);
      await sendToSupport(tester);
      await AnalyticsManager.flushPending(force: true);

      expect(_CannedUpload.requests, 1);
      final review = presented.first.arguments as Map;
      expect(review['alert'], isFalse);
      final rows = ((review['snapshot'] as Map)['sections'] as List).single['rows'] as List;
      expect(rows.map((row) => row['kind']), ['label', 'rich_text']);
      final code = (rows.last['blocks'] as List).single as Map;
      expect(code['kind'], 'code');
      expect(jsonDecode(code['text'] as String), containsPair('schema_version', 2));
      final ticket = presented.last.arguments as Map;
      expect(ticket['cancelId'], 'ok');
      expect((((ticket['snapshot'] as Map)['sections'] as List).single['rows'] as List).single['title'], 'OMI-TKT-42');
      analytics.expectSingle('Diagnostics Sent', {'schema_version': 2, 'disconnect_count': 1});
      expect(find.byType(OmiAlertDialog), findsNothing);
    });

    testWidgets('Cancel in the native review records dialog_cancelled and uploads nothing', (tester) async {
      _presenter([
        {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'},
      ]);
      await sendToSupport(tester);
      await AnalyticsManager.flushPending(force: true);

      expect(_CannedUpload.requests, 0);
      analytics.expectSingle('Diagnostics Send Failed', {
        'failure_stage': 'dialog_cancelled',
        'status_code': 0,
        'schema_version': 2,
        'disconnect_count': 1,
      });
      expect(find.byType(OmiAlertDialog), findsNothing);
    });

    testWidgets('an oversized bundle keeps the Flutter review dialog', (tester) async {
      final presented = _presenter([]);
      mockBleHostApi(
          'getExtendedDeviceDiagnostics',
          jsonEncode({
            'ble_log': [for (var line = 0; line < 3000; line++) 'x' * 100],
          }));
      await sendToSupport(tester);

      expect(presented.where((call) => call.method == 'present'), isEmpty);
      expect(find.byType(OmiAlertDialog), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      for (var frame = 0; frame < 10; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(_CannedUpload.requests, 0);
    });
  });
}
