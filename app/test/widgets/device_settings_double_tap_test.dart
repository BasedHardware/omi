import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/omi_button_action.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({this.device, this.findResult = true, this.findCompleter});

  final BtDevice? device;
  final bool findResult;
  final Completer<bool>? findCompleter;
  int findCalls = 0;

  @override
  bool get isConnected => true;

  @override
  BtDevice? get connectedDevice => device;

  @override
  BtDevice? get pairedDevice => null;

  @override
  Future<void> getDeviceInfo() async {}

  @override
  Future<bool> findDevice() {
    findCalls++;
    return findCompleter?.future ?? Future.value(findResult);
  }

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
    home: ChangeNotifierProvider<DeviceProvider>.value(value: provider, child: const DeviceSettings()),
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

  testWidgets('shows a row per remappable gesture plus the fixed long press', (tester) async {
    final provider = _StubDeviceProvider();
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.byKey(const Key('button_gesture_singleTap')), findsOneWidget);
    expect(find.byKey(const Key('button_gesture_doubleTap')), findsOneWidget);
    expect(find.byKey(const Key('button_gesture_tripleTap')), findsOneWidget);
    expect(find.byKey(const Key('button_gesture_longPress')), findsOneWidget);

    // Defaults: single = ask question, double = mute (seeded), triple = end conversation.
    expect(find.text('Ask Omi a Question'), findsOneWidget);
    expect(find.text('End Conversation'), findsOneWidget);
    expect(find.text('Power On / Off'), findsOneWidget);
    expect(find.text("Hold for 3 seconds to turn your Omi on or off. This can't be changed."), findsOneWidget);
  });

  testWidgets('picking a triple tap action persists it and updates the chip', (tester) async {
    final provider = _StubDeviceProvider();
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    await tester.tap(find.byKey(const Key('button_gesture_tripleTap')));
    await tester.pumpAndSettle();

    expect(find.text('Triple Tap Action'), findsOneWidget);
    // The current action is ticked; every action is offered.
    expect(find.byKey(const Key('button_action_tripleTap_endConversation')), findsOneWidget);
    expect(find.byKey(const Key('button_action_tripleTap_askQuestion')), findsOneWidget);
    expect(find.byKey(const Key('button_action_tripleTap_none')), findsOneWidget);

    await tester.tap(find.byKey(const Key('button_action_tripleTap_none')));
    await tester.pumpAndSettle();

    expect(find.text('Triple Tap Action'), findsNothing);
    expect(find.text('Do Nothing'), findsOneWidget);
    expect(SharedPreferencesUtil().buttonActionFor(OmiButtonGesture.tripleTap), OmiButtonAction.none);
    expect((await SharedPreferences.getInstance()).getInt('tripleTapAction'), OmiButtonAction.none.storedValue);
    // Other gestures are untouched.
    expect(SharedPreferencesUtil().buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.muteUnmute);
  });

  testWidgets('the long press row is informational only', (tester) async {
    final provider = _StubDeviceProvider();
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    await tester.tap(find.byKey(const Key('button_gesture_longPress')));
    await tester.pumpAndSettle();

    expect(find.byType(ListTile), findsNothing);
  });

  testWidgets('Find triggers one guarded request for a connected Omi', (tester) async {
    final findCompleter = Completer<bool>();
    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
      findCompleter: findCompleter,
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('Find'), findsOneWidget);

    await tester.tap(find.byKey(const Key('find_device_button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('find_device_button')));
    await tester.pump();

    expect(provider.findCalls, 1);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    findCompleter.complete(true);
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('Find reports when the pendant cannot be reached', (tester) async {
    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
      findResult: false,
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();
    await tester.tap(find.byKey(const Key('find_device_button')));
    await tester.pumpAndSettle();

    expect(provider.findCalls, 1);
    expect(find.text('An error occurred. Please try again.'), findsOneWidget);
  });

  testWidgets('Find clears its loading state when the provider throws', (tester) async {
    final findCompleter = Completer<bool>();
    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
      findCompleter: findCompleter,
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();
    await tester.tap(find.byKey(const Key('find_device_button')));
    await tester.pump();

    findCompleter.completeError(StateError('find failed'));
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('An error occurred. Please try again.'), findsOneWidget);
  });

  testWidgets('Find times out a stalled provider request', (tester) async {
    final findCompleter = Completer<bool>();
    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
      findCompleter: findCompleter,
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();
    await tester.tap(find.byKey(const Key('find_device_button')));
    await tester.pump();

    await tester.pump(const Duration(seconds: 30));
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('An error occurred. Please try again.'), findsOneWidget);

    findCompleter.complete(true);
  });
}
