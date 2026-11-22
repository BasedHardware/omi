import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/pages/activity/needs_attention_section.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/transcription_hold_wire.dart';

/// #25918: a recording held by the free plan's monthly allowance is not a failure. Activity says it
/// is waiting for minutes and offers Upgrade, never "Couldn't transcribe" with a Try Again that the
/// server can only refuse.

const _spent =
    TranscriptionAllowanceSnapshot(mode: 'on_device', reason: 'plan_allowance_exhausted', remainingSeconds: 0);
const _left = TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_within_allowance', remainingSeconds: 600);

UsageProvider _usage(PlanType plan, {TranscriptionAllowanceSnapshot? allowance = _spent}) => UsageProvider()
  ..debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 19200,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      transcriptionAllowance: allowance));

ServerConversation _held({bool newServer = true}) => ServerConversation.fromJson({
      ...heldListRowJson(),
      if (!newServer) 'transcription_wait': null,
    });

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-user'});
    await SharedPreferencesUtil.init();
    TranscriptionPendingConversations.reset();
  });
  tearDown(TranscriptionPendingConversations.reset);

  group('heldByFreeAllowance', () {
    test('the wire field decodes and a spent free plan reads held', () {
      final row = _held();
      expect(row.transcriptionWait, 'overdue');
      expect(heldByFreeAllowance(row, _usage(PlanType.basic)), isTrue);
    });
    test('an older server (no transcription_wait) keeps the failed row', () {
      expect(_held(newServer: false).transcriptionWait, isNull);
      expect(heldByFreeAllowance(_held(newServer: false), _usage(PlanType.basic)), isFalse);
    });
    test('paid plans (a trial is an active Omi Pro plan on the wire) never read held', () {
      for (final plan in [PlanType.unlimitedV2, PlanType.unlimited, PlanType.plus]) {
        expect(heldByFreeAllowance(_held(), _usage(plan)), isFalse, reason: plan.wireName);
      }
    });
    test('minutes left, no allowance answer, or no subscription keep the failed row', () {
      expect(heldByFreeAllowance(_held(), _usage(PlanType.basic, allowance: _left)), isFalse);
      expect(heldByFreeAllowance(_held(), _usage(PlanType.basic, allowance: null)), isFalse);
      expect(heldByFreeAllowance(_held(), UsageProvider()), isFalse);
      expect(heldByFreeAllowance(_held(), null), isFalse);
    });
  });

  Future<int Function()> pump(WidgetTester tester, UsageProvider usage, ServerConversation row) async {
    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage(enabled: true, items: [], unseenCount: 0)),
    );
    await store.refresh();
    final monitor = CaptureWedgeMonitor(
        featureGate: () async => false,
        track: (_, __) {},
        bleRetry: (_) async {},
        appBuild: () => 'fixture',
        platform: () => 'ios');
    addTearDown(store.dispose);
    addTearDown(monitor.dispose);
    var attempts = 0;
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        theme: buildOmiTheme(brightness: Brightness.light),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: NeedsAttentionSection(
            store: store,
            captureMonitor: monitor,
            failedConversations: [row],
            openConversation: (_, __) async {},
            reprocess: (id) async {
              attempts++;
              return reProcessConversationServer(id, send: (_) async => heldJsonResponse(409, heldReprocess409Body));
            },
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    return () => attempts;
  }

  testWidgets('a held row says it is waiting for minutes and offers Upgrade, not Try Again', (tester) async {
    final attempts = await pump(tester, _usage(PlanType.basic), _held());
    expect(find.byKey(Key('activity_held_$heldConversationId')), findsOneWidget);
    expect(find.text('Not transcribed yet'), findsOneWidget);
    expect(find.textContaining("You've used this month's 300 minutes"), findsOneWidget);
    expect(find.text('Upgrade'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.textContaining("Couldn't transcribe"), findsNothing);
    expect(find.textContaining('Processing Failed'), findsNothing);
    // Upgrade never runs a reprocess: the server can only refuse it while the recording is held.
    await tester.tap(find.text('Upgrade'));
    await tester.pump(const Duration(seconds: 3));
    expect(attempts(), 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a paid plan sees the same row as today, with Try Again', (tester) async {
    await pump(tester, _usage(PlanType.unlimitedV2), _held());
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.text('Upgrade'), findsNothing);
    expect(find.textContaining('Processing Failed'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('new app against an older server keeps today\'s row', (tester) async {
    await pump(tester, _usage(PlanType.basic), _held(newServer: false));
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.text('Upgrade'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
