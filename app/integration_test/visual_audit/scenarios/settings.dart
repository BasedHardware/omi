// The Settings sheet, the Account page, each settings group page and settings search.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../harness.dart';

const _account = 'Signed-in fixture account; no device connected';

final settingsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'settings-sheet',
    title: 'Settings sheet, every row',
    page: 'lib/pages/settings/settings_drawer.dart (SettingsDrawer)',
    state: 'Signed-in fixture account; a device connected',
    run: (a) async {
      await a.pump(const SettingsDrawer(), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true)),
      ]);
      await a.scrollSeries('Open the Settings sheet');
    },
  ),
  AuditScenario(
    id: 'settings-account',
    title: 'Account page',
    page: 'lib/pages/settings/profile.dart (ProfilePage)',
    state: _account,
    run: (a) async {
      await a.pump(const ProfilePage());
      await a.scrollSeries('Open Account from the Settings sheet');
    },
  ),
  AuditScenario(
    id: 'settings-device',
    title: 'Device group, device connected',
    page: 'lib/pages/settings/settings_groups.dart (DeviceGroupPage)',
    state: 'Signed-in fixture account; a device connected',
    run: (a) async {
      await a.pump(const DeviceGroupPage(), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true)),
      ]);
      await a.scrollSeries('Open Device from the Settings sheet');
    },
  ),
  AuditScenario(
    id: 'settings-device-disconnected',
    title: 'Device group, no device',
    page: 'lib/pages/settings/settings_groups.dart (DeviceGroupPage)',
    state: _account,
    run: (a) async {
      await a.pump(const DeviceGroupPage());
      await a.scrollSeries('Open Device with no device connected');
    },
  ),
  AuditScenario(
    id: 'settings-recording',
    title: 'Recording & Transcription group',
    page: 'lib/pages/settings/settings_groups.dart (RecordingGroupPage)',
    state: _account,
    run: (a) async {
      await a.pump(const RecordingGroupPage());
      await a.scrollSeries('Open Recording & Transcription');
    },
  ),
  AuditScenario(
    id: 'settings-notifications',
    title: 'Notifications & Display group',
    page: 'lib/pages/settings/settings_groups.dart (NotificationsDisplayGroupPage)',
    state: _account,
    run: (a) async {
      await a.pump(const NotificationsDisplayGroupPage());
      await a.scrollSeries('Open Notifications & Display');
    },
  ),
  AuditScenario(
    id: 'settings-privacy',
    title: 'Data & Privacy group',
    page: 'lib/pages/settings/settings_groups.dart (PrivacyDataGroupPage)',
    state: _account,
    run: (a) async {
      await a.pump(const PrivacyDataGroupPage());
      await a.scrollSeries('Open Data & Privacy');
    },
  ),
  AuditScenario(
    id: 'settings-help',
    title: 'Help & About group',
    page: 'lib/pages/settings/settings_groups.dart (HelpAboutGroupPage)',
    state: _account,
    run: (a) async {
      await a.pump(const HelpAboutGroupPage());
      await a.scrollSeries('Open Help & About');
    },
  ),
  AuditScenario(
    id: 'settings-search',
    title: 'Settings search',
    page: 'lib/pages/settings/settings_drawer.dart (SettingsDrawer)',
    state: _account,
    run: (a) async {
      await a.pump(const SettingsDrawer());
      await a.tap(find.bySemanticsLabel('Search'));
      for (final query in ['vocab', 'sign', 'profile', 'permissions']) {
        await a.enterText(find.byType(TextField).first, query);
        await a.shot('Search Settings for "$query"', step: query);
      }
    },
  ),
];
