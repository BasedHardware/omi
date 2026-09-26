import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/utils/enums.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/widgets/app_review_prompt.dart';

const _readingDuration = Duration(seconds: 15);
const _bottomIdleDuration = Duration(seconds: 2);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences storage;
  final now = DateTime(2026, 9, 22, 12);

  setUp(() async {
    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      'uid': 'user-1',
      'onboardingCompleted': true,
      'app_review_policy_v1': jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': now.subtract(const Duration(days: 8)).millisecondsSinceEpoch,
        'readingDays': ['2026-09-19', '2026-09-20', '2026-09-22'],
        'attempts': <Object>[],
      }),
    });
    storage = await SharedPreferences.getInstance();
    await SharedPreferencesUtil.init();
  });

  testWidgets('reading does not initialize the lazy calling feature', (tester) async {
    var callProviderCreations = 0;
    var nativeRequests = 0;
    final service = _service(storage, requestNativeReview: () async => nativeRequests++);
    await tester.pumpWidget(
      ChangeNotifierProvider<PhoneCallProvider>(
        lazy: true,
        create: (_) {
          callProviderCreations++;
          throw StateError('Reading must not initialize phone calls');
        },
        child: MaterialApp(
            home: Scaffold(
                body: AppReviewPrompt(
          contentId: 'summary-1',
          moment: AppReviewMoment.dailySummaryRead,
          enabled: true,
          service: service,
          child: const SingleChildScrollView(child: SizedBox(height: 120)),
        ))),
      ),
    );
    await tester.pump();
    await _finishReading(tester);
    expect(callProviderCreations, 0);
    expect(nativeRequests, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('paused phone capture cancels an armed reading request', (tester) async {
    final capture = _ReviewCapture();
    addTearDown(capture.dispose);
    var nativeRequests = 0;
    final service = _service(storage, requestNativeReview: () async => nativeRequests++);
    await tester.pumpWidget(ChangeNotifierProvider<CaptureProvider>.value(
      value: capture,
      child: MaterialApp(
          home: Scaffold(
              body: AppReviewPrompt(
        contentId: 'summary-1',
        moment: AppReviewMoment.dailySummaryRead,
        enabled: true,
        service: service,
        child: const SingleChildScrollView(child: SizedBox(height: 120)),
      ))),
    ));
    await tester.pump();
    await tester.pump(const Duration(seconds: 14));
    capture.pause();
    await tester.pump();
    await _finishReading(tester);
    expect(nativeRequests, 0);
  });

  testWidgets('requests after a daily-summary reading moment', (tester) async {
    var nativeRequests = 0;
    final service = _service(storage, requestNativeReview: () async => nativeRequests++);

    await _pumpPrompt(tester, service: service, moment: AppReviewMoment.dailySummaryRead, contentId: 'summary-1');
    await _finishReading(tester);

    expect(nativeRequests, 1);
  });

  testWidgets('requests after a conversation reading moment', (tester) async {
    var nativeRequests = 0;
    final service = _service(storage, requestNativeReview: () async => nativeRequests++);

    await _pumpPrompt(tester, service: service, moment: AppReviewMoment.conversationRead, contentId: 'conversation-1');
    await _finishReading(tester);

    expect(nativeRequests, 1);
  });

  testWidgets('shares one persisted budget across summary and conversation widgets', (tester) async {
    var summaryRequests = 0;
    var conversationRequests = 0;
    final summaryService = _service(storage, requestNativeReview: () async => summaryRequests++);
    final conversationService = _service(storage, requestNativeReview: () async => conversationRequests++);

    await _pumpPrompt(
      tester,
      service: summaryService,
      moment: AppReviewMoment.dailySummaryRead,
      contentId: 'summary-1',
    );
    await _finishReading(tester);
    expect(summaryRequests, 1);

    await _pumpPrompt(
      tester,
      service: conversationService,
      moment: AppReviewMoment.conversationRead,
      contentId: 'conversation-1',
    );
    await _finishReading(tester);

    expect(conversationRequests, 0);
  });

  testWidgets('suppresses signed-out and onboarding users', (tester) async {
    var signedOutRequests = 0;
    final signedOutService = _service(storage, requestNativeReview: () async => signedOutRequests++);
    SharedPreferencesUtil().uid = '';

    await _pumpPrompt(tester,
        service: signedOutService, moment: AppReviewMoment.dailySummaryRead, contentId: 'summary-1');
    await _finishReading(tester);
    expect(signedOutRequests, 0);

    SharedPreferencesUtil().uid = 'user-1';
    SharedPreferencesUtil().onboardingCompleted = false;
    var onboardingRequests = 0;
    final onboardingService = _service(storage, requestNativeReview: () async => onboardingRequests++);

    await _pumpPrompt(
      tester,
      service: onboardingService,
      moment: AppReviewMoment.conversationRead,
      contentId: 'conversation-1',
    );
    await _finishReading(tester);
    expect(onboardingRequests, 0);
  });

  testWidgets('rechecks the owner after native availability resolves', (tester) async {
    final availability = Completer<bool>();
    var availabilityRequested = false;
    var nativeRequests = 0;
    final service = _service(
      storage,
      isAvailable: () {
        availabilityRequested = true;
        return availability.future;
      },
      requestNativeReview: () async => nativeRequests++,
    );

    await _pumpPrompt(tester, service: service, moment: AppReviewMoment.dailySummaryRead, contentId: 'summary-1');
    await _finishReading(tester);
    for (var i = 0; i < 5 && !availabilityRequested; i++) {
      await tester.pump();
    }
    expect(availabilityRequested, isTrue);

    SharedPreferencesUtil().uid = 'user-2';
    availability.complete(true);
    await tester.pump();
    await tester.pump();

    expect(nativeRequests, 0);
  });

  testWidgets('does not request for empty or disabled content', (tester) async {
    var emptyRequests = 0;
    final emptyService = _service(storage, requestNativeReview: () async => emptyRequests++);
    await _pumpPrompt(tester, service: emptyService, moment: AppReviewMoment.dailySummaryRead, contentId: '');
    await _finishReading(tester);
    expect(emptyRequests, 0);

    var disabledRequests = 0;
    final disabledService = _service(storage, requestNativeReview: () async => disabledRequests++);
    await _pumpPrompt(
      tester,
      service: disabledService,
      moment: AppReviewMoment.conversationRead,
      contentId: 'conversation-1',
      enabled: false,
    );
    await _finishReading(tester);
    expect(disabledRequests, 0);
  });

  testWidgets('handles native availability and request errors without surfacing them', (tester) async {
    var unavailableRequests = 0;
    final unavailableService = _service(
      storage,
      isAvailable: () async => false,
      requestNativeReview: () async => unavailableRequests++,
    );
    await _pumpPrompt(
      tester,
      service: unavailableService,
      moment: AppReviewMoment.dailySummaryRead,
      contentId: 'summary-1',
    );
    await _finishReading(tester);
    expect(unavailableRequests, 0);

    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      'uid': 'user-1',
      'onboardingCompleted': true,
      'app_review_policy_v1': jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': now.subtract(const Duration(days: 8)).millisecondsSinceEpoch,
        'readingDays': ['2026-09-19', '2026-09-20', '2026-09-22'],
        'attempts': <Object>[],
      }),
    });
    storage = await SharedPreferences.getInstance();
    await SharedPreferencesUtil.init();

    var requestThrew = false;
    final throwingService = _service(
      storage,
      requestNativeReview: () async {
        requestThrew = true;
        throw StateError('fixture native failure');
      },
    );
    await _pumpPrompt(
      tester,
      service: throwingService,
      moment: AppReviewMoment.conversationRead,
      contentId: 'conversation-1',
    );
    await _finishReading(tester);
    await tester.pump();
    await tester.pump();

    expect(requestThrew, isTrue);
    expect(tester.takeException(), isNull);
  });
}

