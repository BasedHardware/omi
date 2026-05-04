import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:upgrader/upgrader.dart';

import 'package:omi/backend/http/api/agents.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/phone_calls/active_call_banner.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/apple_reminders_sync_service.dart';
import 'package:omi/services/quick_actions_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/services/announcement_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'widgets/battery_info_widget.dart';

class HomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  const HomePageWrapper({super.key, this.navigateToRoute});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  String? _navigateToRoute;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        context.read<DeviceProvider>().initiateConnection('HomePageWrapper', boundDeviceOnly: true);
      }
      // Check actual system permission state — the SharedPreferences flag may
      // be stale (e.g. user granted via Settings > Permissions, or reinstall).
      final notifGranted = await Permission.notification.isGranted;
      if (notifGranted) {
        SharedPreferencesUtil().notificationsEnabled = true;
        NotificationService.instance.register();
        NotificationService.instance.saveNotificationToken();
      }
    });
    _navigateToRoute = widget.navigateToRoute;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return HomePage(navigateToRoute: _navigateToRoute);
  }
}

class HomePage extends StatefulWidget {
  final String? navigateToRoute;
  const HomePage({super.key, this.navigateToRoute});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox(), const SizedBox()];

  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;
  StreamSubscription? _notificationStreamSubscription;

  final GlobalKey<HomeContentPageState> _homeContentPageKey = GlobalKey<HomeContentPageState>();
  final GlobalKey<State<ConversationsPage>> _conversationsPageKey = GlobalKey<State<ConversationsPage>>();
  final GlobalKey<State<ActionItemsPage>> _actionItemsPageKey = GlobalKey<State<ActionItemsPage>>();
  final GlobalKey<AppsPageState> _appsPageKey = GlobalKey<AppsPageState>();
  late final List<Widget> _pages;

  // Freemium switch handler for auto-switch dialogs
  final FreemiumSwitchHandler _freemiumHandler = FreemiumSwitchHandler();

  CaptureProvider? _captureProvider;
  DeviceProvider? _deviceProviderForQuickActions;
  CaptureProvider? _captureProviderForQuickActions;

  void _initiateApps() {
    context.read<AppProvider>().getApps();
    context.read<AppProvider>().getPopularApps();
  }

  void _scrollToTop(int pageIndex) {
    switch (pageIndex) {
      case 0:
        _homeContentPageKey.currentState?.scrollToTop();
        break;
      case 1:
        final conversationsState = _conversationsPageKey.currentState;
        if (conversationsState != null) {
          (conversationsState as dynamic).scrollToTop();
        }
        break;
      case 2:
        final actionItemsState = _actionItemsPageKey.currentState;
        if (actionItemsState != null) {
          (actionItemsState as dynamic).scrollToTop();
        }
        break;
      case 3:
        _appsPageKey.currentState?.scrollToTop();
        break;
    }
  }

  void _addGoal() {
    context.read<HomeProvider>().setIndex(1);
    final conversationsState = _conversationsPageKey.currentState;
    if (conversationsState != null) {
      (conversationsState as dynamic).addGoal();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    String event = '';
    if (state == AppLifecycleState.paused) {
      event = 'App is paused';
      // Stop keepalive when app goes to background
      if (mounted) {
        Provider.of<MessageProvider>(context, listen: false).stopVmKeepalive();
      }
    } else if (state == AppLifecycleState.resumed) {
      event = 'App is resumed';

      // Reload convos
      if (mounted) {
        Provider.of<ConversationProvider>(context, listen: false).refreshConversations();
        Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
      }

      // Ensure agent VM is running and restart keepalive
      if (mounted && SharedPreferencesUtil().claudeAgentEnabled) {
        ensureAgentVm();
        Provider.of<MessageProvider>(context, listen: false).startVmKeepalive();
      }

      // Sync Apple Reminders on foreground resume
      if (mounted && PlatformService.isApple) {
        final taskProvider = Provider.of<TaskIntegrationProvider>(context, listen: false);
        if (taskProvider.selectedApp == TaskIntegrationApp.appleReminders) {
          AppleRemindersSyncService().syncOnForegroundResume().then((_) {
            if (mounted) {
              Provider.of<ActionItemsProvider>(context, listen: false).forceRefreshActionItems();
            }
          });
        }
      }
    } else if (state == AppLifecycleState.hidden) {
      event = 'App is hidden';
    } else if (state == AppLifecycleState.detached) {
      event = 'App is detached';
    } else {
      return;
    }
    Logger.debug(event);
    PlatformManager.instance.crashReporter.logInfo(event);
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {'/facts': const MemoriesPage()};
  bool? previousConnection;

  void _onReceiveTaskData(dynamic data) async {
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
    _pages = [
      HomeContentPage(key: _homeContentPageKey),
      ConversationsPage(key: _conversationsPageKey),
      ActionItemsPage(key: _actionItemsPageKey, onAddGoal: _addGoal),
      AppsPage(key: _appsPageKey),
    ];
    SharedPreferencesUtil().onboardingCompleted = true;
    if (!SharedPreferencesUtil().permissionsCompleted) {
      SharedPreferencesUtil().permissionsCompleted = true;
    }
    updateUserOnboardingState(completed: true);

    // Navigate uri
    Uri? navigateToUri;
    var pageAlias = "home";
    var homePageIdx = 0;
    String? detailPageId;

    if (widget.navigateToRoute != null && widget.navigateToRoute!.isNotEmpty) {
      navigateToUri = Uri.tryParse("http://localhost.com${widget.navigateToRoute!}");
      Logger.debug("initState ${navigateToUri?.pathSegments.join("...")}");
      var segments = navigateToUri?.pathSegments ?? [];
      if (segments.isNotEmpty) {
        pageAlias = segments[0];
      }
      if (segments.length > 1) {
        detailPageId = segments[1];
      }

      switch (pageAlias) {
        case "action-items":
          homePageIdx = 2;
          break;
        case "memories":
        case "facts":
          homePageIdx = 0;
          break;
        case "apps":
          homePageIdx = 3;
          break;
      }
    }

    // Home controller
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    WidgetsBinding.instance.addObserver(this);

    // Pre-warm agent VM and WebSocket so session is ready by the time the user opens chat
    if (SharedPreferencesUtil().claudeAgentEnabled) {
      print('[HomePage] claudeAgentEnabled=true, calling ensureAgentVm + starting keepalive + preConnectAgent');
      ensureAgentVm();
      final messageProvider = Provider.of<MessageProvider>(context, listen: false);
      messageProvider.startVmKeepalive();
      messageProvider.preConnectAgent();
    } else {
      print('[HomePage] claudeAgentEnabled=false, skipping VM ensure');
    }

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();

      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.always || permission == LocationPermission.whileInUse) {
        await ForegroundUtil.initializeForegroundService();
        await ForegroundUtil.startForegroundTask();
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(
          context,
          listen: false,
        ).streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Navigate
      if (!mounted) return;
      switch (pageAlias) {
        case "apps":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            final appProvider = context.read<AppProvider>();
            var app = await appProvider.getAppFromId(detailPageId);
            if (app != null && mounted) {
              Navigator.push(context, MaterialPageRoute(builder: (context) => AppDetailPage(app: app)));
            }
          }
          break;
        case "chat":
          Logger.debug('inside chat alias $detailPageId');
          if (detailPageId != null && detailPageId.isNotEmpty) {
            var appId = detailPageId != "omi" ? detailPageId : ''; // omi ~ no select
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
          // Navigate to chat page directly since it's no longer in the tab bar
          // All async setup (streamDeviceRecording, refreshMessages) is already awaited above,
          // so the widget tree is fully settled — push directly.
          if (mounted) {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const ChatPage(isPivotBottom: false)),
            );
          }
          break;
        case "settings":
          // Use context from the current widget instead of navigator key for bottom sheet
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              SettingsDrawer.show(context);
            }
          });
          if (detailPageId == 'data-privacy') {
            globalNavigatorKey.currentState?.push(MaterialPageRoute(builder: (context) => const DataPrivacyPage()));
          }
          break;
        case "memories":
        case "facts":
          globalNavigatorKey.currentState?.push(MaterialPageRoute(builder: (context) => const MemoriesPage()));
          break;
        case "conversation":
          // Handle conversation deep link: /conversation/{id}?share=1
          if (detailPageId != null && detailPageId.isNotEmpty) {
            // Check for share query param
            final shouldOpenShare = navigateToUri?.queryParameters['share'] == '1';
            final conversationId = detailPageId; // Capture non-null value

            WidgetsBinding.instance.addPostFrameCallback((_) async {
              if (!mounted) return;

              // Fetch conversation from server
              final conversation = await getConversationById(conversationId);
              if (conversation != null && mounted) {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                        ConversationDetailPage(conversation: conversation, openShareToContactsOnLoad: shouldOpenShare),
                  ),
                );
              } else {
                Logger.debug('Conversation not found: $conversationId');
              }
            });
          }
          break;
        case "daily-summary":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            // Track notification opened
            MixpanelManager().dailySummaryNotificationOpened(
              summaryId: detailPageId,
              date: '', // Date not available in navigate_to, will be fetched when detail page loads
            );

            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => DailySummaryDetailPage(summaryId: detailPageId!)),
                );
              }
            });
          }
          break;
        case "wrapped":
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(context, MaterialPageRoute(builder: (context) => const Wrapped2025Page()));
            }
          });
          break;
        case "action-items":
          // Tab index already set to 2 (ActionItemsPage) above
          break;
        default:
      }
    });

    _listenToMessagesFromNotification();
    _listenToFreemiumThreshold();
    _checkForAnnouncements();
    _registerAutoSyncCallback();
    _initQuickActions();
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  void _checkForAnnouncements() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;

      await Future.delayed(const Duration(seconds: 2));

      if (!mounted) return;

      final announcementProvider = Provider.of<AnnouncementProvider>(context, listen: false);
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      await AnnouncementService().checkAndShowAnnouncements(
        context,
        announcementProvider,
        connectedDevice: deviceProvider.connectedDevice,
      );

      // Register callback for device connection to check firmware announcements
      deviceProvider.onDeviceConnected = _onDeviceConnectedForAnnouncements;
    });
  }

  void _registerAutoSyncCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      final syncProvider = Provider.of<SyncProvider>(context, listen: false);
      deviceProvider.onOfflineDataDetected = (device, fileCount, totalBytes) {
        if (!syncProvider.isSyncing) {
          Logger.debug('HomePage: Auto-sync triggered ($fileCount files, $totalBytes bytes)');
          syncProvider.syncWals();
        }
      };
    });
  }

  void _initQuickActions() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      QuickActionsService.instance.initialize(context);
      _deviceProviderForQuickActions = Provider.of<DeviceProvider>(context, listen: false);
      _deviceProviderForQuickActions!.addListener(_onDeviceStateChangedForQuickActions);
      _captureProviderForQuickActions = Provider.of<CaptureProvider>(context, listen: false);
      _captureProviderForQuickActions!.addListener(_onDeviceStateChangedForQuickActions);
    });
  }

  void _onDeviceStateChangedForQuickActions() {
    if (!mounted) return;
    QuickActionsService.instance.updateShortcuts(context);
  }

  void _onDeviceConnectedForAnnouncements(BtDevice device) async {
    if (!mounted) return;

    final announcementProvider = Provider.of<AnnouncementProvider>(context, listen: false);
    await AnnouncementService().showFirmwareUpdateAnnouncements(
      context,
      announcementProvider,
      device.firmwareRevision,
      device.modelNumber,
    );
  }

  void _listenToFreemiumThreshold() {
    // Listen to capture provider for freemium threshold events
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      _captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      _captureProvider!.addListener(_onCaptureProviderChanged);
      // Connect freemium session reset callback
      _captureProvider!.onFreemiumSessionReset = () {
        _freemiumHandler.resetDialogFlag();
      };
    });
  }

  void _onCaptureProviderChanged() {
    if (!mounted || _captureProvider == null) return;

    if (!context.read<UsageProvider>().showSubscriptionUI) return;

    _freemiumHandler.checkAndShowDialog(context, _captureProvider!).catchError((e) {
      Logger.debug('[Freemium] Error checking dialog: $e');
      return false;
    });
  }

  void _listenToMessagesFromNotification() {
    _notificationStreamSubscription = NotificationService.instance.listenForServerMessages.listen((message) {
      if (mounted) {
        var selectedApp = Provider.of<AppProvider>(context, listen: false).getSelectedApp();
        if (selectedApp == null || message.appId == selectedApp.id) {
          Provider.of<MessageProvider>(context, listen: false).addMessage(message);
        }
        // chatPageKey.currentState?.scrollToBottom();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return MyUpgradeAlert(
      upgrader: _upgrader,
      dialogStyle: Platform.isIOS ? UpgradeDialogStyle.cupertino : UpgradeDialogStyle.material,
      child: Consumer<ConnectivityProvider>(
        builder: (ctx, connectivityProvider, child) {
          bool isConnected = connectivityProvider.isConnected;
          previousConnection ??= true;

          if (previousConnection != isConnected &&
              connectivityProvider.isInitialized &&
              connectivityProvider.previousConnection != isConnected) {
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
              //         backgroundColor: const Color(0xFF424242), // Dark gray instead of red
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
                //       backgroundColor: const Color(0xFF2E7D32), // Dark green instead of bright green
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
                  if (!mounted) return;

                  final convoProvider = ctx.read<ConversationProvider>();
                  final messageProvider = ctx.read<MessageProvider>();

                  if (convoProvider.conversations.isEmpty) {
                    await convoProvider.getInitialConversations();
                  } else {
                    // Force refresh when internet connection is restored
                    await convoProvider.forceRefreshConversations();
                  }

                  if (messageProvider.messages.isEmpty) {
                    await messageProvider.refreshMessages();
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
              backgroundColor: Theme.of(context).colorScheme.primary,
              resizeToAvoidBottomInset: false,
              appBar: homeProvider.selectedIndex == 5 ? null : _buildAppBar(context),
              body: GestureDetector(
                onTap: () {
                  primaryFocus?.unfocus();
                  // context.read<HomeProvider>().memoryFieldFocusNode.unfocus();
                  // context.read<HomeProvider>().chatFieldFocusNode.unfocus();
                },
                child: Stack(
                  children: [
                    Column(
                      children: [
                        // Show slim green call bar on non-home/conversations tabs when a call is active
                        if (homeProvider.selectedIndex > 1) const ActiveCallTopBar(),
                        Expanded(
                          child: IndexedStack(index: context.watch<HomeProvider>().selectedIndex, children: _pages),
                        ),
                      ],
                    ),
                    Consumer<HomeProvider>(
                      builder: (context, home, child) {
                        if (home.isChatFieldFocused ||
                            home.isAppsSearchFieldFocused ||
                            home.isMemoriesSearchFieldFocused) {
                          return const SizedBox.shrink();
                        }

                        return Stack(
                          children: [
                            BottomNavBar(
                              onTabTap: (index, isRepeat) {
                                if (isRepeat) {
                                  _scrollToTop(index);
                                } else {
                                  // When tapping Conversations directly, reset to conversations view
                                  if (index == 1) {
                                    final cp = context.read<ConversationProvider>();
                                    if (cp.showDailySummaries) cp.toggleDailySummaries();
                                  }
                                  home.setIndex(index);
                                }
                              },
                            ),
                            if (home.selectedIndex == 0)
                              Positioned(
                                left: 16,
                                right: 16,
                                bottom: 78,
                                child: _buildChatBar(context),
                              ),
                          ],
                        );
                      },
                    ),
                    // Merge action bar - floats above bottom nav when in selection mode
                    if (homeProvider.selectedIndex == 1)
                      const Positioned(left: 0, right: 0, bottom: 0, child: MergeActionBar()),
                    // Task selection action bar - floats above bottom nav on the
                    // tasks tab when selection mode is active in ActionItemsProvider.
                    if (homeProvider.selectedIndex == 2)
                      const Positioned(left: 0, right: 0, bottom: 0, child: TaskSelectionActionBar()),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildChatBar(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        MixpanelManager().bottomNavigationTabClicked('Chat');
        Navigator.push(context, MaterialPageRoute(builder: (context) => const ChatPage(isPivotBottom: false)));
      },
      child: Container(
        height: 62,
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(32),
          border: Border.all(color: const Color(0xFF35343B), width: 1),
          boxShadow: [
            BoxShadow(
                color: Colors.black.withValues(alpha: 0.65),
                blurRadius: 60,
                spreadRadius: 14,
                offset: const Offset(0, -16)),
            BoxShadow(
                color: Colors.black.withValues(alpha: 0.45),
                blurRadius: 32,
                spreadRadius: 6,
                offset: const Offset(0, -8)),
            BoxShadow(color: Colors.black.withValues(alpha: 0.25), blurRadius: 10, offset: const Offset(0, 2)),
          ],
        ),
        child: Row(
          children: [
            const SizedBox(width: 18),
            Expanded(
              child: Text(
                'Ask Omi anything about your life...',
                style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            GestureDetector(
              onTap: () {
                HapticFeedback.lightImpact();
                MixpanelManager().bottomNavigationTabClicked('Chat Voice');
                Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (context) => const ChatPage(isPivotBottom: false, autoStartVoice: true)));
              },
              child: Container(
                width: 42,
                height: 42,
                margin: const EdgeInsets.only(right: 6),
                decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                child: const Icon(FontAwesomeIcons.microphone, size: 15, color: Colors.black),
              ),
            ),
          ],
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: Theme.of(context).colorScheme.surface,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const BatteryInfoWidget(),
          const SizedBox.shrink(),
          Row(
            children: [
              // Sync icon - shows when there are pending files on device or a device is paired
              // Only shown on home page (index 0)
              Consumer3<HomeProvider, DeviceProvider, SyncProvider>(
                builder: (context, homeProvider, deviceProvider, syncProvider, child) {
                  final device = deviceProvider.pairedDevice;
                  // Only show orange indicator for files still on device (SD card or Limitless)
                  final hasPendingOnDevice = syncProvider.missingWalsOnDevice.isNotEmpty;
                  final isSyncing = syncProvider.isSyncing;

                  // Show sync icon only on Conversations tab and if there's a paired device OR if there are pending files on device
                  if (homeProvider.selectedIndex == 1 && (device != null || hasPendingOnDevice)) {
                    return GestureDetector(
                      onTap: () {
                        HapticFeedback.mediumImpact();
                        final page = deviceProvider.supportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
                        Navigator.push(context, MaterialPageRoute(builder: (context) => page));
                      },
                      child: Container(
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: isSyncing
                              ? Colors.deepPurple.withValues(alpha: 0.2)
                              : hasPendingOnDevice
                                  ? Colors.orange.withValues(alpha: 0.15)
                                  : const Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.cloud_rounded,
                          size: 18,
                          color: isSyncing
                              ? Colors.deepPurpleAccent
                              : hasPendingOnDevice
                                  ? Colors.orangeAccent
                                  : Colors.white70,
                        ),
                      ),
                    );
                  }
                  return const SizedBox.shrink();
                },
              ),
              // Search and Calendar buttons - only on home page
              Consumer2<HomeProvider, ConversationProvider>(
                builder: (context, homeProvider, convoProvider, _) {
                  // Only show search and calendar buttons on Conversations tab (index 1)
                  if (homeProvider.selectedIndex != 1) {
                    return const SizedBox.shrink();
                  }

                  // Hide search button if there's an active search query
                  bool shouldShowSearchButton = convoProvider.previousQuery.isEmpty;
                  return Row(
                    children: [
                      // Search button - show when no active search, clicking closes search bar
                      if (shouldShowSearchButton)
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: homeProvider.showConvoSearchBar
                                ? Colors.deepPurple.withValues(alpha: 0.5)
                                : const Color(0xFF1F1F25),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const Icon(Icons.search, size: 18, color: Colors.white70),
                            onPressed: () {
                              HapticFeedback.mediumImpact();
                              homeProvider.toggleConvoSearchBar();
                            },
                          ),
                        ),
                      // Calendar button - only show when date filter is active
                      if (convoProvider.selectedDate != null) ...[
                        const SizedBox(width: 8),
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.deepPurple.withValues(alpha: 0.5),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const Icon(FontAwesomeIcons.calendarDay, size: 16, color: Colors.white),
                            onPressed: () async {
                              HapticFeedback.mediumImpact();
                              // Open date picker to change date, cancel clears filter
                              DateTime selectedDate = convoProvider.selectedDate ?? DateTime.now();
                              await showCupertinoModalPopup<void>(
                                context: context,
                                builder: (BuildContext context) {
                                  return Container(
                                    height: 420,
                                    padding: const EdgeInsets.only(top: 6.0),
                                    margin: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
                                    color: const Color(0xFF1F1F25),
                                    child: SafeArea(
                                      top: false,
                                      child: Column(
                                        children: [
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                                            decoration: const BoxDecoration(
                                              color: Color(0xFF1F1F25),
                                              border: Border(bottom: BorderSide(color: Color(0xFF35343B), width: 0.5)),
                                            ),
                                            child: Row(
                                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                              children: [
                                                CupertinoButton(
                                                  padding: EdgeInsets.zero,
                                                  onPressed: () async {
                                                    // Get provider before pop to avoid using invalid context
                                                    final provider = Provider.of<ConversationProvider>(
                                                      context,
                                                      listen: false,
                                                    );
                                                    Navigator.of(context).pop();
                                                    await provider.clearDateFilter();
                                                    MixpanelManager().calendarFilterCleared();
                                                  },
                                                  child: Text(
                                                    context.l10n.removeFilter,
                                                    style: const TextStyle(color: Colors.white, fontSize: 16),
                                                  ),
                                                ),
                                                const Spacer(),
                                                CupertinoButton(
                                                  padding: EdgeInsets.zero,
                                                  onPressed: () async {
                                                    final provider = Provider.of<ConversationProvider>(
                                                      context,
                                                      listen: false,
                                                    );
                                                    Navigator.of(context).pop();
                                                    await provider.filterConversationsByDate(selectedDate);
                                                    MixpanelManager().calendarFilterApplied(selectedDate);
                                                  },
                                                  child: Text(
                                                    context.l10n.done,
                                                    style: const TextStyle(
                                                      color: Colors.deepPurple,
                                                      fontSize: 16,
                                                      fontWeight: FontWeight.w600,
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          Expanded(
                                            child: Material(
                                              color: ResponsiveHelper.backgroundSecondary,
                                              child: CalendarDatePicker2(
                                                config: getDefaultCalendarConfig(
                                                  firstDate: DateTime(2020),
                                                  lastDate: DateTime.now(),
                                                  currentDate: DateTime.now(),
                                                ),
                                                value: [selectedDate],
                                                onValueChanged: (dates) {
                                                  if (dates.isNotEmpty) {
                                                    selectedDate = dates[0];
                                                  }
                                                },
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                },
                              );
                            },
                          ),
                        ),
                      ],
                      const SizedBox(width: 8),
                    ],
                  );
                },
              ),
              // Tasks page buttons - export and completed toggle
              Consumer2<HomeProvider, ActionItemsProvider>(
                builder: (context, homeProvider, actionItemsProvider, _) {
                  if (homeProvider.selectedIndex != 2) {
                    return const SizedBox.shrink();
                  }
                  final showCompleted = actionItemsProvider.showCompletedView;
                  return Row(
                    children: [
                      // Export button
                      Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: const Icon(FontAwesomeIcons.arrowUpFromBracket, size: 16, color: Colors.white70),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            MixpanelManager().exportTasksBannerClicked();
                            Navigator.of(
                              context,
                            ).push(MaterialPageRoute(builder: (context) => const TaskIntegrationsPage()));
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      // Completed toggle
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: showCompleted ? Colors.deepPurple.withValues(alpha: 0.5) : const Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: Icon(
                            FontAwesomeIcons.solidCircleCheck,
                            size: 16,
                            color: showCompleted ? Colors.white : Colors.white70,
                          ),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            actionItemsProvider.toggleShowCompletedView();
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                  );
                },
              ),
              // Apps tab — Create app pull-down menu (shown only on Apps tab, left of settings)
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  if (homeProvider.selectedIndex != 3) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: PullDownButton(
                      itemBuilder: (context) => [
                        PullDownMenuItem(
                          title: context.l10n.createAnApp,
                          subtitle: context.l10n.createAndShareYourApp,
                          iconWidget: const Icon(Icons.apps, size: 18),
                          onTap: () {
                            MixpanelManager().pageOpened('Submit App');
                            routeToPage(context, const AddAppPage());
                          },
                        ),
                        PullDownMenuItem(
                          title: context.l10n.addMcpServer,
                          subtitle: context.l10n.connectExternalAiTools,
                          iconWidget: const Icon(Icons.cable, size: 18),
                          onTap: () {
                            MixpanelManager().pageOpened('Add MCP Server');
                            routeToPage(context, const AddMcpServerPage());
                          },
                        ),
                      ],
                      buttonBuilder: (context, showMenu) => GestureDetector(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          showMenu();
                        },
                        child: Container(
                          width: 36,
                          height: 36,
                          decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                          child: const Icon(Icons.add, size: 18, color: Colors.white70),
                        ),
                      ),
                    ),
                  );
                },
              ),
              // Settings button - always visible
              Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: const Icon(FontAwesomeIcons.gear, size: 16, color: Colors.white70),
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    MixpanelManager().pageOpened('Settings');
                    String language = SharedPreferencesUtil().userPrimaryLanguage;
                    bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                    String transcriptModel = SharedPreferencesUtil().transcriptionModel;
                    SettingsDrawer.show(context);
                    if (language != SharedPreferencesUtil().userPrimaryLanguage ||
                        hasSpeech != SharedPreferencesUtil().hasSpeakerProfile ||
                        transcriptModel != SharedPreferencesUtil().transcriptionModel) {
                      if (context.mounted) {
                        context.read<CaptureProvider>().onRecordProfileSettingChanged();
                      }
                    }
                  },
                ),
              ),
            ],
          ),
        ],
      ),
      elevation: 0,
      centerTitle: true,
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // Stop VM keepalive timer
    try {
      Provider.of<MessageProvider>(context, listen: false).stopVmKeepalive();
    } catch (_) {}
    // Cancel stream subscription to prevent memory leak
    _notificationStreamSubscription?.cancel();
    // Remove capture provider listener using stored reference
    if (_captureProvider != null) {
      _captureProvider!.removeListener(_onCaptureProviderChanged);
      _captureProvider!.onFreemiumSessionReset = null;
      _captureProvider = null;
    }
    // Remove device provider callback
    try {
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      deviceProvider.onDeviceConnected = null;
      deviceProvider.onOfflineDataDetected = null;
    } catch (_) {}
    _deviceProviderForQuickActions?.removeListener(_onDeviceStateChangedForQuickActions);
    _deviceProviderForQuickActions = null;
    _captureProviderForQuickActions?.removeListener(_onDeviceStateChangedForQuickActions);
    _captureProviderForQuickActions = null;
    QuickActionsService.instance.reset();
    // Clean up freemium handler
    _freemiumHandler.dispose();
    // Remove foreground task callback to prevent memory leak
    FlutterForegroundTask.removeTaskDataCallback(_onReceiveTaskData);
    ForegroundUtil.stopForegroundTask();
    super.dispose();
  }
}
