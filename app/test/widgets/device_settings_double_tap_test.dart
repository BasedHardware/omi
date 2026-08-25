import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  bool get isConnected => true;

  @override
  BtDevice? get connectedDevice => null;

  @override
  BtDevice? get pairedDevice => null;

  @override
  Future<void> getDeviceInfo() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(DeviceProvider provider) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: ChangeNotifierProvider<DeviceProvider>.value(
      value: provider,
      child: const DeviceSettings(),
    ),
  );
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({'doubleTapAction': 1});
    await SharedPreferencesUtil.init();
  });

  testWidgets('double-tap action 1 uses mute and unmute terminology', (tester) async {
    final provider = _StubDeviceProvider();
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('Mute / Unmute'), findsOneWidget);
    expect(find.text('Pause/Resume'), findsNothing);

    await tester.tap(find.text('Mute / Unmute'));
    await tester.pumpAndSettle();

    expect(find.text('Mute / Unmute'), findsNWidgets(2));
    expect(find.text('Pause/Resume Recording'), findsNothing);
  });
}
