// Home: the recording source sheet, the announcement dialog, and the screen the app shows when
// start-up fails. The Home capture surfaces themselves are in capture.dart.
import 'package:flutter/material.dart';

import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/startup_failure_app.dart';

import '../harness.dart';

final homeScenarios = <AuditScenario>[
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
