/// The rename dialog validates locally before touching BLE, sends the trimmed
/// name, closes only on a device-confirmed rename, and stays open with an
/// error when the pendant did not take the name.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/rename_device_widget.dart';

Widget _host({required Future<bool> Function(String) onRename, String initialName = 'Omi'}) {
  return MaterialApp(
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
            key: const Key('open'),
            onPressed: () async {
              final result = await showDialog<bool>(
                context: context,
                builder: (_) => RenameDeviceWidget(initialName: initialName, onRename: onRename),
              );
              _lastResult = result;
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
}

bool? _lastResult;

Future<void> _openDialog(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('open')));
  await tester.pumpAndSettle();
  expect(find.byKey(const Key('rename_device_field')), findsOneWidget);
}

void main() {
  setUp(() => _lastResult = null);

  testWidgets('sends the trimmed name and closes with true when the device confirms', (tester) async {
    final sent = <String>[];
    await tester.pumpWidget(
      _host(
        onRename: (name) async {
          sent.add(name);
          return true;
        },
      ),
    );
    await _openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), '  Kitchen Omi ');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(sent, ['Kitchen Omi']);
    expect(find.byKey(const Key('rename_device_field')), findsNothing);
    expect(_lastResult, isTrue);
  });

  testWidgets('rejects an empty name locally without calling the device', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _host(
        onRename: (_) async {
          calls++;
          return true;
        },
      ),
    );
    await _openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), '   ');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(calls, 0);
    expect(find.byKey(const Key('rename_device_error')), findsOneWidget);
    expect(find.byKey(const Key('rename_device_field')), findsOneWidget);
  });

  testWidgets('rejects a name over the byte budget locally', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _host(
        onRename: (_) async {
          calls++;
          return true;
        },
      ),
    );
    await _openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'x' * 21);
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(calls, 0);
    expect(find.byKey(const Key('rename_device_error')), findsOneWidget);
  });

  testWidgets('stays open with an error when the device does not take the name', (tester) async {
    await tester.pumpWidget(_host(onRename: (_) async => false));
    await _openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Kitchen Omi');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('rename_device_field')), findsOneWidget);
    expect(find.byKey(const Key('rename_device_error')), findsOneWidget);
    expect(_lastResult, isNull);
  });

  testWidgets('shows progress and ignores repeated saves while the write is in flight', (tester) async {
    final gate = Completer<bool>();
    var calls = 0;
    await tester.pumpWidget(
      _host(
        onRename: (_) {
          calls++;
          return gate.future;
        },
      ),
    );
    await _openDialog(tester);

    await tester.enterText(find.byKey(const Key('rename_device_field')), 'Kitchen Omi');
    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pump();
    expect(calls, 1);

    gate.complete(true);
    await tester.pumpAndSettle();
    expect(_lastResult, isTrue);
  });

  testWidgets('an unchanged name closes without touching the device', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      _host(
        onRename: (_) async {
          calls++;
          return true;
        },
        initialName: 'Omi',
      ),
    );
    await _openDialog(tester);

    await tester.tap(find.byKey(const Key('rename_device_save')));
    await tester.pumpAndSettle();

    expect(calls, 0);
    expect(_lastResult, isFalse);
  });
}
