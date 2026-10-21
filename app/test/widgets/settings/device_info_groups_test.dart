import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device/device_info_groups.dart';
import 'package:omi/services/devices/device_custom_names.dart';

/// A disconnected device reports none of its GATT values (BtDevice says 'Unknown'), so the page
/// hides those rows instead of listing "Unknown" four times.
void main() {
  Future<AppLocalizations> pump(WidgetTester tester, BtDevice device, {VoidCallback? onRenameDevice}) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: SingleChildScrollView(
            child: DeviceInfoGroups(pairedDevice: device, isDeviceConnected: false, onRenameDevice: onRenameDevice),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return AppLocalizations.of(tester.element(find.byType(DeviceInfoGroups)));
  }

  testWidgets('unknown name and hardware values are hidden', (tester) async {
    final l10n = await pump(
      tester,
      BtDevice(id: 'd1', name: 'Unknown', type: DeviceType.omi, rssi: 0, firmwareRevision: '2.0.10'),
    );
    expect(find.text(l10n.deviceName), findsNothing);
    expect(find.text(l10n.hardwareSection), findsNothing);
    expect(find.text(l10n.hardwareRevision), findsNothing);
    expect(find.text(l10n.modelNumber), findsNothing);
    expect(find.text(l10n.manufacturer), findsNothing);
    expect(find.text('2.0.10'), findsOneWidget);
  });

  testWidgets('known values show their rows', (tester) async {
    final l10n = await pump(
      tester,
      BtDevice(
        id: 'd1',
        name: 'Omi Device',
        type: DeviceType.omi,
        rssi: 0,
        modelNumber: 'Omi DevKit 2',
        manufacturerName: 'Based Hardware',
      ),
    );
    expect(find.text(l10n.deviceName), findsOneWidget);
    expect(find.text('Omi Device'), findsOneWidget);
    expect(find.text(l10n.hardwareSection), findsOneWidget);
    expect(find.text('Omi DevKit 2'), findsOneWidget);
    expect(find.text('Based Hardware'), findsOneWidget);
    expect(find.text(l10n.hardwareRevision), findsNothing);
  });

  testWidgets('a device the page can rename shows its custom name and opens rename on tap', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().setDeviceCustomName('d1', 'Kitchen Omi');
    var taps = 0;

    final l10n = await pump(
      tester,
      BtDevice(id: 'd1', name: 'Omi Device', type: DeviceType.omi, rssi: 0),
      onRenameDevice: () => taps++,
    );

    expect(find.text(l10n.deviceName), findsOneWidget);
    expect(find.text('Kitchen Omi'), findsOneWidget);
    expect(find.text('Omi Device'), findsNothing);
    await tester.tap(find.byKey(const Key('device_name_row')));
    expect(taps, 1);
  });
}
