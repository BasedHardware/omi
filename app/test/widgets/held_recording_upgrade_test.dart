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
import 'package:omi/pages/activity/past_processing_section.dart';
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

ServerConversation _recording({String? admission = 'allowance_held', String homeStep = 'failed', String? title}) =>
    ServerConversation.fromJson({
      ...heldListRowJson(),
      'transcription_admission': admission,
      'home_step': homeStep,
      if (title != null) 'structured': {...heldListRowJson()['structured'] as Map<String, dynamic>, 'title': title},
    });

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-user'});
    await SharedPreferencesUtil.init();
    TranscriptionPendingConversations.reset();
  });
  tearDown(TranscriptionPendingConversations.reset);

  group('transcription admission', () {
    test('the wire field stays with the row and an exhausted Basic plan can upgrade', () {
      final row = _recording();
      expect(row.isTranscriptionAllowanceHeld, isTrue);
      expect(row.withHomeStep('transcribing').isTranscriptionAllowanceHeld, isTrue);
      expect(heldRecordingUpgradeLimitMinutes(row, _usage(PlanType.basic)), 300);
    });
    test('an overdue wait alone cannot prove a hold, even with exhausted minutes', () {
      final row = _recording(admission: null);
      expect(row.transcriptionWait, 'overdue');
      expect(row.isTranscriptionAllowanceHeld, isFalse);
      expect(heldRecordingUpgradeLimitMinutes(row, _usage(PlanType.basic)), isNull);
    });
    test('a hold stays held across paid, replenished, and unavailable allowance', () {
      final row = _recording();
      for (final usage in [
        _usage(PlanType.unlimitedV2),
        _usage(PlanType.plus),
        _usage(PlanType.basic, allowance: _left),
        _usage(PlanType.basic, allowance: null),
        UsageProvider(),
        null,
      ]) {
        expect(heldRecordingUpgradeLimitMinutes(row, usage), isNull);
      }
      expect(row.isTranscriptionAllowanceHeld, isTrue);
    });
  });

  test('Activity places the same recording once as held, in progress, then finished', () {
    // A young held recording can still have the server's pre-existing transcribing Home step.
    final held = _recording(homeStep: 'transcribing');
    // Guard a loaded row whose old failed Home step survived a list/detail merge.
    final admitted = _recording(admission: 'processing');
    final finished = _recording(admission: null, homeStep: 'ready');
    final tomorrow = held.createdAt.toLocal().add(const Duration(days: 2));

    List<ServerConversation> attention(ServerConversation row) => failedActivityConversations(
          pending: [],
          conversations: [row],
          v3Only: true,
        );
    List<ServerConversation> processing(ServerConversation row) => pastProcessingConversations(
          pending: [],
          conversations: [row],
          now: tomorrow,
        );

    expect(attention(held).single.id, held.id);
    expect(processing(held), isEmpty);
    expect(attention(admitted), isEmpty);
    expect(processing(admitted).single.id, held.id);
    expect(attention(finished), isEmpty);
    expect(processing(finished), isEmpty);
  });

  Future<int Function()> pump(WidgetTester tester, UsageProvider usage, ServerConversation row,
      {double textScale = 1, Future<ReprocessResult> Function(String)? reprocess}) async {
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
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
        theme: buildOmiTheme(brightness: Brightness.light),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SingleChildScrollView(
              child: NeedsAttentionSection(
            store: store,
            captureMonitor: monitor,
            failedConversations: [row],
            openConversation: (_, __) async {},
            reprocess: (id) async {
              attempts++;
              if (reprocess != null) return reprocess(id);
              return reProcessConversationServer(id, send: (_) async => heldJsonResponse(409, heldReprocess409Body));
            },
          )),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    return () => attempts;
  }

  testWidgets('a held row says it is waiting for minutes and offers Upgrade, not Try Again', (tester) async {
    final attempts = await pump(tester, _usage(PlanType.basic), _recording());
    expect(find.byKey(const Key('activity_held_$heldConversationId')), findsOneWidget);
    expect(find.text('Not transcribed yet'), findsOneWidget);
    expect(find.textContaining("You've used this month's 300 minutes"), findsOneWidget);
    expect(find.text('Upgrade'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.byIcon(Icons.hourglass_empty), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
    expect(find.textContaining("Couldn't transcribe"), findsNothing);
    expect(find.textContaining('Processing Failed'), findsNothing);
    // Upgrade never runs a reprocess: the server can only refuse it while the recording is held.
    await tester.tap(find.text('Upgrade'));
    await tester.pump(const Duration(seconds: 3));
    expect(attempts(), 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a replenished allowance leaves the held row waiting with no action', (tester) async {
    await pump(
        tester, _usage(PlanType.basic, allowance: _left), _recording(homeStep: 'transcribing', title: 'Transcribing…'));
    expect(find.text('Not transcribed yet'), findsOneWidget);
    expect(find.textContaining('Waiting for transcription allowance'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Upgrade'), findsNothing);
    expect(find.text('Transcribing…'), findsNothing);
    expect(find.textContaining('Processing Failed'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an older server\'s overdue-only row keeps Retry without an allowance claim', (tester) async {
    await pump(tester, _usage(PlanType.basic), _recording(admission: null));
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.text('Upgrade'), findsNothing);
    expect(find.textContaining('300 minutes'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a real failure still retries even when the account is at its limit', (tester) async {
    final failed = ServerConversation.fromJson({
      ...heldListRowJson(),
      'transcription_wait': null,
      'status': 'failed',
    });
    final calls = <String>[];
    final attempts = await pump(tester, _usage(PlanType.basic), failed, reprocess: (id) async {
      calls.add(id);
      return ReprocessSuccess(_recording(admission: null, homeStep: 'ready'));
    });

    expect(find.textContaining('Processing Failed'), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
    expect(find.byIcon(Icons.hourglass_empty), findsNothing);
    expect(find.text('Upgrade'), findsNothing);
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(attempts(), 1);
    expect(calls, [failed.id]);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('at the largest text size the action sits under the text, the title stays readable', (tester) async {
    tester.view.physicalSize = const Size(402, 874);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await pump(tester, _usage(PlanType.basic), _recording(), textScale: 3.1);
    final title = tester.getRect(find.text('Not transcribed yet'));
    final upgrade = tester.getRect(find.text('Upgrade'));
    expect(upgrade.top, greaterThan(title.bottom));
    expect(title.width, greaterThan(150), reason: 'not squeezed to one letter per line');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
