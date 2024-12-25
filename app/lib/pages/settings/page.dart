import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/settings/about.dart';
import 'package:friend_private/pages/settings/developer.dart';
import 'package:friend_private/pages/settings/profile.dart';
import 'package:friend_private/pages/settings/widgets.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'device_settings/device_settings_page.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late bool optInAnalytics;
  late bool optInEmotionalFeedback;
  late bool devModeEnabled;
  String? version;
  String? buildVersion;
  bool isTester = false;

  @override
  void initState() {
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
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 16),
                // Account & Device Section
                CustomListTile(
                  title: 'Profile',
                  onTap: () => routeToPage(context, const ProfilePage()),
                  icon: Icons.person_outline_rounded,
                  showChevron: true,
                ),
                const SizedBox(height: 12),
                CustomListTile(
                  title: 'Device Settings',
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => const DeviceSettings(),
                      ),
                    );
                  },
                  icon: Icons.bluetooth_outlined,
                  showChevron: true,
                ),
                const SizedBox(height: 12),
                CustomListTile(
                  title: 'Developer Mode',
                  onTap: () async {
                    await routeToPage(context, const DeveloperSettingsPage());
                    setState(() {});
                  },
                  icon: Icons.code_rounded,
                  showChevron: true,
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 32, 0, 12),
                  child: Text(
                    'SUPPORT',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
                CustomListTile(
                  title: 'Need Help? Chat with us',
                  onTap: () async {
                    await Intercom.instance.displayMessenger();
                  },
                  icon: Icons.chat_bubble_outline_rounded,
                  showChevron: true,
                ),
                const SizedBox(height: 12),
                CustomListTile(
                  title: 'Guides & Tutorials',
                  onTap: () async {
                    await Intercom.instance.displayHelpCenter();
                  },
                  icon: Icons.help_outline_rounded,
                  showChevron: true,
                ),
                const SizedBox(height: 12),
                CustomListTile(
                  title: 'About Omi',
                  onTap: () => routeToPage(context, const AboutOmiPage()),
                  icon: Icons.workspace_premium_outlined,
                  showChevron: true,
                ),

                const SizedBox(height: 12),
                CustomListTile(
                  title: 'Sign Out',
                  onTap: () async {
                    await showDialog(
                      context: context,
                      builder: (ctx) {
                        return getDialog(
                          context,
                          () => Navigator.of(context).pop(),
                          () {
                            signOut();
                            Navigator.of(context).pop();
                            routeToPage(context, const DeciderWidget(), replace: true);
                          },
                          "Sign Out?",
                          "Are you sure you want to sign out?",
                        );
                      },
                    );
                  },
                  icon: Icons.logout_rounded,
                  showChevron: false,
                ),

                const SizedBox(height: 28),
                Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      'Version: $version+$buildVersion',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
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
