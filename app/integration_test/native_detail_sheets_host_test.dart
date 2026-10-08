import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/feedback_prompt_policy.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

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

const _owner = 'native-detail-sheets-owner';

App _template(String id, String name) => App(
      id: id,
      name: name,
      author: 'tester',
      description: 'Pulls out decisions and owners',
      image: '/apps/$id.png',
      capabilities: {'memories'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: 0,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

/// The template owner with a fixed catalog and inert I/O; it records reprocessing requests.
class _TemplateOwner extends ConversationDetailProvider {
  final templates = [_template('decisions', 'Decisions'), _template('actions', 'Action items')];
  final reprocessed = <String?>[];

  @override
  List<App> get cachedEnabledConversationApps => templates;
  @override
  List<App> get cachedSuggestedApps => const [];
  @override
  Future<void> fetchAndCacheSuggestedApps() async {}
  @override
  Future<void> fetchAndCacheEnabledConversationApps() async {}
  @override
  String? getLastUsedSummarizationAppId() => null;
  @override
  void trackLastUsedSummarizationApp(String appId) {}
  @override
  Future<bool> reprocessConversation({String? appId}) async {
    reprocessed.add(appId);
    return true;
  }
}

/// Simulator-only: flutter drive --driver integration_test/native_ui_host_driver.dart
/// --target integration_test/native_detail_sheets_host_test.dart --flavor dev
/// --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() {
  runNativeHostSuite((checkNativeHost) {
    setUpAll(() {
      try {
        Env.init(_EnvNoIntercom());
      } on Error {
        // Already initialized in this isolate.
      }
    });

    testWidgets('Give feedback opens the native reason sheet and one reason submits once', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      VisibilityDetectorController.instance.updateInterval = Duration.zero;
      AnalyticsManager().bindIdentity(_owner);
      ProductTelemetry.instance = ProductTelemetry(emit: (_) {});
      FeedbackPromptPolicy.instance = FeedbackPromptPolicy(sampleFraction: 1, ownerKey: () => _owner);
      final submitted = <(int, MobileFeedbackReason?)>[];
      Future<MobileFeedbackReceipt?> submit({
        required MobileFeedbackKind kind,
        required String targetId,
        required int value,
        MobileFeedbackReason? reason,
        String? correlationId,
        String? feedbackId,
        required MobileFeedbackTargetKind targetKind,
      }) async {
        submitted.add((value, reason));
        return MobileFeedbackReceipt(feedbackId: feedbackId ?? 'feedback-1', eventId: 'event-1', created: true);
      }

      // The prompt in its native mode, as the native detail page mounts it, with the fake ledger. Its
      // rows are what the page projects; the page itself stays Flutter so the sheet is the only view.
      var projected = <NativeRow>[];
      NativeRow row(String id) => projected.singleWhere((row) => row.id == id);
      await tester.pumpWidget(nativeHostApp(Scaffold(
          body: CustomScrollView(slivers: [
        SummaryFeedbackPrompt(
            conversationId: 'conversation-feedback',
            submitFeedback: submit,
            onNativePresentation: (rows) => projected = rows),
      ]))));
      await tester.pump(const Duration(seconds: 1));
      await row('detail_summary_feedback').onVisible!(null);
      await tester.pump(const Duration(seconds: 1));
      expect(row('detail_summary_feedback_open').enabled, isTrue);
      // Resolves when the sheet closes.
      unawaited(Future.sync(() => row('detail_summary_feedback_open').action!(null)));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-conversation-detail-sheets-feedback-dark');
      expect(nativeProjectedRow(tester, 'feedback_close').symbol, 'xmark');
      await nativeProjectedRow(tester, 'feedback_reason_summaryIncomplete').action!(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(submitted, [(-1, MobileFeedbackReason.summaryIncomplete)]);
      expect(find.byType(UiKitView), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the summary template chooser opens natively and reprocesses with the chosen template once',
        (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final conversation = ServerConversation(
          id: 'conversation-templates',
          createdAt: DateTime.utc(2026, 10, 4, 10),
          status: ConversationStatus.completed,
          structured: Structured('Sprint planning', 'We agreed to ship the native screens.'));
      final owner = _TemplateOwner()
        ..selectedDate = conversationLocalDayKey(conversation.createdAt)
        ..setCachedConversation(conversation);
      addTearDown(owner.dispose);
      await tester.pumpWidget(nativeHostApp(
          Builder(
              builder: (context) => Scaffold(
                  body: Center(
                      child: TextButton(
                          // The same sheet the summary's template pill opens.
                          onPressed: () => showSummarizedAppsSheet(context),
                          child: const Text('summary template'))))),
          providers: [ChangeNotifierProvider<ConversationDetailProvider>.value(value: owner)]));
      await tester.tap(find.text('summary template'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-conversation-detail-sheets-templates-dark');
      expect(nativeProjectedRow(tester, 'template_app:0').title, 'Action items');
      expect(nativeProjectedRow(tester, 'template_create').kind, 'navigation');
      await nativeProjectedRow(tester, 'template_app:0').action!(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(owner.reprocessed, ['actions']);
      expect(find.byType(SummarizedAppsBottomSheet), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
  });
}
