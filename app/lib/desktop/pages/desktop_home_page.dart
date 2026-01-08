import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/desktop/pages/settings/desktop_settings_modal.dart';
import 'package:omi/desktop/pages/settings/desktop_shortcuts_page.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/services/shortcut_service.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'apps/desktop_apps_page.dart';
import 'apps/desktop_add_app_page.dart';
import 'conversations/desktop_conversations_page.dart';
import 'chat/desktop_chat_page.dart';
import 'memories/desktop_memories_page.dart';
import 'actions/desktop_actions_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:window_manager/window_manager.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import '../../pages/conversations/sync_page.dart';

enum MacWindowButtonType { close, minimize, maximize }

class _MacWindowButton extends StatefulWidget {
  final MacWindowButtonType type;
  final VoidCallback onTap;

  const _MacWindowButton({
    required this.type,
    required this.onTap,
  });

  @override
  State<_MacWindowButton> createState() => _MacWindowButtonState();
}

class _MacWindowButtonState extends State<_MacWindowButton> {
  bool _isHovered = false;

  Color _getButtonColor() {
    switch (widget.type) {
      case MacWindowButtonType.close:
        return const Color(0xFFFF5F57);
      case MacWindowButtonType.minimize:
        return const Color(0xFFFFBD2E);
      case MacWindowButtonType.maximize:
        return const Color(0xFF28CA42);
    }
  }

  IconData _getButtonIcon() {
    switch (widget.type) {
      case MacWindowButtonType.close:
        return FontAwesomeIcons.xmark;
      case MacWindowButtonType.minimize:
        return FontAwesomeIcons.minus;
      case MacWindowButtonType.maximize:
        return FontAwesomeIcons.expand;
    }
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: _getButtonColor(),
            borderRadius: BorderRadius.circular(6),
          ),
          child: _isHovered
              ? Icon(
                  _getButtonIcon(),
                  size: 8,
                  color: widget.type == MacWindowButtonType.close
                      ? Colors.white.withOpacity(0.9)
                      : Colors.black.withOpacity(0.7),
                )
              : null,
        ),
      ),
    );
  }
}

class DesktopHomePage extends StatefulWidget {
  final String? navigateToRoute;
  const DesktopHomePage({super.key, this.navigateToRoute});

  @override
  State<DesktopHomePage> createState() => _DesktopHomePageState();
}

