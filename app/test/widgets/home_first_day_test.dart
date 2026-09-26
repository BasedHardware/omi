import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/home_first_day.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';

/// Home on the first day (v2 FirstDay): Welcome, Getting started (N of 4) and Good to know.
class _Devices extends ChangeNotifier implements DeviceProvider {
  _Devices(this._paired);

  final BtDevice? _paired;

  @override
  BtDevice? get pairedDevice => _paired;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ServerMessage _asked() => ServerMessage('m1', DateTime.utc(2026, 9, 25), 'What did I promise?', MessageSender.human,
    MessageType.text, null, false, const [], const [], const []);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Widget app(Widget child, {BtDevice? paired, bool voice = false, bool asked = false}) {
    final home = HomeProvider()..hasSpeakerProfile = voice;
    final messages = MessageProvider()..messages = [if (asked) _asked()];
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: _Devices(paired)),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<MessageProvider>.value(value: messages),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );
  }

  testWidgets('the first day welcomes by name', (tester) async {
    SharedPreferencesUtil().givenName = 'Alex';
    await tester.pumpWidget(app(const HomeFirstDayHeader()));
    expect(find.text('Welcome, Alex'), findsOneWidget);
    expect(find.text('Your first day with Omi'), findsOneWidget);
  });

  testWidgets('Getting started counts what is done and strikes it through', (tester) async {
    final pendant = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
    await tester.pumpWidget(app(const HomeGettingStarted(conversationCount: 0), paired: pendant, voice: true));
    expect(find.text('Getting started'), findsOneWidget);
    expect(find.text('2 of 4'), findsOneWidget);
    for (final step in ['Connect a device', 'Teach Omi your voice', 'Have a conversation', 'Ask Omi about it']) {
      expect(find.text(step), findsOneWidget);
    }
    final connect = tester.widget<Text>(find.text('Connect a device'));
    expect(connect.style?.decoration, TextDecoration.lineThrough);
    final ask = tester.widget<Text>(find.text('Ask Omi about it'));
    expect(ask.style?.decoration, isNull);

    final semantics = tester.ensureSemantics();
    expect(
      tester.getSemantics(find.byKey(const ValueKey('getting_started_connect'))),
      isSemantics(isChecked: true, hasCheckedState: true),
    );
    expect(
      tester.getSemantics(find.byKey(const ValueKey('getting_started_ask'))),
      isSemantics(isChecked: false, hasCheckedState: true, isButton: true),
    );
    semantics.dispose();
  });

  testWidgets('Getting started folds away once all four are done', (tester) async {
    final pendant = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
    await tester.pumpWidget(
      app(const HomeGettingStarted(conversationCount: 1), paired: pendant, voice: true, asked: true),
    );
    expect(find.byKey(const ValueKey('home_getting_started')), findsNothing);
  });

  testWidgets('Good to know shows three tips side by side', (tester) async {
    await tester.pumpWidget(app(const HomeGoodToKnow()));
    expect(find.text('Good to know'), findsOneWidget);
    expect(find.text('Finish anytime'), findsOneWidget);
    expect(find.text('Star what matters'), findsOneWidget);
    expect(find.text('Private by default'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
