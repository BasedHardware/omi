import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

import '../mobile/native_ui/native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

Memory _memory({required String id, String content = 'Prefers async standups', bool? userReview, bool edited = false}) {
  return Memory(
    id: id,
    uid: 'review-controller-user',
    content: content,
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 9, 1),
    updatedAt: DateTime.utc(2026, 9, 1),
    visibility: MemoryVisibility.private,
    userReview: userReview,
    edited: edited,
  );
}

MemoryReviewItem _item(String id, {String content = 'Prefers async standups'}) =>
    MemoryReviewItem(memoryId: id, content: content, category: 'work');

MemoriesProvider _provider(
  List<Memory> rows, {
  ReviewMemoryRequest? review,
  EditMemoryRequest? edit,
}) {
  return MemoriesProvider(
    fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
        GetMemoriesResult(List<Memory>.from(rows), true),
    fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
        const GetLedgerHistoryResult([], supported: true),
    reviewMemoryRequest: review ?? (id, value) async => true,
    editMemoryRequest: edit ?? (id, value) async => const EditMemoryResult(persisted: true),
  );
}

class _Analytics implements AnalyticsAdapter {
  final events = <String>[];
  bool _ready = false;

  @override
  Future<void> init() async => _ready = true;
  @override
  bool get isInitialized => _ready;
  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}
  @override
  void alias({required String newUserId}) {}
  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);
  @override
  void enable() {}
  @override
  void disable() {}
  @override
  void reset() {}
  @override
  void registerSuperProperties(Map<String, Object> properties) {}
  @override
  void setInteractionContext({String? screenName, required String target}) {}
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'review-controller-user'});
    await SharedPreferencesUtil.init();
  });

  group('MemoryReviewController', () {
    test('a verdict paints optimistically and reverts with a failure when it does not persist', () async {
      final answer = Completer<bool>();
      final provider = _provider([_memory(id: 'mem-1')], review: (id, value) => answer.future);
      addTearDown(provider.dispose);
      await provider.loadMemories();
      final controller = MemoryReviewController(items: [_item('mem-1')], source: MemoryReviewSource.chatBlock);
      addTearDown(controller.dispose);
      final memory = controller.memoryFor(provider, 'mem-1');

      final review = controller.review(provider, _item('mem-1'), memory, true);
      expect(controller.stateFor(provider, memory, 'mem-1'), MemoryReviewRowState.confirmed);
      expect(controller.isInFlight('mem-1'), isTrue);
      answer.complete(false);
      await review;

      expect(controller.isInFlight('mem-1'), isFalse);
      expect(controller.isFailed('mem-1'), isTrue);
      expect(controller.stateFor(provider, controller.memoryFor(provider, 'mem-1'), 'mem-1'),
          MemoryReviewRowState.pending);
    });

    test('a persisted correction whose row moved to a new id still reads as the corrected text', () async {
      final provider = _provider(const []);
      addTearDown(provider.dispose);
      await provider.loadMemories();
      final controller = MemoryReviewController(items: [_item('mem-old')], source: MemoryReviewSource.chatBlock);
      addTearDown(controller.dispose);

      expect(await controller.saveEdit(provider, _item('mem-old'), null, 'Prefers written standups'), isTrue);
      expect(controller.stateFor(provider, null, 'mem-old'), MemoryReviewRowState.updated);
      expect(controller.contentOf(_item('mem-old'), null), 'Prefers written standups');
    });

    test('an edit that does not persist is marked failed and saves nothing for an empty value', () async {
      final edits = <String>[];
      final provider = _provider([_memory(id: 'mem-1')], edit: (id, value) async {
        edits.add(value);
        return const EditMemoryResult(persisted: false);
      });
      addTearDown(provider.dispose);
      await provider.loadMemories();
      final controller = MemoryReviewController(items: [_item('mem-1')], source: MemoryReviewSource.chatBlock);
      addTearDown(controller.dispose);
      final memory = controller.memoryFor(provider, 'mem-1');

      expect(await controller.saveEdit(provider, _item('mem-1'), memory, ''), isFalse);
      expect(edits, isEmpty);
      expect(await controller.saveEdit(provider, _item('mem-1'), memory, 'Edited'), isFalse);
      expect(edits, ['Edited']);
      expect(controller.isFailed('mem-1'), isTrue);
      controller.clearFailed('mem-1');
      expect(controller.isFailed('mem-1'), isFalse);
    });

    test('the shown impression counts once per card identity', () async {
      AnalyticsManager.resetForTesting();
      addTearDown(AnalyticsManager.resetForTesting);
      final analytics = _Analytics();
      AnalyticsManager.configure(analytics);
      await AnalyticsManager.init();
      analytics.events.clear();

      for (var i = 0; i < 3; i++) {
        MemoryReviewController(
                items: [_item('mem-1')], source: MemoryReviewSource.chatBlock, impressionKey: 'dedupe-card')
            .dispose();
      }
      MemoryReviewController(items: const [], source: MemoryReviewSource.chatBlock, impressionKey: 'empty').dispose();
      MemoryReviewController(items: [_item('mem-1')], source: MemoryReviewSource.chatBlock, impressionKey: 'other-card')
          .dispose();
      final deferred = MemoryReviewController(
          items: [_item('mem-1')], source: MemoryReviewSource.chatBlock, impressionKey: 'deferred-card', shown: false);
      await AnalyticsManager.flushPending(force: true);
      expect(analytics.events.where((event) => event == 'memory_review_card_shown'), hasLength(2),
          reason: 'once per identity, and not before a deferred card is shown');
      deferred
        ..recordShown()
        ..recordShown()
        ..dispose();
      await AnalyticsManager.flushPending(force: true);
      expect(analytics.events.where((event) => event == 'memory_review_card_shown'), hasLength(3));
    });
  });

  group('native review rows', () {
    late List<NativeRow> rows;

    Future<MemoryReviewController> pump(
        WidgetTester tester, MemoriesProvider? provider, List<MemoryReviewItem> items) async {
      final controller = MemoryReviewController(items: items, source: MemoryReviewSource.chatBlock);
      addTearDown(controller.dispose);
      Widget app = MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: ListenableBuilder(
          listenable: controller,
          builder: (context, _) {
            rows = nativeMemoryReviewRows(context, controller,
                id: (part, index) => 'chat_${part}_m1_$index', header: 'Learned');
            return const Scaffold(body: SizedBox());
          },
        ),
      );
      app = ChangeNotifierProvider(
          create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {}), child: app);
      if (provider != null) app = ChangeNotifierProvider<MemoriesProvider>.value(value: provider, child: app);
      await tester.pumpWidget(app);
      await tester.pump();
      return controller;
    }

    testWidgets('a pending row offers Right, Wrong and Fix; a settled one is a status label', (tester) async {
      final provider = _provider([_memory(id: 'mem-1'), _memory(id: 'mem-2', userReview: true)]);
      addTearDown(provider.dispose);
      await provider.loadMemories();
      await pump(tester, provider, [_item('mem-1'), _item('mem-2')]);

      expect(rows.map((row) => row.id), ['chat_reviewtitle_m1_0', 'chat_review_m1_0', 'chat_review_m1_1']);
      expect(rows.every((row) => row.valid), isTrue);
      expect(rows.any((row) => row.id.contains('mem-')), isFalse);
      final pending = rows[1];
      expect(pending.kind, 'menu');
      expect(pending.options,
          {'right': _l10n.memoryReviewRight, 'wrong': _l10n.memoryReviewWrong, 'fix': _l10n.memoryReviewFix});
      final settled = rows[2];
      expect(settled.kind, 'label');
      expect(settled.subtitle, '${_l10n.memoryReviewConfirmed}\nWork');

      await pending.action!('wrong');
      await tester.pump();
      expect(rows[1].kind, 'label');
      expect(rows[1].subtitle, '${_l10n.memoryReviewDropped}\nWork');
    });

    testWidgets('without a memories owner every row is a plain label', (tester) async {
      await pump(tester, null, [_item('mem-1')]);
      expect(rows.where((row) => row.id.startsWith('chat_review_')).single.kind, 'label');
    });

    testWidgets('Fix saves only on Save, with the edited text', (tester) async {
      NativeTestHost.install();
      final edits = <String>[];
      final provider = _provider([_memory(id: 'mem-1')], edit: (id, value) async {
        edits.add(value);
        return const EditMemoryResult(persisted: true);
      });
      addTearDown(provider.dispose);
      await provider.loadMemories();
      await pump(tester, provider, [_item('mem-1')]);
      final replies = <Map<String, Object?>>[
        {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'},
        {
          'action': 'save',
          'values': {'memory_fix_text': '  Prefers written standups  '},
          'reason': 'action',
        },
      ];
      final presented = <Map>[];
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_config, (call) async {
        if (call.method != 'present') return null;
        presented.add((call.arguments as Map)['snapshot'] as Map);
        return replies[presented.length - 1];
      });
      addTearDown(() => messenger.setMockMethodCallHandler(_config, null));

      await rows[1].action!('fix');
      await tester.pump();
      expect(edits, isEmpty, reason: 'Cancel writes nothing');
      final field = ((presented.single['sections'] as List).single['rows'] as List).single as Map;
      expect(field['value'], 'Prefers async standups');
      expect(field['maximumLength'], 10000);

      await rows[1].action!('fix');
      await tester.pump();
      expect(edits, ['Prefers written standups']);
    });
  });
}
