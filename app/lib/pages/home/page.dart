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
import 'package:omi/pages/home/widgets/home_hero.dart';
import 'package:omi/pages/memories/brain_page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/phone_calls/active_call_banner.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/integrations/apple_reminders_sync_service.dart';
import 'package:omi/services/quick_actions_service.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/services/announcement_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
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
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
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

  final GlobalKey<State<ConversationsPage>> _conversationsPageKey = GlobalKey<State<ConversationsPage>>();
  final GlobalKey<State<ActionItemsPage>> _actionItemsPageKey = GlobalKey<State<ActionItemsPage>>();
  final GlobalKey<AppsPageState> _appsPageKey = GlobalKey<AppsPageState>();
  late final List<Widget> _pages;

  // The Home hero's entrance plays once per launch. HomeHero is mounted and
  // unmounted by the tab switch, so without this it would replay every time the
  // user came back to Home. Not setState — nothing needs to rebuild on it.
  bool _heroEntrancePlayed = false;

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
      // 0 is the chat — it follows the live edge on its own, and yanking a
      // reader back to the top of a conversation is not what "tap the tab
      // again" should mean.
      case 0:
        break;
      case 1:
        final conversationsState = _conversationsPageKey.currentState;
        if (conversationsState != null) {
          (conversationsState as dynamic).scrollToTop();
        }
        break;
      // 2 is the Brain graph — pan/zoom, nothing to scroll.
      case 3:
        final actionItemsState = _actionItemsPageKey.currentState;
        if (actionItemsState != null) {
          (actionItemsState as dynamic).scrollToTop();
        }
        break;
      case 4:
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
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        captureProvider.refreshInProgressConversations();
        // Pick up any batch recordings the native layer wrote while backgrounded/closed.
        Provider.of<LocalRecordingsProvider>(context, listen: false).refresh();
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
      // Home *is* the chat. Tapping the composer used to push ChatPage as a
      // route — a leftover from when Chat was its own nav tab (the tap still
      // fired bottomNavigationTabClicked('Chat')). It now lives here, so asking
      // Omi something never leaves the tab. The hero is the empty state.
      ChatPage(
        embedded: true,
        // Centred and inset: as an empty state it fills the message area, which
        // has no padding of its own — without this the headline runs to both
        // screen edges and clips.
        emptyState: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Center(
            child: HomeHero(
              animate: !_heroEntrancePlayed,
              onEntranceComplete: () => _heroEntrancePlayed = true,
            ),
          ),
        ),
      ),
      ConversationsPage(key: _conversationsPageKey),
      // Brain tab. BrainPage paints no background, inheriting this Scaffold's;
      // it passes embedded/trackOpenEvent through to MemoryGraphPage (the host
      // Scaffold supplies the app bar, and IndexedStack builds this at launch so
      // the open event fires from the tab tap instead — see onTabTap).
      const BrainPage(),
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
          homePageIdx = 4;
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
            Navigator.push(context, MaterialPageRoute(builder: (context) => const ChatPage(isPivotBottom: false)));
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
            PlatformManager.instance.analytics.dailySummaryNotificationOpened(
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

      // Register callback for device connection to check firmware announcements and device onboarding
      deviceProvider.onDeviceConnected = (BtDevice device) {
        _onDeviceConnectedForAnnouncements(device);
        _checkDeviceOnboarding(device);
      };

      // Also check if already connected right now
      if (deviceProvider.isConnected && deviceProvider.connectedDevice != null) {
        _checkDeviceOnboarding(deviceProvider.connectedDevice!);
      }
    });
  }

  bool _deviceOnboardingShown = false;

  void _checkDeviceOnboarding(BtDevice device) async {
    if (device.type != DeviceType.omi) return;
    if (!mounted) return;

    // Onboarding is the CV1 consumer-pendant button tutorial. DevKit/Glass/Neo/
    // Friend all also enumerate as DeviceType.omi, so only proceed for a positively
    // identified CV1. pairedDevice has the GATT model by now.
    final pairedModel = Provider.of<DeviceProvider>(context, listen: false).pairedDevice?.modelNumber;
    if (!DeviceUtils.isOmiCv1(modelNumber: pairedModel, deviceName: device.name)) return;

    if (_deviceOnboardingShown) return;
    if (SharedPreferencesUtil().deviceOnboardingCompleted) return;

    // Double-check with Firestore
    final state = await getUserOnboardingState();
    if (state?['device_onboarding_completed'] == true) {
      SharedPreferencesUtil().deviceOnboardingCompleted = true;
      return;
    }

    if (!mounted || _deviceOnboardingShown) return;
    _deviceOnboardingShown = true;
    routeToPage(context, const InteractiveDeviceOnboardingWrapper());
  }

  void _registerAutoSyncCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      final syncProvider = Provider.of<SyncProvider>(context, listen: false);
      deviceProvider.onOfflineDataDetected = (device, fileCount, totalBytes) {
        // Custom STT users sync manually (with confirmation) — never auto-sync,
        // since offline files are transcribed on Omi and count toward the limit.
        if (SharedPreferencesUtil().useCustomStt) {
          Logger.debug('HomePage: Auto-sync skipped, custom STT provider enabled');
          return;
        }
        // Omi users can disable auto-sync from device settings. Defaults to on.
        if (!SharedPreferencesUtil().autoSyncOfflineRecordings) {
          Logger.debug('HomePage: Auto-sync skipped, disabled by user');
          return;
        }
        if (!syncProvider.isSyncing) {
          Logger.debug('HomePage: Auto-sync triggered ($fileCount files, $totalBytes bytes)');
          syncProvider.syncWals(trigger: WakeTrigger.deviceConnected);
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
                        // Deliberately not hiding on isChatFieldFocused: Home
                        // *is* the chat, so focusing the composer is the most
                        // ordinary thing on the tab — dropping the nav bar every
                        // time would make the app feel like it navigated away.
                        // The search fields still hide it; those take over the
                        // whole screen with results.
                        if (home.isAppsSearchFieldFocused || home.isMemoriesSearchFieldFocused) {
                          return const SizedBox.shrink();
                        }

                        return Stack(
                          children: [
                            BottomNavBar(
                              onTabTap: (index, isRepeat) {
                                if (isRepeat) {
                                  _scrollToTop(index);
                                } else {
                                  // The Brain page is built once by IndexedStack
                                  // and never "opens", so record the open here.
                                  if (index == 2) {
                                    PlatformManager.instance.analytics.brainMapOpened();
                                  }
                                  home.setIndex(index);
                                }
                              },
                            ),
                            // Home is the chat; the hero is its empty state and
                            // is supplied to ChatPage rather than overlaid here.
                          ],
                        );
                      },
                    ),
                    // Merge action bar - floats above bottom nav when in selection mode
                    if (homeProvider.selectedIndex == 1)
                      const Positioned(left: 0, right: 0, bottom: 0, child: MergeActionBar()),
                    // Task selection action bar - floats above bottom nav on the
                    // tasks tab when selection mode is active in ActionItemsProvider.
                    if (homeProvider.selectedIndex == 3)
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

  /// Tabs that render their own full-bleed surface and carry no app-bar chrome:
  /// Conversations (1), Brain (3) and Apps (4).
  ///
  /// Conversations keeps its calendar button — only the device status chip and
  /// the settings gear drop away. Apps carries its own overflow menu next to
  /// the search field, so it needs neither.
  // Conversations (1), Brain (2) and Apps (4) render no app bar content of
  // their own; Home (0) and Tasks (3) do.
  static bool _hidesAppBarChrome(int selectedIndex) => selectedIndex == 1 || selectedIndex == 2 || selectedIndex == 4;

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    // Tabs in [_hidesAppBarChrome] render no app bar content of their own, and
    // the two Conversations buttons are conditional. When nothing is showing,
    // a full-height bar leaves an empty band above the page's own headline —
    // so collapse it to zero rather than reserve space for nothing.
    final selectedIndex = context.watch<HomeProvider>().selectedIndex;
    final showsSyncButton = selectedIndex == 1 &&
        (context.watch<DeviceProvider>().pairedDevice != null ||
            context.watch<SyncProvider>().missingWalsOnDevice.isNotEmpty);
    final showsCalendarButton = selectedIndex == 1 && context.watch<ConversationProvider>().selectedDate != null;
    final isBarEmpty = _hidesAppBarChrome(selectedIndex) && !showsSyncButton && !showsCalendarButton;

    return AppBar(
      automaticallyImplyLeading: false,
      toolbarHeight: isBarEmpty ? 0 : kToolbarHeight,
      backgroundColor: Theme.of(context).colorScheme.surface,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Device/battery status chip — hidden on the tabs that keep a bare
          // app bar. See [_hidesAppBarChrome].
          Consumer<HomeProvider>(
            builder: (context, homeProvider, _) =>
                _hidesAppBarChrome(homeProvider.selectedIndex) ? const SizedBox.shrink() : const BatteryInfoWidget(),
          ),
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
              // Calendar button - only on the Conversations tab. Search now
              // lives inline with the folder chips (see FolderTabs).
              Consumer2<HomeProvider, ConversationProvider>(
                builder: (context, homeProvider, convoProvider, _) {
                  if (homeProvider.selectedIndex != 1) {
                    return const SizedBox.shrink();
                  }

                  return Row(
                    children: [
                      // Calendar button - only show when date filter is active
                      if (convoProvider.selectedDate != null) ...[
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.deepPurple.withValues(alpha: 0.5),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const FaIcon(FontAwesomeIcons.calendarDay, size: 16, color: Colors.white),
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
                                                    PlatformManager.instance.analytics.calendarFilterCleared();
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
                                                    PlatformManager.instance.analytics.calendarFilterApplied(
                                                      selectedDate,
                                                    );
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
                  if (homeProvider.selectedIndex != 3) {
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
                          icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16, color: Colors.white70),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            PlatformManager.instance.analytics.exportTasksBannerClicked();
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
                          icon: FaIcon(
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
              // The Apps tab's create menu now lives in the overflow menu
              // beside its search field — see _AppsOverflowMenu.
              // Settings button — hidden on the tabs that keep a bare app bar.
              // See [_hidesAppBarChrome]; Settings stays reachable from Home,
              // Tasks, and Apps.
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  if (_hidesAppBarChrome(homeProvider.selectedIndex)) return const SizedBox.shrink();
                  return Container(
                    width: 36,
                    height: 36,
                    decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                    child: IconButton(
                      padding: EdgeInsets.zero,
                      icon: const FaIcon(FontAwesomeIcons.gear, size: 16, color: Colors.white70),
                      onPressed: () {
                        HapticFeedback.mediumImpact();
                        PlatformManager.instance.analytics.pageOpened('Settings');
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
                  );
                },
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
