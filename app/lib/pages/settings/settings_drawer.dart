import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/settings/about.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'device_settings.dart';

enum SettingsMode {
  no_device,
  omi,
}

class SettingsDrawer extends StatefulWidget {
  final SettingsMode mode;

  const SettingsDrawer({
    super.key,
    this.mode = SettingsMode.omi,
  });

  @override
  State<SettingsDrawer> createState() => _SettingsDrawerState();

  static void show(BuildContext context, {SettingsMode mode = SettingsMode.omi}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => SettingsDrawer(mode: mode),
    );
  }
}

class _SettingsDrawerState extends State<SettingsDrawer> {
  String? version;
  String? buildVersion;

  @override
  void initState() {
    super.initState();
    PackageInfo.fromPlatform().then((PackageInfo packageInfo) {
      version = packageInfo.version;
      buildVersion = packageInfo.buildNumber.toString();
      setState(() {});
    });
  }

  Widget _buildSettingsItem({
    required String title,
    required Widget icon,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 1),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: icon,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ),
              const Icon(
                Icons.chevron_right,
                color: Color(0xFF3C3C43),
                size: 20,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildOmiModeContent(BuildContext context) {
    return Column(
      children: [
        // Profile & Notifications Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Profile',
              icon: const FaIcon(FontAwesomeIcons.solidUser, color: Color(0xFF8E8E93), size: 20),
              onTap: () {
                Navigator.pop(context);
                routeToPage(context, const ProfilePage());
              },
            ),
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildSettingsItem(
              title: 'Device Settings',
              icon: const FaIcon(FontAwesomeIcons.bluetooth, color: Color(0xFF8E8E93), size: 20),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const DeviceSettings(),
                  ),
                );
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Share & Get Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Share Omi for iPhone',
              icon: const FaIcon(FontAwesomeIcons.solidShareFromSquare, color: Color(0xFF007AFF), size: 20),
              onTap: () async {
                Navigator.pop(context);
                // TODO: Add share functionality
              },
            ),
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildSettingsItem(
              title: 'Get Omi for Mac',
              icon: const FaIcon(FontAwesomeIcons.desktop, color: Color(0xFF8E8E93), size: 20),
              onTap: () async {
                Navigator.pop(context);
                // TODO: Add Mac app download link
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Support Section
        if (PlatformService.isIntercomSupported)
          _buildSectionContainer(
            children: [
              _buildSettingsItem(
                title: 'Send Feedback',
                icon: const FaIcon(FontAwesomeIcons.solidEnvelope, color: Color(0xFF8E8E93), size: 20),
                onTap: () async {
                  Navigator.pop(context);
                  await Intercom.instance.displayMessenger();
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              _buildSettingsItem(
                title: 'Report a bug',
                icon: const FaIcon(FontAwesomeIcons.exclamationTriangle, color: Color(0xFF8E8E93), size: 20),
                onTap: () async {
                  Navigator.pop(context);
                  await Intercom.instance.displayMessenger();
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              _buildSettingsItem(
                title: 'Help Center',
                icon: const FaIcon(FontAwesomeIcons.book, color: Color(0xFF8E8E93), size: 20),
                onTap: () async {
                  Navigator.pop(context);
                  await Intercom.instance.displayHelpCenter();
                },
              ),
            ],
          ),
        if (PlatformService.isIntercomSupported) const SizedBox(height: 32),

        // Privacy & Settings Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Data & Privacy',
              icon: const FaIcon(FontAwesomeIcons.shield, color: Color(0xFF8E8E93), size: 20),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const DataPrivacyPage(),
                  ),
                );
              },
            ),
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildSettingsItem(
              title: 'Developer Mode',
              icon: const FaIcon(FontAwesomeIcons.code, color: Color(0xFF8E8E93), size: 20),
              onTap: () async {
                Navigator.pop(context);
                await routeToPage(context, const DeveloperSettingsPage());
              },
            ),
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildSettingsItem(
              title: 'About Omi',
              icon: const FaIcon(FontAwesomeIcons.infoCircle, color: Color(0xFF8E8E93), size: 20),
              onTap: () {
                Navigator.pop(context);
                routeToPage(context, const AboutOmiPage());
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Sign Out Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Sign Out',
              icon: const FaIcon(FontAwesomeIcons.signOutAlt, color: Color(0xFF8E8E93), size: 20),
              onTap: () async {
                // Capture the provider reference before any navigation
                final personaProvider = Provider.of<PersonaProvider>(context, listen: false);
                final navigator = Navigator.of(context);

                navigator.pop(); // Close the settings drawer

                await showDialog(
                  context: context,
                  builder: (ctx) {
                    return getDialog(context, () {
                      Navigator.of(ctx).pop();
                    }, () async {
                      Navigator.of(ctx).pop(); // Close dialog first
                      await SharedPreferencesUtil().clearUserPreferences();
                      personaProvider.setRouting(PersonaProfileRouting.no_device);
                      await signOut();
                      if (context.mounted) {
                        routeToPage(context, const DeciderWidget(), replace: true);
                      }
                    }, "Sign Out?", "Are you sure you want to sign out?");
                  },
                );
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Version Info
        Text(
          '${version ?? ""}${buildVersion != null ? " ($buildVersion)" : ""}',
          style: const TextStyle(
            color: Color(0xFF8E8E93),
            fontSize: 13,
            fontWeight: FontWeight.w400,
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _buildNoDeviceModeContent(BuildContext context) {
    return Column(
      children: [
        // Support Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Need Help? Chat with us',
              icon: const FaIcon(FontAwesomeIcons.solidComments, color: Color(0xFF8E8E93), size: 20),
              onTap: () async {
                Navigator.pop(context);
                await Intercom.instance.displayMessenger();
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Sign Out Section
        _buildSectionContainer(
          children: [
            _buildSettingsItem(
              title: 'Sign Out',
              icon: const FaIcon(FontAwesomeIcons.signOutAlt, color: Color(0xFF8E8E93), size: 20),
              onTap: () async {
                // Capture the provider reference before any navigation
                final personaProvider = Provider.of<PersonaProvider>(context, listen: false);
                final navigator = Navigator.of(context);

                navigator.pop(); // Close the settings drawer

                await showDialog(
                  context: context,
                  builder: (ctx) {
                    return getDialog(context, () {
                      Navigator.of(ctx).pop();
                    }, () async {
                      Navigator.of(ctx).pop(); // Close dialog first
                      SharedPreferencesUtil().hasOmiDevice = null;
                      SharedPreferencesUtil().verifiedPersonaId = null;
                      personaProvider.setRouting(PersonaProfileRouting.no_device);
                      await signOut();
                      if (context.mounted) {
                        routeToPage(context, const DeciderWidget(), replace: true);
                      }
                    }, "Sign Out?", "Are you sure you want to sign out?");
                  },
                );
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Version Info
        Text(
          '${version ?? ""}${buildVersion != null ? " ($buildVersion)" : ""}',
          style: const TextStyle(
            color: Color(0xFF8E8E93),
            fontSize: 13,
            fontWeight: FontWeight.w400,
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.9,
      decoration: const BoxDecoration(
        color: Color(0xFF000000),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
        ),
      ),
      child: Column(
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 8),
            height: 4,
            width: 36,
            decoration: BoxDecoration(
              color: const Color(0xFF3C3C43),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Stack(
              children: [
                // Centered title
                Center(
                  child: const Text(
                    'Settings',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                // Done button positioned to the right
                Positioned(
                  right: 0,
                  child: GestureDetector(
                    onTap: () => Navigator.pop(context),
                    child: const Text(
                      'Done',
                      style: TextStyle(
                        color: Color(0xFF007AFF),
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Content
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: widget.mode == SettingsMode.omi ? _buildOmiModeContent(context) : _buildNoDeviceModeContent(context),
            ),
          ),
        ],
      ),
    );
  }
}
