import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/facts/page.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/people.dart';
import 'package:friend_private/pages/settings/personal_details.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/settings/recordings_storage_permission.dart';
import 'package:friend_private/pages/settings/webview.dart';
import 'package:friend_private/pages/settings/widgets.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/gradient_borders.dart';
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
    Future<void> _showMockupOmiFeebackNotification() async {
      showDialog(
        context: context,
        builder: (BuildContext context) {
          return Dialog(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12.0),
            ),
            elevation: 5.0,
            backgroundColor: Colors.black,
            child: Container(
              padding: const EdgeInsets.all(20.0),
              decoration: BoxDecoration(
                border: const GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const _MockNotification(
                    path: 'assets/images/emotional_feedback_1.png',
                  ),
                  const SizedBox(
                    height: 25,
                  ),
                  const Text(
                    "Omi will send you feedback in real-time.",
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color.fromRGBO(255, 255, 255, .8)),
                  ),
                  const SizedBox(
                    height: 25,
                  ),
                  Container(
                    padding: const EdgeInsets.only(
                      left: 8,
                      right: 8,
                      top: 8,
                      bottom: 8,
                    ),
                    child: TextButton(
                      style: TextButton.styleFrom(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(50, 30),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        alignment: Alignment.center,
                      ),
                      child: const Text(
                        "Ok, I understand",
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Color.fromRGBO(255, 255, 255, .8),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      onPressed: () {
                        Navigator.of(context).pop();
                      },
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
    }

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
                      onOptInEmotionalFeedback: () {
                        var enabled = !SharedPreferencesUtil().optInEmotionalFeedback;
                        SharedPreferencesUtil().optInEmotionalFeedback = enabled;

                        setState(() {
                          optInEmotionalFeedback = enabled;
                        });

                        // Show a mockup notifications to help user understand about Omi Feedback
                        if (enabled) {
                          _showMockupOmiFeebackNotification();
                        }
                      },
                      viewPrivacyDetails: () {
                        Navigator.of(context).push(MaterialPageRoute(builder: (c) => const PrivacyInfoPage()));
                        MixpanelManager().privacyDetailsPageOpened();
                      },
                      optInEmotionalFeedback: optInEmotionalFeedback,
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
                      authorizeSavingRecordings: SharedPreferencesUtil().permissionStoreRecordingsEnabled,
                      onAuthorizeSavingRecordingsClicked: () async {
                        await routeToPage(context, const RecordingsStoragePermission());
                        setState(() {});
                      }),
                  const SizedBox(height: 32.0),
                  getItemAddOn('Plugins', () {
                    MixpanelManager().pluginsOpened();
                    routeToPage(context, const PluginsPage());
                  }, icon: Icons.integration_instructions),
                  getItemAddOn('Calendar Integration', () {
                    routeToPage(context, const CalendarPage());
                  }, icon: Icons.calendar_month),
                  const Divider(
                    color: Colors.transparent,
                  ),
                  getItemAddOn('Speech Recognition', () {
                    routeToPage(context, const SpeakerIdPage());
                  }, icon: Icons.multitrack_audio),
                  getItemAddOn('Identifying Others', () {
                    routeToPage(context, const UserPeoplePage());
                  }, icon: Icons.people),
                  const Divider(
                    color: Colors.transparent,
                  ),
                  getItemAddOn(
                      SharedPreferencesUtil().givenName.isEmpty
                          ? 'About YOU (by Omi)'
                          : 'About ${SharedPreferencesUtil().givenName.toUpperCase()} (by Omi) ', () {
                    routeToPage(context, const FactsPage());
                  }, icon: Icons.self_improvement),
                  getItemAddOn('How Omi should call you?', () {
                    // routeToPage(context, const PersonalDetails());
                    showModalBottomSheet(
                        context: context,
                        builder: (c) {
                          return Container(
                            child: const PersonalDetails(),
                          );
                        });
                  }, icon: Icons.person),
                  const Divider(
                    color: Colors.transparent,
                  ),
                  getItemAddOn('Developer Mode', () async {
                    MixpanelManager().devModePageOpened();
                    await routeToPage(context, const DeveloperSettingsPage());
                    setState(() {});
                  }, icon: Icons.code, visibility: devModeEnabled),
                  const SizedBox(height: 16),
                  ListTile(
                    title: const Text('Need help?', style: TextStyle(color: Colors.white)),
                    subtitle: const Text('team@basedhardware.com'),
                    contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
                    trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                    onTap: () {
                      launchUrl(Uri.parse('mailto:team@basedhardware.com'));
                      MixpanelManager().supportContacted();
                    },
                  ),
                  ListTile(
                    contentPadding: const EdgeInsets.fromLTRB(4, 0, 24, 0),
                    title: const Text('Join the community!', style: TextStyle(color: Colors.white)),
                    subtitle: const Text('2300+ members and counting.'),
                    trailing: const Icon(Icons.discord, color: Colors.purple, size: 20),
                    onTap: () {
                      launchUrl(Uri.parse('https://discord.gg/ZutWMTJnwA'));
                      MixpanelManager().joinDiscordClicked();
                    },
                  ),
                  getItemAddOn('Privacy Policy', () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => const PageWebView(
                          url: 'https://www.omi.me/pages/privacy',
                          title: 'Privacy Policy',
                        ),
                      ),
                    );
                  }, icon: Icons.privacy_tip_outlined, visibility: true),
                  // getItemAddOn('About omi', () {
                  //   Navigator.of(context).push(
                  //     MaterialPageRoute(
                  //       builder: (c) => const PageWebView(
                  //         url: 'https://www.omi.me/',
                  //         title: 'omi',
                  //       ),
                  //     ),
                  //   );
                  // }, icon: Icons.language_outlined, visibility: true),
                  const SizedBox(height: 32),
                  getItemAddOn('Delete Account', () {
                    showDialog(
                        context: context,
                        builder: (ctx) {
                          return getDialog(
                            context,
                            () {
                              Navigator.of(context).pop();
                            },
                            () async {
                              // send email to team@basedhardware.com
                              launchUrl(Uri.parse('mailto:team@basedhardware.com?subject=Delete%20My%20Account'));
                            },
                            'Deleting Account?',
                            'Please send us an email at team@basedhardware.com',
                            okButtonText: 'Open Email',
                            singleButton: false,
                          );
                        });
                  }, icon: Icons.warning, visibility: true),
                  getItemAddOn('Sign Out', () {
                    signOut();
                    Navigator.pushAndRemoveUntil(
                        context, MaterialPageRoute(builder: (context) => const AuthWrapper()), (route) => false);
                  }, icon: Icons.logout, visibility: true),
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

class _MockNotification extends StatelessWidget {
  const _MockNotification({super.key, required this.path});

  final String path;

  @override
  Widget build(BuildContext context) {
    // Forgive me, should be a goog dynamic layout but not static image, btw I have no time.
    return Image.asset(
      path,
      fit: BoxFit.fitWidth,
    );
  }
}
