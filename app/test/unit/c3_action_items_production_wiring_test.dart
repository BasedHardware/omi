import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../spine/c3_fixture.dart';
import '../support/typed_action_items_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('createProductionActionItemsProvider always attaches ActionItemsApi', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    final provider = createProductionActionItemsProvider();
    addTearDown(provider.dispose);
    expect(provider, isA<ActionItemsProvider>());
    expect(provider.usesTypedActionItemsApi, isTrue);
  });

  test('main.dart boots ActionItemsProvider through createProductionActionItemsProvider', () {
    final source = File('lib/main.dart').readAsStringSync();
    expect(source.contains('createProductionActionItemsProvider()'), isTrue);
    expect(source.contains('create: (context) => ActionItemsProvider()'), isFalse);
    expect(source.contains('lazy: true, create: (context) => ActionItemsProvider()'), isFalse);
  });

  testWidgets('production action-items provider renders 503 as error, not an empty account', (tester) async {
    final fixture = await tester.runAsync(C3Fixture.start);
    addTearDown(fixture!.close);
    Env.overrideApiBaseUrl(fixture.backend.baseUrl);
    var outage = true;
    late final ActionItemsProvider provider;
    final screen = await tester.runAsync(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      provider = createProductionActionItemsProvider(
        send: (request) async {
          if (outage && request.method == 'GET' && Uri.parse(request.url).path == '/v1/action-items') {
            fixture.backend.failNext('GET', '/v1/action-items', status: 503);
          }
          return fixture.send(request);
        },
      );
      final widget = await buildTypedActionItemsScreen(provider);
      await provider.ensureLoaded();
      await pumpEventQueue();
      return widget;
    });
    expect(provider.usesTypedActionItemsApi, isTrue);
    addTearDown(provider.dispose);
    await tester.pumpWidget(screen!);
    await tester.pump();
    final page = find.byType(ActionItemsPage);
    expect(page, findsOneWidget);
    expect(identical(tester.element(page).read<ActionItemsProvider>(), provider), isTrue);
    expect(provider.apiViewState.phase, ApiViewPhase.error);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.error'))), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.action_items.empty')), findsNothing);
    expect(find.textContaining('Create Action Item'), findsNothing);
    outage = false;
    await tester.runAsync(() async => await provider.forceRefreshActionItems());
    await tester.pump();
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.error'))), findsNothing);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.action_items.empty'))), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });

  test('production Home today and load-more go through ActionItemsApi.list', () async {
    final fixture = await C3Fixture.start();
    addTearDown(fixture.close);
    Env.overrideApiBaseUrl(fixture.backend.baseUrl);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final urls = <Uri>[];
    final provider = createProductionActionItemsProvider(
      send: (request) async {
        final uri = Uri.parse(request.url);
        urls.add(uri);
        if (uri.path != '/v1/action-items') return fixture.send(request);
        final offset = int.parse(uri.queryParameters['offset'] ?? '0');
        final dueWindow = uri.queryParameters.containsKey('due_start_date');
        if (dueWindow) {
          return http.Response(
            jsonEncode({
              'action_items': [
                {
                  'id': 'due-today',
                  'description': 'due today',
                  'completed': false,
                  'due_at': DateTime.now().toUtc().toIso8601String(),
                },
              ],
              'has_more': false,
            }),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'action_items': [
              {
                'id': offset == 0 ? 'page-one' : 'page-two',
                'description': offset == 0 ? 'page one' : 'page two',
                'completed': false,
              },
            ],
            'has_more': offset == 0,
          }),
          200,
          headers: const {'content-type': 'application/json'},
        );
      },
    );
    addTearDown(provider.dispose);
    expect(provider.usesTypedActionItemsApi, isTrue);
    await provider.ensureLoaded();
    expect(provider.actionItems.map((item) => item.id), ['page-one']);
    await provider.loadMoreActionItems();
    expect(provider.actionItems.map((item) => item.id), ['page-one', 'page-two']);
    await provider.ensureHomeTodayTasksLoaded(now: DateTime.now());
    expect(provider.todayPreviewTasks(now: DateTime.now()).map((item) => item.id), ['due-today']);
    final listUrls = urls.where((uri) => uri.path == '/v1/action-items').toList();
    expect(listUrls.length, greaterThanOrEqualTo(3));
    expect(listUrls.any((uri) => uri.queryParameters['offset'] == '1'), isTrue);
    expect(listUrls.any((uri) => uri.queryParameters.containsKey('due_start_date')), isTrue);
    expect(listUrls.any((uri) => uri.queryParameters.containsKey('due_end_date')), isTrue);
  });

  test('typed Home today 503 does not pin empty and does not overwrite the list phase', () async {
    final fixture = await C3Fixture.start();
    addTearDown(fixture.close);
    Env.overrideApiBaseUrl(fixture.backend.baseUrl);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    var failDueWindow = true;
    final provider = createProductionActionItemsProvider(
      send: (request) async {
        final uri = Uri.parse(request.url);
        if (failDueWindow && uri.queryParameters.containsKey('due_start_date')) {
          fixture.backend.failNext('GET', '/v1/action-items', status: 503);
        }
        return fixture.send(request);
      },
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
    await provider.ensureHomeTodayTasksLoaded(now: DateTime.now());
    expect(provider.todayPreviewTasks(now: DateTime.utc(2026, 9, 18, 15)), isEmpty);
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
    failDueWindow = false;
    await provider.ensureHomeTodayTasksLoaded(now: DateTime.now());
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
  });
}
