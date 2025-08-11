import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/settings/about.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/settings/widgets.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'device_settings.dart';

enum SettingsMode {
  no_device,
  omi,
}

class SettingsPage extends StatefulWidget {
  final SettingsMode mode;

  const SettingsPage({
    super.key,
    this.mode = SettingsMode.omi,
  });

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

  Widget _buildOmiModeContent(BuildContext context) {
    // Group settings by category: Account, Device, Support, Info, Actions
    return Column(
      children: [
        const SizedBox(height: 24.0),
        // Account Settings
        getItemAddOn2(
          'Profile',
          () => routeToPage(context, const ProfilePage()),
          icon: const Icon(Icons.person, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 12),
        getItemAddOn2(
          'Usage',
          () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => const UsagePage(),
              ),
            );
          },
          icon: const Icon(Icons.bar_chart_sharp, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 12),

        // Device Settings
        getItemAddOn2(
          'Device Settings',
          () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => const DeviceSettings(),
              ),
            );
          },
          icon: const Icon(Icons.bluetooth_connected_sharp, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 12),

        // Data & Privacy
        getItemAddOn2(
          'Data & Privacy',
          () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => const DataPrivacyPage(),
              ),
            );
          },
          icon: const Icon(Icons.shield_outlined, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 12),

        // Advanced Settings
        getItemAddOn2(
          'Developer Mode',
          () async {
            await routeToPage(context, const DeveloperSettingsPage());
            setState(() {});
          },
          icon: const Icon(Icons.code, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 12),

        // Help & Support
        !PlatformService.isIntercomSupported
            ? const SizedBox()
            : getItemAddOn2(
                'Guides & Tutorials',
                () async {
                  await Intercom.instance.displayHelpCenter();
                },
                icon: const Icon(Icons.help_outline_outlined, color: Colors.white, size: 22),
              ),
        SizedBox(height: PlatformService.isIntercomSupported ? 12 : 0),
        !PlatformService.isIntercomSupported
            ? const SizedBox()
            : getItemAddOn2(
                'Need Help? Chat with us',
                () async {
                  await Intercom.instance.displayMessenger();
                },
                icon: const Icon(Icons.chat, color: Colors.white, size: 22),
              ),
        SizedBox(height: PlatformService.isIntercomSupported ? 12 : 0),

        // Information
        getItemAddOn2(
          'About Omi',
          () => routeToPage(context, const AboutOmiPage()),
          icon: const Icon(Icons.info_outline, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 24),

        // Actions
        getItemAddOn2(
          'Sign Out',
          () async {
            await showDialog(
              context: context,
              builder: (ctx) {
                return getDialog(context, () {
                  Navigator.of(context).pop();
                }, () async {
                  await SharedPreferencesUtil().clearUserPreferences();
                  Provider.of<PersonaProvider>(context, listen: false).setRouting(PersonaProfileRouting.no_device);
                  await signOut();
                  Navigator.of(context).pop();
                  routeToPage(context, const AppShell(), replace: true);
                }, "Sign Out?", "Are you sure you want to sign out?");
              },
            );
          },
          icon: const Icon(Icons.logout, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 20),

        // Version Info
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8.0),
          child: Align(
            alignment: Alignment.center,
            child: Text(
              'Version: $version+$buildVersion',
              style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 14),
            ),
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _buildNoDeviceModeContent(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 24.0),

        // Help & Support
        getItemAddOn2(
          'Need Help? Chat with us',
          () async {
            await Intercom.instance.displayMessenger();
          },
          icon: const Icon(Icons.chat, color: Colors.white, size: 22),
        ),
        const SizedBox(height: 24),

        // Actions
        getItemAddOn2('Sign Out', () async {
          await showDialog(
            context: context,
            builder: (ctx) {
              return getDialog(context, () {
                Navigator.of(context).pop();
              }, () async {
                SharedPreferencesUtil().hasOmiDevice = null;
                SharedPreferencesUtil().verifiedPersonaId = null;
                Provider.of<PersonaProvider>(context, listen: false).setRouting(PersonaProfileRouting.no_device);
                await signOut();
                Navigator.of(context).pop();
                routeToPage(context, const AppShell(), replace: true);
              }, "Sign Out?", "Are you sure you want to sign out?");
            },
          );
        }, icon: const Icon(Icons.logout, color: Colors.white, size: 22)),
        const SizedBox(height: 20),

        // Version Info
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8.0),
          child: Align(
            alignment: Alignment.center,
            child: Text(
              'Version: $version+$buildVersion',
              style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 14),
            ),
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
        canPop: true,
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: const Text(
              'Settings',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w600,
              ),
            ),
            centerTitle: true,
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
            child: widget.mode == SettingsMode.omi ? _buildOmiModeContent(context) : _buildNoDeviceModeContent(context),
          ),
        ));
  }
}
