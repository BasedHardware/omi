// Home: the header device pill and record button, the recording source sheet, the announcement
// dialog, and the screen the app shows when start-up fails.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/startup_failure_app.dart';

import '../fakes.dart';
import '../../../harness.dart';

final homeScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-header',
    title: 'Home header device pill and record button',
    page: 'lib/pages/home/widgets/battery_info_widget.dart (BatteryInfoWidget, HomeRecordButton)',
    state: 'An Omi device connected at 72% battery, not charging; nothing recording',
    run: (a) async {
      final device = AuditDeviceProvider(
          connected: true,
          battery: 72,
          device: BtDevice(id: 'd1', name: 'Omi Device', type: DeviceType.omi, rssi: -40));
      await a.pump(
          const Padding(
            padding: EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              BatteryInfoWidget(),
              SizedBox(height: 32),
              HomeRecordButton(),
            ]),
          ),
          providers: [ChangeNotifierProvider<DeviceProvider>.value(value: device)]);
      await a.shot('The header slice of Home: device pill and record button');
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
    state: 'Start-up threw "Could not reach the Omi backend"; this revision takes no retry callback',
    run: (a) async {
      // StartupFailureApp is its own MaterialApp; it nests under the harness app unchanged.
      await a.pump(StartupFailureApp(error: Exception('Could not reach the Omi backend')), scaffold: false);
      await a.shot('The start-up failure screen');
    },
  ),
];
