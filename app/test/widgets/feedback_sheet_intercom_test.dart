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

// A separate isolate from feedback_prompt_sheet_test.dart on purpose:
// Env.init writes a late final, so this file initializes Env with an Intercom
// app id while that file initializes it without one.
class _EnvWithIntercom implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => 'test-intercom-app';
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

void main() {
  setUpAll(() => Env.init(_EnvWithIntercom()));

  setUp(() {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    AnalyticsManager().bindIdentity('feedback-test-owner');
    ProductTelemetry.instance = ProductTelemetry(emit: (_) {});
  });

  testWidgets('chat row appears in the sheet when Intercom is available', (tester) async {
    // Constructed inside the body's zone; see feedback_prompt_sheet_test.dart.
    FeedbackPromptPolicy.instance = FeedbackPromptPolicy(sampleFraction: 1, ownerKey: () => 'feedback-test-owner');
    final calls = <_Captured>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: CustomScrollView(
            slivers: [
              RecordingQualityFeedbackPrompt(recordingId: 'conversation-0', submitFeedback: _submitter(calls)),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('recording_feedback_give_feedback')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('feedback_chat_with_us')), findsOneWidget);
    expect(calls, isEmpty);
  });
}

class _Captured {
  _Captured(this.kind, this.targetId, this.value, this.reason, this.feedbackId);
  final MobileFeedbackKind kind;
  final String targetId;
  final int value;
  final MobileFeedbackReason? reason;
  final String? feedbackId;
}

MobileFeedbackSubmit _submitter(List<_Captured> calls) {
  return ({
    required kind,
    required targetId,
    required value,
    reason,
    correlationId,
    feedbackId,
    required targetKind,
  }) async {
    calls.add(_Captured(kind, targetId, value, reason, feedbackId));
    return MobileFeedbackReceipt(feedbackId: feedbackId ?? 'feedback-1', eventId: 'event-1', created: true);
  };
}
