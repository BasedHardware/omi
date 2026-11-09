import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

import 'journeys/support/hermetic_boot.dart';
import 'journeys/support/fixture_backend.dart';

class _PausedAuthGateway extends ScriptableGateway {
  _PausedAuthGateway() : super(user: const AuthUserSnapshot(uid: JourneyFixtureBackend.fixtureUid));
  final started = Completer<void>();
  final response = Completer<RefreshedAuthToken?>();

  @override
  Future<RefreshedAuthToken?> forceRefresh() {
    if (!started.isCompleted) started.complete();
    return response.future;
  }
}

/// Real swipe/Undo UI, HTTP adapter and persisted owner projection on loopback.
/// No production accounts, recordings, credentials or backend are used.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> waitFor(WidgetTester tester, bool Function() condition) async {
    for (var attempt = 0; attempt < 100 && !condition(); attempt++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pump();
    }
    expect(condition(), isTrue, reason: 'bounded memory-deletion operation must settle');
    await tester.pumpAndSettle();
  }

  testWidgets('swipe, Undo, refusal, retry and offline reopen preserve the right rows', (tester) async {
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    final provider = MemoriesProvider();
    addTearDown(provider.dispose);
    expect(await tester.runAsync(() => provider.createMemory('Synthetic memory for deletion')), isTrue);
    final row = provider.memories.single;
    final path = '/v3/memories/${row.id}';

    await JourneyHermeticBoot.pumpPage(tester,
        page: Scaffold(
          appBar: AppBar(title: const Text('Memories')),
          body: AnimatedBuilder(
            animation: provider,
            builder: (context, _) => ListView(
              children: provider.memories
                  .map((memory) => MemoryItem(memory: memory, provider: provider, onTap: (_, __, ___) {}))
                  .toList(),
            ),
          ),
        ));

    Future<void> swipe() async {
      await tester.drag(find.byKey(Key(row.id)), const Offset(-700, 0));
      await tester.pumpAndSettle();
    }

    await swipe();
    expect(provider.memories, isEmpty);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(provider.memories.single.id, row.id);
    expect(server.countOf('DELETE', path), 0);

    server.failNext('DELETE', path, status: 503);
    server.failNext('DELETE', path, status: 503); // The real HTTP adapter retries a 5xx once.
    await swipe();
    await tester.pump(const Duration(seconds: 6));
    await waitFor(tester, () => provider.memories.isNotEmpty);
    expect(server.countOf('DELETE', path), 2);
    expect(find.text('Failed to delete items'), findsOneWidget);
    expect(server.memories, hasLength(1));

    await swipe();
    await tester.pump(const Duration(seconds: 6));
    await waitFor(tester, () => SharedPreferencesUtil().confirmedMemoryDeletionIds.contains(row.id));
    expect(server.countOf('DELETE', path), 3);
    expect(server.memories, isEmpty);
    expect(provider.memories, isEmpty);
    expect(SharedPreferencesUtil().cachedMemories, isEmpty);

    final reopened = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true, failureReason: MemoriesFetchFailureReason.noResponse),
    );
    addTearDown(reopened.dispose);
    await reopened.loadMemories();
    expect(reopened.loadFailed, isTrue);
    expect(reopened.memories, isEmpty);
  });

  for (final status in [404, 403]) {
    testWidgets('DELETE $status is ${status == 404 ? 'idempotent absence' : 'a refusal that restores the row'}',
        (tester) async {
      final server = await JourneyHermeticBoot.start();
      addTearDown(JourneyHermeticBoot.stop);
      final provider = MemoriesProvider();
      addTearDown(provider.dispose);
      await tester.runAsync(() => provider.createMemory('Synthetic response case'));
      final row = provider.memories.single;
      final path = '/v3/memories/${row.id}';
      if (status == 404) server.memories.clear();
      server.failNext('DELETE', path, status: status);
      var failures = 0;
      await provider.deleteMemory(row, onFailure: () => failures++);
      await tester.runAsync(() => provider.confirmPendingDeletion(id: row.id));
      expect(server.countOf('DELETE', path), 1);
      expect(provider.memories, hasLength(status == 404 ? 0 : 1));
      expect(failures, status == 404 ? 0 : 1);
    });
  }
  for (final action in ['create', 'delete']) {
    testWidgets('retired owner cannot send a memory $action after delayed authentication', (tester) async {
      final server = await JourneyHermeticBoot.start();
      addTearDown(JourneyHermeticBoot.stop);
      final provider = MemoriesProvider();
      addTearDown(provider.dispose);
      await tester.runAsync(() => provider.createMemory('Synthetic authentication fence'));
      final row = provider.memories.single;
      final path = action == 'create' ? '/v3/memories' : '/v3/memories/${row.id}';
      final method = action == 'create' ? 'POST' : 'DELETE';
      final countBefore = server.countOf(method, path);
      final gateway = _PausedAuthGateway();
      AuthService.installLocalHarnessTokenGateway(gateway);
      SharedPreferencesUtil().tokenExpirationTime = 1;
      late Future<dynamic> operation;
      if (action == 'create') {
        operation = provider.createMemory('Must not cross the owner boundary');
      } else {
        await provider.deleteMemory(row);
        operation = provider.confirmPendingDeletion(id: row.id);
      }
      await tester.runAsync(() => gateway.started.future.timeout(const Duration(seconds: 5)));
      provider.clearUserData();
      SharedPreferencesUtil().uid = 'replacement-owner';
      gateway.response.complete(RefreshedAuthToken(
        token: JourneyHermeticBoot.fixtureToken,
        expirationTime: DateTime.now().add(const Duration(hours: 1)),
      ));
      await tester.runAsync(() => operation);
      expect(server.countOf(method, path), countBefore, reason: 'retired work must stop before HTTP dispatch');
      expect(provider.memories, isEmpty);
    });
  }
}
