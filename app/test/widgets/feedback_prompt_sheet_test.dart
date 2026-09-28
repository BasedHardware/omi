import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/feedback_prompt_policy.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

class _EnvNoIntercom implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

/// What the prompt asked the [submitMobileFeedback] request path for.
class CapturedFeedback {
  CapturedFeedback(this.kind, this.targetId, this.value, this.reason, this.feedbackId);

  final MobileFeedbackKind kind;
  final String targetId;
  final int value;
  final MobileFeedbackReason? reason;
  final String? feedbackId;
}

/// A submitMobileFeedback stand-in that records every request and acks it.
MobileFeedbackSubmit recordingSubmitter(List<CapturedFeedback> calls) {
  return ({
    required kind,
    required targetId,
    required value,
    reason,
    correlationId,
    feedbackId,
    required targetKind,
  }) async {
    calls.add(CapturedFeedback(kind, targetId, value, reason, feedbackId));
    return MobileFeedbackReceipt(feedbackId: feedbackId ?? 'feedback-1', eventId: 'event-1', created: true);
  };
}

void main() {
  // The sheet reads Env.intercomAppId while open; per-isolate statics need an
  // instance before the first pump.
  setUpAll(() => Env.init(_EnvNoIntercom()));

  setUp(() {
    // Report visibility on every frame so the prompt's claim path runs inside
    // the test's pumps instead of the controller's default 500ms interval.
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    AnalyticsManager().bindIdentity('feedback-test-owner');
    ProductTelemetry.instance = ProductTelemetry(emit: (_) {});
  });

  // Must run inside the test body's zone: a policy created in setUp (a
  // different zone) deadlocks the prompt's await chain under fake async, and
  // the previous test's queue future would too. sampleFraction 1 keeps every
  // target eligible so the tests do not depend on the sampling hash.
  void resetFeedbackPolicy() {
    FeedbackPromptPolicy.instance = FeedbackPromptPolicy(sampleFraction: 1, ownerKey: () => 'feedback-test-owner');
  }

  Future<void> pumpPrompt(WidgetTester tester, Widget prompt) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: CustomScrollView(slivers: [prompt])),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('recording prompt opens the sheet with recording reasons only', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('recording_feedback_give_feedback')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('feedback_reason_recordingMissingAudio')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingPoorTranscription')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingWrongSpeaker')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingDelayedOrStuck')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingFragmentedOrDuplicated')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingOther')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_summaryInaccurate')), findsNothing);
    expect(find.byKey(const ValueKey('feedback_all_good')), findsOneWidget);
    expect(calls, isEmpty);
  });

  testWidgets('summary prompt opens the sheet with summary reasons only', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(
        tester, SummaryFeedbackPrompt(conversationId: 'conversation-2', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byKey(const ValueKey('summary_feedback_give_feedback')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('feedback_reason_summaryInaccurate')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_summaryIncomplete')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_summaryIrrelevant')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_summaryWrongContext')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_summaryOther')), findsOneWidget);
    expect(find.byKey(const ValueKey('feedback_reason_recordingMissingAudio')), findsNothing);
    expect(calls, isEmpty);
  });

  testWidgets('selecting a reason submits -1 with the mapped reason', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byKey(const ValueKey('recording_feedback_give_feedback')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('feedback_reason_recordingPoorTranscription')));
    await tester.pumpAndSettle();

    expect(calls.length, 1);
    final request = calls.single;
    expect(request.kind, MobileFeedbackKind.recordingQuality);
    expect(request.targetId, 'conversation-0');
    expect(request.value, -1);
    expect(request.reason, MobileFeedbackReason.recordingPoorTranscription);
    // The prompt reached its post-response state and collapsed.
    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsNothing);
  });

  testWidgets('"All good" submits +1 without a reason and keeps the helpful value signal', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    final emitted = <RegisteredEvent>[];
    ProductTelemetry.instance = ProductTelemetry(emit: emitted.add);
    await pumpPrompt(
        tester, SummaryFeedbackPrompt(conversationId: 'conversation-2', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byKey(const ValueKey('summary_feedback_give_feedback')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('feedback_all_good')));
    await tester.pumpAndSettle();

    expect(calls.length, 1);
    final request = calls.single;
    expect(request.kind, MobileFeedbackKind.summaryHelpfulness);
    expect(request.value, 1);
    expect(request.reason, isNull);
    expect(
      emitted.any((event) => event is ProductValueEvent && event.kind == ProductValueEventKind.feedbackHelpful),
      isTrue,
    );
    expect(find.byKey(const ValueKey('summary_feedback_give_feedback')), findsNothing);
  });

  testWidgets('chat row is hidden when Intercom is unavailable', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byKey(const ValueKey('recording_feedback_give_feedback')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('feedback_chat_with_us')), findsNothing);
  });

  testWidgets('closing the sheet without a choice submits nothing and keeps the prompt', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byKey(const ValueKey('recording_feedback_give_feedback')));
    await tester.pumpAndSettle();
    // Tap the scrim outside the sheet.
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();

    expect(calls, isEmpty);
    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsOneWidget);
  });

  testWidgets('dismiss ✕ still dismisses without submitting and suppresses the target', (tester) async {
    resetFeedbackPolicy();
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();

    expect(calls, isEmpty);
    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsNothing);

    // The decision was recorded: a fresh prompt for the same target shows nothing.
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));
    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsNothing);
  });

  testWidgets('an already-claimed target shows no prompt', (tester) async {
    resetFeedbackPolicy();
    await FeedbackPromptPolicy.instance.claim('conversation-0');
    final calls = <CapturedFeedback>[];
    await pumpPrompt(tester,
        RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: recordingSubmitter(calls)));

    expect(find.byKey(const ValueKey('recording_feedback_give_feedback')), findsNothing);
    expect(calls, isEmpty);
  });
}
