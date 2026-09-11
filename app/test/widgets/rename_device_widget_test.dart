import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/rename_device_widget.dart';

const _deviceId = 'AA:BB:CC:DD:EE:FF';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<List<bool?>> openDialog(WidgetTester tester) async {
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
                      builder: (_) => const RenameDeviceWidget(deviceId: _deviceId, advertisedName: 'Omi'),
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
}
