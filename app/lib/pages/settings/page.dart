import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/about.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/profile.dart';
import 'package:friend_private/pages/settings/widgets.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:package_info_plus/package_info_plus.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late String _selectedLanguage;
  late bool optInAnalytics;
  late bool optInEmotionalFeedback;
  late bool devModeEnabled;
  String? version;
  String? buildVersion;

  @override
  void initState() {
    _selectedLanguage = SharedPreferencesUtil().recordingsLanguage;
    optInAnalytics = SharedPreferencesUtil().optInAnalytics;
    optInEmotionalFeedback = SharedPreferencesUtil().optInEmotionalFeedback;
    devModeEnabled = SharedPreferencesUtil().devModeEnabled;
    PackageInfo.fromPlatform().then((PackageInfo packageInfo) {
      version = packageInfo.version;
      buildVersion = packageInfo.buildNumber.toString();
      setState(() {});
    });
    super.initState();
  }

  bool loadingExportMemories = false;

  @override
  Widget build(BuildContext context) {
    return PopScope(
        canPop: true,
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: const Text('Settings'),
            centerTitle: false,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new),
              onPressed: () {
                Navigator.pop(context);
              },
            ),
            elevation: 0,
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Column(
              children: [
                const SizedBox(height: 32.0),
                ...getRecordingSettings((String? newValue) {
                  if (newValue == null) return;
                  if (newValue == _selectedLanguage) return;
                  if (newValue != 'en') {
                    showDialog(
                      context: context,
                      barrierDismissible: false,
                      builder: (c) => getDialog(
                        context,
                        () => Navigator.of(context).pop(),
                        () => {},
                        'Language Limitations',
                        'Speech profiles are only available for English language. We are working on adding support for other languages.',
                        singleButton: true,
                      ),
                    );
                  }
                  setState(() => _selectedLanguage = newValue);
                  SharedPreferencesUtil().recordingsLanguage = _selectedLanguage;
                  MixpanelManager().recordingLanguageChanged(_selectedLanguage);
                }, _selectedLanguage),
                getItemAddOn2(
                  'Profile',
                  () => routeToPage(context, const ProfilePage()),
                  icon: Icons.person,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  'Plugins',
                  () => routeToPage(context, const PluginsPage()),
                  icon: Icons.integration_instructions,
                ),
                const SizedBox(height: 8),
                getItemAddOn2(
                  'Calendar Integration',
                  () => routeToPage(context, const CalendarPage()),
                  icon: Icons.calendar_month,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  'About Omi',
                  () => routeToPage(context, const AboutOmiPage()),
                  icon: Icons.workspace_premium_sharp,
                ),
                const SizedBox(height: 8),
                getItemAddOn2('Developer Mode', () async {
                  await routeToPage(context, const DeveloperSettingsPage());
                  setState(() {});
                }, icon: Icons.code),
                const SizedBox(height: 32),
                getItemAddOn2('Sign Out', () {
                  // TODO: confirmation
                  signOut();
                  routeToPage(context, const DeciderWidget(), replace: true);
                }, icon: Icons.logout),
                const SizedBox(height: 24),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8.0),
                  child: Align(
                    alignment: Alignment.center,
                    child: Text(
                      'Version: $version+$buildVersion',
                      style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                    ),
                  ),
                ),
                const SizedBox(height: 32),
              ],
            ),
          ),
        ));
  }
}
