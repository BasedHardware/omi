// The firmware page at the largest iOS text size (accessibility-extra-extra-extra-large, body 17 → 53 pt),
// laid out with SF Pro so line breaks match the phone.
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/device.dart';

import '../../helpers/sfpro_font_fixtures.dart';

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  int get batteryLevel => 90;

  @override
  int get displayBatteryLevel => batteryLevel;

  @override
  bool get batteryReadingStuck => false;

  @override
  bool get isCharging => false;

  @override
  void setOnFirmwareUpdatePage(bool value) {}

  @override
  void resetFirmwareUpdateState() {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Fails when [text] is cut short or broken inside a word.
void expectWholeWords(WidgetTester tester, String text) {
  final paragraph = tester.renderObject<RenderParagraph>(find.text(text));
  expect(paragraph.didExceedMaxLines, isFalse, reason: '"$text" is cut short');
  double line(int offset) => paragraph.getOffsetForCaret(TextPosition(offset: offset), Rect.zero).dy;
  for (var i = 1; i < text.length; i++) {
    if (text[i - 1] == ' ' || text[i] == ' ') continue;
    expect(line(i), line(i - 1), reason: '"$text" breaks inside a word before "${text.substring(i)}"');
  }
}

void main() {
  setUpAll(() async {
    for (final family in ['Roboto', 'FlutterTest', '.SF UI Text', 'CupertinoSystemText']) {
      final loader = FontLoader(family);
      for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
        loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
      }
      await loader.load();
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'large-text-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('an up-to-date pendant keeps Current Version and Update Guide whole at the largest text size',
      (tester) async {
    tester.view.physicalSize = const Size(393 * 3, 852 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    debugLatestFirmwareLookup = ({
      required deviceModelNumber,
      required firmwareRevision,
      required hardwareRevision,
      required manufacturerName,
      serialNumber,
    }) async =>
        DeviceUtils.firmwareUpToDate;
    addTearDown(() => debugLatestFirmwareLookup = null);

    await tester.pumpWidget(ChangeNotifierProvider<DeviceProvider>.value(
      value: _Device(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(53 / 17)),
          child: child!,
        ),
        home: FirmwareUpdate(
          device: BtDevice(
            id: 'd',
            name: 'Omi',
            type: DeviceType.omi,
            rssi: -40,
            modelNumber: 'Omi CV 1',
            firmwareRevision: '3.0.21',
            hardwareRevision: '1',
            manufacturerName: 'Based Hardware',
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Your device is up to date'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Update Guide'), 200, scrollable: find.byType(Scrollable).first);
    expectWholeWords(tester, 'Current Version');
    expectWholeWords(tester, 'Update Guide');
    expect(tester.takeException(), isNull, reason: 'no overflow');

    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });
}
