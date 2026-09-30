import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:device_info_plus_platform_interface/device_info_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/recording_analytics.dart';

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

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

  void mockBleHostApiError(String method) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    mockedChannels.add(channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      channel,
      (ByteData? message) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>['native_error', 'boom', null]),
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
    _CannedUpload.status = 500;
    _CannedUpload.body = '{}';
    _CannedUpload.requests = 0;
    // The upload URL is never dialed: the canned client answers every request.
    Env.overrideApiBaseUrl('http://diagnostics-support.test/');
    // Construct the pooled client under the canned overrides so its IOClient
    // answers from [_CannedUpload] instead of a real socket.
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _CannedHttpOverrides());
    PlatformManager.initializeForLocalHarness();
    AuthService.installLocalHarnessTokenGateway(_SyntheticGateway());
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

  Future<void> pumpPage(WidgetTester tester) async {
    final provider = DeviceProvider();
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: const DeviceDiagnostics(deviceId: 'AA:BB:CC:DD:EE:FF'),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> openSupportDialog(WidgetTester tester) async {
    await tester.tap(find.byTooltip('Send to support'));
    await tester.pumpAndSettle();
  }

  testWidgets('cancelling the review dialog tracks dialog_cancelled', (tester) async {
    await pumpPage(tester);
    await openSupportDialog(tester);
    expect(find.textContaining('"schema_version"'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);

    analytics.expectSingle('Diagnostics Send Failed', {
      'failure_stage': 'dialog_cancelled',
      'status_code': 0,
      'schema_version': 2,
      'disconnect_count': 1,
    });
    expect(analytics.propertiesOf('Diagnostics Send Failed').single['bundle_bytes'] as int, greaterThan(0));
    expect(analytics.names, isNot(contains('Diagnostics Sent')));
    expect(_CannedUpload.requests, 0);
  });

  testWidgets('a non-201 upload response tracks upload with the status code', (tester) async {
    _CannedUpload.status = 503;
    await pumpPage(tester);
    await openSupportDialog(tester);

    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);

    // The pooled client retries server errors once; both attempts hit the wire.
    expect(_CannedUpload.requests, greaterThan(0));
    analytics.expectSingle('Diagnostics Send Failed', {
      'failure_stage': 'upload',
      'status_code': 503,
      'schema_version': 2,
      'disconnect_count': 1,
    });
    expect(analytics.propertiesOf('Diagnostics Send Failed').single['bundle_bytes'] as int, greaterThan(0));
  });

  testWidgets('a 201 response with an unparseable body tracks ticket_parse', (tester) async {
    _CannedUpload.status = 201;
    _CannedUpload.body = '{"unexpected": true}';
    await pumpPage(tester);
    await openSupportDialog(tester);

    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);

    analytics.expectSingle('Diagnostics Send Failed', {
      'failure_stage': 'ticket_parse',
      'status_code': 201,
      'schema_version': 2,
      'disconnect_count': 1,
    });
  });

  testWidgets('a successful send tracks Diagnostics Sent and shows the ticket', (tester) async {
    _CannedUpload.status = 201;
    _CannedUpload.body = '{"ticket": "OMI-TKT-42"}';
    await pumpPage(tester);
    await openSupportDialog(tester);

    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);

    expect(find.text('OMI-TKT-42'), findsOneWidget);
    analytics.expectSingle('Diagnostics Sent', {
      'schema_version': 2,
      'disconnect_count': 1,
    });
    expect(analytics.propertiesOf('Diagnostics Sent').single['bundle_bytes'] as int, greaterThan(0));
    expect(analytics.names, isNot(contains('Diagnostics Send Failed')));
  });

  testWidgets('a bundle build failure tracks build_bundle without bundle metrics', (tester) async {
    await pumpPage(tester);
    mockBleHostApiError('getDeviceDiagnostics');
    await openSupportDialog(tester);

    // The review dialog never opens when the bundle cannot be built.
    expect(find.textContaining('"schema_version"'), findsNothing);
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);

    analytics.expectSingle('Diagnostics Send Failed', {
      'failure_stage': 'build_bundle',
      'status_code': 0,
      'bundle_bytes': 0,
      'disconnect_count': 0,
      'schema_version': 0,
    });
    expect(_CannedUpload.requests, 0);
  });
}