AppReviewService _service(
  SharedPreferences storage, {
  Future<bool> Function()? isAvailable,
  required Future<void> Function() requestNativeReview,
}) {
  return AppReviewService.forTesting(
    storage: storage,
    clock: () => DateTime(2026, 9, 22, 12),
    platform: 'android',
    appVersion: '1.0.543',
    isAvailable: isAvailable ?? () async => true,
    requestNativeReview: requestNativeReview,
  );
}

Future<void> _pumpPrompt(
  WidgetTester tester, {
  required AppReviewService service,
  required AppReviewMoment moment,
  required String contentId,
  bool enabled = true,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: AppReviewPrompt(
          key: ValueKey(contentId),
          contentId: contentId,
          moment: moment,
          enabled: enabled,
          service: service,
          child: const SingleChildScrollView(
            child: SizedBox(height: 120, child: Text('A useful reading surface')),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

Future<void> _finishReading(WidgetTester tester) async {
  await tester.pump(_readingDuration);
  await tester.pump(_bottomIdleDuration);
  await tester.pump();
}

class _ReviewCapture extends ChangeNotifier implements CaptureProvider {
  RecordingState _state = RecordingState.stop;
  @override
  RecordingState get recordingState => _state;
  @override
  bool get isCallActive => false;
  @override
  bool get isPhoneMicBatchRecording => false;
  void pause() {
    _state = RecordingState.pause;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
