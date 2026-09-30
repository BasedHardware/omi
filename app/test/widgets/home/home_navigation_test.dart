import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/http/api/memories.dart' show GetMemoriesResult;
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/home/home_deep_links.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/home/home_prompt_gate.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/enums.dart';

/// Home shell navigation: links open inside the one Home (nav #3, #18), prompts wait while the
/// person is busy (onboarding-home #23), and Settings changes are compared after the sheet closes
/// (onboarding-home #25).
void main() {
  group('HomeDeepLink.parse', () {
    test('splits alias, id and query', () {
      final link = HomeDeepLink.parse('/conversation/abc?share=1')!;
      expect(link.alias, 'conversation');
      expect(link.id, 'abc');
      expect(link.query['share'], '1');
    });

    test('preserves reserved characters in an encoded Siri chat draft', () {
      final link = HomeDeepLink.parse(
        '/chat?draft=What%20is%20A%26B%20%3D%20C%2BD%20%23100%25%3F%20%F0%9F%98%80',
      )!;
      expect(link.alias, 'chat');
      expect(link.query['draft'], 'What is A&B = C+D #100%? 😀');
    });

    test('accepts a route without a leading slash and ignores empty segments', () {
      final link = HomeDeepLink.parse('apps//xyz')!;
      expect(link.alias, 'apps');
      expect(link.id, 'xyz');
    });

    test('null or empty routes are not links', () {
      expect(HomeDeepLink.parse(null), isNull);
      expect(HomeDeepLink.parse(''), isNull);
      expect(HomeDeepLink.parse('/'), isNull);
    });

    test('selects the parent tab before the page', () {
      // Two pages now: conversations, memories and search open over Home; tasks over Tasks.
      expect(HomeDeepLink.parse('/conversations')!.tabIndex, HomeProvider.homeTab);
      // Live Activity links open over Home; index 1 is now Tasks.
      final capture = HomeDeepLink.parse('/capture?recording=active-session')!;
      expect(capture.tabIndex, HomeProvider.homeTab);
      expect(capture.query['recording'], 'active-session');
      expect(HomeDeepLink.parse('/action-items')!.tabIndex, HomeProvider.tasksTab);
      expect(HomeDeepLink.parse('/apps/xyz')!.tabIndex, isNull, reason: 'the app catalog is not a tab any more');
      expect(HomeDeepLink.parse('/memories')!.tabIndex, HomeProvider.homeTab);
      expect(HomeDeepLink.parse('/conversation/abc')!.tabIndex, HomeProvider.homeTab);
      expect(HomeDeepLink.parse('/memory/m-1')!.tabIndex, HomeProvider.homeTab);
      expect(HomeDeepLink.parse('/task/t-1')!.tabIndex, HomeProvider.tasksTab);
      expect(HomeDeepLink.parse('/search?q=meeting')!.tabIndex, HomeProvider.homeTab);
    });
  });

  group('promptsBlocked', () {
    bool blocked({
      RecordingState recording = RecordingState.stop,
      bool batch = false,
      bool micInterrupted = false,
      PhoneCallState call = PhoneCallState.idle,
      bool firmware = false,
    }) =>
        promptsBlocked(
          recordingState: recording,
          phoneMicBatchRecording: batch,
          micInterruptedByCall: micInterrupted,
          callState: call,
          firmwareUpdateInProgress: firmware,
        );

    test('idle, passive wearable capture and a muted pendant do not hold prompts', () {
      expect(blocked(), isFalse);
      expect(blocked(recording: RecordingState.deviceRecord), isFalse);
      expect(blocked(recording: RecordingState.pause), isFalse);
    });

    test('recording, a call or a firmware update holds prompts', () {
      expect(blocked(recording: RecordingState.record), isTrue);
      expect(blocked(recording: RecordingState.initialising), isTrue);
      expect(blocked(recording: RecordingState.systemAudioRecord), isTrue);
      expect(blocked(batch: true), isTrue);
      expect(blocked(micInterrupted: true), isTrue);
      expect(blocked(call: PhoneCallState.active), isTrue);
      expect(blocked(call: PhoneCallState.ringing), isTrue);
      expect(blocked(firmware: true), isTrue);
    });
  });

  group('HomeNavigation', () {
    tearDown(() {
      // Nothing registered leaks into the next test.
      HomeNavigation.unregister(_record);
    });

    testWidgets('openRoute pops to the existing Home and lets it open the page', (tester) async {
      final navigatorKey = GlobalKey<NavigatorState>();
      await tester.pumpWidget(MaterialApp(navigatorKey: navigatorKey, home: const Text('home')));
      navigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => const Text('conversation')));
      await tester.pumpAndSettle();
      expect(find.text('conversation'), findsOneWidget);

      _opened.clear();
      HomeNavigation.register(_record);
      final opened = await HomeNavigation.openRoute('/chat/omi', navigator: navigatorKey.currentState);
      await tester.pumpAndSettle();

      expect(opened, isTrue);
      expect(_opened, ['/chat/omi']);
      expect(find.text('home'), findsOneWidget);
      expect(find.text('conversation'), findsNothing);
    });

    testWidgets('openRoute drops the link when no Home appears', (tester) async {
      await tester.runAsync(() async {
        final opened = await HomeNavigation.openRoute(
          '/chat/omi',
          timeout: const Duration(milliseconds: 60),
          pollInterval: const Duration(milliseconds: 10),
        );
        expect(opened, isFalse);
      });
    });
  });

  testWidgets('indexed task opens by backend id outside the visible filtered page', (tester) async {
    const task = ActionItemWithMetadata(id: 'task-150', description: 'Older indexed task', completed: false);
    final provider = ActionItemsProvider(
      getActionItems: (
              {limit = 100,
              offset = 0,
              completed,
              conversationId,
              startDate,
              endDate,
              dueStartDate,
              dueEndDate}) async =>
          const ActionItemsResponse(actionItems: [], hasMore: false),
    );
    addTearDown(provider.dispose);
    final opened = <String>[];
    final requested = <String>[];
    await tester.pumpWidget(ChangeNotifierProvider<ActionItemsProvider>.value(
      value: provider,
      child: const MaterialApp(home: SizedBox(key: Key('task-link-home'))),
    ));
    final context = tester.element(find.byKey(const Key('task-link-home')));

    await openHomeDeepLink(context, const HomeDeepLink('task', id: 'task-150'),
        openSettings: () async {},
        taskById: (id) async {
          requested.add(id);
          return task;
        },
        onTaskOpened: (item) => opened.add(item.id));

    expect(requested, ['task-150']);
    expect(opened, ['task-150']);
  });

  testWidgets('indexed memory opens by backend id outside the visible filter', (tester) async {
    final now = DateTime.now();
    final memory = Memory(
      id: 'memory-hidden-by-filter',
      uid: 'owner',
      content: 'Private remembered fact',
      category: MemoryCategory.manual,
      createdAt: now,
      updatedAt: now,
      visibility: MemoryVisibility.private,
    );
    final provider = MemoriesProvider();
    addTearDown(provider.dispose);
    final requested = <String>[];
    final opened = <String>[];
    await tester.pumpWidget(ChangeNotifierProvider<MemoriesProvider>.value(
      value: provider,
      child: const MaterialApp(home: SizedBox(key: Key('memory-link-home'))),
    ));
    final context = tester.element(find.byKey(const Key('memory-link-home')));
    await openHomeDeepLink(
      context,
      const HomeDeepLink('memory', id: 'memory-hidden-by-filter'),
      openSettings: () async {},
      memoryById: (id) async {
        requested.add(id);
        return memory;
      },
      onMemoryOpened: (row) => opened.add(row.id),
    );
    expect(requested, ['memory-hidden-by-filter']);
    expect(opened, ['memory-hidden-by-filter']);
  });

  testWidgets('stale indexed task link does not open a cancelled task', (tester) async {
    const cancelled = ActionItemWithMetadata(
      id: 'cancelled-task',
      description: 'No longer visible',
      completed: false,
      status: 'cancelled',
    );
    final opened = <String>[];
    var unavailable = 0;
    await tester.pumpWidget(const MaterialApp(home: SizedBox(key: Key('stale-task-home'))));
    final context = tester.element(find.byKey(const Key('stale-task-home')));
    await openHomeDeepLink(context, const HomeDeepLink('task', id: 'cancelled-task'),
        openSettings: () async {},
        taskById: (_) async => cancelled,
        onTaskOpened: (row) => opened.add(row.id),
        onItemUnavailable: () => unavailable++);
    expect(opened, isEmpty);
    expect(unavailable, 1);
  });

  test('indexed memory resolver follows owner-wide cursors beyond the visible page', () async {
    final now = DateTime.now();
    Memory memory(String id, {String uid = 'owner', MemoryLayer? layer}) => Memory(
          id: id,
          uid: uid,
          content: id,
          category: MemoryCategory.manual,
          createdAt: now,
          updatedAt: now,
          visibility: MemoryVisibility.private,
          layer: layer,
        );
    final cursors = <String?>[];
    final found = await resolveIndexedMemoryById('target',
        uid: 'owner',
        ownerIsCurrent: () => true,
        fetchPage: ({required limit, required offset, cursor}) async {
          cursors.add(cursor);
          return cursor == null
              ? GetMemoriesResult([memory('other')], true, nextCursor: 'second')
              : GetMemoriesResult([memory('target')], true);
        });
    expect(cursors, [null, 'second']);
    expect(found?.id, 'target');

    final archived = await resolveIndexedMemoryById('target',
        uid: 'owner',
        ownerIsCurrent: () => true,
        fetchPage: ({required limit, required offset, cursor}) async =>
            GetMemoriesResult([memory('target', layer: MemoryLayer.archive)], true));
    expect(archived, isNull);

    final foreign = await resolveIndexedMemoryById('target',
        uid: 'owner',
        ownerIsCurrent: () => true,
        fetchPage: ({required limit, required offset, cursor}) async =>
            GetMemoriesResult([memory('target', uid: 'other')], true));
    expect(foreign, isNull);

    var stillCurrent = true;
    final switched = await resolveIndexedMemoryById('target',
        uid: 'owner',
        ownerIsCurrent: () => stillCurrent,
        fetchPage: ({required limit, required offset, cursor}) async {
          stillCurrent = false;
          return GetMemoriesResult([memory('target')], true);
        });
    expect(switched, isNull);
  });
}

final List<String> _opened = [];

Future<void> _record(String route) async => _opened.add(route);
