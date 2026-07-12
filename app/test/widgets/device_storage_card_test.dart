import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/device_storage_card.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

const int _mb = 1024 * 1024;

Widget _app(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: child),
  );
}

RingStatus _status({required int usedMb, required int freeMb}) =>
    RingStatus(usedBytes: usedMb * _mb, unreadPackets: 0, freeBytes: freeMb * _mb, rtcValid: 1);

Color? _barColor(WidgetTester tester) {
  final indicator = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
  return indicator.valueColor?.value;
}

void main() {
  testWidgets('normal fill: percent, bar value and purple color, no warning', (tester) async {
    await tester.pumpWidget(_app(DeviceStorageCard(status: _status(usedMb: 338, freeMb: 131))));
    await tester.pump();

    // 338 / (338+131) = 0.7207 -> 72%
    expect(find.text('72% full'), findsOneWidget);
    expect(find.textContaining('338 MB of 469 MB used'), findsOneWidget);
    expect(find.textContaining('131 MB free'), findsOneWidget);

    final indicator = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
    expect(indicator.value, closeTo(0.7207, 0.001));
    expect(_barColor(tester), ResponsiveHelper.purplePrimary);

    // No nearly-full warning below 95%.
    expect(find.text('Device nearly full — sync to free space.'), findsNothing);
  });

  testWidgets('warning band (>=80%, <95%) turns the bar amber', (tester) async {
    // 400 / 469 = 0.853
    await tester.pumpWidget(_app(DeviceStorageCard(status: _status(usedMb: 400, freeMb: 69))));
    await tester.pump();
    expect(_barColor(tester), ResponsiveHelper.warningColor);
    expect(find.text('Device nearly full — sync to free space.'), findsNothing);
  });

  testWidgets('nearly full (>=95%) turns bar red and shows the sync hint', (tester) async {
    // 460 / 469 = 0.981
    await tester.pumpWidget(_app(DeviceStorageCard(status: _status(usedMb: 460, freeMb: 9))));
    await tester.pump();
    expect(find.text('98% full'), findsOneWidget);
    expect(_barColor(tester), ResponsiveHelper.errorColor);
    expect(find.text('Device nearly full — sync to free space.'), findsOneWidget);
  });

  testWidgets('empty device: zero total does not divide by zero', (tester) async {
    await tester.pumpWidget(_app(DeviceStorageCard(status: _status(usedMb: 0, freeMb: 0))));
    await tester.pump();
    expect(find.text('0% full'), findsOneWidget);
    final indicator = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
    expect(indicator.value, 0.0);
  });
}
