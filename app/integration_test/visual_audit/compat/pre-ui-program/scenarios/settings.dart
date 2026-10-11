// The old Settings sheet, the old Profile page (the equivalent of today's Account page) and
// settings search. The settings group pages did not exist yet.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../../../harness.dart';

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
    title: 'Profile page (today\'s Account page)',
    page: 'lib/pages/settings/profile.dart (ProfilePage)',
    state: _account,
    run: (a) async {
      await a.pump(const ProfilePage());
      await a.scrollSeries('Open Profile from the Settings sheet');
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