class _DesktopHomePageState extends State<DesktopHomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);

  PageController? _controller;
  late AnimationController _sidebarAnimationController;
  late Animation<double> _sidebarSlideAnimation;

  // State for Get Omi Widget
  bool _showGetOmiWidget = true;

  void _initiateApps() {
    context.read<AppProvider>().getApps();
    context.read<AppProvider>().getPopularApps();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    String event = '';
    if (state == AppLifecycleState.paused) {
      event = 'App is paused';
    } else if (state == AppLifecycleState.resumed) {
      event = 'App is resumed';

      // // Reload convos
      if (mounted) {
        Provider.of<ConversationProvider>(context, listen: false).refreshConversations();
        Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
      }
    } else if (state == AppLifecycleState.hidden) {
      event = 'App is hidden';
    } else if (state == AppLifecycleState.detached) {
      event = 'App is detached';
    } else {
      return;
    }
    debugPrint(event);
    PlatformManager.instance.crashReporter.logInfo(event);
  }

  bool? previousConnection;

  @override
  void initState() {
    super.initState();
    SharedPreferencesUtil().onboardingCompleted = true;
    _showGetOmiWidget = SharedPreferencesUtil().showGetOmiCard;

    // Initialize shortcut service to listen for native navigation requests
    if (ShortcutService.isSupported) {
      ShortcutService.initialize();
      ShortcutService.onOpenKeyboardShortcutsPage = () {
        if (mounted) {
          routeToPage(context, const DesktopShortcutsPage());
        }
      };
    }

    // Initialize animations
    _sidebarAnimationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _sidebarSlideAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _sidebarAnimationController, curve: Curves.easeOutCubic),
    );

    // Navigate uri
    Uri? navigateToUri;
    var pageAlias = "home";
    var homePageIdx = 0;
    String? detailPageId;

    if (widget.navigateToRoute != null && widget.navigateToRoute!.isNotEmpty) {
      navigateToUri = Uri.tryParse("http://localhost.com${widget.navigateToRoute!}");
      debugPrint("initState ${navigateToUri?.pathSegments.join("...")}");
      var segments = navigateToUri?.pathSegments ?? [];
      if (segments.isNotEmpty) {
        pageAlias = segments[0];
      }
      if (segments.length > 1) {
        detailPageId = segments[1];
      }

      switch (pageAlias) {
        case "memories":
          homePageIdx = 0;
          break;
        case "chat":
          homePageIdx = 1;
        case "memoriesPage":
          homePageIdx = 2;
          break;
        case "apps":
          homePageIdx = 3;
          break;
      }
    }

    // Home controller
    _controller = PageController(initialPage: homePageIdx);
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    context.read<HomeProvider>().onSelectedIndexChanged = (index) {
      _controller?.animateToPage(index, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
    };
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();

      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false)
            .streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Handle navigation
      switch (pageAlias) {
        case "chat":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            var appId = detailPageId != "omi" ? detailPageId : '';
            if (mounted) {
              var appProvider = Provider.of<AppProvider>(context, listen: false);
              var messageProvider = Provider.of<MessageProvider>(context, listen: false);
              App? selectedApp;
              if (appId.isNotEmpty) {
                selectedApp = await appProvider.getAppFromId(appId);
              }
              appProvider.setSelectedChatAppId(appId);
              await messageProvider.refreshMessages();
              if (messageProvider.messages.isEmpty) {
                messageProvider.sendInitialAppMessage(selectedApp);
              }
            }
          } else {
            if (mounted) {
              await Provider.of<MessageProvider>(context, listen: false).refreshMessages();
            }
          }
          break;
        default:
      }

      // Start sidebar animation
      _sidebarAnimationController.forward();
    });

    _listenToMessagesFromNotification();
  }

  void _listenToMessagesFromNotification() {
    NotificationService.instance.listenForServerMessages.listen((message) {
      if (mounted) {
        var selectedApp = Provider.of<AppProvider>(context, listen: false).getSelectedApp();
        if (selectedApp == null || message.appId == selectedApp.id) {
          Provider.of<MessageProvider>(context, listen: false).addMessage(message);
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);
    return MyUpgradeAlert(
      upgrader: _upgrader,
      dialogStyle: Platform.isIOS ? UpgradeDialogStyle.cupertino : UpgradeDialogStyle.material,
      child: Consumer<ConnectivityProvider>(
        builder: (ctx, connectivityProvider, child) {
          bool isConnected = connectivityProvider.isConnected;
          previousConnection ??= true;
          if (previousConnection != isConnected && connectivityProvider.isInitialized) {
            previousConnection = isConnected;
            if (!isConnected) {
              // TODO: Re-enable when internet connection banners are redesigned
              // Future.delayed(const Duration(seconds: 2), () {
              //   if (mounted && !connectivityProvider.isConnected) {
              //     ScaffoldMessenger.of(ctx).showMaterialBanner(
              //       MaterialBanner(
              //         content: const Text(
              //           'No internet connection. Please check your connection.',
              //           style: TextStyle(color: Colors.white70),
              //         ),
              //         backgroundColor: const Color(0xFF424242),
              //         leading: const Icon(Icons.wifi_off, color: Colors.white70),
              //         actions: [
              //           TextButton(
              //             onPressed: () {
              //               ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
              //             },
              //             child: const Text('Dismiss', style: TextStyle(color: Colors.white70)),
              //           ),
              //         ],
              //       ),
              //     );
              //   }
              // });
            } else {
              // Handle connection restored
              Future.delayed(Duration.zero, () {
                // TODO: Re-enable when internet connection banners are redesigned
                // if (mounted) {
                //   ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                //   ScaffoldMessenger.of(ctx).showMaterialBanner(
                //     MaterialBanner(
                //       content: const Text(
                //         'Internet connection is restored.',
                //         style: TextStyle(color: Colors.white),
                //       ),
                //       backgroundColor: const Color(0xFF2E7D32),
                //       leading: const Icon(Icons.wifi, color: Colors.white),
                //       actions: [
                //         TextButton(
                //           onPressed: () {
                //             if (mounted) {
                //               ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                //             }
                //           },
                //           child: const Text('Dismiss', style: TextStyle(color: Colors.white)),
                //         ),
                //       ],
                //       onVisible: () => Future.delayed(const Duration(seconds: 3), () {
                //         if (mounted) {
                //           ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                //         }
                //       }),
                //     ),
                //   );
                // }

                WidgetsBinding.instance.addPostFrameCallback((_) async {
                  if (mounted) {
                    if (ctx.read<ConversationProvider>().conversations.isEmpty) {
                      await ctx.read<ConversationProvider>().getInitialConversations();
                    } else {
                      // Force refresh when internet connection is restored
                      await ctx.read<ConversationProvider>().forceRefreshConversations();
                    }
                    if (ctx.read<MessageProvider>().messages.isEmpty) {
                      await ctx.read<MessageProvider>().refreshMessages();
                    }
                  }
                });
              });
            }
          }
          return child!;
        },
        child: Consumer2<HomeProvider, CaptureProvider>(
          builder: (context, homeProvider, captureProvider, _) {
            return Scaffold(
              backgroundColor: ResponsiveHelper.backgroundPrimary,
              body: Stack(
                children: [
                  // Main app content
                  Container(
                    decoration: const BoxDecoration(
                      color: ResponsiveHelper.backgroundPrimary,
                    ),
                    child: Row(
                      children: [
                        // Sidebar
                        _buildSidebar(responsive, homeProvider),

                        // Main content area with rounded container
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            child: Container(
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                  width: 1,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.05),
                                    blurRadius: 20,
                                    offset: const Offset(0, 4),
                                  ),
                                ],
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(16),
                                child: GestureDetector(
                                  onTap: () {
                                    primaryFocus?.unfocus();
                                  },
                                  child: PageView(
                                    controller: _controller,
                                    physics: const NeverScrollableScrollPhysics(),
                                    children: [
                                      const DesktopConversationsPage(),
                                      const DesktopChatPage(),
                                      const DesktopMemoriesPage(),
                                      const DesktopActionsPage(),
                                      DesktopAppsPage(
                                        onNavigateToCreateApp: navigateToCreateApp,
                                      ),
                                      DesktopAddAppPage(
                                        onNavigateBack: navigateBackToApps,
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildSidebar(ResponsiveHelper responsive, HomeProvider homeProvider) {
    return AnimatedBuilder(
      animation: _sidebarSlideAnimation,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(-50 * (1 - _sidebarSlideAnimation.value), 0),
          child: Opacity(
            opacity: _sidebarSlideAnimation.value,
            child: Container(
              width: responsive.sidebarWidth(baseWidth: 230),
              decoration: const BoxDecoration(
                color: Colors.transparent,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // macOS window controls + Logo section
                  _buildLogoSection(),

                  const SizedBox(height: 8),

                  // Main navigation section
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Main navigation items
                          _buildNavItem(
                            icon: FontAwesomeIcons.house,
                            label: 'Conversations',
                            index: 0,
                            isSelected: homeProvider.selectedIndex == 0,
                            onTap: () => _navigateToIndex(0, homeProvider),
                          ),
                          _buildNavItem(
                            icon: FontAwesomeIcons.solidComments,
                            label: 'Chat',
                            index: 1,
                            isSelected: homeProvider.selectedIndex == 1,
                            onTap: () => _navigateToIndex(1, homeProvider),
                          ),
                          _buildNavItem(
                            icon: FontAwesomeIcons.brain,
                            label: 'Memories',
                            index: 2,
                            isSelected: homeProvider.selectedIndex == 2,
                            onTap: () => _navigateToIndex(2, homeProvider),
                          ),
                          _buildNavItem(
                            icon: FontAwesomeIcons.squareCheck,
                            label: 'Actions',
                            index: 3,
                            isSelected: homeProvider.selectedIndex == 3,
                            onTap: () => _navigateToIndex(3, homeProvider),
                          ),
                          _buildNavItem(
                            icon: FontAwesomeIcons.gripVertical,
                            label: 'Apps',
                            index: 4,
                            isSelected: homeProvider.selectedIndex == 4,
                            onTap: () => _navigateToIndex(4, homeProvider),
                          ),

                          const Spacer(),

                          // Subscription upgrade banner
                          _buildSubscriptionBanner(),

                          // Get Omi Device widget
                          if (_showGetOmiWidget) ...[
                            const SizedBox(height: 12),
                            _buildGetOmiWidget(),
                          ],

                          // Sync notification when available
                          Consumer2<ConversationProvider, SyncProvider>(
                              builder: (context, convoProvider, syncProvider, child) {
                            if (homeProvider.selectedIndex == 0 && syncProvider.missingWalsInSeconds >= 120) {
                              return Container(
                                margin: const EdgeInsets.only(top: 12),
                                child: _buildSecondaryNavItem(
                                  icon: Icons.download_rounded,
                                  label: 'Sync Available',
                                  onTap: () => routeToPage(context, const SyncPage()),
                                  showAccent: true,
                                ),
                              );
                            }
                            return const SizedBox.shrink();
                          }),

                          const SizedBox(height: 16),

                          // Divider before secondary items
                          Container(
                            height: 1,
                            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                          ),

                          const SizedBox(height: 12),

                          // Secondary navigation items (same style as main nav)
                          _buildBottomNavItem(
                            icon: FontAwesomeIcons.gear,
                            label: 'Settings',
                                    onTap: () {
                              MixpanelManager().pageOpened('Settings');
                              DesktopSettingsModal.show(context);
                            },
                          ),
                          _buildBottomNavItem(
                            icon: FontAwesomeIcons.gift,
                            label: 'Refer a Friend',
                            onTap: () {
                              MixpanelManager().pageOpened('Refer a Friend');
                              launchUrl(Uri.parse('https://affiliate.omi.me'));
                            },
                          ),
                          _buildBottomNavItem(
                            icon: FontAwesomeIcons.circleQuestion,
                            label: 'Help',
                            onTap: () {
                              if (PlatformService.isIntercomSupported) {
                                Intercom.instance.displayHelpCenter();
                              }
                            },
                          ),

                          const SizedBox(height: 16),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildLogoSection() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 32, 20, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Window controls row
          Row(
            children: [
              _buildMacWindowButton(
                type: MacWindowButtonType.close,
                onTap: () async => await windowManager.close(),
              ),
              const SizedBox(width: 8),
              _buildMacWindowButton(
                type: MacWindowButtonType.minimize,
                onTap: () async => await windowManager.minimize(),
              ),
              const SizedBox(width: 8),
              _buildMacWindowButton(
                type: MacWindowButtonType.maximize,
                onTap: () async {
                  bool isMaximized = await windowManager.isMaximized();
                  if (isMaximized) {
                    await windowManager.unmaximize();
                  } else {
                    await windowManager.maximize();
                  }
                },
              ),
            ],
          ),

          const SizedBox(height: 36),

          // Logo and brand name
          Row(
            children: [
              // Omi logo icon
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(8),
                ),
                child: Assets.images.herologo.image(
                  fit: BoxFit.contain,
                ),
              ),
              const SizedBox(width: 10),
              // Brand name
              const Text(
                'Omi',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: ResponsiveHelper.textPrimary,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(width: 8),
              // Pro badge (shows for unlimited users)
              Consumer<UsageProvider>(
                builder: (context, usageProvider, child) {
                  final isUnlimited = usageProvider.subscription?.subscription.plan == PlanType.unlimited;
                  if (!isUnlimited) return const SizedBox.shrink();
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                                        border: Border.all(
                        color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                    child: const Text(
                      'Pro',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: ResponsiveHelper.purplePrimary,
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSecondaryNavItem({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    bool showAccent = false,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: showAccent ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.1) : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: showAccent
                ? Border.all(
                    color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                    width: 1,
                  )
                : null,
          ),
          child: Row(
                                        children: [
                                          Icon(
                icon,
                color: showAccent ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                                            size: 16,
                                          ),
              const SizedBox(width: 12),
                                          Expanded(
                                            child: Text(
                  label,
                                              style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                    color: showAccent ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                                              ),
                                            ),
                                          ),
                                        ],
          ),
        ),
      ),
                              );
                            }

  // Bottom nav items with same style as main navigation
  Widget _buildBottomNavItem({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 2),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(10),
          hoverColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                Icon(
                  icon,
                  color: ResponsiveHelper.textTertiary,
                  size: 17,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                      color: ResponsiveHelper.textSecondary,
                    ),
                    ),
                  ),
                ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem({
    required IconData icon,
    required String label,
    required int index,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 2),
      child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                MixpanelManager()
                    .bottomNavigationTabClicked(['Conversations', 'Chat', 'Memories', 'Actions', 'Apps'][index]);
                onTap();
              },
          borderRadius: BorderRadius.circular(10),
          hoverColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
              child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
                decoration: BoxDecoration(
              color: isSelected ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.8) : Colors.transparent,
              borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    Icon(
                      icon,
                  color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                  size: 17,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        label,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                          color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
      ),
    );
  }

  void _navigateToIndex(int index, HomeProvider homeProvider) {
    if (homeProvider.selectedIndex == index) return;

    homeProvider.setIndex(index);
    _controller?.animateToPage(
      index,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
    );
  }

  /// Navigate to create app page (index 5)
  void navigateToCreateApp() {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    homeProvider.setIndex(5);
    _controller?.animateToPage(
      5,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
    );
  }

  /// Navigate back to apps page (index 4)
  void navigateBackToApps() {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    homeProvider.setIndex(4);
    _controller?.animateToPage(
      4,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
    );
  }

  Widget _buildMacWindowButton({
    required MacWindowButtonType type,
    required VoidCallback onTap,
  }) {
    return _MacWindowButton(
      type: type,
      onTap: onTap,
    );
  }

  Widget _buildSubscriptionBanner() {
    return Consumer<UsageProvider>(
      builder: (context, usageProvider, child) {
        // Don't show if subscription UI is hidden or user is already on unlimited
        if (usageProvider.subscription?.showSubscriptionUi != true) {
          return const SizedBox.shrink();
        }

        final isUnlimited = usageProvider.subscription?.subscription.plan == PlanType.unlimited;

        if (isUnlimited) {
          return const SizedBox.shrink();
        }

        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              MixpanelManager().pageOpened('Plan & Usage');
              routeToPage(context, const UsagePage(showUpgradeDialog: true));
            },
            borderRadius: BorderRadius.circular(10),
            child: Ink(
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    ResponsiveHelper.purplePrimary,
                    ResponsiveHelper.purpleAccent,
                  ],
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    FontAwesomeIcons.bolt,
                    color: Colors.white,
                    size: 13,
                  ),
                  SizedBox(width: 8),
                  Text(
                    'Upgrade to Pro',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildGetOmiWidget() {
    return Consumer<UsageProvider>(
      builder: (context, usageProvider, child) {
        final isUnlimited = usageProvider.subscription?.subscription.plan == PlanType.unlimited;

        if (!_showGetOmiWidget) {
          return const SizedBox.shrink();
        }

        return ClipRRect(
          borderRadius: BorderRadius.circular(12),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () async {
                  MixpanelManager().track('Get Omi Device Clicked');
                  final url = Uri.parse('https://www.omi.me');
                  if (await canLaunchUrl(url)) {
                    await launchUrl(url, mode: LaunchMode.externalApplication);
                  }
                },
                child: Container(
                padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
                      width: 1,
                    ),
                  ),
                child: Row(
                    children: [
                    // Omi device image
                    SizedBox(
                      width: 40,
                      height: 40,
                      child: Assets.images.omiWithRopeNoPadding.image(
                        fit: BoxFit.contain,
                      ),
                    ),
                    const SizedBox(width: 12),
                    // Text content
                    Expanded(
                        child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                            const Text(
                            'Get Omi Device',
                              style: TextStyle(
                              fontSize: 13,
                                fontWeight: FontWeight.w600,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Wearable AI companion',
                                    style: TextStyle(
                              fontSize: 11,
                              color: ResponsiveHelper.textTertiary.withValues(alpha: 0.8),
                            ),
                          ),
                        ],
                        ),
                    ),
                      // Close button for unlimited users
                      if (isUnlimited)
                      GestureDetector(
                        onTap: () {
                              setState(() {
                                _showGetOmiWidget = false;
                              });
                              SharedPreferencesUtil().showGetOmiCard = false;
                            },
                        child: Icon(
                          Icons.close,
                          color: ResponsiveHelper.textTertiary.withValues(alpha: 0.6),
                          size: 16,
                        ),
                      ),
                    if (!isUnlimited)
                const Icon(
                        FontAwesomeIcons.chevronRight,
                        color: ResponsiveHelper.textTertiary,
                  size: 12,
                ),
              ],
            ),
          ),
            ),
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    ForegroundUtil.stopForegroundTask();
    _sidebarAnimationController.dispose();
    if (_controller != null) {
      _controller!.dispose();
      _controller = null;
    }
    super.dispose();
  }
}
