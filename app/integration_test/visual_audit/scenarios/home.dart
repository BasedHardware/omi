// Home: the announcement dialog and the screen the app shows when start-up fails (the Recording
// from sheet is in capture.dart). The Home capture surfaces themselves are in capture.dart.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/search/search_page.dart';
import 'package:omi/startup_failure_app.dart';

import '../harness.dart';

final homeScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-search',
    title: 'Search everything: before typing, then results for a word',
    page: 'lib/pages/search/search_page.dart (SearchPage)',
    state: 'Signed-in fixture account; the conversation search answers with one conversation',
    run: (a) async {
      await a.pump(
        SearchPage(
          searchConversations: (query) async => [
            ServerConversation(
              id: 'c1',
              createdAt: DateTime(2026, 9, 24, 14, 42),
              structured: Structured('App UX and battery', '## Summary\n**Battery drain** reports from two users'),
              source: ConversationSource.omi,
            ),
          ],
        ),
        scaffold: false,
      );
      await a.shot('Open Search', step: 'idle');
      await a.tester.enterText(find.byKey(const ValueKey('search_field')), 'battery');
      await a.tester.pump(const Duration(milliseconds: 350));
      await a.settle();
      await a.shot('Search for battery', step: 'results');
    },
  ),
  AuditScenario(
    id: 'home-announcement',
    title: 'Announcement dialog',
    page: 'lib/pages/announcements/announcement_dialog.dart (AnnouncementDialog)',
    state: 'One active announcement with a title and a body, opened on a neutral host',
    run: (a) async {
      final announcement = Announcement.fromJson({
        'id': 'a-1',
        'type': 'announcement',
        'created_at': '2026-09-01T00:00:00Z',
        'active': true,
        'content': {'title': 'Meet Omi Memories', 'body': 'Everything you said, remembered.'},
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
      await a.pump(StartupFailureApp(error: Exception('Could not reach the Omi backend'), onRetry: () async {}),
          scaffold: false);
      await a.shot('The start-up failure screen with Try Again and Contact Support');
    },
  ),
];
