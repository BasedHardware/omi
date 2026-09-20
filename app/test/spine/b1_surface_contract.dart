import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';
import 'dart:ui' show SemanticsAction, SemanticsActionEvent, Tristate;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import '../support/addressability_widgets.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';
import '../support/addressability_fixture.dart';
import 'b1_route_dismissal.dart';

final _handlers = <String, developer.ServiceExtensionHandler>{};

Future<Map<String, dynamic>> _wire(String operation, {Map<String, String> params = const {}}) async {
  final method = 'ext.omi.controls.$operation';
  final response = await _handlers[method]!(method, {'version': 'semantic-controls/v2', ...params});
  expect(response.isError(), isFalse);
  return jsonDecode(response.result!) as Map<String, dynamic>;
}

/// Identical keys may be mounted in cached tabs or another route root.
Finder catalogControl(Finder root, Key key, {required String scope}) {
  final visible = find.byKey(key, skipOffstage: true);
  return scope == 'root' ? find.descendant(of: root, matching: visible) : visible;
}

/// Shared executable done template. Fixtures replace external I/O only; the
/// production adapter, actual page Type, providers, keys and semantics stay real.
Future<void> checkSurface(WidgetTester tester, String id, Type pageType) async {
  final routes = (jsonDecode(addressableRoutesJson) as List).cast<Map<String, dynamic>>();
  final route = routes.singleWhere((r) => r['id'] == id);
  final api = AppAddressability.instance;
  // Ask for the production shell before setting up I/O. The skeleton's expected
  // failure cannot hide a broken fixture setup in the eventual implementation.
  final shell = api.buildShell(initialRoute: id == 'onboarding' ? 'onboarding' : 'home');
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
  try {
    if (id != 'onboarding') {
      await expectLater(api.navigate('onboarding'),
          throwsA(isA<AddressabilityRefused>().having((e) => e.code, 'code', 'auth-required')));
    }
    final navigation = _wire('navigate', params: {
      'destination': id,
      if (id == 'conversation_detail') 'record_id': 'seeded-conv-j1-0001',
    });
    if (route['reach']['kind'] == 'push' || route['reach']['kind'] == 'sheet') {
      late Future<void> competing;
      expect(() => competing = api.navigate('home'), returnsNormally, reason: 'refusals are failed Futures');
      await expectLater(competing, throwsA(isA<AddressabilityRefused>().having((error) => error.code, 'code', 'busy')));
      expect(api.visibleRoute, isNull, reason: 'no destination is ready during transition');
    }
    // Bound frames; waitReady owns the asynchronous condition, not pumpAndSettle
    // on an app with perpetual capture/shimmer animations.
    for (var frame = 0; frame < 60; frame++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect((await navigation)['ok'], isTrue);
    final rootKey = ValueKey<String>(route['root'] as String);
    final root = find.byKey(rootKey, skipOffstage: true);
    expect(root, findsOneWidget);
    expect(find.byKey(rootKey, skipOffstage: false), findsOneWidget);
    final retainedPage = find.byType(pageType).evaluate().single;
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
    final catalog = (jsonDecode(addressableControlsJson) as Map<String, dynamic>)[id] as List;
    expect(catalog, isNotEmpty);
    if (id == 'chat') {
      // Establish the actionable send state before checking its semantics.
      await tester.enterText(find.byKey(OmiKeys.chatInput), 'fixture input');
      await tester.pump();
    }
    for (final item in catalog.cast<Map<String, dynamic>>()) {
      final value = item['key'] as String;
      final control = catalogControl(root, ValueKey<String>(value), scope: item['scope'] as String);
      expect(control, findsOneWidget, reason: 'catalogued control must be unique and onstage: $value');
      if (item['scope'] == 'root') {
        expect(find.descendant(of: root, matching: control), findsOneWidget);
      }
      expect(isCatalogInteractive(tester.widget(control), includeDisabled: true), isTrue,
          reason: 'the catalog key belongs on the actual interactive constructor, not a decorative wrapper');
      expect(AddressKey.valid(value), isTrue);
      final data = tester.getSemantics(control).getSemanticsData();
      expect(data.identifier, value);
      expect(item.containsKey('label_en'), isFalse, reason: 'ARB owns labels, not a second English catalog');
      if (item['row_id'] != null) {
        final row = find.ancestor(of: control, matching: find.byType(ConversationListItem));
        expect(row, findsOneWidget);
        final record = tester.widget<ConversationListItem>(row).conversation;
        expect(record.id, item['row_id']);
        expect(value, AddressKey.row('conversations', record.id), reason: 'rendered key derives from id, not index');
        expect(record.structured.title, isNotEmpty);
        expect(data.label, record.structured.title);
      } else {
        final arb = jsonDecode(File('lib/l10n/app_en.arb').readAsStringSync()) as Map<String, dynamic>;
        expect(item['label_arb'], isA<String>());
        expect(arb[item['label_arb']], isA<String>());
        expect(data.label, arb[item['label_arb']], reason: 'English fixture uses the current localized human label');
      }
      expect(data.flagsCollection.isEnabled, Tristate.isTrue);
      expect(data.flagsCollection.isButton, item['role'] == 'button');
      expect(data.flagsCollection.isTextField, item['role'] == 'textField');
      expect(data.hasAction(item['action'] == 'setText' ? SemanticsAction.setText : SemanticsAction.tap), isTrue);
    }
    if (id == 'chat') {
      final input = tester.getSemantics(find.byKey(OmiKeys.chatInput));
      tester.binding.performSemanticsAction(SemanticsActionEvent(
        viewId: tester.view.viewId,
        nodeId: input.id,
        type: SemanticsAction.setText,
        arguments: 'accessible input',
      ));
      await tester.pump();
      expect(tester.widget<TextField>(find.byKey(OmiKeys.chatInput)).controller!.text, 'accessible input',
          reason: 'accessibility action must change the real control, not an agent-only semantics node');
    }
    // Catalog declaration/reference check only. Uncatalogued directory debt is
    // deliberately outside surface acceptance; changed-file no-growth still runs.
    final scan = await tester.runAsync(() => Process.run('python3', [
          '../scripts/check_app_addressability.py',
          '--surface',
          id,
        ]));
    expect(scan!.exitCode, 0, reason: '${scan.stdout}\n${scan.stderr}');
    void accessibleTap(Key key) {
      final entries =
          catalog.cast<Map<String, dynamic>>().where((item) => ValueKey<String>(item['key'] as String) == key);
      final scope = entries.isEmpty ? 'shell' : entries.single['scope'] as String;
      final node = tester.getSemantics(catalogControl(root, key, scope: scope));
      tester.binding.performSemanticsAction(SemanticsActionEvent(
        viewId: tester.view.viewId,
        nodeId: node.id,
        type: SemanticsAction.tap,
      ));
    }

    if (id == 'home') {
      expect(tester.getSemantics(find.byKey(OmiKeys.homeTabHome)).getSemanticsData().flagsCollection.isSelected,
          Tristate.isTrue);
      accessibleTap(OmiKeys.homeTabConversations);
      await tester.pump(const Duration(seconds: 1));
      expect(api.visibleRoute, 'conversations', reason: 'tab semantics must call the real owner');
      accessibleTap(const ValueKey<String>('omi.home.tab_apps'));
      await tester.pump(const Duration(seconds: 1));
      expect(api.visibleRoute, 'apps');
      expect(find.byKey(const ValueKey<String>('omi.apps.root')), findsOneWidget);
      expect(find.byType(AppsPage), findsOneWidget);
      expect((await _wire('capabilities'))['routes'], contains('apps'));
      final awayFromApps = api.navigate('home');
      await tester.pump(const Duration(seconds: 1));
      await awayFromApps;
      expect(api.visibleRoute, 'home');
      expect(find.byType(AppsPage), findsNothing);
      final reachedById = _wire('navigate', params: {'destination': 'apps'});
      await tester.pump(const Duration(seconds: 1));
      expect((await reachedById)['ok'], isTrue);
      expect(api.visibleRoute, 'apps');
      expect(find.byType(AppsPage), findsOneWidget);
      final returned = api.navigate('home');
      await tester.pump(const Duration(seconds: 1));
      await returned;
      expect(find.byType(pageType).evaluate().single, same(retainedPage));
    }
    if (id == 'conversations') {
      accessibleTap(ValueKey<String>((catalog.single as Map)['key'] as String));
      await tester.pump(const Duration(seconds: 1));
      expect(api.visibleRoute, 'conversation_detail', reason: 'row semantics must open the actual seeded detail');
      expect(find.byKey(OmiKeys.conversationDetailRoot), findsOneWidget);
      expect(find.textContaining('Journey one seeded conversation'), findsWidgets);
      await tester.binding.handlePopRoute();
      await tester.pump(const Duration(seconds: 1));
      expect(api.visibleRoute, id);
    }
    if (route['reach']['kind'] == 'push' || route['reach']['kind'] == 'sheet') {
      final closeKey = switch (id) {
        'settings' => OmiKeys.settingsDone,
        'devices' => OmiKeys.devicesBack,
        'conversation_detail' => OmiKeys.conversationDetailBack,
        _ => null,
      };
      final closingRoute = ModalRoute.of(retainedPage)!;
      await expectRouteDismissed(tester, closingRoute, retainedPage, () async {
        if (closeKey == null) {
          await tester.binding.handlePopRoute();
        } else {
          accessibleTap(closeKey);
        }
      });
      expect(find.byType(pageType, skipOffstage: false), findsNothing);
      expect(api.visibleRoute, isNot(id));
    } else if (id != 'onboarding') {
      final next = id == 'home' ? 'conversations' : 'home';
      final switched = api.navigate(next);
      await tester.pump(const Duration(seconds: 1));
      await switched;
      expect(api.visibleRoute, next);
      expect(find.byKey(rootKey, skipOffstage: true), findsNothing);
      expect(find.byKey(rootKey, skipOffstage: false), findsOneWidget, reason: 'visited tabs remain mounted');
      expect(find.byType(pageType, skipOffstage: false).evaluate().single, same(retainedPage));
      final returned = api.navigate(id);
      await tester.pump(const Duration(seconds: 1));
      await returned;
      expect(find.byKey(rootKey, skipOffstage: true), findsOneWidget);
      expect(find.byType(pageType).evaluate().single, same(retainedPage), reason: 'return must preserve tab state');
    }
    if (id == 'onboarding') {
      accessibleTap(const ValueKey<String>('omi.onboarding.local_dev'));
      await tester.pump(const Duration(seconds: 1));
      expect((await _wire('state'))['auth'], 'signedIn');
      expect(api.visibleRoute, 'home');
      expect(find.byType(HomeContentPage), findsOneWidget);
    }
    await tester.pumpWidget(const SizedBox.shrink());
    expect(api.rootMounted, isFalse, reason: 'disposed scope must invalidate route readiness');
    final disposed = await _wire('state');
    expect(disposed['route'], isNull);
    expect((disposed['readiness'] as Map)['routed'], isFalse);
  } finally {
    semantics.dispose();
  }
}
