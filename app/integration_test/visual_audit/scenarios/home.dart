// Home: the recording source sheet, the announcement dialog, and the screen the app shows when
// start-up fails. The Home capture surfaces themselves are in capture.dart.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import '../../../test/helpers/proactivity_fakes.dart';

import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/startup_failure_app.dart';

import '../harness.dart';

final homeScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-proactivity-v2',
    title: 'Daily Recaps and For You',
    page: 'lib/pages/home/widgets/home_daily_recaps.dart (HomeDailyRecaps)',
    state: 'Synthetic recap, conversation mentor and commitment follow-up; no network or account data',
    run: (a) async {
      final h = OutcomeHarness();
      addTearDown(h.outbox.dispose);
      await h.bind();
      await a.pump(SingleChildScrollView(
          child: HomeDailyRecaps(
        outbox: h.outbox,
        load: () async => (
          items: [
            DailySummary(
                id: 'recap',
                date: '2026-10-03',
                createdAt: DateTime.utc(2026, 10, 3),
                headline: 'A day of progress',
                overview: 'Synthetic recap',
                stats: DayStats(totalConversations: 3, actionItemsCount: 2))
          ],
          ok: true
        ),
        loadFeed: (_) async => ApiSuccess(feedResponse(items: [
          const GeneratedProactivityFeedItem(
              id: 'mentor-item',
              producer: 'conversation_mentor_v2',
              title: 'A connection worth revisiting',
              body: 'Revisit the decision in your conversation.',
              createdAt: '2026-10-03T09:00:00Z',
              acted: false,
              dismissed: false,
              feedback: 'none',
              target: GeneratedProactivityTarget(kind: 'conversation', id: 'synthetic-conversation')),
          feedItem(producer: 'commitment_followup'),
        ])),
        openTarget: (_, {canOpen}) async => true,
      )));
      expect(find.text('Daily Recaps'), findsOneWidget);
      expect(find.text('For You'), findsOneWidget);
      expect(find.text('A connection worth revisiting'), findsOneWidget);
      await a.shot('Render both producer cards below Daily Recaps');
    },
  ),
  AuditScenario(
    id: 'home-record-options',
    title: 'Recording source sheet',
    page: 'lib/pages/home/widgets/battery_info_widget.dart (RecordOptionsSheet)',
    state: 'Opened on a neutral black host; capture is not started',
    run: (a) async {
      await a.pumpHost(
        (context) => showModalBottomSheet(
          context: context,
          backgroundColor: Colors.transparent,
          builder: (_) => RecordOptionsSheet(onPickPhoneMic: () {}, onPickPhoneCall: () {}),
        ),
        background: Colors.black,
      );
      await a.shot('Open the recording source sheet');
    },
  ),
  AuditScenario(
    id: 'home-announcement',
    title: 'Announcement dialog',
    page: 'lib/pages/announcements/announcement_dialog.dart (AnnouncementDialog)',
    state: 'One active announcement with a title, a body and a call to action into Memories, opened on a neutral host',
    run: (a) async {
      final announcement = Announcement.fromJson({
        'id': 'a-1',
        'type': 'announcement',
        'created_at': '2026-09-01T00:00:00Z',
        'active': true,
        'content': {
          'title': 'Meet Omi Memories',
          'body': 'Everything you said, remembered.',
          'cta': {'text': 'See My Memories', 'action': 'navigate:/memories'},
        },
      });
      await a.pumpHost((context) => AnnouncementDialog.show(context, announcement));
      await a.shot('Show the announcement dialog');
    },
  ),
  AuditScenario(
    id: 'home-startup-failure',
    title: 'Start-up failure screen',
    page: 'lib/startup_failure_app.dart (StartupFailureApp)',
    state: 'Start-up threw "Could not reach the Omi backend"; a retry callback is available',
    run: (a) async {
      // StartupFailureApp is its own MaterialApp; it nests under the harness app unchanged.
      await a.pump(
        StartupFailureApp(error: Exception('Could not reach the Omi backend'), onRetry: () async {}),
        scaffold: false,
      );
      await a.shot('The start-up failure screen with Try Again and Contact Support');
      // The raw error stays behind Details until support asks for it.
      expect(find.textContaining('Could not reach the Omi backend', findRichText: true), findsNothing);
      await a.tap(find.byKey(const Key('startup_failure_details')));
      expect(find.text('Exception: Could not reach the Omi backend', findRichText: true), findsOneWidget);
      await a.shot('Open Details to show the raw error for support', step: 'details');
    },
  ),
];
