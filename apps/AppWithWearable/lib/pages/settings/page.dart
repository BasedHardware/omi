import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:friend_private/pages/backup/page.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/privacy.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
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
        canPop: false,
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
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 4),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'RECORDING SETTINGS',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Center(
                      child: Container(
                    height: 60,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    padding: const EdgeInsets.only(left: 16, right: 12, top: 8, bottom: 10),
                    child: DropdownButton<String>(
                      menuMaxHeight: 350,
                      value: _selectedLanguage,
                      onChanged: (String? newValue) {
                        setState(() {
                          _selectedLanguage = newValue!;
                        });
                        SharedPreferencesUtil().recordingsLanguage = _selectedLanguage;
                        MixpanelManager().recordingLanguageChanged(_selectedLanguage);
                      },
                      dropdownColor: Colors.black,
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                      underline: Container(
                        height: 0,
                        color: Colors.white,
                      ),
                      isExpanded: true,
                      itemHeight: 48,
                      items: availableLanguages.keys.map<DropdownMenuItem<String>>((String key) {
                        return DropdownMenuItem<String>(
                          value: availableLanguages[key],
                          child: Text(
                            '$key (${availableLanguages[key]})',
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                          ),
                        );
                      }).toList(),
                    ),
                  )),
                  const SizedBox(height: 32.0),
                  // TODO: remove this settings?
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'NOTIFICATIONS',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                      textAlign: TextAlign.start,
                    ),
                  ),
                  InkWell(
                    onTap: () {
                      setState(() {
                        if (postMemoryNotificationIsChecked) {
                          postMemoryNotificationIsChecked = false;
                          SharedPreferencesUtil().postMemoryNotificationIsChecked = false;
                        } else {
                          postMemoryNotificationIsChecked = true;
                          SharedPreferencesUtil().postMemoryNotificationIsChecked = true;
                        }
                      });
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(0, 16, 8.0, 0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Post memory analysis',
                            style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                          ),
                          Container(
                            decoration: BoxDecoration(
                              color: postMemoryNotificationIsChecked
                                  ? const Color.fromARGB(255, 150, 150, 150)
                                  : Colors.transparent, // Fill color when checked
                              border: Border.all(
                                color: const Color.fromARGB(255, 150, 150, 150),
                                width: 2,
                              ),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            width: 22,
                            height: 22,
                            child: postMemoryNotificationIsChecked // Show the icon only when checked
                                ? const Icon(
                                    Icons.check,
                                    color: Colors.white, // Tick color
                                    size: 18,
                                  )
                                : null, // No icon when unchecked
                          ),
                        ],
                      ),
                    ),
                  ),
                  InkWell(
                    onTap: () {
                      setState(() {
                        if (reconnectNotificationIsChecked) {
                          reconnectNotificationIsChecked = false;
                          SharedPreferencesUtil().reconnectNotificationIsChecked = false;
                        } else {
                          reconnectNotificationIsChecked = true;
                          SharedPreferencesUtil().reconnectNotificationIsChecked = true;
                        }
                      });
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(0, 12, 8.0, 0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Reminder to reconnect',
                            style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                          ),
                          Container(
                            decoration: BoxDecoration(
                              color: reconnectNotificationIsChecked
                                  ? const Color.fromARGB(255, 150, 150, 150)
                                  : Colors.transparent, // Fill color when checked
                              border: Border.all(
                                color: const Color.fromARGB(255, 150, 150, 150),
                                width: 2,
                              ),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            width: 22,
                            height: 22,
                            child: reconnectNotificationIsChecked // Show the icon only when checked
                                ? const Icon(
                                    Icons.check,
                                    color: Colors.white, // Tick color
                                    size: 18,
                                  )
                                : null, // No icon when unchecked
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'PREFERENCES',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                      textAlign: TextAlign.start,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
                    child: InkWell(
                      onTap: () {
                        setState(() {
                          optInAnalytics = false;
                          SharedPreferencesUtil().optInAnalytics = !SharedPreferencesUtil().optInAnalytics;
                          optInAnalytics ? MixpanelManager().optInTracking() : MixpanelManager().optOutTracking();
                        });
                      },
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 12.0),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: GestureDetector(
                                child: const Text(
                                  'Help improve Friend by sharing anonymized analytics data',
                                  style: TextStyle(
                                      color: Color.fromARGB(255, 150, 150, 150),
                                      fontSize: 16,
                                      decoration: TextDecoration.underline),
                                ),
                                onTap: () {
                                  Navigator.of(context)
                                      .push(MaterialPageRoute(builder: (c) => const PrivacyInfoPage()));
                                  MixpanelManager().privacyDetailsPageOpened();
                                },
                              ),
                            ),
                            const SizedBox(
                              width: 8,
                            ),
                            Container(
                              decoration: BoxDecoration(
                                color: optInAnalytics
                                    ? const Color.fromARGB(255, 150, 150, 150)
                                    : Colors.transparent, // Fill color when checked
                                border: Border.all(
                                  color: const Color.fromARGB(255, 150, 150, 150),
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              width: 22,
                              height: 22,
                              child: optInAnalytics // Show the icon only when checked
                                  ? const Icon(
                                      Icons.check,
                                      color: Colors.white, // Tick color
                                      size: 18,
                                    )
                                  : null, // No icon when unchecked
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
                    child: InkWell(
                      onTap: () {
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
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 12.0),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              'Developer Mode',
                              style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                            ),
                            Container(
                              decoration: BoxDecoration(
                                color: devModeEnabled
                                    ? const Color.fromARGB(255, 150, 150, 150)
                                    : Colors.transparent, // Fill color when checked
                                border: Border.all(
                                  color: const Color.fromARGB(255, 150, 150, 150),
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              width: 22,
                              height: 22,
                              child: devModeEnabled // Show the icon only when checked
                                  ? const Icon(
                                      Icons.check,
                                      color: Colors.white, // Tick color
                                      size: 18,
                                    )
                                  : null, // No icon when unchecked
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
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
                  const SizedBox(height: 36.0),
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
                  GestureDetector(
                    onTap: () {
                      MixpanelManager().pluginsOpened();
                      Navigator.of(context).push(MaterialPageRoute(builder: (c) => const PluginsPage()));
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(0, 16, 8.0, 0),
                      child: Container(
                        decoration: BoxDecoration(
                          color: const Color.fromARGB(255, 29, 29, 29),
                          borderRadius: BorderRadius.circular(10.0),
                        ),
                        child: const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                'Plugins',
                                style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                              ),
                              Icon(
                                Icons.arrow_forward_ios,
                                color: Color.fromARGB(255, 255, 255, 255),
                                size: 16,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  Visibility(
                    visible: false,
                    child: InkWell(
                      onTap: () {
                        Navigator.of(context).push(MaterialPageRoute(builder: (c) => const SpeakerIdPage()));
                      },
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
                        child: Container(
                          decoration: BoxDecoration(
                            color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
                            borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
                          ),
                          child: const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  'Speech Profile Set Up',
                                  style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                                ),
                                Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Visibility(
                    visible: true,
                    child: GestureDetector(
                      onTap: () {
                        Navigator.of(context).push(MaterialPageRoute(builder: (c) => const BackupsPage()));
                      },
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
                        child: Container(
                          decoration: BoxDecoration(
                            color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
                            borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
                          ),
                          child: const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Row(
                                  children: [
                                    Text(
                                      'Backups',
                                      style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                                    ),
                                    SizedBox(width: 16),
                                    Icon(Icons.backup, color: Colors.white, size: 16),
                                  ],
                                ),
                                Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Visibility(
                    visible: devModeEnabled,
                    child: GestureDetector(
                      onTap: () {
                        MixpanelManager().devModePageOpened();
                        Navigator.of(context).push(MaterialPageRoute(builder: (c) => const DeveloperSettingsPage()));
                      },
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
                        child: Container(
                          decoration: BoxDecoration(
                            color: const Color.fromARGB(255, 29, 29, 29),
                            borderRadius: BorderRadius.circular(10.0),
                          ),
                          child: const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  'Developer Mode',
                                  style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                                ),
                                Icon(
                                  Icons.arrow_forward_ios,
                                  color: Color.fromARGB(255, 255, 255, 255),
                                  size: 16,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: Text(
                      SharedPreferencesUtil().uid,
                      style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                      maxLines: 1,
                      textAlign: TextAlign.center,
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
                ],
              ),
            ),
          ),
        ));
  }
}
