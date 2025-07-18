import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/desktop/pages/onboarding/desktop_onboarding_wrapper.dart';
import 'package:omi/pages/settings/about.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/desktop/pages/settings/desktop_profile_page.dart';
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
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:window_manager/window_manager.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:flutter/services.dart';
import '../../pages/conversations/sync_page.dart';
import 'home/widgets/battery_info_widget.dart';

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
            color: _isHovered ? _getButtonColor() : const Color(0xFFFFFFFF).withOpacity(0.07),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: _isHovered ? _getButtonColor().withOpacity(0.8) : const Color(0xFFD0D0D0),
              width: 0.5,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
                blurRadius: 1,
                offset: const Offset(0, 0.5),
              ),
            ],
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
  final GlobalKey _profileCardKey = GlobalKey();

  bool _isRecordingMinimized = false;

  // Native overlay platform channel
  static const _overlayChannel = MethodChannel('overlayPlatform');

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
    PlatformManager.instance.instabug.logInfo(event);
  }

  bool? previousConnection;

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

    // Setup overlay channel method handler for callbacks from native side
    _overlayChannel.setMethodCallHandler(_handleOverlayMethod);

    super.initState();
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
              width: responsive.sidebarWidth(baseWidth: 280),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.85),
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
                      padding: const EdgeInsets.symmetric(horizontal: 20),
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

                          // Profile card at bottom
                          _buildProfileCard(),

                          // Sync notification when available
                          Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
                            if (homeProvider.selectedIndex == 0 && convoProvider.missingWalsInSeconds >= 120) {
                              return Container(
                                margin: const EdgeInsets.fromLTRB(0, 8, 0, 16),
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
                                      child: const Row(
                                        children: [
                                          Icon(
                                            Icons.download_rounded,
                                            color: ResponsiveHelper.purplePrimary,
                                            size: 16,
                                          ),
                                          SizedBox(width: 8),
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
                MixpanelManager()
                    .bottomNavigationTabClicked(['Conversations', 'Chat', 'Memories', 'Actions', 'Apps'][index]);
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
                decoration: const BoxDecoration(
                  color: ResponsiveHelper.purplePrimary,
                  borderRadius: BorderRadius.only(
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

  // Global floating recording widget methods
  void minimizeRecording() {
    setState(() {
      _isRecordingMinimized = true;
    });
    _showNativeOverlay(); // Show native overlay when minimizing

    // Update overlay with current state
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    final recordingState = captureProvider.recordingState;
    final isRecording = recordingState == RecordingState.systemAudioRecord;
    final isPaused = captureProvider.isPaused;

    _updateOverlayState(isRecording: isRecording, isPaused: isPaused);

    // Update with latest transcript if available
    if (captureProvider.segments.isNotEmpty) {
      final latestSegment = captureProvider.segments.last;
      _updateOverlayTranscript(
        transcript: latestSegment.text.trim(),
        segmentCount: captureProvider.segments.length,
      );
    } else {
      _updateOverlayStatus(_getStatusText(recordingState, isPaused));
    }
  }

  void expandRecording() {
    setState(() {
      _isRecordingMinimized = false;
    });
    _hideNativeOverlay();
  }

  Future<void> toggleRecordingFromFloat(CaptureProvider provider) async {
    var recordingState = provider.recordingState;

    if (recordingState == RecordingState.systemAudioRecord) {
      await provider.pauseSystemAudioRecording();
    } else {
      await provider.resumeSystemAudioRecording();
    }

    // Update overlay state
    final isRecording = provider.recordingState == RecordingState.systemAudioRecord;
    final isPaused = provider.isPaused;
    await _updateOverlayState(isRecording: isRecording, isPaused: isPaused);
  }

  Future<void> stopRecordingFromFloat(CaptureProvider provider) async {
    await provider.stopSystemAudioRecording();
    await provider.forceProcessingCurrentConversation();
    _hideNativeOverlay(); // Hide overlay when stopping
    setState(() {
      _isRecordingMinimized = false;
    });
  }

  String _getStatusText(RecordingState state, bool isPaused) {
    if (isPaused) return 'Recording paused';
    switch (state) {
      case RecordingState.initialising:
        return 'Initializing recording...';
      case RecordingState.systemAudioRecord:
        return 'Listening for audio...';
      default:
        return 'Ready to record';
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Reset minimized state when recording stops completely
    final captureProvider = Provider.of<CaptureProvider>(context);
    if (captureProvider.recordingState == RecordingState.stop && _isRecordingMinimized) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _isRecordingMinimized = false;
          });
        }
      });
    }

    // Update native overlay with real-time transcript and state changes
    if (_isRecordingMinimized) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _updateNativeOverlayFromProvider(captureProvider);
      });
    }
  }

  void _updateNativeOverlayFromProvider(CaptureProvider captureProvider) {
    final recordingState = captureProvider.recordingState;
    final isRecording = recordingState == RecordingState.systemAudioRecord;
    final isPaused = captureProvider.isPaused;

    // Update overlay state
    _updateOverlayState(isRecording: isRecording, isPaused: isPaused);

    // Update transcript or status
    if (captureProvider.segments.isNotEmpty) {
      final latestSegment = captureProvider.segments.last;
      _updateOverlayTranscript(
        transcript: latestSegment.text.trim(),
        segmentCount: captureProvider.segments.length,
      );
    } else {
      _updateOverlayStatus(_getStatusText(recordingState, isPaused));
    }
  }

  // Legacy Flutter floating widget removed - now using native macOS overlay

  Widget _buildWindowControls() {
    return Container(
      height: 52,
      padding: const EdgeInsets.fromLTRB(24, 16, 16, 0),
      child: Row(
        children: [
          // Close button
          _buildMacWindowButton(
            type: MacWindowButtonType.close,
            onTap: () async {
              await windowManager.close();
            },
          ),
          const SizedBox(width: 8),

          // Minimize button
          _buildMacWindowButton(
            type: MacWindowButtonType.minimize,
            onTap: () async {
              await windowManager.minimize();

              // Show overlay if recording is active
              final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
              final recordingState = captureProvider.recordingState;
              final isRecording = recordingState == RecordingState.systemAudioRecord;
              final isInitializing = recordingState == RecordingState.initialising;
              final isPaused = captureProvider.isPaused;
              final isRecordingOrInitializing = isRecording || isInitializing || isPaused;

              if (isRecordingOrInitializing) {
                setState(() {
                  _isRecordingMinimized = true;
                });
                _showNativeOverlay();

                // Update overlay with current state
                _updateOverlayState(isRecording: isRecording, isPaused: isPaused);

                // Update with latest transcript if available
                if (captureProvider.segments.isNotEmpty) {
                  final latestSegment = captureProvider.segments.last;
                  _updateOverlayTranscript(
                    transcript: latestSegment.text.trim(),
                    segmentCount: captureProvider.segments.length,
                  );
                } else {
                  _updateOverlayStatus(_getStatusText(recordingState, isPaused));
                }
              }
            },
          ),
          const SizedBox(width: 8),

          // Maximize/Restore button
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

  Widget _buildProfileCard() {
    final userName = SharedPreferencesUtil().givenName;
    final userEmail = SharedPreferencesUtil().email;

    return Container(
      key: _profileCardKey,
      margin: const EdgeInsets.fromLTRB(0, 0, 0, 16),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _showProfilePopup(context),
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(12),
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
                // Profile picture
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                      width: 1.5,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      userName.isNotEmpty ? userName[0].toUpperCase() : 'U',
                      style: const TextStyle(
                        color: ResponsiveHelper.purplePrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),

                const SizedBox(width: 12),

                // User info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        userName.isNotEmpty ? userName : 'User',
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        userEmail.isNotEmpty ? userEmail : 'No email set',
                        style: const TextStyle(
                          color: ResponsiveHelper.textTertiary,
                          fontSize: 11,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),

                // Chevron icon
                const Icon(
                  FontAwesomeIcons.chevronUp,
                  color: ResponsiveHelper.textSecondary,
                  size: 12,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showProfilePopup(BuildContext context) {
    final RenderBox? profileCardBox = _profileCardKey.currentContext?.findRenderObject() as RenderBox?;
    if (profileCardBox == null) return;

    final Offset profileCardPosition = profileCardBox.localToGlobal(Offset.zero);
    final Size profileCardSize = profileCardBox.size;

    // Calculate profile card width - exact same width as the profile card
    final profileCardWidth = profileCardSize.width;

    // Menu height estimate (profile header + dividers + 7 menu items)
    const double menuHeight = 320.0;
    const double gap = 8.0; // Gap between popup and profile card

    showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        profileCardPosition.dx, // Left edge aligned with profile card
        profileCardPosition.dy - menuHeight - gap, // Position above the profile card (menuHeight + gap pixels up)
        profileCardPosition.dx + profileCardWidth, // Right edge aligned with profile card
        profileCardPosition.dy - gap, // Bottom edge positioned gap pixels above profile card top
      ),
      color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.95),
      elevation: 12,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      // Add custom animation for bottom-up slide
      popUpAnimationStyle: const AnimationStyle(
        duration: Duration(milliseconds: 200),
        curve: Curves.easeOutCubic,
      ),
      items: [
        // Profile header
        PopupMenuItem<String>(
          enabled: false,
          padding: EdgeInsets.zero,
          child: _buildProfileHeader(profileCardWidth),
        ),

        // Divider
        PopupMenuItem<String>(
          enabled: false,
          height: 1,
          padding: EdgeInsets.zero,
          child: Container(
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: 16),
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          ),
        ),

        // Settings options
        _buildPopupMenuItem('profile', Icons.person, 'Profile', profileCardWidth),
        _buildPopupMenuItem('device', Icons.bluetooth_connected, 'Device Settings', profileCardWidth),
        _buildPopupMenuItem('developer', Icons.code, 'Developer Mode', profileCardWidth),
        _buildPopupMenuItem('about', Icons.info_outline, 'About Omi', profileCardWidth),

        // Divider before sign out
        PopupMenuItem<String>(
          enabled: false,
          height: 1,
          padding: EdgeInsets.zero,
          child: Container(
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          ),
        ),

        _buildPopupMenuItem('signout', Icons.logout, 'Sign Out', profileCardWidth, isDestructive: true),
      ],
    ).then((String? result) {
      if (result != null) {
        _handleProfileMenuSelection(result);
      }
    });
  }

  Widget _buildProfileHeader(double width) {
    final userName = SharedPreferencesUtil().givenName;
    final userEmail = SharedPreferencesUtil().email;

    return Container(
      width: width,
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          // Profile picture
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(
                color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                width: 2,
              ),
            ),
            child: Center(
              child: Text(
                userName.isNotEmpty ? userName[0].toUpperCase() : 'U',
                style: const TextStyle(
                  color: ResponsiveHelper.purplePrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),

          const SizedBox(width: 12),

          // User info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  userName.isNotEmpty ? userName : 'User',
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  userEmail.isNotEmpty ? userEmail : 'No email set',
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 12,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  PopupMenuItem<String> _buildPopupMenuItem(String value, IconData icon, String title, double width,
      {bool isDestructive = false}) {
    return PopupMenuItem<String>(
      value: value,
      padding: EdgeInsets.zero,
      child: Container(
        width: width,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Icon(
              icon,
              color: isDestructive ? Colors.red.shade400 : ResponsiveHelper.textSecondary,
              size: 18,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  color: isDestructive ? Colors.red.shade400 : ResponsiveHelper.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _handleProfileMenuSelection(String value) {
    switch (value) {
      case 'profile':
        MixpanelManager().pageOpened('Settings');
        routeToPage(context, const DesktopProfilePage());
        break;
      case 'device':
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (context) => const DeviceSettings(),
          ),
        );
        break;
      case 'developer':
        routeToPage(context, const DeveloperSettingsPage());
        break;
      case 'help':
        if (PlatformService.isIntercomSupported) {
          Intercom.instance.displayHelpCenter();
        }
        break;
      case 'about':
        routeToPage(context, const AboutOmiPage());
        break;
      case 'signout':
        _showSignOutDialog();
        break;
    }
  }

  void _showSignOutDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: const Text(
          'Sign Out?',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: const Text(
          'Are you sure you want to sign out?',
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text(
              'Cancel',
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ),
          TextButton(
            onPressed: () async {
              await SharedPreferencesUtil().clearUserPreferences();
              Navigator.of(context).pop();
              await signOut();
              if (mounted) {
                routeToPage(context, const DesktopOnboardingWrapper(), replace: true);
              }
            },
            child: Text(
              'Sign Out',
              style: TextStyle(
                color: Colors.red.shade400,
              ),
            ),
          ),
        ],
      ),
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
    _hideNativeOverlay(); // Clean up overlay when page is disposed
    super.dispose();
  }

  // Handle method calls from native overlay
  Future<void> _handleOverlayMethod(MethodCall call) async {
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);

    switch (call.method) {
      case 'onPlayPause':
        await toggleRecordingFromFloat(captureProvider);
        break;
      case 'onStop':
        await stopRecordingFromFloat(captureProvider);
        break;
      case 'onExpand':
        expandRecording();
        break;
    }
  }

  // Native overlay methods
  Future<void> _showNativeOverlay() async {
    try {
      await _overlayChannel.invokeMethod('showOverlay');
    } catch (e) {
      print('Error showing native overlay: $e');
    }
  }

  Future<void> _hideNativeOverlay() async {
    try {
      await _overlayChannel.invokeMethod('hideOverlay');
    } catch (e) {
      print('Error hiding native overlay: $e');
    }
  }

  Future<void> _updateOverlayState({
    required bool isRecording,
    required bool isPaused,
  }) async {
    try {
      await _overlayChannel.invokeMethod('updateOverlayState', {
        'isRecording': isRecording,
        'isPaused': isPaused,
      });
    } catch (e) {
      print('Error updating overlay state: $e');
    }
  }

  Future<void> _updateOverlayTranscript({
    required String transcript,
    required int segmentCount,
  }) async {
    try {
      await _overlayChannel.invokeMethod('updateOverlayTranscript', {
        'transcript': transcript,
        'segmentCount': segmentCount,
      });
    } catch (e) {
      print('Error updating overlay transcript: $e');
    }
  }

  Future<void> _updateOverlayStatus(String status) async {
    try {
      await _overlayChannel.invokeMethod('updateOverlayStatus', {
        'status': status,
      });
    } catch (e) {
      print('Error updating overlay status: $e');
    }
  }
}
