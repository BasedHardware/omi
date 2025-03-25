import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/settings/about.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/widgets.dart';
import 'package:omi/utils/other/temp.dart';
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
    return Column(
      children: [
        const SizedBox(height: 32.0),
        getItemAddOn2(
          'Need Help? Chat with us',
          () async {
            await Intercom.instance.displayMessenger();
          },
          icon: Icons.chat,
        ),
        const SizedBox(height: 20),
        getItemAddOn2(
          'Profile',
          () => routeToPage(context, const ProfilePage()),
          icon: Icons.person,
        ),
        const SizedBox(height: 20),
        getItemAddOn2(
          'Device Settings',
          () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => const DeviceSettings(),
              ),
            );
          },
          icon: Icons.bluetooth_connected_sharp,
        ),
        const SizedBox(height: 8),
        getItemAddOn2(
          'Guides & Tutorials',
          () async {
            await Intercom.instance.displayHelpCenter();
          },
          icon: Icons.help_outline_outlined,
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
        getItemAddOn2('Sign Out', () async {
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
                routeToPage(context, const DeciderWidget(), replace: true);
              }, "Sign Out?", "Are you sure you want to sign out?");
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
    );
  }

  Widget _buildNoDeviceModeContent(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 32.0),
        getItemAddOn2(
          'Need Help? Chat with us',
          () async {
            await Intercom.instance.displayMessenger();
          },
          icon: Icons.chat,
        ),
        const SizedBox(height: 32),
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
                routeToPage(context, const DeciderWidget(), replace: true);
              }, "Sign Out?", "Are you sure you want to sign out?");
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
            child: widget.mode == SettingsMode.omi ? _buildOmiModeContent(context) : _buildNoDeviceModeContent(context),
          ),
        ));
  }
}
