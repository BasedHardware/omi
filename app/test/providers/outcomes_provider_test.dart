// ux-contract §17 Outcomes, audit 2026-11-19: a failure is never a value, and a write that fails
// says so. Provider- and helper-level cases for P1, G3, G4, T1, T4, T5, H2, V1/V5 and C6.
import 'package:flutter_test/flutter_test.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/conversation_detail/share_flow.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';

UserSubscriptionResponse _plan(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      phoneCallQuota: PhoneCallQuota(hasAccess: true, isPaid: plan != PlanType.basic),
    );

Goal _goal(String id) => Goal(
      id: id,
      title: id,
      goalType: 'numeric',
      targetValue: 10,
      currentValue: 3,
      minValue: 0,
      maxValue: 10,
      isActive: true,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

class _ThrowingWrites extends GoalWrites {
  const _ThrowingWrites();

  @override
  Future<bool> delete(String goalId) async => throw const FormatException('malformed answer');
}

class _FailingWrites extends GoalWrites {
  const _FailingWrites();

  @override
  Future<bool> delete(String goalId) async => false;

  @override
  Future<Goal?> progress(String goalId, double currentValue) async => null;
}

ActionItemWithMetadata _task(String id, {bool completed = false, bool locked = false, String? reminder}) =>
    ActionItemWithMetadata(
      id: id,
      description: id,
      completed: completed,
      isLocked: locked,
      appleReminderId: reminder,
    );

ServerConversation _row(String id, {bool discarded = false, String? piece}) => ServerConversation.fromJson({
      'id': id,
      'created_at': '2026-11-19T10:00:00Z',
      'started_at': '2026-11-19T10:00:00Z',
      'finished_at': '2026-11-19T10:10:00Z',
      'status': 'completed',
      'discarded': discarded,
      'structured': {'title': 't', 'overview': '', 'emoji': ''},
      'transcript_segments': const [],
      if (piece != null) ...{
        'kind': 'conversation',
        'recording_pieces': [
          {'recording_id': piece, 'audio_file_id': 'a1', 'start': 0.0, 'end': 60.0},
        ],
      },
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'outcome-user'});
    await SharedPreferencesUtil.init();
  });

  group('P1 Restore Purchases', () {
    test('a failed plan read is "failed", never the free plan', () async {
      final usage = UsageProvider(subscriptionRequest: () async => null);
      addTearDown(usage.dispose);
      expect(await usage.restorePurchases(), RestoreOutcome.failed);
    });

    test('a read that throws is "failed"', () async {
      final usage = UsageProvider(subscriptionRequest: () async => throw Exception('offline'));
      addTearDown(usage.dispose);
      expect(await usage.restorePurchases(), RestoreOutcome.failed);
    });

    test('a paid plan restores; a free plan says free', () async {
      final paid = UsageProvider(subscriptionRequest: () async => _plan(PlanType.unlimited));
      final free = UsageProvider(subscriptionRequest: () async => _plan(PlanType.basic));
      addTearDown(paid.dispose);
      addTearDown(free.dispose);
      expect(await paid.restorePurchases(), RestoreOutcome.paid);
      expect(await free.restorePurchases(), RestoreOutcome.free);
    });
  });

  group('Goals', () {
    test('G3: a failed load is loadFailed, not an empty list of goals', () async {
      final goals = GoalsProvider(goalsFetcher: () async => null);
      addTearDown(goals.dispose);
      await goals.loadGoals();
      expect(goals.goals, isEmpty);
      expect(goals.loadFailed, isTrue);

      final ok = GoalsProvider(goalsFetcher: () async => [_goal('a')]);
      addTearDown(ok.dispose);
      await ok.loadGoals();
      expect(ok.loadFailed, isFalse);
    });

    test('G4: a delete whose answer cannot be read puts the goal back and says it failed', () async {
      final goals = GoalsProvider(goalsFetcher: () async => [_goal('a')], writes: const _ThrowingWrites());
      addTearDown(goals.dispose);
      await goals.loadGoals();
      expect(await goals.deleteGoal('a'), isFalse);
      expect(goals.goals.map((g) => g.id), ['a']);
    });

    test('G1: a failed progress save answers null and keeps the saved value', () async {
      final goals = GoalsProvider(goalsFetcher: () async => [_goal('a')], writes: const _FailingWrites());
      addTearDown(goals.dispose);
      await goals.loadGoals();
      expect(await goals.updateGoalProgress('a', 8), isNull);
      expect(goals.goals.single.currentValue, 3);
    });
  });

  group('Tasks', () {
    late List<String> reminders;

    Future<ActionItemsProvider> tasks(
      List<ActionItemWithMetadata> rows, {
      bool deleteOk = true,
      bool failMore = false,
    }) async {
      reminders = [];
      var reads = 0;
      final p = ActionItemsProvider(
        getActionItems: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async {
          reads++;
          if (failMore && reads > 1) return null;
          return ActionItemsResponse(actionItems: List.of(rows), hasMore: failMore);
        },
        deleteActionItemRequest: (id) async => deleteOk,
        bulkDeleteActionItemsRequest: (ids) async => ids,
        deleteLinkedReminder: (item) => reminders.add(item.id),
      );
      await p.ensureLoaded();
      addTearDown(p.dispose);
      return p;
    }

    test('T1: a failed load-more is reported, not a list that just ends', () async {
      final p = await tasks([_task('a')], failMore: true);
      expect(p.hasMore, isTrue);
      await p.loadMoreActionItems();
      expect(p.loadMoreFailed, isTrue);
    });

    test('T1: a fresh first page clears a failed load-more, so scrolling pages again', () async {
      var failMore = true;
      var reads = 0;
      final p = ActionItemsProvider(
        getActionItems: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async {
          reads++;
          if (offset > 0 && failMore) return null;
          return ActionItemsResponse(actionItems: [_task('a')], hasMore: true);
        },
        deleteActionItemRequest: (id) async => true,
        bulkDeleteActionItemsRequest: (ids) async => ids,
        deleteLinkedReminder: (_) {},
      );
      addTearDown(p.dispose);
      await p.ensureLoaded();
      await p.loadMoreActionItems();
      expect(p.loadMoreFailed, isTrue);

      failMore = false;
      await p.forceRefreshActionItems();
      expect(reads, greaterThanOrEqualTo(3));
      expect(p.loadMoreFailed, isFalse);
    });

    test('T4: the Apple Reminder stays when the server refuses the delete', () async {
      final p = await tasks([_task('a', reminder: 'r1')], deleteOk: false);
      expect(await p.deleteActionItem(p.actionItems.single), isFalse);
      expect(reminders, isEmpty, reason: 'the task came back, so its Reminder must still exist');
      expect(p.actionItems.map((t) => t.id), ['a']);

      p.stageDeleteActionItem(p.actionItems.single);
      expect(await p.commitStagedDelete('a'), isFalse);
      expect(reminders, isEmpty);
    });

    test('T4: the Apple Reminder goes once the server confirmed', () async {
      final p = await tasks([_task('a', reminder: 'r1')]);
      expect(await p.deleteActionItem(p.actionItems.single), isTrue);
      expect(reminders, ['a']);
    });

    test('T5: locked tasks kept by design are not a failure', () async {
      final p = await tasks([_task('a', completed: true), _task('locked', completed: true, locked: true)]);
      final result = await p.clearSection(p.actionItems.where((t) => t.completed).toList());
      expect(result.failed, 0);
      expect(result.lockedKept, 1);
      expect(result.deleted, 1);
    });
  });

  test('H2: a reply cut off mid-stream keeps the words already shown', () async {
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('reply-1', 'The first half of the answer', MessageChunkType.data);
        throw Exception('connection dropped');
      };
    addTearDown(provider.dispose);
    provider.addMessageLocally('hello');
    await provider.sendMessageStreamToServer('hello');

    final reply = provider.messages.last;
    expect(provider.isReplyFailed(reply), isTrue);
    expect(reply.text, contains('The first half of the answer'));
    expect(provider.canRetryReply(reply), isTrue);
  });

  group('V1/V5 share', () {
    Future<(ShareFlowEnd, List<ConversationVisibility>)> share({
      bool wasPrivate = true,
      bool confirm = true,
      ShareResultStatus? status = ShareResultStatus.success,
      bool revertOk = true,
    }) async {
      final shown = <ConversationVisibility>[];
      final end = await runConversationShare(
        wasPrivate: wasPrivate,
        confirm: () async => confirm,
        setVisibility: (v) async => v == ConversationVisibility.shared || revertOk,
        onVisibility: shown.add,
        openSheet: () async => status ?? (throw Exception('sheet failed')),
      );
      return (end, shown);
    }

    test('shared after consent', () async {
      final (end, shown) = await share();
      expect(end, ShareFlowEnd.shared);
      expect(shown, [ConversationVisibility.shared]);
    });

    test('no consent changes nothing', () async {
      final (end, shown) = await share(confirm: false);
      expect(end, ShareFlowEnd.cancelled);
      expect(shown, isEmpty);
    });

    test('a dismissed sheet makes it private again', () async {
      final (end, shown) = await share(status: ShareResultStatus.dismissed);
      expect(end, ShareFlowEnd.dismissed);
      expect(shown, [ConversationVisibility.shared, ConversationVisibility.private_]);
    });

    test('a sheet that failed after it went public is reverted, and says "not shared"', () async {
      final (end, shown) = await share(status: null);
      expect(end, ShareFlowEnd.failed);
      expect(shown.last, ConversationVisibility.private_);
    });

    test('a revert that fails says it is still shared, never "not shared"', () async {
      final (end, shown) = await share(status: ShareResultStatus.dismissed, revertOk: false);
      expect(end, ShareFlowEnd.stillPublic);
      expect(shown, [ConversationVisibility.shared]);
    });
  });

  test('C6: a discarded conversation ends the processing page; a kept one wins', () {
    expect(FinishedCapturePage.discarded([_row('c1', discarded: true, piece: 'rec-1')], 'rec-1'), isTrue);
    expect(FinishedCapturePage.discarded([_row('rec-1', discarded: true)], 'rec-1'), isTrue);
    expect(
      FinishedCapturePage.discarded([_row('c1', discarded: true, piece: 'rec-1'), _row('c2', piece: 'rec-1')], 'rec-1'),
      isFalse,
    );
    expect(FinishedCapturePage.discarded([_row('c9', discarded: true, piece: 'other')], 'rec-1'), isFalse);
  });
}
