import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/settings/webview.dart';
import 'package:friend_private/pages/settings/widgets.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late String _selectedLanguage;
  late bool optInAnalytics;
  late bool devModeEnabled;
  late bool postMemoryNotificationIsChecked;
  late bool reconnectNotificationIsChecked;
  String? version;
  String? buildVersion;

  @override
  void initState() {
    _selectedLanguage = SharedPreferencesUtil().recordingsLanguage;
    optInAnalytics = SharedPreferencesUtil().optInAnalytics;
    devModeEnabled = SharedPreferencesUtil().devModeEnabled;
    postMemoryNotificationIsChecked = SharedPreferencesUtil().postMemoryNotificationIsChecked;
    reconnectNotificationIsChecked = SharedPreferencesUtil().reconnectNotificationIsChecked;
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
            backgroundColor: Theme.of(context).colorScheme.surface,
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
          body: Padding(
            padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom, left: 8, right: 8),
            child: SingleChildScrollView(
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
                  ...getPreferencesWidgets(
                    onOptInAnalytics: () {
                      setState(() {
                        optInAnalytics = !SharedPreferencesUtil().optInAnalytics;
                        SharedPreferencesUtil().optInAnalytics = !SharedPreferencesUtil().optInAnalytics;
                        optInAnalytics ? MixpanelManager().optInTracking() : MixpanelManager().optOutTracking();
                      });
                    },
                    viewPrivacyDetails: () {
                      Navigator.of(context).push(MaterialPageRoute(builder: (c) => const PrivacyInfoPage()));
                      MixpanelManager().privacyDetailsPageOpened();
                    },
                    optInAnalytics: optInAnalytics,
                    devModeEnabled: devModeEnabled,
                    onDevModeClicked: () {
                      setState(() {
                        if (devModeEnabled) {
                          devModeEnabled = false;
                          SharedPreferencesUtil().devModeEnabled = false;
                          MixpanelManager().developerModeDisabled();
                        } else {
                          devModeEnabled = true;
                          MixpanelManager().developerModeEnabled();
                          SharedPreferencesUtil().devModeEnabled = true;
                        }
                      });
                    },
                  ),
                  const SizedBox(height: 16),
                  ListTile(
                    title: const Text('Need help?', style: TextStyle(color: Colors.white)),
                    subtitle: const Text('team@basedhardware.com'),
                    contentPadding: const EdgeInsets.fromLTRB(0, 0, 10, 0),
                    trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                    onTap: () {
                      launchUrl(Uri.parse('mailto:team@basedhardware.com'));
                      MixpanelManager().supportContacted();
                    },
                  ),
                  ListTile(
                    contentPadding: const EdgeInsets.fromLTRB(0, 0, 10, 0),
                    title: const Text('Join the community!', style: TextStyle(color: Colors.white)),
                    subtitle: const Text('2300+ members and counting.'),
                    trailing: const Icon(Icons.discord, color: Colors.purple, size: 20),
                    onTap: () {
                      launchUrl(Uri.parse('https://discord.gg/ZutWMTJnwA'));
                      MixpanelManager().joinDiscordClicked();
                    },
                  ),
                  const SizedBox(height: 32.0),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'ADD ONS',
                      style: TextStyle(
                        color: Colors.white,
                      ),
                      textAlign: TextAlign.start,
                    ),
                  ),
                  getItemAddOn('Plugins', () {
                    MixpanelManager().pluginsOpened();
                    routeToPage(context, const PluginsPage());
                  }, icon: Icons.integration_instructions),
                  getItemAddOn('Speech Profile', () {
                    routeToPage(context, const SpeakerIdPage());
                  }, icon: Icons.multitrack_audio),
                  getItemAddOn('Calendar Integration', () {
                    routeToPage(context, const CalendarPage());
                  }, icon: Icons.calendar_month),
                  getItemAddOn('Developer Mode', () async {
                    MixpanelManager().devModePageOpened();
                    await routeToPage(context, const DeveloperSettingsPage());
                    setState(() {});
                  }, icon: Icons.code, visibility: devModeEnabled),
                  const SizedBox(height: 32.0),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'ABOUT US',
                      style: TextStyle(
                        color: Colors.white,
                      ),
                      textAlign: TextAlign.start,
                    ),
                  ),
                  getItemAddOn('Privacy Policy', () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => const PageWebView(
                          url: 'https://basedhardware.com/pages/privacy',
                          title: 'Privacy Policy',
                        ),
                      ),
                    );
                  }, icon: Icons.privacy_tip_outlined, visibility: true),
                  getItemAddOn('Our Website', () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => const PageWebView(
                          url: 'https://basedhardware.com/',
                          title: 'Based Hardware',
                        ),
                      ),
                    );
                  }, icon: Icons.language_outlined, visibility: true),
                  const SizedBox(height: 32),
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: GestureDetector(
                      onTap: () {
                        Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                        ScaffoldMessenger.of(context)
                            .showSnackBar(const SnackBar(content: Text('UID copied to clipboard')));
                      },
                      child: Text(
                        SharedPreferencesUtil().uid,
                        style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                        maxLines: 1,
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
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
          ),
        ));
  }
}
