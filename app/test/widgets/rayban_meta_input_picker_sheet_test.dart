import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/widgets/rayban_meta_input_picker_sheet.dart';

void main() {
  Widget buildPicker({
    required Future<List<BluetoothHfpInput>> Function() inputLoader,
    required Future<void> Function(BtDevice) connector,
    required VoidCallback onConnected,
  }) {
    return MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: RayBanMetaInputPickerSheet(
          inputLoader: inputLoader,
          connector: connector,
          onConnected: onConnected,
        ),
      ),
    );
  }

  testWidgets('builds and connects the selected UID-backed Ray-Ban Meta device', (tester) async {
    BtDevice? connectedDevice;
    var connectedCallbackCount = 0;

    await tester.pumpWidget(
      buildPicker(
        inputLoader: () async => [BluetoothHfpInput(uid: 'stable-port-uid', name: 'EL AI 000F')],
        connector: (device) async => connectedDevice = device,
        onConnected: () => connectedCallbackCount++,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('rayban_meta_input_stable-port-uid')));
    await tester.pumpAndSettle();

    expect(connectedDevice?.id, 'stable-port-uid');
    expect(connectedDevice?.name, 'EL AI 000F');
    expect(connectedDevice?.type, DeviceType.raybanMeta);
    expect(connectedDevice?.locator?.extras[RayBanMetaDiscoverer.audioOnlyExtraKey], isTrue);
    expect(connectedCallbackCount, 1);
  });

  testWidgets('shows the localized empty state when iOS reports no Bluetooth microphones', (tester) async {
    await tester.pumpWidget(
      buildPicker(inputLoader: () async => [], connector: (_) async {}, onConnected: () {}),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('No Bluetooth microphones found. Connect your glasses in iPhone Settings, then try again.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('rayban_meta_input_retry')), findsOneWidget);
  });

  testWidgets('keeps the picker open and shows an error when connection fails', (tester) async {
    var connectedCallbackCount = 0;
    await tester.pumpWidget(
      buildPicker(
        inputLoader: () async => [BluetoothHfpInput(uid: 'unavailable-uid', name: 'Renamed Glasses')],
        connector: (_) async => throw StateError('unavailable'),
        onConnected: () => connectedCallbackCount++,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('rayban_meta_input_unavailable-uid')));
    await tester.pumpAndSettle();

    expect(
      find.text('Could not connect to that microphone. Make sure it is connected in iPhone Settings.'),
      findsOneWidget,
    );
    expect(find.text('Renamed Glasses'), findsOneWidget);
    expect(connectedCallbackCount, 0);
  });
}
