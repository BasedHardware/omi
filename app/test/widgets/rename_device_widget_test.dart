import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/rename_device_widget.dart';
import 'package:omi/services/devices/stored_device_name.dart';

const _deviceId = 'AA:BB:CC:DD:EE:FF';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<List<bool?>> openDialog(WidgetTester tester, {Future<bool> Function(String name)? saveToDevice}) async {
    final results = <bool?>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  results.add(
                    await showDialog<bool>(
                      context: context,
                      builder: (_) =>
                          RenameDeviceWidget(deviceId: _deviceId, advertisedName: 'Omi', saveToDevice: saveToDevice),
                    ),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    return results;
  }

  testWidgets('shows the advertised name as the hint when no custom name is stored', (tester) async {
    await openDialog(tester);

    final field = tester.widget<TextField>(find.byKey(const Key('rename_device_field')));
    expect(field.controller?.text, isEmpty);
    expect(field.decoration?.hintText, 'Omi');
  });

  testWidgets('saving a typed name stores it and reports success', (tester) async {
    final results = await openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Studio Pendant');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), 'Studio Pendant');
    expect(results.single, isTrue);
  });

  testWidgets('a name the device cannot store is refused at the keyboard, not after saving', (tester) async {
    await openDialog(tester, saveToDevice: (_) async => true);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'ஸ்ரீ' * 11);
    await tester.pumpAndSettle();

    final field = tester.widget<TextField>(find.byKey(const Key('rename_device_field')));
    expect(utf8.encode(field.controller!.text).length, lessThanOrEqualTo(maxStoredDeviceNameBytes));
  });

  testWidgets('a save that throws reports the failure instead of silently stopping', (tester) async {
    await openDialog(tester, saveToDevice: (_) async => throw Exception('ble down'));

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Studio Pendant');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), isNull);
    final context = tester.element(find.byKey(const Key('rename_device_field')));
    expect(find.text(AppLocalizations.of(context)!.anErrorOccurredTryAgain), findsOneWidget);
  });

  testWidgets('prefills the field with an existing custom name', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Studio Pendant');

    await openDialog(tester);

    final field = tester.widget<TextField>(find.byKey(const Key('rename_device_field')));
    expect(field.controller?.text, 'Studio Pendant');
  });

  testWidgets('clearing the field removes the override', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Studio Pendant');

    await openDialog(tester);
    await tester.enterText(find.byKey(const Key('rename_device_field')), '');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), isNull);
  });

  testWidgets('caps the typed name so long names cannot overflow the settings row', (tester) async {
    final results = await openDialog(tester);

    await tester.enterText(
      find.byKey(const Key('rename_device_field')),
      'My extremely long omi pendant name for the kitchen table',
    );
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId)!.length, 32);
    expect(results.single, isTrue);
  });

  testWidgets('cancel leaves the stored name untouched', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Studio Pendant');

    final results = await openDialog(tester);
    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Discarded');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), 'Studio Pendant');
    expect(results.single, isFalse);
  });

  testWidgets('explains that the name is kept on this phone', (tester) async {
    await openDialog(tester);

    expect(find.text('Stored on this phone only.'), findsOneWidget);
  });

  testWidgets('hides the reset action when no custom name is stored', (tester) async {
    await openDialog(tester);

    expect(find.byKey(const Key('rename_device_reset')), findsNothing);
  });

  testWidgets('reset clears a stored custom name', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Studio Pendant');

    final results = await openDialog(tester);
    await tester.tap(find.byKey(const Key('rename_device_reset')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), isNull);
    expect(results.single, isTrue);
  });

  testWidgets('with device storage the name is written to the device before it is kept here', (tester) async {
    final written = <String>[];
    final results = await openDialog(tester, saveToDevice: (name) async {
      written.add(name);
      return true;
    });

    await tester.enterText(find.byKey(const Key('rename_device_field')), '  Kitchen Omi ');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(written, ['Kitchen Omi']);
    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), 'Kitchen Omi');
    expect(results, [true]);
  });

  testWidgets('a failed device write keeps the old name and shows an error', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Old name');
    final results = await openDialog(tester, saveToDevice: (name) async => false);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Kitchen Omi');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('rename_device_error')), findsOneWidget);
    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), 'Old name');
    expect(results, isEmpty);
  });

  testWidgets('reset with device storage clears the name on the device too', (tester) async {
    await SharedPreferencesUtil().setDeviceCustomName(_deviceId, 'Kitchen Omi');
    final written = <String>[];
    await openDialog(tester, saveToDevice: (name) async {
      written.add(name);
      return true;
    });

    await tester.tap(find.byKey(const Key('rename_device_reset')));
    await tester.pumpAndSettle();

    expect(written, ['']);
    expect(SharedPreferencesUtil().getDeviceCustomName(_deviceId), isNull);
  });

  testWidgets('says the name lives on the Omi when the device stores it', (tester) async {
    await openDialog(tester, saveToDevice: (name) async => true);

    expect(find.text('Saved on your Omi, so any phone that connects to it shows this name.'), findsOneWidget);
    expect(find.text('Stored on this phone only.'), findsNothing);
  });
}
