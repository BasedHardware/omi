import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What the Home tab shows. These are everyday display preferences, so they live in Settings >
/// Notifications & Display (D4), not in Developer Settings. Every switch applies (and is saved) when flipped.
class HomeScreenSettingsPage extends StatefulWidget {
  const HomeScreenSettingsPage({super.key});

  @override
  State<HomeScreenSettingsPage> createState() => _HomeScreenSettingsPageState();
}

class _HomeScreenSettingsPageState extends State<HomeScreenSettingsPage> {
  final _prefs = SharedPreferencesUtil();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.homeScreen)),
      body: ListView(
        padding: const EdgeInsets.all(OmiSpacing.lg),
        children: [
          OmiSettingsGroup(
            children: [
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.bullseye),
                title: l10n.goalTracker,
                subtitle: l10n.trackYourGoalsOnHomepage,
                value: _prefs.showGoalTrackerEnabled,
                onChanged: (v) => setState(() => _prefs.showGoalTrackerEnabled = v),
              ),
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.chartLine),
                title: l10n.dailyScore,
                subtitle: l10n.showDailyScoreOnHomepage,
                value: _prefs.showDailyScoreEnabled,
                onChanged: (v) => setState(() => _prefs.showDailyScoreEnabled = v),
              ),
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.listCheck),
                title: l10n.tasks,
                subtitle: l10n.showTasksOnHomepage,
                value: _prefs.showTasksEnabled,
                onChanged: (v) => setState(() => _prefs.showTasksEnabled = v),
              ),
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.phone),
                title: l10n.showPhoneCallButtonTitle,
                subtitle: l10n.showPhoneCallButtonDesc,
                value: _prefs.showPhoneCallButton,
                onChanged: (v) => setState(() => _prefs.showPhoneCallButton = v),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
