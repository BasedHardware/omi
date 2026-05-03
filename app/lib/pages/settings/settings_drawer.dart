import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/pages/settings/permissions_page.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/auth/clear_user_state.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:omi/backend/http/api/announcements.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'device_settings.dart';
import '../conversations/auto_sync_page.dart';
import '../conversations/sync_page.dart';

class _SearchableItem {
  final String title;
  final Widget icon;
  final VoidCallback onTap;

  const _SearchableItem({required this.title, required this.icon, required this.onTap});
}

class SettingsDrawer extends StatefulWidget {
  const SettingsDrawer({super.key});

  @override
  State<SettingsDrawer> createState() => _SettingsDrawerState();

  static void show(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const SettingsDrawer(),
    );
  }
}

class _SettingsDrawerState extends State<SettingsDrawer> {
  String? version;
  String? buildVersion;
  String? shortDeviceInfo;

  bool _isSearching = false;
  String _searchQuery = '';
  late TextEditingController _searchController;
  late FocusNode _searchFocusNode;

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    _searchFocusNode = FocusNode();
    _loadAppAndDeviceInfo();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
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
        return context.l10n.unknownDevice;
      }
    } catch (e) {
      return context.l10n.unknownDevice;
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
          shortDeviceInfo = context.l10n.unknownDevice;
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
        decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
          child: Row(
            children: [
              SizedBox(width: 24, height: 24, child: icon),
              const SizedBox(width: 16),
              Expanded(
                child: Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w400),
                    ),
                    if (showBetaTag) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.orange.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          context.l10n.beta,
                          style: const TextStyle(
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
                        child: Text(
                          context.l10n.newTag,
                          style: const TextStyle(
                            color: Colors.green,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                    if (trailingChip != null) ...[const SizedBox(width: 8), trailingChip],
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(children: children),
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
          style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w400),
        ),
        const SizedBox(width: 2),
        GestureDetector(
          onTap: _copyVersionInfo,
          child: Container(
            padding: const EdgeInsets.all(2),
            child: const Icon(Icons.copy, size: 12, color: Color(0xFF8E8E93)),
          ),
        ),
      ],
    );
  }

  Future<void> _copyVersionInfo() async {
    final versionPart = buildVersion != null ? 'Omi AI ${version ?? ""} ($buildVersion)' : 'Omi AI ${version ?? ""}';
    final devicePart = shortDeviceInfo ?? context.l10n.unknownDevice;
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
                boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 4, offset: const Offset(0, 2))],
              ),
              child: Text(
                context.l10n.appAndDeviceCopied,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 14),
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

  List<_SearchableItem> _buildSearchableItems(BuildContext context) {
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);

    void goToProfile() => routeToPage(context, const ProfilePage());
    void goToNotifications() => routeToPage(context, const NotificationsSettingsPage());
    void goToUsage() => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const UsagePage()));
    void goToSync() {
      final page = SharedPreferencesUtil().deviceSupportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
      Navigator.of(context).push(MaterialPageRoute(builder: (context) => page));
    }

    void goToDevice() => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const DeviceSettings()));
    void goToIntegrations() =>
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const IntegrationsPage()));
    void goToPermissions() {
      MixpanelManager().permissionsSettingsOpened();
      routeToPage(context, const PermissionsPage());
    }

    void goToMemories() => routeToPage(context, const MemoriesPage());
    void goToDeveloper() async => await routeToPage(context, const DeveloperSettingsPage());

    const profileIcon = FaIcon(FontAwesomeIcons.solidUser, color: Color(0xFF8E8E93), size: 20);
    const notifIcon = FaIcon(FontAwesomeIcons.solidBell, color: Color(0xFF8E8E93), size: 20);
    const usageIcon = FaIcon(FontAwesomeIcons.chartLine, color: Color(0xFF8E8E93), size: 20);
    const deviceIcon = FaIcon(FontAwesomeIcons.bluetooth, color: Color(0xFF8E8E93), size: 20);
    const permIcon = FaIcon(FontAwesomeIcons.shieldHalved, color: Color(0xFF8E8E93), size: 20);
    const memIcon = FaIcon(FontAwesomeIcons.brain, color: Color(0xFF8E8E93), size: 20);
    const devIcon = FaIcon(FontAwesomeIcons.code, color: Color(0xFF8E8E93), size: 20);
    const intIcon = FaIcon(FontAwesomeIcons.networkWired, color: Color(0xFF8E8E93), size: 20);
    const syncIcon = FaIcon(FontAwesomeIcons.solidCloud, color: Color(0xFF8E8E93), size: 20);

    final items = <_SearchableItem>[
      // --- Profile ---
      _SearchableItem(title: context.l10n.profile, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.name, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.email, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.language, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.customVocabulary, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.speechProfile, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.identifyingOthers, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.voiceResponseMode, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.paymentMethods, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.conversationDisplay, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.dataPrivacy, icon: profileIcon, onTap: goToProfile),
      _SearchableItem(title: context.l10n.deleteAccountTitle, icon: profileIcon, onTap: goToProfile),
      // --- Notifications ---
      _SearchableItem(title: context.l10n.notifications, icon: notifIcon, onTap: goToNotifications),
      _SearchableItem(title: context.l10n.notificationFrequency, icon: notifIcon, onTap: goToNotifications),
      _SearchableItem(title: context.l10n.dailySummary, icon: notifIcon, onTap: goToNotifications),
      _SearchableItem(title: context.l10n.deliveryTime, icon: notifIcon, onTap: goToNotifications),
      // --- Plan & Usage ---
      _SearchableItem(title: context.l10n.planAndUsage, icon: usageIcon, onTap: goToUsage),
      // --- Offline Sync ---
      _SearchableItem(title: context.l10n.offlineSync, icon: syncIcon, onTap: goToSync),
      // --- Device Settings (only when connected) ---
      if (deviceProvider.isConnected) ...[
        _SearchableItem(title: context.l10n.deviceSettings, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.deviceName, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.firmware, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.sdCardSync, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.wifiSync, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.doubleTap, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.ledBrightness, icon: deviceIcon, onTap: goToDevice),
        _SearchableItem(title: context.l10n.micGain, icon: deviceIcon, onTap: goToDevice),
      ],
      // --- Integrations ---
      _SearchableItem(title: context.l10n.integrations, icon: intIcon, onTap: goToIntegrations),
      // --- Permissions ---
      _SearchableItem(title: context.l10n.permissions, icon: permIcon, onTap: goToPermissions),
      _SearchableItem(title: context.l10n.microphone, icon: permIcon, onTap: goToPermissions),
      _SearchableItem(title: context.l10n.bluetooth, icon: permIcon, onTap: goToPermissions),
      _SearchableItem(title: context.l10n.location, icon: permIcon, onTap: goToPermissions),
      _SearchableItem(title: context.l10n.backgroundActivity, icon: permIcon, onTap: goToPermissions),
      // --- Memories ---
      _SearchableItem(title: context.l10n.memories, icon: memIcon, onTap: goToMemories),
      // --- Support ---
      if (PlatformService.isIntercomSupported) ...[
        _SearchableItem(
          title: context.l10n.feedbackBug,
          icon: const FaIcon(FontAwesomeIcons.solidEnvelope, color: Color(0xFF8E8E93), size: 20),
          onTap: () async {
            final Uri url = Uri.parse('https://feedback.omi.me/');
            if (await canLaunchUrl(url)) await launchUrl(url, mode: LaunchMode.inAppBrowserView);
          },
        ),
        _SearchableItem(
          title: context.l10n.helpCenter,
          icon: const FaIcon(FontAwesomeIcons.book, color: Color(0xFF8E8E93), size: 20),
          onTap: () async {
            final Uri url = Uri.parse('https://help.omi.me/en/');
            if (await canLaunchUrl(url)) {
              try {
                await launchUrl(url, mode: LaunchMode.inAppBrowserView);
              } catch (e) {
                await launchUrl(url, mode: LaunchMode.externalApplication);
              }
            }
          },
        ),
      ],
      // --- Developer ---
      _SearchableItem(title: context.l10n.developerSettings, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.apiKeys, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.debugAndDiagnostics, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.conversationEvents, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.realTimeTranscript, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.audioBytes, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.daySummary, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.autoCreateSpeakers, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.goalTracker, icon: devIcon, onTap: goToDeveloper),
      _SearchableItem(title: context.l10n.apiEnvironment, icon: devIcon, onTap: goToDeveloper),
      // --- What's New ---
      _SearchableItem(
        title: context.l10n.whatsNew,
        icon: const FaIcon(FontAwesomeIcons.solidStar, color: Color(0xFF8E8E93), size: 20),
        onTap: () {
          MixpanelManager().whatsNewOpened();
          ChangelogSheet.showWithLoading(context, () => getAppChangelogs(limit: 5));
        },
      ),
      // --- Mac app ---
      _SearchableItem(
        title: context.l10n.getOmiForMac,
        icon: const FaIcon(FontAwesomeIcons.desktop, color: Color(0xFF8E8E93), size: 20),
        onTap: () async {
          final Uri url = Uri.parse('https://apps.apple.com/us/app/omi-ai-scale-yourself/id6502156163');
          await launchUrl(url, mode: LaunchMode.externalApplication);
        },
      ),
      // --- Referral ---
      _SearchableItem(
        title: context.l10n.referralProgram,
        icon: const FaIcon(FontAwesomeIcons.gift, color: Color(0xFF8E8E93), size: 20),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ReferralPage())),
      ),
      // --- Sign Out ---
      _SearchableItem(
        title: context.l10n.signOut,
        icon: const FaIcon(FontAwesomeIcons.signOutAlt, color: Color(0xFF8E8E93), size: 20),
        onTap: () async {
          final navigator = Navigator.of(context);
          navigator.pop();
          await showDialog(
            context: context,
            builder: (ctx) {
              return getDialog(
                ctx,
                () => Navigator.of(ctx).pop(),
                () async {
                  Navigator.of(ctx).pop();
                  final rootCtx = globalNavigatorKey.currentContext;
                  if (rootCtx != null && rootCtx.mounted) {
                    clearAllUserState(rootCtx);
                  }
                  await SharedPreferencesUtil().clear();
                  await AuthService.instance.signOut();
                  if (rootCtx != null && rootCtx.mounted) {
                    routeToPage(rootCtx, const AppShell(), replace: true);
                  }
                },
                context.l10n.signOutQuestion,
                context.l10n.signOutConfirmation,
              );
            },
          );
        },
      ),
    ];

    return items;
  }

  Widget _buildSearchResults(BuildContext context) {
    final allItems = _buildSearchableItems(context);
    final query = _searchQuery.toLowerCase();
    final filtered = allItems.where((item) => item.title.toLowerCase().contains(query)).toList();

    if (filtered.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.only(top: 48),
          child: Text(
            'No results',
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 16, fontWeight: FontWeight.w400),
          ),
        ),
      );
    }

    return Column(
      children:
          filtered.map((item) => _buildSettingsItem(title: item.title, icon: item.icon, onTap: item.onTap)).toList(),
    );
  }

  Widget _buildOmiModeContent(BuildContext context) {
    return Consumer<UsageProvider>(
      builder: (context, usageProvider, child) {
        return Column(
          children: [
            // Profile & Notifications Section
            _buildSectionContainer(
              children: [
                // Wrapped 2025 - temporarily disabled
                // _buildSettingsItem(
                //   title: context.l10n.wrapped2025,
                //   icon: const FaIcon(FontAwesomeIcons.gift, color: Color(0xFF8E8E93), size: 20),
                //   showNewTag: true,
                //   onTap: () {
                //     Navigator.of(context).push(
                //       MaterialPageRoute(
                //         builder: (context) => const Wrapped2025Page(),
                //       ),
                //     );
                //   },
                // ),
                // const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.profile,
                  icon: const FaIcon(FontAwesomeIcons.solidUser, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const ProfilePage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.notifications,
                  icon: const FaIcon(FontAwesomeIcons.solidBell, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const NotificationsSettingsPage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                Consumer<UsageProvider>(
                  builder: (context, usageProvider, child) {
                    final sp = usageProvider.subscription?.subscription.plan;
                    final isUnlimited = sp == PlanType.unlimited || sp == PlanType.operator || sp == PlanType.architect;
                    return _buildSettingsItem(
                      title: context.l10n.planAndUsage,
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
                                  const FaIcon(FontAwesomeIcons.crown, color: Colors.amber, size: 10),
                                  const SizedBox(width: 4),
                                  Text(
                                    context.l10n.pro.toUpperCase(),
                                    style: const TextStyle(
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
                        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const UsagePage()));
                      },
                    );
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.offlineSync,
                  icon: const FaIcon(FontAwesomeIcons.solidCloud, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    final page =
                        SharedPreferencesUtil().deviceSupportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
                    Navigator.of(context).push(MaterialPageRoute(builder: (context) => page));
                  },
                ),
                Consumer<DeviceProvider>(
                  builder: (context, deviceProvider, child) {
                    if (!deviceProvider.isConnected) {
                      return const SizedBox.shrink();
                    }
                    return Column(
                      children: [
                        const Divider(height: 1, color: Color(0xFF3C3C43)),
                        _buildSettingsItem(
                          title: context.l10n.deviceSettings,
                          icon: const FaIcon(FontAwesomeIcons.bluetooth, color: Color(0xFF8E8E93), size: 20),
                          onTap: () {
                            Navigator.of(context).push(MaterialPageRoute(builder: (context) => const DeviceSettings()));
                          },
                        ),
                      ],
                    );
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.integrations,
                  icon: const FaIcon(FontAwesomeIcons.networkWired, color: Color(0xFF8E8E93), size: 20),
                  showBetaTag: true,
                  onTap: () {
                    Navigator.of(context).push(MaterialPageRoute(builder: (context) => const IntegrationsPage()));
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.permissions,
                  icon: const FaIcon(FontAwesomeIcons.shieldHalved, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    MixpanelManager().permissionsSettingsOpened();
                    routeToPage(context, const PermissionsPage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.memories,
                  icon: const FaIcon(FontAwesomeIcons.brain, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    routeToPage(context, const MemoriesPage());
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
                    title: context.l10n.feedbackBug,
                    icon: const FaIcon(FontAwesomeIcons.solidEnvelope, color: Color(0xFF8E8E93), size: 20),
                    onTap: () async {
                      final Uri url = Uri.parse('https://feedback.omi.me/');
                      if (await canLaunchUrl(url)) {
                        await launchUrl(url, mode: LaunchMode.inAppBrowserView);
                      }
                    },
                  ),
                  const Divider(height: 1, color: Color(0xFF3C3C43)),
                  _buildSettingsItem(
                    title: context.l10n.helpCenter,
                    icon: const FaIcon(FontAwesomeIcons.book, color: Color(0xFF8E8E93), size: 20),
                    onTap: () async {
                      final Uri url = Uri.parse('https://help.omi.me/en/');
                      if (await canLaunchUrl(url)) {
                        try {
                          await launchUrl(url, mode: LaunchMode.inAppBrowserView);
                        } catch (e) {
                          await launchUrl(url, mode: LaunchMode.externalApplication);
                        }
                      }
                    },
                  ),
                  const Divider(height: 1, color: Color(0xFF3C3C43)),
                ],
                _buildSettingsItem(
                  title: context.l10n.developerSettings,
                  icon: const FaIcon(FontAwesomeIcons.code, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
                    await routeToPage(context, const DeveloperSettingsPage());
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.whatsNew,
                  icon: const FaIcon(FontAwesomeIcons.solidStar, color: Color(0xFF8E8E93), size: 20),
                  onTap: () {
                    MixpanelManager().whatsNewOpened();
                    ChangelogSheet.showWithLoading(context, () => getAppChangelogs(limit: 5));
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // Share & Get Section
            _buildSectionContainer(
              children: [
                _buildSettingsItem(
                  title: context.l10n.getOmiForMac,
                  icon: const FaIcon(FontAwesomeIcons.desktop, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
                    final Uri url = Uri.parse('https://apps.apple.com/us/app/omi-ai-scale-yourself/id6502156163');
                    await launchUrl(url, mode: LaunchMode.externalApplication);
                  },
                ),
                const Divider(height: 1, color: Color(0xFF3C3C43)),
                _buildSettingsItem(
                  title: context.l10n.referralProgram,
                  icon: const FaIcon(FontAwesomeIcons.gift, color: Color(0xFF8E8E93), size: 20),
                  showNewTag: true,
                  onTap: () {
                    Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ReferralPage()));
                  },
                ),
              ],
            ),
            const SizedBox(height: 32),

            // Sign Out Section
            _buildSectionContainer(
              children: [
                _buildSettingsItem(
                  title: context.l10n.signOut,
                  icon: const FaIcon(FontAwesomeIcons.signOutAlt, color: Color(0xFF8E8E93), size: 20),
                  onTap: () async {
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
                            // The drawer's context is unmounted by the time we
                            // get here (we popped it before opening the
                            // confirm dialog), so routing through it is a
                            // silent no-op. Use the root navigator instead so
                            // we always land back on the auth screen.
                            final rootCtx = globalNavigatorKey.currentContext;
                            if (rootCtx != null && rootCtx.mounted) {
                              clearAllUserState(rootCtx);
                            }
                            await SharedPreferencesUtil().clear();
                            await AuthService.instance.signOut();
                            if (rootCtx != null && rootCtx.mounted) {
                              routeToPage(rootCtx, const AppShell(), replace: true);
                            }
                          },
                          context.l10n.signOutQuestion,
                          context.l10n.signOutConfirmation,
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
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.9,
      decoration: const BoxDecoration(
        color: Color(0xFF000000),
        borderRadius: BorderRadius.only(topLeft: Radius.circular(28), topRight: Radius.circular(28)),
      ),
      child: ClipRRect(
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(28), topRight: Radius.circular(28)),
        child: Column(
          children: [
            // Handle bar
            Container(
              margin: const EdgeInsets.only(top: 8),
              height: 4,
              width: 36,
              decoration: BoxDecoration(color: const Color(0xFF3C3C43), borderRadius: BorderRadius.circular(2)),
            ),
            // Header
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              transitionBuilder: (child, animation) => FadeTransition(opacity: animation, child: child),
              child: _isSearching
                  ? Padding(
                      key: const ValueKey('search-header'),
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                      child: Row(
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: _searchController,
                              focusNode: _searchFocusNode,
                              autofocus: true,
                              style: const TextStyle(color: Colors.white, fontSize: 14),
                              cursorColor: Colors.white,
                              decoration: InputDecoration(
                                hintText: 'Search settings…',
                                hintStyle: const TextStyle(color: Colors.white60, fontSize: 14),
                                filled: true,
                                fillColor: const Color(0xFF1C1C1E),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(24),
                                  borderSide: BorderSide.none,
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(24),
                                  borderSide: BorderSide.none,
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(24),
                                  borderSide: BorderSide.none,
                                ),
                                prefixIcon: const Icon(Icons.search, color: Colors.white60),
                                suffixIcon: _searchQuery.isNotEmpty
                                    ? GestureDetector(
                                        onTap: () {
                                          setState(() => _searchQuery = '');
                                          _searchController.clear();
                                        },
                                        child: const Icon(Icons.close, color: Colors.white60),
                                      )
                                    : null,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12),
                              ),
                              onChanged: (value) => setState(() => _searchQuery = value),
                            ),
                          ),
                          const SizedBox(width: 10),
                          GestureDetector(
                            onTap: () {
                              setState(() {
                                _isSearching = false;
                                _searchQuery = '';
                                _searchController.clear();
                              });
                              _searchFocusNode.unfocus();
                            },
                            child: const Text('Cancel', style: TextStyle(color: Colors.white, fontSize: 16)),
                          ),
                        ],
                      ),
                    )
                  : Padding(
                      key: const ValueKey('normal-header'),
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                      child: Row(
                        children: [
                          GestureDetector(
                            onTap: () {
                              setState(() => _isSearching = true);
                              Future.microtask(() => _searchFocusNode.requestFocus());
                            },
                            child: const Icon(Icons.search, color: Colors.white, size: 22),
                          ),
                          Expanded(
                            child: Center(
                              child: Text(
                                context.l10n.settings,
                                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                              ),
                            ),
                          ),
                          GestureDetector(
                            onTap: () => Navigator.pop(context),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                              decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20)),
                              child: Text(
                                context.l10n.done,
                                style: const TextStyle(color: Colors.black, fontSize: 14, fontWeight: FontWeight.w600),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
            ),
            const SizedBox(height: 16),
            // Content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: _isSearching && _searchQuery.isNotEmpty
                    ? _buildSearchResults(context)
                    : _buildOmiModeContent(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
