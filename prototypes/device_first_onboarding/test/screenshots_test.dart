@Tags(<String>['screenshots'])
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device_first_prototype/src/app/app_gallery.dart';
import 'package:omi_device_first_prototype/src/app/app_shell.dart';
import 'package:omi_device_first_prototype/src/content.dart';
import 'package:omi_device_first_prototype/src/flow.dart';
import 'package:omi_device_first_prototype/src/theme.dart';
import 'package:omi_device_first_prototype/src/v2/paywall_first_flow.dart';

import 'support.dart';

/// Renders every screen to test/goldens/ with real fonts.
///
///   flutter test --tags screenshots --update-goldens
///
/// Not part of the regular run (`flutter test --exclude-tags screenshots`):
/// these are review images, not regression goldens.
Future<void> _loadFonts() async {
  ByteData read(String path) => ByteData.view(File(path).readAsBytesSync().buffer);

  final root = Platform.environment['FLUTTER_ROOT'];
  if (root != null) {
    final dir = '$root/bin/cache/artifacts/material_fonts';
    final roboto = FontLoader('Roboto');
    for (final name in <String>['Roboto-Regular.ttf', 'Roboto-Medium.ttf', 'Roboto-Bold.ttf', 'Roboto-Light.ttf']) {
      if (File('$dir/$name').existsSync()) roboto.addFont(Future<ByteData>.value(read('$dir/$name')));
    }
    await roboto.load();
    if (File('$dir/MaterialIcons-Regular.otf').existsSync()) {
      await (FontLoader('MaterialIcons')..addFont(Future<ByteData>.value(read('$dir/MaterialIcons-Regular.otf'))))
          .load();
    }
  }
  final serif = FontLoader(DfTheme.serifFamily);
  for (final name in <String>['InstrumentSerif-Regular.ttf', 'InstrumentSerif-Italic.ttf']) {
    if (File('fonts/$name').existsSync()) serif.addFont(Future<ByteData>.value(read('fonts/$name')));
  }
  await serif.load();
}

Future<void> _shoot(WidgetTester tester, Widget home, String path,
    {Duration wait = const Duration(milliseconds: 600), bool light = true}) async {
  setSize(tester, const Size(390, 844));
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(brightness: light ? Brightness.light : Brightness.dark, fontFamily: 'Roboto'),
      home: RepaintBoundary(key: const ValueKey<String>('shot'), child: home),
    ),
  );
  await tester.pump(wait);
  await tester.pump(const Duration(milliseconds: 300));
  await expectLater(find.byKey(const ValueKey<String>('shot')), matchesGoldenFile(path));
}

String _n(int i) => i.toString().padLeft(2, '0');

void main() {
  setUpAll(_loadFonts);

  // v2: paywall-first, Aurora Light (and the dark looks for comparison).
  for (final direction in DfDirection.values) {
    for (final step in V2Step.values) {
      testWidgets('v2 ${direction.name} ${step.name}', (tester) async {
        await _shoot(
          tester,
          PaywallFirstFlow(
            direction: direction,
            trial: TrialLength.oneWeek,
            today: testToday,
            initialStep: step,
            searchDuration: const Duration(hours: 1),
          ),
          'goldens/v2_${direction.name}/${_n(V2Step.values.indexOf(step))}_${step.name}.png',
          wait: Duration(milliseconds: step == V2Step.finishing ? 1400 : 600),
          light: DfTheme.of(direction).isLight,
        );
      });
    }
  }

  // The app, Free and Unlimited.
  for (final (plan, label) in const <(DfPlanState, String)>[
    (DfPlanState.free(), 'free'),
    (DfPlanState.trial(30), 'unlimited'),
  ]) {
    for (var i = 0; i < appScreens.length; i++) {
      final (title, builder) = appScreens[i];
      testWidgets('app $label $title', (tester) async {
        const theme = DfTheme.auroraLight;
        await _shoot(
          tester,
          DfThemeScope(
            theme: theme,
            child: Scaffold(body: OmiApp(plan: plan, today: testToday, home: builder)),
          ),
          'goldens/app_$label/${_n(i)}_${title.split(' ').first}.png',
        );
      });
    }
  }

  // v1: device-first, in its two original looks.
  for (final direction in <DfDirection>[DfDirection.graphite, DfDirection.aurora]) {
    for (final step in DfStep.values) {
      testWidgets('v1 ${direction.name} ${step.name}', (tester) async {
        await _shoot(
          tester,
          DeviceFirstFlow(
            direction: direction,
            trial: TrialLength.oneMonth,
            initialStep: step,
            searchDuration: const Duration(hours: 1),
          ),
          'goldens/v1_${direction.name}/${_n(DfStep.values.indexOf(step))}_${step.name}.png',
          wait: Duration(milliseconds: step == DfStep.setup ? 1400 : 600),
          light: false,
        );
      });
    }
  }
}
