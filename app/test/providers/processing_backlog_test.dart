import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';

UserSubscriptionResponse subscription({ProcessingBacklog? backlog}) => UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.plus, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 3600,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      processingBacklog: backlog,
    );

void main() {
  test('flags-off responses preserve absence; backlog survives cache round trip', () {
    expect(UserSubscriptionResponse.fromJson(subscription().toJson()).processingBacklog, isNull);
    final input = ProcessingBacklog.fromJson({
      'state': 'waiting_choice',
      'held_audio_count': 3,
      'held_audio_seconds': 7200,
      'deferred_conversations': 2,
      'deferred_seconds': 1800,
      'estimated_units': 12.25,
      'estimated_hours': 1.75,
      'estimated_percent': 22.5,
      'remaining_units': 10,
      'exceeds_remaining': true,
      'processable_count': 2,
    });
    final parsed = UserSubscriptionResponse.fromJson(subscription(backlog: input).toJson()).processingBacklog!;
    expect(parsed.toJson(), input.toJson());
    expect(parsed.estimatedHours, 1.75);
    expect(parsed.waitingSeconds, 9000);
    expect(parsed.exceedsRemaining, true);
  });

  test('unlimited remaining allowance stays null and missing deferred duration defaults zero', () {
    final backlog = ProcessingBacklog.fromJson({
      'state': 'waiting_choice',
      'remaining_units': null,
      'held_audio_seconds': 120,
      'estimated_hours': 10,
      'exceeds_remaining': false
    });
    expect(backlog.remainingUnits, isNull);
    expect(backlog.toJson()['remaining_units'], isNull);
    expect(backlog.deferredSeconds, 0);
    expect(backlog.waitingSeconds, 120);
    expect(backlog.exceedsRemaining, false);
  });

  test('uncertain retries reuse UUID until definite success, then the next action gets a new UUID', () async {
    final keys = <String>[];
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) async {
      keys.add(idempotencyKey);
      if (keys.length == 1) throw StateError('lost reply');
      if (keys.length == 2) return null;
      return const ProcessingBacklog(state: 'waiting_choice');
    });
    addTearDown(usage.dispose);
    final waiting = subscription(backlog: const ProcessingBacklog(state: 'waiting_choice'));
    usage.debugSetSubscription(waiting);
    expect(await usage.processBacklog(), false);
    usage.debugSetSubscription(waiting); // A subscription refresh cannot mint a new identity.
    expect(await usage.processBacklog(), false);
    expect(await usage.processBacklog(), true);
    expect(keys.take(3).toSet(), hasLength(1));
    expect(keys.first, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
    expect(await usage.processBacklog(), true);
    expect(keys.last, isNot(keys.first));
  });

  test('cancel/new decision and auth session reset each end an uncertain retry identity', () async {
    final keys = <String>[];
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) async {
      keys.add(idempotencyKey);
      return null;
    });
    addTearDown(usage.dispose);
    final waiting = subscription(backlog: const ProcessingBacklog(state: 'waiting_choice'));
    usage.debugSetSubscription(waiting);
    expect(await usage.processBacklog(), false);
    usage.cancelBacklogDecision();
    expect(await usage.processBacklog(), false);
    usage.clearUserData();
    usage.debugSetSubscription(waiting);
    expect(await usage.processBacklog(), false);
    expect(keys.toSet(), hasLength(3));
  });

  test('another surface cannot cancel an in-flight retry identity', () async {
    final keys = <String>[];
    final response = Completer<ProcessingBacklog?>();
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) {
      keys.add(idempotencyKey);
      return response.future;
    });
    addTearDown(usage.dispose);
    usage.debugSetSubscription(subscription(backlog: const ProcessingBacklog(state: 'waiting_choice')));
    final pending = usage.processBacklog();
    usage.cancelBacklogDecision();
    response.complete(null);
    expect(await pending, false);
    expect(await usage.processBacklog(), false);
    expect(keys.toSet(), hasLength(1));
  });

  test('only explicit waiting choice starts; concurrent calls deduplicate and use server snapshot', () async {
    var calls = 0;
    final response = Completer<ProcessingBacklog?>();
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) {
      calls++;
      return response.future;
    });
    addTearDown(usage.dispose);
    for (final state in ['capped', 'processing', 'none']) {
      usage.debugSetSubscription(subscription(backlog: ProcessingBacklog(state: state)));
      expect(await usage.processBacklog(), false);
    }
    usage.debugSetSubscription(subscription(backlog: const ProcessingBacklog(state: 'waiting_choice')));
    expect(calls, 0, reason: 'a reset or upgrade response must not start the backlog');
    final pending = usage.processBacklog();
    expect(usage.isProcessingBacklog, true);
    expect(await usage.processBacklog(), false);
    response.complete(const ProcessingBacklog(state: 'processing', deferredConversations: 2));
    expect(await pending, true);
    expect(calls, 1);
    expect(usage.subscription!.processingBacklog!.state, 'processing');
    expect(usage.isProcessingBacklog, false);
  });

  test('an older subscription fetch cannot replace the explicit processing snapshot', () async {
    final response = Completer<UserSubscriptionResponse?>();
    final usage = UsageProvider(
        subscriptionRequest: () => response.future,
        processBacklogRequest: ({required idempotencyKey}) async => const ProcessingBacklog(state: 'processing'));
    addTearDown(usage.dispose);
    final waiting = subscription(backlog: const ProcessingBacklog(state: 'waiting_choice'));
    usage.debugSetSubscription(waiting);
    final refresh = usage.fetchSubscription();
    expect(await usage.processBacklog(), true);
    response.complete(waiting);
    await refresh;
    expect(usage.subscription!.processingBacklog!.state, 'processing');
  });

  test('failed processing keeps choice and allows retry', () async {
    var calls = 0;
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) async {
      calls++;
      if (calls == 1) throw StateError('offline');
      return const ProcessingBacklog(state: 'processing');
    });
    addTearDown(usage.dispose);
    usage.debugSetSubscription(subscription(backlog: const ProcessingBacklog(state: 'waiting_choice')));
    expect(await usage.processBacklog(), false);
    expect(usage.subscription!.processingBacklog!.isWaitingChoice, true);
    expect(usage.isProcessingBacklog, false);
    expect(await usage.processBacklog(), true);
  });

  test('logout drops in-flight processing response', () async {
    final response = Completer<ProcessingBacklog?>();
    final usage = UsageProvider(processBacklogRequest: ({required idempotencyKey}) => response.future);
    addTearDown(usage.dispose);
    usage.debugSetSubscription(subscription(backlog: const ProcessingBacklog(state: 'waiting_choice')));
    final pending = usage.processBacklog();
    usage.clearUserData();
    usage.debugSetSubscription(subscription());
    response.complete(const ProcessingBacklog(state: 'processing'));
    expect(await pending, false);
    expect(usage.subscription!.processingBacklog, isNull);
    expect(usage.isProcessingBacklog, false);
  });

  test('processing_deferred defaults false and survives conversation persistence', () {
    final original = ServerConversation(
        id: 'deferred', createdAt: DateTime.utc(2026), structured: Structured('', ''), processingDeferred: true);
    expect(ServerConversation.fromJson(original.toJson()).processingDeferred, true);
    final legacy = Map<String, dynamic>.from(original.toJson())..remove('processing_deferred');
    expect(ServerConversation.fromJson(legacy).processingDeferred, false);
  });
}
