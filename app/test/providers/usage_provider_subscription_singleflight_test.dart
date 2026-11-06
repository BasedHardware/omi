import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';

UserSubscriptionResponse _subscription(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('fetchSubscription single-flights: a second caller awaits the real in-flight request', () async {
    var requests = 0;
    Completer<UserSubscriptionResponse?>? gate;
    final provider = UsageProvider(subscriptionRequest: () {
      requests++;
      gate = Completer<UserSubscriptionResponse?>();
      return gate!.future;
    });

    // Onboarding (wrapper.dart) starts the fetch on sign-in...
    final first = provider.fetchSubscription();
    // ...and AppShell's `_subscriptionReady` joins the same request instead of
    // receiving an already-completed no-op future.
    final second = provider.fetchSubscription();

    expect(requests, 1, reason: 'the second caller must not issue another request');
    expect(identical(first, second), isTrue, reason: 'the `unlimited` deep link must await the real in-flight fetch');

    await Future<void>.delayed(Duration.zero);
    expect(provider.isLoading, isTrue, reason: 'the joined future must not resolve early');
    expect(provider.subscription, isNull, reason: 'a paywall decision must not be made before the server responds');

    gate!.complete(_subscription(PlanType.unlimited));
    await second;

    expect(provider.subscription, isNotNull);
    expect(provider.isLoading, isFalse);
    provider.dispose();
  });

  test('after the fetch settles, a new call issues a fresh request', () async {
    var requests = 0;
    final responses = <UserSubscriptionResponse?>[_subscription(PlanType.unlimited)];
    final provider = UsageProvider(
        subscriptionRequest: () async => responses.length > requests++ ? responses[0] : _subscription(PlanType.basic));

    await provider.fetchSubscription();
    await provider.fetchSubscription();

    expect(requests, 2);
    provider.dispose();
  });

  test('clearUserData detaches the in-flight fetch so the next session cannot join it', () async {
    var requests = 0;
    Completer<UserSubscriptionResponse?>? gate;
    final provider = UsageProvider(subscriptionRequest: () {
      requests++;
      gate = Completer<UserSubscriptionResponse?>();
      return gate!.future;
    });

    final stale = provider.fetchSubscription();
    provider.clearUserData();
    gate!.complete(_subscription(PlanType.unlimited));
    await stale;

    // The next account must issue its own request, not await the stale one.
    final next = provider.fetchSubscription();
    expect(requests, 2);
    gate!.complete(_subscription(PlanType.basic));
    await next;
    expect(provider.subscription?.subscription.plan, PlanType.basic);
    provider.dispose();
  });
}
