import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'device_settings.dart';
import '../conversations/sync_page.dart';

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
  String? shortDeviceInfo;

  @override
  void initState() {
    super.initState();
    _loadAppAndDeviceInfo();
  }

  Future<String> _getShortDeviceInfo() async {
    try {
      final deviceInfoPlugin = DeviceInfoPlugin();

      if (Platform.isAndroid) {
        final androidInfo = await deviceInfoPlugin.androidInfo;
        return '${androidInfo.brand} ${androidInfo.model} — Android ${androidInfo.version.release}';
      } else if (Platform.isIOS) {
        final iosInfo = await deviceInfoPlugin.iosInfo;
        return '${iosInfo.name} — iOS ${iosInfo.systemVersion}';
      } else {
        return 'Unknown Device';
      }
    } catch (e) {
      return 'Unknown Device';
    }
  }

  Future<void> _loadAppAndDeviceInfo() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      final shortDevice = await _getShortDeviceInfo();

      if (mounted) {
        setState(() {
          version = packageInfo.version;
          buildVersion = packageInfo.buildNumber.toString();
          shortDeviceInfo = shortDevice;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          shortDeviceInfo = 'Unknown Device';
        });
      }
    }
  }

  Widget _buildSettingsItem({
    required String title,
    required Widget icon,
    required VoidCallback onTap,
    bool showBetaTag = false,
    bool showNewTag = false,
    Widget? trailingChip,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 1),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
          child: Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: icon,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    if (showBetaTag) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.orange.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Text(
                          'BETA',
                          style: TextStyle(
                            color: Colors.orange,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                    if (showNewTag) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.green.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Text(
                          'NEW',
                          style: TextStyle(
                            color: Colors.green,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                    if (trailingChip != null) ...[
                      const SizedBox(width: 8),
                      trailingChip,
                    ],
                  ],
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
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildVersionInfoSection() {
    if (!Platform.isIOS && !Platform.isAndroid) {
      return const SizedBox.shrink();
    }

    final displayText = buildVersion != null ? '${version ?? ""} ($buildVersion)' : (version ?? '');

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          displayText,
          style: const TextStyle(
            color: Color(0xFF8E8E93),
            fontSize: 13,
            fontWeight: FontWeight.w400,
          ),
        ),
        const SizedBox(width: 2),
        GestureDetector(
          onTap: _copyVersionInfo,
          child: Container(
            padding: const EdgeInsets.all(2),
            child: const Icon(
              Icons.copy,
              size: 12,
              color: Color(0xFF8E8E93),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _copyVersionInfo() async {
    final versionPart = buildVersion != null ? 'Omi AI ${version ?? ""} ($buildVersion)' : 'Omi AI ${version ?? ""}';
    final devicePart = shortDeviceInfo ?? 'Unknown Device';
    final fullVersionInfo = '$versionPart — $devicePart';

    await Clipboard.setData(ClipboardData(text: fullVersionInfo));

    if (mounted) {
      _showCopyNotification();
    }
  }

  void _showCopyNotification() {
    final overlay = Overlay.of(context);
    late OverlayEntry overlayEntry;

    overlayEntry = OverlayEntry(
      builder: (_) => Positioned(
        bottom: 20,
        left: 0,
        right: 0,
        child: Center(
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: MediaQuery.of(context).size.width * 0.7,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.black87,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.2),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Text(
                'App and device details copied',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          ),
        ),
      ),
    );

    overlay.insert(overlayEntry);

    Future.delayed(const Duration(seconds: 2), () {
      overlayEntry.remove();
    });
  }

  Widget _buildOmiModeContent(BuildContext context) {
    return Consumer<UsageProvider>(builder: (context, usageProvider, child) {
      return Column(
        children: [
          // Profile & Notifications Section
          _buildSectionContainer(
            children: [
              _buildSettingsItem(
                title: 'Profile',
                icon: const FaIcon(FontAwesomeIcons.solidUser, color: Color(0xFF8E8E93), size: 20),
                onTap: () {
                  routeToPage(context, const ProfilePage());
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              Consumer<UsageProvider>(
                builder: (context, usageProvider, child) {
                  final isUnlimited = usageProvider.subscription?.subscription.plan == PlanType.unlimited;
                  return _buildSettingsItem(
                    title: 'Plan & Usage',
                    icon: const FaIcon(FontAwesomeIcons.chartLine, color: Color(0xFF8E8E93), size: 20),
                    trailingChip: isUnlimited
                        ? Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: Colors.amber.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                FaIcon(
                                  FontAwesomeIcons.crown,
                                  color: Colors.amber,
                                  size: 10,
                                ),
                                const SizedBox(width: 4),
                                const Text(
                                  'PRO',
                                  style: TextStyle(
                                    color: Colors.amber,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                              ],
                            ),
                          )
                        : null,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => const UsagePage(),
                        ),
                      );
                    },
                  );
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              _buildSettingsItem(
                title: 'Offline Sync',
                icon: const FaIcon(FontAwesomeIcons.solidCloud, color: Color(0xFF8E8E93), size: 20),
                onTap: () {
                  Navigator.pop(context);
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const SyncPage(),
                    ),
                  );
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
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              _buildSettingsItem(
                title: 'Chat Tools',
                icon: const FaIcon(FontAwesomeIcons.networkWired, color: Color(0xFF8E8E93), size: 20),
                showBetaTag: true,
                onTap: () {
                  Navigator.pop(context);
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const IntegrationsPage(),
                    ),
                  );
                },
              ),
            ],
          ),
          const SizedBox(height: 32),

          // Support & Settings Section
          _buildSectionContainer(
            children: [
              if (PlatformService.isIntercomSupported) ...[
                _buildSettingsItem(
                  title: 'Feedback / Bug',
                  icon: const FaIcon(FontAwesomeIcons.solidEnvelope, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
                    Navigator.pop(context);
                    final Uri url = Uri.parse('https://feedback.omi.me/');
                    if (await canLaunchUrl(url)) {
                      await launchUrl(url, mode: LaunchMode.inAppBrowserView);
                    }
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: 'Help Center',
                  icon: const FaIcon(FontAwesomeIcons.book, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
                    Navigator.pop(context);
                    final Uri url = Uri.parse('https://help.omi.me/en/');
                    if (await canLaunchUrl(url)) {
                      await launchUrl(url, mode: LaunchMode.inAppBrowserView);
                    }
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
              ],
              _buildSettingsItem(
                title: 'Developer Settings',
                icon: const FaIcon(FontAwesomeIcons.code, color: Color(0xFF8E8E93), size: 20),
                onTap: () async {
                  Navigator.pop(context);
                  await routeToPage(context, const DeveloperSettingsPage());
                },
              ),
            ],
          ),
          const SizedBox(height: 32),

          // Share & Get Section
          _buildSectionContainer(
            children: [
              _buildSettingsItem(
                title: 'Get Omi for Mac',
                icon: const FaIcon(FontAwesomeIcons.desktop, color: Color(0xFF8E8E93), size: 20),
                onTap: () async {
                  Navigator.pop(context);
                  final Uri url = Uri.parse('https://apps.apple.com/us/app/omi-ai-scale-yourself/id6502156163');
                  await launchUrl(url, mode: LaunchMode.externalApplication);
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43)),
              _buildSettingsItem(
                title: 'Referral Program',
                icon: const FaIcon(FontAwesomeIcons.gift, color: Color(0xFF8E8E93), size: 20),
                showNewTag: true,
                onTap: () {
                  Navigator.pop(context);
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const ReferralPage(),
                    ),
                  );
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
                      return getDialog(
                        ctx,
                        () => Navigator.of(ctx).pop(),
                        () async {
                          Navigator.of(ctx).pop();
                          await SharedPreferencesUtil().clear();
                          await AuthService.instance.signOut();
                          personaProvider.setRouting(PersonaProfileRouting.no_device);
                          if (context.mounted) {
                            routeToPage(context, const AppShell(), replace: true);
                          }
                        },
                        "Sign Out?",
                        "Are you sure you want to sign out?",
                      );
                    },
                  );
                },
              ),
            ],
          ),
          const SizedBox(height: 32),

          // Version Info
          _buildVersionInfoSection(),
          const SizedBox(height: 24),
        ],
      );
    });
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
                    return getDialog(
                      ctx,
                      () => Navigator.of(ctx).pop(),
                      () async {
                        Navigator.of(ctx).pop(); // Close dialog first
                        SharedPreferencesUtil().hasOmiDevice = null;
                        SharedPreferencesUtil().verifiedPersonaId = null;
                        personaProvider.setRouting(PersonaProfileRouting.no_device);
                        await AuthService.instance.signOut();
                        if (context.mounted) {
                          routeToPage(context, const AppShell(), replace: true);
                        }
                      },
                      "Sign Out?",
                      "Are you sure you want to sign out?",
                    );
                  },
                );
              },
            ),
          ],
        ),
        const SizedBox(height: 32),

        // Version Info
        _buildVersionInfoSection(),
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
                        color: Colors.white,
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
              child:
                  widget.mode == SettingsMode.omi ? _buildOmiModeContent(context) : _buildNoDeviceModeContent(context),
            ),
          ),
        ],
      ),
    );
  }
}
