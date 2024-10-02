import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/sdcard/page.dart';
import 'package:friend_private/pages/settings/about.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/profile.dart';
import 'package:friend_private/pages/settings/widgets.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:friend_private/services/translation_service.dart';

import 'device_settings.dart';

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
            title:  Text(TranslationService.translate( 'Settings')),
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
                  setState(() => _selectedLanguage = newValue);
                  SharedPreferencesUtil().recordingsLanguage = _selectedLanguage;
                  MixpanelManager().recordingLanguageChanged(_selectedLanguage);
                }, _selectedLanguage),
                getItemAddOn2(
                  TranslationService.translate( 'Need Help? Chat with us'),
                  () async {
                    await Intercom.instance.displayMessenger();
                  },
                  icon: Icons.chat,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  TranslationService.translate( 'Profile'),
                  () => routeToPage(context, const ProfilePage()),
                  icon: Icons.person,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  TranslationService.translate( 'Device Settings'),
                  () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => DeviceSettings(),
                      ),
                    );
                  },
                  icon: Icons.bluetooth_connected_sharp,
                ),
                const SizedBox(height: 8),
                getItemAddOn2(
                  TranslationService.translate( 'Guides & Tutorials'),
                  () async {
                    await Intercom.instance.displayHelpCenter();
                  },
                  icon: Icons.help_outline_outlined,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  TranslationService.translate( 'Plugins'),
                  () => routeToPage(context, const PluginsPage()),
                  icon: Icons.integration_instructions,
                ),
                const SizedBox(height: 8),
                getItemAddOn2(
                  TranslationService.translate( 'Calendar Integration'),
                  () => routeToPage(context, const CalendarPage()),
                  icon: Icons.calendar_month,
                ),
                const SizedBox(height: 20),
                getItemAddOn2(
                  TranslationService.translate( 'About Omi'),
                  () => routeToPage(context, const AboutOmiPage()),
                  icon: Icons.workspace_premium_sharp,
                ),
                const SizedBox(height: 8),
                getItemAddOn2(TranslationService.translate( 'Developer Mode'), () async {
                  await routeToPage(context, const DeveloperSettingsPage());
                  setState(() {});
                }, icon: Icons.code),
                const SizedBox(height: 32),
                getItemAddOn2(TranslationService.translate( 'Sign Out'), () async {
                  await showDialog(
                    context: context,
                    builder: (ctx) {
                      return getDialog(context, () {
                        Navigator.of(context).pop();
                      }, () {
                        signOut();
                        Navigator.of(context).pop();
                        routeToPage(context, const DeciderWidget(), replace: true);
                      }, TranslationService.translate( "Sign Out?"), TranslationService.translate( "Are you sure you want to sign out?"));
                    },
                  );
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
