@Tags(<String>['screenshots'])
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device_first_prototype/src/content.dart';
import 'package:omi_device_first_prototype/src/flow.dart';
import 'package:omi_device_first_prototype/src/theme.dart';

/// Renders every screen in both directions to test/goldens/ with real fonts.
///
///   flutter test --tags screenshots --update-goldens
///
/// Not part of the regular run (`flutter test --exclude-tags screenshots`):
/// these are review images, not regression goldens.
Future<void> _loadFonts() async {
  final root = Platform.environment['FLUTTER_ROOT'];
  if (root == null) return;
  final dir = '$root/bin/cache/artifacts/material_fonts';
  Future<ByteData> read(String name) async => ByteData.view(File('$dir/$name').readAsBytesSync().buffer);

  final roboto = FontLoader('Roboto');
  for (final name in <String>['Roboto-Regular.ttf', 'Roboto-Medium.ttf', 'Roboto-Bold.ttf', 'Roboto-Light.ttf']) {
    if (File('$dir/$name').existsSync()) roboto.addFont(read(name));
  }
  await roboto.load();
  if (File('$dir/MaterialIcons-Regular.otf').existsSync()) {
    await (FontLoader('MaterialIcons')..addFont(read('MaterialIcons-Regular.otf'))).load();
  }
}

void main() {
  setUpAll(_loadFonts);

  for (final direction in DfDirection.values) {
    for (final step in DfStep.values) {
      testWidgets('${direction.name} ${step.name}', (tester) async {
        tester.view.physicalSize = const Size(390, 844);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(
          MaterialApp(
            debugShowCheckedModeBanner: false,
            theme: ThemeData(brightness: Brightness.dark, fontFamily: 'Roboto'),
            home: DeviceFirstFlow(
              direction: direction,
              trial: TrialLength.oneMonth,
              initialStep: step,
              searchDuration: const Duration(hours: 1),
            ),
          ),
        );
        await tester.pump(Duration(milliseconds: step == DfStep.setup ? 1400 : 600));
        await tester.pump(const Duration(milliseconds: 300));
        final index = DfStep.values.indexOf(step).toString().padLeft(2, '0');
        await expectLater(
          find.byType(DeviceFirstFlow),
          matchesGoldenFile('goldens/${direction.name}/${index}_${step.name}.png'),
        );
      });
    }
  }
}
