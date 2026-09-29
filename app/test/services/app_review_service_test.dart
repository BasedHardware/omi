import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/services/app_review_service.dart';

void main() {
  late DateTime now;
  late SharedPreferences preferences;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    preferences = await SharedPreferences.getInstance();
    now = DateTime(2026, 9, 22, 12);
  });

  AppReviewService service({
    String platform = 'ios',
    String version = '1.2+99',
    Future<bool> Function()? isAvailable,
    Future<void> Function()? requestNativeReview,
    Future<bool> Function(String key, String value)? writeState,
    Future<Duration> Function()? cooldown,
    AppReviewTelemetry? telemetry,
  }) {
    return AppReviewService.forTesting(
      storage: preferences,
      clock: () => now,
      platform: platform,
      appVersion: version,
      isAvailable: isAvailable,
      requestNativeReview: requestNativeReview,
      writeState: writeState,
      cooldown: cooldown,
      telemetry: telemetry,
    );
  }

  test('bad experience stores only a timestamp per category', () async {
    final reviewService = service();
    await reviewService.recordBadExperience(AppReviewBadExperience.negativeChatRating);

    final raw = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
    expect(raw['badExperiences'], {'negativeChatRating': now.millisecondsSinceEpoch});
    expect(raw.containsKey('conversation'), isFalse);
  });

  for (final category in AppReviewBadExperience.values) {
    test('$category suppresses requests for three days across service instances', () async {
      final writer = service();
      await writer.recordBadExperience(category);
      final events = <Map<String, Object>>[];
      var requests = 0;
      final reader = service(
        isAvailable: () async => true,
        requestNativeReview: () async => requests++,
        telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
      );
      now = now.add(const Duration(days: 2));
      await reader.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
      expect(events.single['decision'], 'recent_bad_experience');
      expect(requests, 0);
      now = now.add(const Duration(days: 1));
      await reader.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
      expect(events.last['event'], 'App Review Request Finished');
      expect(requests, 1);
    });
  }

  test('remote cooldown override is applied to later versions', () async {
    final first = service(isAvailable: () async => true, requestNativeReview: () async {});
    await first.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
    now = now.add(const Duration(days: 8));
    final events = <Map<String, Object>>[];
    final second = service(
      version: '1.3',
      cooldown: () async => const Duration(days: 7),
      isAvailable: () async => false,
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await second.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
    expect(events.single['decision'], 'unavailable');
  });

  test('can ask on the first value moment without familiarity history', () async {
    var availabilityCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async {
        availabilityCalls++;
        return false;
      },
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    expect(availabilityCalls, 1);
    expect(events.single['event'], 'App Review Opportunity');
    expect(events.single['decision'], 'unavailable');
  });

  test('checks lifecycle around availability and persists before native request', () async {
    var lifecycleChecks = 0;
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async => true,
      requestNativeReview: () async {
        requestCalls++;
        final state = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
        expect((state['attempts'] as List).length, 1);
      },
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(
      moment: AppReviewMoment.conversationRead,
      isStillAppropriate: () {
        lifecycleChecks++;
        return true;
      },
    );

    expect(lifecycleChecks, 3);
    expect(requestCalls, 1);
    expect(events.map((event) => event['event']), [
      'App Review Opportunity',
      'App Review Request Attempted',
      'App Review Request Finished',
    ]);
    expect(events.first['decision'], 'eligible');
    expect(events.last['result'], 'returned');
  });

  test('cancels after the final persistence lifecycle check without invoking native review', () async {
    var lifecycleChecks = 0;
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async => true,
      requestNativeReview: () async => requestCalls++,
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(
      moment: AppReviewMoment.dailySummaryRead,
      isStillAppropriate: () {
        lifecycleChecks++;
        return lifecycleChecks < 3;
      },
    );

    expect(lifecycleChecks, 3);
    expect(requestCalls, 0);
    expect(events.single['decision'], 'lifecycle_changed');
    final state = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
    expect((state['attempts'] as List).length, 1);
  });

  test('unavailable native review consumes the session latch without a durable attempt', () async {
    var availabilityCalls = 0;
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async {
        availabilityCalls++;
        return false;
      },
      requestNativeReview: () async => requestCalls++,
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
    await reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    final state = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
    expect(availabilityCalls, 1);
    expect(requestCalls, 0);
    expect(state['attempts'], isEmpty);
    expect(events.map((event) => event['decision']), ['unavailable', 'session_already_attempted']);
  });

  test('native request errors are recorded once and do not emit a second opportunity', () async {
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async => true,
      requestNativeReview: () async => throw StateError('native failure'),
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.conversationRead, isStillAppropriate: () => true);

    expect(events.where((event) => event['event'] == 'App Review Opportunity'), hasLength(1));
    expect(events.last['event'], 'App Review Request Finished');
    expect(events.last['result'], 'error');
    final state = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
    expect((state['attempts'] as List).length, 1);
  });

  test('a new build of the same marketing version cannot request again', () async {
    final first = service(isAvailable: () async => true, requestNativeReview: () async {});
    await first.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    now = now.add(const Duration(days: 31));
    final events = <Map<String, Object>>[];
    final second = service(
      version: '1.2+100',
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await second.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    expect(events.single['decision'], 'version_already_attempted');
  });

  test('concurrent triggers serialize to one native call', () async {
    var requestCalls = 0;
    final reviewService = service(isAvailable: () async => true, requestNativeReview: () async => requestCalls++);
    await Future.wait([
      reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true),
      reviewService.requestReview(moment: AppReviewMoment.conversationRead, isStillAppropriate: () => true),
    ]);

    expect(requestCalls, 1);
  });

  test('legacy shown flags no longer block an eligible request', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{'has_shown_review_prompt': true});
    preferences = await SharedPreferences.getInstance();
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async => true,
      requestNativeReview: () async {},
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.conversationRead, isStillAppropriate: () => true);

    expect(events.first['decision'], 'eligible');
    final state = jsonDecode(preferences.getString('app_review_policy_v1')!) as Map<String, dynamic>;
    expect(state['attempts'], hasLength(1));
    expect(state['migrationComplete'], isTrue);
  });

  test('future or malformed state fails closed', () async {
    await preferences.setString(
      'app_review_policy_v1',
      jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': now.add(const Duration(days: 1)).millisecondsSinceEpoch,
        'readingDays': <String>[],
        'attempts': <Object>[],
      }),
    );
    var availabilityCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async {
        availabilityCalls++;
        return true;
      },
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    expect(availabilityCalls, 0);
    expect(events.single['decision'], 'storage_error');
  });

  test('a failed preference write fails closed before invoking native review', () async {
    final firstSeen = DateTime(2026, 9, 1, 12).millisecondsSinceEpoch;
    final state = jsonEncode(<String, Object?>{
      'schema': 1,
      'migrationComplete': true,
      'migratedAtMs': null,
      'firstSeenAtMs': firstSeen,
      'readingDays': ['2026-09-01', '2026-09-02', '2026-09-08'],
      'attempts': <Object>[],
    });
    SharedPreferences.setMockInitialValues(<String, Object>{'app_review_policy_v1': state});
    preferences = await SharedPreferences.getInstance();
    var availabilityCalls = 0;
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async {
        availabilityCalls++;
        return true;
      },
      requestNativeReview: () async => requestCalls++,
      writeState: (key, value) async => false,
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);

    expect(availabilityCalls, 1);
    expect(requestCalls, 0);
    expect(events.single['decision'], 'storage_error');
  });

  test('a throwing preference write also fails closed', () async {
    final firstSeen = DateTime(2026, 9, 1, 12).millisecondsSinceEpoch;
    SharedPreferences.setMockInitialValues(<String, Object>{
      'app_review_policy_v1': jsonEncode(<String, Object?>{
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': firstSeen,
        'readingDays': ['2026-09-01', '2026-09-02', '2026-09-08'],
        'attempts': <Object>[],
      }),
    });
    preferences = await SharedPreferences.getInstance();
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      isAvailable: () async => true,
      requestNativeReview: () async => requestCalls++,
      writeState: (key, value) async => throw StateError('preference write failed'),
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.conversationRead, isStillAppropriate: () => true);

    expect(requestCalls, 0);
    expect(events.single['decision'], 'storage_error');
  });

  test('unsupported platforms never invoke the plugin or a store fallback', () async {
    var availabilityCalls = 0;
    var requestCalls = 0;
    final events = <Map<String, Object>>[];
    final reviewService = service(
      platform: 'macos',
      isAvailable: () async {
        availabilityCalls++;
        return true;
      },
      requestNativeReview: () async => requestCalls++,
      telemetry: (event, properties) => events.add(<String, Object>{'event': event, ...properties}),
    );
    await reviewService.requestReview(moment: AppReviewMoment.conversationRead, isStillAppropriate: () => true);

    expect(availabilityCalls, 0);
    expect(requestCalls, 0);
    expect(events.single['decision'], 'not_ios_or_android');
  });
}
