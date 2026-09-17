import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';
import 'dart:ui' show SemanticsAction, SemanticsActionEvent, Tristate;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';
import '../support/addressability_fixture.dart';

final _handlers = <String, developer.ServiceExtensionHandler>{};

Future<Map<String, dynamic>> _wire(String operation, {Map<String, String> params = const {}}) async {
  final method = 'ext.omi.controls.$operation';
  final response = await _handlers[method]!(method, {'version': 'semantic-controls/v2', ...params});
  expect(response.isError(), isFalse);
  return jsonDecode(response.result!) as Map<String, dynamic>;
}

/// Shared executable done template. Fixtures replace external I/O only; the
/// production adapter, actual page Type, providers, keys and semantics stay real.
Future<void> checkSurface(WidgetTester tester, String id, Type pageType) async {
  final routes = (jsonDecode(addressableRoutesJson) as List).cast<Map<String, dynamic>>();
  final route = routes.singleWhere((r) => r['id'] == id);
  final api = AppAddressability.instance;
  // Ask for the production shell before setting up I/O. The skeleton's expected
  // failure cannot hide a broken fixture setup in the eventual implementation.
  final shell = api.buildShell();
  expect(
      () => SemanticControls.instance.installIfEligible(register: (name, handler) {
            developer.registerExtension(name, handler);
            _handlers[name] = handler;
          }),
      returnsNormally);
  final providers = await tester.runAsync(() => prepareAddressabilityFixture(id));
  addTearDown(disposeAddressabilityFixture);
  await JourneyHermeticBoot.pumpPage(tester, page: shell, providers: providers!);
  final semantics = tester.ensureSemantics();
  addTearDown(semantics.dispose);
  final navigation = _wire('navigate', params: {
    'destination': id,
    if (id == 'conversation_detail') 'record_id': 'seeded-conv-j1-0001',
  });
  if (route['reach']['kind'] == 'push' || route['reach']['kind'] == 'sheet') {
    await expectLater(
        api.navigate('home'), throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'busy')));
  }
  // Bound frames; waitReady owns the asynchronous condition, not pumpAndSettle
  // on an app with perpetual capture/shimmer animations.
  for (var frame = 0; frame < 60; frame++) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  expect((await navigation)['ok'], isTrue);
  final root = find.byKey(ValueKey<String>(route['root'] as String));
  expect(root, findsOneWidget);
  final page = find.byType(pageType);
  expect(page, findsOneWidget, reason: 'must reach the actual production page, not a catalog placeholder');
  expect(
      find.ancestor(of: root, matching: page).evaluate().isNotEmpty ||
          find.descendant(of: root, matching: page).evaluate().isNotEmpty ||
          root.evaluate().single == page.evaluate().single,
      isTrue);
  expect(api.visibleRoute, id);
  expect(api.rootMounted, isTrue);
  expect(api.pendingTransitions, 0);
  final state = await _wire('state');
  expect(state, api.controls.snapshot(), reason: 'the installed wire must read the production projection');
  expect((await _wire('capabilities'))['routes'], contains(id));
  final requiredProvider = route['ready_provider'];
  if (requiredProvider != null) {
    expect((state['providers'] as Map)[requiredProvider], 'ready');
  }
  expect(state['route'], id);
  expect((state['readiness'] as Map)['routed'], isTrue);
  if (id == 'onboarding') {
    expect(state['auth'], 'signedOut');
  } else {
    expect(state['auth'], 'signedIn');
  }
  await expectLater(api.navigate('not_a_route'),
      throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'unknown-route')));
  final unknownWire = await _handlers['ext.omi.controls.navigate']!(
      'ext.omi.controls.navigate', {'version': 'semantic-controls/v2', 'destination': 'not_a_route'});
  expect(unknownWire.isError(), isTrue);
  expect(api.visibleRoute, id);
  if (id == 'onboarding') {
    await expectLater(api.navigate('chat'),
        throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'auth-required')));
  }
  if (id == 'conversation_detail') {
    await expectLater(api.navigate(id),
        throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'record-required')));
    await expectLater(api.navigate(id, recordId: 'foreign-record'),
        throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'record-unavailable')));
    expect(api.visibleRoute, id);
  }
  final keys = <String>{};
  final controls = find.descendant(
      of: root,
      matching: find.byWidgetPredicate((widget) =>
          widget is ButtonStyleButton ||
          widget is IconButton ||
          widget is TextField ||
          widget is Checkbox ||
          widget is Switch ||
          widget is Slider ||
          (widget is ListTile && widget.onTap != null)));
  expect(controls.evaluate(), isNotEmpty, reason: 'an empty shell cannot satisfy a surface');
  for (final element in controls.evaluate()) {
    final key = element.widget.key;
    expect(key, isA<ValueKey<String>>(), reason: '${element.widget.runtimeType} needs its own key');
    final value = (key as ValueKey<String>).value;
    expect(AddressKey.valid(value), isTrue);
    expect(keys.add(value), isTrue, reason: 'duplicate visible control key: $value');
    final node = tester.getSemantics(find.byWidget(element.widget));
    final data = node.getSemanticsData();
    expect(data.identifier, value);
    expect(data.label.trim(), isNotEmpty);
    expect(data.label, isNot(contains('omi.')));
    expect(data.label, isNot(contains('seeded-')));
    if (element.widget is TextField) {
      final field = element.widget as TextField;
      expect(data.flagsCollection.isTextField, isTrue);
      expect(data.hasAction(SemanticsAction.setText), field.enabled != false && !field.readOnly);
    }
    if (element.widget is IconButton || element.widget is ButtonStyleButton) {
      final enabled = element.widget is IconButton
          ? (element.widget as IconButton).onPressed != null
          : (element.widget as ButtonStyleButton).onPressed != null ||
              (element.widget as ButtonStyleButton).onLongPress != null;
      expect(data.flagsCollection.isButton, isTrue);
      expect(data.flagsCollection.isEnabled, enabled ? Tristate.isTrue : Tristate.isFalse);
    }
    if (element.widget is IconButton && (element.widget as IconButton).onPressed != null ||
        element.widget is ButtonStyleButton && (element.widget as ButtonStyleButton).onPressed != null) {
      expect(data.hasAction(SemanticsAction.tap), isTrue);
    }
  }
  if (id == 'chat') {
    expect(tester.getSemantics(find.byKey(OmiKeys.chatInput)).getSemanticsData().label, 'Message');
    expect(tester.getSemantics(find.byKey(OmiKeys.chatSend)).getSemanticsData().label, 'Send message');
    final input = tester.getSemantics(find.byKey(OmiKeys.chatInput));
    tester.binding.performSemanticsAction(SemanticsActionEvent(
      viewId: tester.view.viewId,
      nodeId: input.id,
      type: SemanticsAction.setText,
      arguments: 'fixture input',
    ));
    await tester.pump();
    expect(tester.widget<TextField>(find.byKey(OmiKeys.chatInput)).controller!.text, 'fixture input',
        reason: 'accessibility action must change the real control, not an agent-only semantics node');
  }
  // This is the same static enumerator as the manifest, now requiring zero
  // debt for the migrated surface rather than merely no growth.
  final scan = await tester.runAsync(() => Process.run('python3', [
        '../scripts/check_app_addressability.py',
        '--surface',
        id,
      ]));
  expect(scan!.exitCode, 0, reason: '${scan.stdout}\n${scan.stderr}');
  if (route['reach']['kind'] == 'push' || route['reach']['kind'] == 'sheet') {
    await tester.binding.handlePopRoute();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(pageType), findsNothing);
    expect(api.visibleRoute, isNot(id));
  } else if (id != 'onboarding') {
    final next = id == 'home' ? 'conversations' : 'home';
    final switched = api.navigate(next);
    await tester.pump(const Duration(seconds: 1));
    await switched;
    expect(api.visibleRoute, next);
    expect(find.byKey(ValueKey<String>(route['root'] as String)), findsNothing,
        reason: 'offstage cached tabs are not visible destinations');
  }
  await tester.pumpWidget(const SizedBox.shrink());
  expect(api.rootMounted, isFalse, reason: 'disposed scope must invalidate route readiness');
  final disposed = await _wire('state');
  expect(disposed['route'], isNull);
  expect((disposed['readiness'] as Map)['routed'], isFalse);
}
