import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/apps/page.dart';
import 'conversations/desktop_conversations_page.dart';
import 'chat/desktop_chat_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'memories/desktop_memories_page.dart';
import 'package:omi/pages/settings/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:window_manager/window_manager.dart';

import '../../pages/conversations/sync_page.dart';
import 'home/widgets/battery_info_widget.dart';

/// Desktop home page - premium minimal design with complete mobile functionality
class DesktopHomePage extends StatefulWidget {
  final String? navigateToRoute;
  const DesktopHomePage({super.key, this.navigateToRoute});

  @override
  State<DesktopHomePage> createState() => _DesktopHomePageState();
}

class _DesktopHomePageState extends State<DesktopHomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();
  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;

  PageController? _controller;
  late AnimationController _sidebarAnimationController;
  late Animation<double> _sidebarSlideAnimation;

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

      // Reload convos
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
    PlatformManager.instance.instabug.logInfo(event);
  }

  bool? previousConnection;

  void _onReceiveTaskData(dynamic data) async {
    debugPrint('_onReceiveTaskData $data');
    if (data is! Map<String, dynamic>) return;
    if (!(data.containsKey('latitude') && data.containsKey('longitude'))) return;
    await updateUserGeolocation(
      geolocation: Geolocation(
        latitude: data['latitude'],
        longitude: data['longitude'],
        accuracy: data['accuracy'],
        altitude: data['altitude'],
        time: DateTime.parse(data['time']).toUtc(),
      ),
    );
  }

  @override
  void initState() {
    SharedPreferencesUtil().onboardingCompleted = true;

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

      // Same mobile initialization logic
      if (!PlatformService.isDesktop) {
        await ForegroundUtil.initializeForegroundService();
        ForegroundUtil.startForegroundTask();
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Handle navigation
      switch (pageAlias) {
        case "chat":
          print('inside chat alias $detailPageId');
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
    super.initState();

    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
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
              Future.delayed(const Duration(seconds: 2), () {
                if (mounted && !connectivityProvider.isConnected) {
                  ScaffoldMessenger.of(ctx).showMaterialBanner(
                    MaterialBanner(
                      content: const Text(
                        'No internet connection. Please check your connection.',
                        style: TextStyle(color: Colors.white70),
                      ),
                      backgroundColor: const Color(0xFF424242),
                      leading: const Icon(Icons.wifi_off, color: Colors.white70),
                      actions: [
                        TextButton(
                          onPressed: () {
                            ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                          },
                          child: const Text('Dismiss', style: TextStyle(color: Colors.white70)),
                        ),
                      ],
                    ),
                  );
                }
              });
            } else {
              // Handle connection restored
              Future.delayed(Duration.zero, () {
                if (mounted) {
                  ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                  ScaffoldMessenger.of(ctx).showMaterialBanner(
                    MaterialBanner(
                      content: const Text(
                        'Internet connection is restored.',
                        style: TextStyle(color: Colors.white),
                      ),
                      backgroundColor: const Color(0xFF2E7D32),
                      leading: const Icon(Icons.wifi, color: Colors.white),
                      actions: [
                        TextButton(
                          onPressed: () {
                            if (mounted) {
                              ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                            }
                          },
                          child: const Text('Dismiss', style: TextStyle(color: Colors.white)),
                        ),
                      ],
                      onVisible: () => Future.delayed(const Duration(seconds: 3), () {
                        if (mounted) {
                          ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                        }
                      }),
                    ),
                  );
                }

                WidgetsBinding.instance.addPostFrameCallback((_) async {
                  if (mounted) {
                    if (ctx.read<ConversationProvider>().conversations.isEmpty) {
                      await ctx.read<ConversationProvider>().getInitialConversations();
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
        child: Consumer<HomeProvider>(
          builder: (context, homeProvider, _) {
            return Scaffold(
              backgroundColor: ResponsiveHelper.backgroundPrimary,
              body: Container(
                decoration: BoxDecoration(
                  gradient: responsive.backgroundGradient,
                ),
                child: Row(
                  children: [
                    // Premium sidebar with device widget
                    _buildSidebar(responsive, homeProvider),

                    // Main content area with rounded container
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        child: Container(
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.4),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                              width: 1,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.05),
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
                                children: const [
                                  DesktopConversationsPage(),
                                  DesktopChatPage(),
                                  DesktopMemoriesPage(),
                                  ActionItemsPage(),
                                  AppsPage(),
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
              width: responsive.sidebarWidth(baseWidth: 280),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withOpacity(0.85),
                borderRadius: const BorderRadius.only(
                  topRight: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                ),
                border: const Border(
                  right: BorderSide(
                    color: ResponsiveHelper.backgroundTertiary,
                    width: 1,
                  ),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.1),
                    blurRadius: 10,
                    offset: const Offset(2, 0),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // macOS window controls at top
                  _buildWindowControls(),

                  const SizedBox(height: 16),

                  // Main navigation section
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Main navigation items
                          _buildNavItem(
                            icon: FontAwesomeIcons.inbox,
                            label: 'Conversations',
                            index: 0,
                            isSelected: homeProvider.selectedIndex == 0,
                            onTap: () => _navigateToIndex(0, homeProvider),
                          ),
                          const SizedBox(height: 4),
                          _buildNavItem(
                            icon: FontAwesomeIcons.solidMessage,
                            label: 'Chat',
                            index: 1,
                            isSelected: homeProvider.selectedIndex == 1,
                            onTap: () => _navigateToIndex(1, homeProvider),
                          ),
                          const SizedBox(height: 4),
                          _buildNavItem(
                            icon: FontAwesomeIcons.brain,
                            label: 'Memories',
                            index: 2,
                            isSelected: homeProvider.selectedIndex == 2,
                            onTap: () => _navigateToIndex(2, homeProvider),
                          ),
                          const SizedBox(height: 4),
                          _buildNavItem(
                            icon: FontAwesomeIcons.listCheck,
                            label: 'Actions',
                            index: 3,
                            isSelected: homeProvider.selectedIndex == 3,
                            onTap: () => _navigateToIndex(3, homeProvider),
                          ),
                          const SizedBox(height: 4),
                          _buildNavItem(
                            icon: FontAwesomeIcons.store,
                            label: 'Apps',
                            index: 4,
                            isSelected: homeProvider.selectedIndex == 4,
                            onTap: () => _navigateToIndex(4, homeProvider),
                          ),

                          const Spacer(),

                          // Device connection status at bottom
                          _buildDeviceStatus(),

                          // Sync notification when available
                          Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
                            if (homeProvider.selectedIndex == 0 && convoProvider.missingWalsInSeconds >= 120) {
                              return Container(
                                margin: const EdgeInsets.fromLTRB(8, 8, 8, 16),
                                child: Material(
                                  color: Colors.transparent,
                                  child: InkWell(
                                    onTap: () {
                                      routeToPage(context, const SyncPage());
                                    },
                                    borderRadius: BorderRadius.circular(8),
                                    child: Container(
                                      padding: const EdgeInsets.all(12),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(
                                          color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Row(
                                        children: [
                                          Icon(
                                            Icons.download_rounded,
                                            color: ResponsiveHelper.purplePrimary,
                                            size: 16,
                                          ),
                                          const SizedBox(width: 8),
                                          Expanded(
                                            child: Text(
                                              'Sync Available',
                                              style: TextStyle(
                                                fontSize: 12,
                                                fontWeight: FontWeight.w500,
                                                color: ResponsiveHelper.textPrimary,
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
                            return const SizedBox.shrink();
                          }),
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

  Widget _buildNavItem({
    required IconData icon,
    required String label,
    required int index,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 1),
      child: Stack(
        children: [
          // Navigation item with full container
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                MixpanelManager().bottomNavigationTabClicked(['Conversations', 'Chat', 'Memories', 'Actions', 'Apps'][index]);
                onTap();
              },
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: isSelected ? ResponsiveHelper.backgroundTertiary.withOpacity(0.8) : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      icon,
                      color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                      size: 18,
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
          // Selection accent line spanning full item height
          if (isSelected)
            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Container(
                width: 5,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary,
                  borderRadius: const BorderRadius.only(
                    topRight: Radius.circular(8),
                    bottomRight: Radius.circular(8),
                  ),
                ),
              ),
            ),
        ],
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

  Widget _buildWindowControls() {
    return Container(
      height: 52,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: Row(
        children: [
          // Close button
          _buildWindowButton(
            color: const Color(0xFFFF5F57),
            onTap: () async {
              await windowManager.close();
            },
          ),
          const SizedBox(width: 8),

          // Minimize button
          _buildWindowButton(
            color: const Color(0xFFFFBD2E),
            onTap: () async {
              await windowManager.minimize();
            },
          ),
          const SizedBox(width: 8),

          // Maximize/Restore button
          _buildWindowButton(
            color: const Color(0xFF28CA42),
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
    );
  }

  Widget _buildWindowButton({
    required Color color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 12,
        height: 12,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(6),
          boxShadow: [
            BoxShadow(
              color: color.withOpacity(0.3),
              blurRadius: 2,
              offset: const Offset(0, 1),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceStatus() {
    return Consumer<DeviceProvider>(
      builder: (context, deviceProvider, child) {
        final isConnected = deviceProvider.connectedDevice != null;

        return Container(
          margin: const EdgeInsets.fromLTRB(8, 0, 8, 16),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isConnected ? ResponsiveHelper.purplePrimary.withOpacity(0.3) : ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: isConnected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isConnected ? 'Device Connected' : 'Device Offline',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: isConnected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                      ),
                    ),
                    if (isConnected && deviceProvider.connectedDevice != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        deviceProvider.connectedDevice!.name,
                        style: TextStyle(
                          fontSize: 10,
                          color: ResponsiveHelper.textQuaternary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              // Battery info integration
              if (isConnected) const DesktopBatteryInfoWidget(),
            ],
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
