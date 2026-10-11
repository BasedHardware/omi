import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/providers/device_provider.dart';

class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

class _FakeHttpClient implements HttpClient {
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async => _FakeHttpRequest();

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeHttpRequest implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() async => _FakeHttpResponse();

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeHttpHeaders implements HttpHeaders {
  @override
  void add(String name, Object value, {bool preserveHeaderCase = false}) {}

  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeHttpResponse implements HttpClientResponse {
  @override
  int get statusCode => 200;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  int initiateConnectionCalls = 0;
  final List<String> callers = [];
  final List<bool> boundDeviceOnlyHistory = [];
  int resetFirmwareUpdateStateCalls = 0;
  bool onFirmwareUpdatePage = false;

  @override
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async {
    initiateConnectionCalls++;
    callers.add(caller);
    boundDeviceOnlyHistory.add(boundDeviceOnly);
  }

  @override
  void resetFirmwareUpdateState() {
    resetFirmwareUpdateStateCalls++;
  }

  @override
  void setOnFirmwareUpdatePage(bool value) {
    onFirmwareUpdatePage = value;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _wrap(DeviceProvider provider, Widget child) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: ChangeNotifierProvider<DeviceProvider>.value(
      value: provider,
      child: child,
    ),
  );
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
  });

  tearDown(() {
    HttpOverrides.global = null;
  });

  group('Omi Pendant FirmwareUpdate reconnect on Done (#20778)', () {
    testWidgets('tapping Done calls initiateConnection with boundDeviceOnly and resets state', (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-device-uuid',
        name: 'Omi Test',
        type: DeviceType.omi,
        modelNumber: 'CV1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, FirmwareUpdate(device: device)));
      await tester.pump();

      // Transition to installed state
      final dynamic state = tester.state(find.byType(FirmwareUpdate));
      state.isInstalled = true;
      state.isLoading = false;
      // Trigger rebuild into success section
      (state as State).setState(() {});
      await tester.pump();

      final doneFinder = find.byKey(const Key('firmware_update_done'));
      expect(doneFinder, findsOneWidget);

      await tester.tap(doneFinder);
      await tester.pump();

      expect(provider.resetFirmwareUpdateStateCalls, greaterThanOrEqualTo(1));
      expect(provider.initiateConnectionCalls, equals(1));
      expect(provider.callers.first, equals('FirmwareUpdateDone'));
      expect(provider.boundDeviceOnlyHistory.first, isTrue);

      // Tearing down the widget tree (dispose) must not duplicate the reconnect call.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(1));
    });

    testWidgets('disposing page after successful install triggers fallback reconnect if Done was not tapped',
        (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-device-uuid',
        name: 'Omi Test',
        type: DeviceType.omi,
        modelNumber: 'CV1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, FirmwareUpdate(device: device)));
      await tester.pump();

      final dynamic state = tester.state(find.byType(FirmwareUpdate));
      state.isInstalled = true;
      state.isLoading = false;
      (state as State).setState(() {});
      await tester.pump();

      // Simulate popping the route without tapping Done
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(1));
      expect(provider.callers.first, equals('FirmwareUpdateExit'));
      expect(provider.boundDeviceOnlyHistory.first, isTrue);
    });

    testWidgets('disposing page without successful install never triggers reconnect', (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-device-uuid',
        name: 'Omi Test',
        type: DeviceType.omi,
        modelNumber: 'CV1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, FirmwareUpdate(device: device)));
      await tester.pump();

      // Page is still in initial/loading/not installed state
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(0));
    });
  });

  group('OmiGlass OTA Update reconnect on Done (#20778)', () {
    testWidgets('tapping Done calls initiateConnection with boundDeviceOnly and resets state', (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-glass-uuid',
        name: 'OmiGlass Test',
        type: DeviceType.openglass,
        modelNumber: 'Glass1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, OmiGlassOtaUpdate(device: device)));
      await tester.pump();

      final dynamic state = tester.state(find.byType(OmiGlassOtaUpdate));
      state.isSuccess = true;
      state.isLoading = false;
      state.isUpdating = false;
      (state as State).setState(() {});
      await tester.pump();

      final doneFinder = find.widgetWithText(OmiButton, 'Done');
      expect(doneFinder, findsOneWidget);

      await tester.tap(doneFinder);
      await tester.pump();

      expect(provider.resetFirmwareUpdateStateCalls, greaterThanOrEqualTo(1));
      expect(provider.initiateConnectionCalls, equals(1));
      expect(provider.callers.first, equals('OmiGlassOtaDone'));
      expect(provider.boundDeviceOnlyHistory.first, isTrue);

      // Tearing down the widget tree must not duplicate the reconnect call.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(1));
    });

    testWidgets('disposing OmiGlass page after successful install triggers fallback reconnect if Done not tapped',
        (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-glass-uuid',
        name: 'OmiGlass Test',
        type: DeviceType.openglass,
        modelNumber: 'Glass1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, OmiGlassOtaUpdate(device: device)));
      await tester.pump();

      final dynamic state = tester.state(find.byType(OmiGlassOtaUpdate));
      state.isSuccess = true;
      state.isLoading = false;
      state.isUpdating = false;
      (state as State).setState(() {});
      await tester.pump();

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(1));
      expect(provider.callers.first, equals('OmiGlassOtaExit'));
      expect(provider.boundDeviceOnlyHistory.first, isTrue);
    });

    testWidgets('disposing OmiGlass page without successful install never triggers reconnect', (tester) async {
      final provider = _StubDeviceProvider();
      final device = BtDevice(
        id: 'test-glass-uuid',
        name: 'OmiGlass Test',
        type: DeviceType.openglass,
        modelNumber: 'Glass1',
        firmwareRevision: '1.0.0',
        hardwareRevision: '1.0.0',
        manufacturerName: 'BasedHardware',
      );

      await tester.pumpWidget(_wrap(provider, OmiGlassOtaUpdate(device: device)));
      await tester.pump();

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(provider.initiateConnectionCalls, equals(0));
    });
  });
}
