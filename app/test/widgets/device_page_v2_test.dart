import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device/device_control_sheets.dart';
import 'package:omi/pages/settings/device/device_page_header.dart';
import 'package:omi/ui/ui.dart';

/// v2 `Device.dc`: the hero with its live-state and battery chips, the inline sliders, and the
/// compact centred title.
void main() {
  Widget app(Widget child) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(disableAnimations: true), child: child!),
        home: Scaffold(body: ListView(padding: const EdgeInsets.all(16), children: [child])),
      );

  final pendant = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40, modelNumber: 'Omi CV 1');

  group('DeviceHeroCard', () {
    testWidgets('a connected pendant shows its state and battery on glass chips', (tester) async {
      await tester.pumpWidget(app(DeviceHeroCard(pairedDevice: pendant, connectedDevice: pendant, batteryLevel: 42)));
      expect(find.byType(OmiPendantInCard), findsOneWidget);
      expect(find.descendant(of: find.byKey(const ValueKey('device_hero_status')), matching: find.text('Connected')),
          findsOneWidget);
      expect(find.descendant(of: find.byKey(const ValueKey('device_hero_battery')), matching: find.text('42%')),
          findsOneWidget);
      expect(tester.getSize(find.byType(DeviceHeroCard)).height, 250);
    });

    testWidgets('audio arriving from the device reads Listening', (tester) async {
      await tester.pumpWidget(app(DeviceHeroCard(
        pairedDevice: pendant,
        connectedDevice: pendant,
        isReceivingAudio: true,
        batteryLevel: 80,
      )));
      expect(find.text('Connected · Listening'), findsOneWidget);
    });

    testWidgets('a device that is away shows Disconnected or Connecting, and no battery', (tester) async {
      await tester.pumpWidget(app(DeviceHeroCard(pairedDevice: pendant, connectedDevice: null, batteryLevel: 42)));
      expect(find.text('Disconnected'), findsOneWidget);
      expect(find.byKey(const ValueKey('device_hero_battery')), findsNothing);

      await tester.pumpWidget(app(DeviceHeroCard(pairedDevice: pendant, connectedDevice: null, isConnecting: true)));
      expect(find.text('Connecting…'), findsOneWidget);
    });
  });

  group('DeviceLevelRow', () {
    testWidgets('shows the value, drags through the slider and announces title and value', (tester) async {
      var value = 60.0;
      double? released;
      await tester.pumpWidget(app(StatefulBuilder(
        builder: (context, setState) => DeviceLevelRow(
          title: 'LED Brightness',
          value: value,
          max: 100,
          divisions: 100,
          valueLabel: (v) => '${v.round()}%',
          onChanged: (v) => setState(() => value = v),
          onChangeEnd: (v) => released = v,
        ),
      )));
      expect(find.text('60%'), findsOneWidget);

      await tester.drag(find.byType(Slider), const Offset(-400, 0));
      await tester.pumpAndSettle();
      expect(value, 0);
      expect(released, 0);
      expect(find.text('0%'), findsOneWidget);

      final semantics = tester.ensureSemantics();
      expect(tester.getSemantics(find.byType(Slider)),
          isSemantics(label: 'LED Brightness', value: '0%', isSlider: true, hasIncreaseAction: true));
      semantics.dispose();
    });
  });

  group('OmiAppBar', () {
    testWidgets('an inline title is a centred header on the button row', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          appBar: OmiAppBar(leading: SizedBox(width: 44, height: 44), inlineTitle: Text('Omi')),
        ),
      ));
      final bar = tester.getRect(find.byType(OmiAppBar));
      final title = tester.getRect(find.text('Omi'));
      expect(title.center.dx, closeTo(bar.center.dx, 1));
      expect(tester.getSize(find.byType(OmiAppBar)).height, lessThan(80));
      final semantics = tester.ensureSemantics();
      expect(tester.getSemantics(find.text('Omi')), matchesSemantics(label: 'Omi', isHeader: true));
      semantics.dispose();
    });

    testWidgets('the status bar reads on the page in both palettes', (tester) async {
      addTearDown(() => OmiColors.use(OmiPalette.dark));
      for (final (palette, expected) in [
        (OmiPalette.dark, SystemUiOverlayStyle.light),
        (OmiPalette.light, SystemUiOverlayStyle.dark),
      ]) {
        OmiColors.use(palette);
        // A fresh tree per palette: in the app, OmiAppearanceScope rebuilds everything on a switch.
        await tester.pumpWidget(
          MaterialApp(key: ValueKey(palette), home: const Scaffold(appBar: OmiAppBar(title: Text('Title')))),
        );
        final region = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
          find.descendant(of: find.byType(OmiAppBar), matching: find.byType(AnnotatedRegion<SystemUiOverlayStyle>)),
        );
        expect(region.value, expected);
      }
    });
  });
}
