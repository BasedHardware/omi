import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'native_test_host.dart';

const _fallback = 'complete flutter surface';

NativeRow _level({
  Object? value = 50,
  double? minimumValue,
  double? maximumValue = 100,
  double? step = 25,
  String kind = 'level',
  NativeAction? action,
}) =>
    NativeRow('led_brightness', 'LED Brightness',
        kind: kind,
        subtitle: '50%',
        value: value,
        minimumValue: minimumValue,
        maximumValue: maximumValue,
        step: step,
        action: action ?? (_) {});

void main() {
  test('a level row is valid only with finite, ordered bounds and a value on its step grid', () {
    expect(_level().valid, true);
    expect(_level(value: 0).valid, true);
    expect(_level(value: 100.0).valid, true);
    expect(_level(step: null, value: 37.5).valid, true, reason: 'Without a step any value in range is valid');
    expect(_level(minimumValue: -10, maximumValue: 10, step: 0.5, value: -2.5).valid, true);
    expect(_level(minimumValue: 1, maximumValue: 5, step: 1, value: 3).valid, true);
    expect(_level(minimumValue: 0, maximumValue: 1, step: 0.1, value: 0.30000000000000004).valid, true,
        reason: 'Floating point steps stay on the grid within 1e-6 of a step');
    expect(_level(maximumValue: 10, step: 4, value: 8).valid, true, reason: 'The maximum need not be on the grid');
    expect(_level(maximumValue: 1000, step: 1, value: 999).valid, true, reason: 'Exactly 1000 steps');

    for (final (reason, row) in [
      ('missing maximum', _level(maximumValue: null)),
      ('maximum equal to the minimum', _level(minimumValue: 100, maximumValue: 100, value: 100)),
      ('maximum below the minimum', _level(minimumValue: 10, maximumValue: 5, step: null, value: 7)),
      ('NaN maximum', _level(maximumValue: double.nan)),
      ('infinite maximum', _level(maximumValue: double.infinity)),
      ('NaN minimum', _level(minimumValue: double.nan)),
      ('infinite minimum', _level(minimumValue: double.negativeInfinity)),
      ('NaN value', _level(value: double.nan)),
      ('infinite value', _level(value: double.infinity, step: null)),
      ('missing value', _level(value: null)),
      ('textual value', _level(value: '50')),
      ('value off the grid', _level(value: 60)),
      ('value off a minimum-anchored grid', _level(minimumValue: 1, maximumValue: 5, step: 2, value: 2)),
      ('value below the minimum', _level(minimumValue: 10, value: 5, step: null)),
      ('value above the maximum', _level(value: 125)),
      ('value below the default minimum', _level(value: -25)),
      ('zero step', _level(step: 0)),
      ('negative step', _level(step: -25)),
      ('NaN step', _level(step: double.nan)),
      ('infinite step', _level(step: double.infinity)),
      ('step larger than the range', _level(step: 101, value: 0)),
      ('more than 1000 steps', _level(maximumValue: 1001, step: 1, value: 1)),
    ]) {
      expect(row.valid, false, reason: reason);
    }
  });

  test('minimumValue and step belong to the level kind only', () {
    expect(_level(kind: 'slider', step: 25).valid, false);
    expect(_level(kind: 'slider', step: null, minimumValue: 0).valid, false);
    expect(_level(kind: 'progress', step: 25).valid, false);
    expect(const NativeRow('save', 'Save', step: 1).valid, false);
    expect(const NativeRow('save', 'Save', minimumValue: 0).valid, false);
    expect(const NativeRow('name', 'Name', kind: 'text', value: '', minimumValue: 0).valid, false);
    // The existing playback slider keeps its contract.
    expect(const NativeRow('position', 'Audio', kind: 'slider', value: 25.5, maximumValue: 100).valid, true);
    expect(const NativeRow('position', 'Audio', kind: 'slider', value: 0, maximumValue: -1).valid, false);
  });

  test('a level row accepts only finite in-range numbers on its grid', () {
    final row = _level(minimumValue: 0, maximumValue: 100, step: 25);
    for (final input in [0, 25, 50.0, 75.00000001, 100]) {
      expect(row.accepts(input), true, reason: '$input');
    }
    for (final input in [-25, 125, 60, 12.5, double.nan, double.infinity, '75', true, null]) {
      expect(row.accepts(input), false, reason: '$input');
    }
    final free = _level(minimumValue: -1, maximumValue: 1, step: null, value: 0);
    expect(free.accepts(-0.333), true);
    expect(free.accepts(1.0001), false);
    expect(_level(maximumValue: null).accepts(50), false, reason: 'A degenerate range accepts nothing');
  });

  test('the projection carries the bounds and step for Swift to mirror', () {
    final projection = _level(minimumValue: 0, maximumValue: 100, step: 25).projection;
    expect(projection['kind'], 'level');
    expect(projection['value'], 50);
    expect(projection['minimumValue'], 0);
    expect(projection['maximumValue'], 100);
    expect(projection['step'], 25);
    expect(projection['subtitle'], '50%');
    final other = const NativeRow('save', 'Save').projection;
    expect(other['minimumValue'], isNull);
    expect(other['step'], isNull);
  });

  test('dispatch passes the committed number to the existing owner and refuses forged values', () async {
    final received = <Object?>[];
    final row = _level(action: received.add);
    Future<void> dispatch(Object? value) =>
        dispatchNativeAction(MethodCall('action', {'id': 'led_brightness', 'value': value}),
            isActive: () => true, rows: [row]);
    await dispatch(75.0);
    await dispatch(0);
    expect(received, [75.0, 0]);
    for (final forged in [60.0, 125.0, -25.0, '75', null, true]) {
      await expectLater(dispatch(forged), throwsA(isA<PlatformException>()), reason: '$forged');
    }
    expect(received, [75.0, 0]);
    final disabled = NativeRow('led_brightness', 'LED Brightness',
        kind: 'level', value: 50, maximumValue: 100, step: 25, enabled: false, action: received.add);
    await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': 'led_brightness', 'value': 75.0}),
            isActive: () => true, rows: [disabled]),
        throwsA(isA<PlatformException>()));
    expect(received, [75.0, 0]);
  });

  testWidgets('a mounted surface publishes the level and routes its commit to the owner', (tester) async {
    final host = NativeTestHost.install();
    final received = <Object?>[];
    await tester
        .pumpWidget(NativeTestHost.app(IosNativeSurface(title: 'Device', fallback: const Text(_fallback), sections: [
      NativeSection('device', [_level(action: received.add)])
    ])));
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsOneWidget);
    final view = host.created.single;
    final update = host.calls.lastWhere((call) => call.$2.method == 'update').$2;
    final row = (((update.arguments as Map)['sections'] as List).single as Map)['rows'] as List;
    expect((row.single as Map)['step'], 25);
    await host.sendFromNative(view, const MethodCall('action', {'id': 'led_brightness', 'value': 75.0}));
    expect(received, [75.0]);
    await host.sendFromNative(view, const MethodCall('action', {'id': 'led_brightness', 'value': 60.0}));
    expect(received, [75.0], reason: 'An off-grid value never reaches the owner');
    expect(tester.takeException(), isNull);
  });

  testWidgets('an invalid level row keeps the complete Flutter surface', (tester) async {
    final host = NativeTestHost.install();
    await tester
        .pumpWidget(NativeTestHost.app(IosNativeSurface(title: 'Device', fallback: const Text(_fallback), sections: [
      NativeSection('device', [_level(value: 60)])
    ])));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    expect(host.created, isEmpty);
  });

  testWidgets('a native modal never presents a level control', (tester) async {
    NativeTestHost.install();
    const config = MethodChannel('com.omi.native_ui/config');
    final calls = <MethodCall>[];
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(config, (call) async {
      calls.add(call);
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(config, null));
    await tester.pumpWidget(NativeTestHost.app(const SizedBox(key: ValueKey('caller'))));
    final context = tester.element(find.byKey(const ValueKey('caller')));
    final result = await showIosNativeModal(context, title: 'Brightness', actions: const [
      NativeRow('cancel', 'Cancel', symbol: 'xmark'),
      NativeRow('save', 'Save')
    ], sections: [
      NativeSection('device', [_level()])
    ]);
    expect(result, isNull, reason: 'null keeps the caller on its Flutter dialog');
    expect(calls.where((call) => call.method == 'present'), isEmpty);
  });
}
