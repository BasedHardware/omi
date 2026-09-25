import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:upgrader/upgrader.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/phone_calls/active_call_banner.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
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
import 'package:omi/services/account_cutover/account_cutover_blocking_gate.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/analytics/background_resource_telemetry.dart';
import 'package:omi/utils/analytics/background_checkpoint_store.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'package:omi/widgets/header_circle_button.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/ui/ui.dart';
import 'home_deep_links.dart';
import 'home_navigation.dart';
import 'home_prompt_gate.dart';
import 'widgets/battery_info_widget.dart';

class HomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  const HomePageWrapper({super.key, this.navigateToRoute});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  @override
  Widget build(BuildContext context) {
    // Self-gate so onboarding/pushAndRemoveUntil destinations cannot boot
    // product traffic while cutover enforcement is blocking.
    return AccountCutoverBlockingGate(
      productBuilder: (context) => _HomePageProduct(navigateToRoute: widget.navigateToRoute),
    );
  }
}

class _HomePageProduct extends StatefulWidget {
  const _HomePageProduct({this.navigateToRoute});

  final String? navigateToRoute;

  @override
  State<_HomePageProduct> createState() => _HomePageProductState();
}

class _HomePageProductState extends State<_HomePageProduct> {
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
      if (!mounted) return;
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

  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;
  StreamSubscription? _notificationStreamSubscription;

  final GlobalKey<HomeContentPageState> _homeContentPageKey = GlobalKey<HomeContentPageState>();
  final GlobalKey<State<ConversationsPage>> _conversationsPageKey = GlobalKey<State<ConversationsPage>>();
  final GlobalKey<State<ActionItemsPage>> _actionItemsPageKey = GlobalKey<State<ActionItemsPage>>();
  final GlobalKey<AppsPageState> _appsPageKey = GlobalKey<AppsPageState>();
  // Keep the IndexedStack slots stable, but defer constructing non-selected
  // tabs until the user visits them. Once created, a tab remains in the stack
  // so its scroll position and other state are preserved.
  final List<Widget?> _pages = List<Widget?>.filled(4, null);
  final Set<int> _scheduledPageInitializations = <int>{};

  // Freemium switch handler for auto-switch dialogs
  final FreemiumSwitchHandler _freemiumHandler = FreemiumSwitchHandler();

  // Holds startup prompts while recording, on a call or during a firmware update.
  final HomePromptGate _promptGate = HomePromptGate();

  late final BackgroundResourceTelemetry _backgroundResourceTelemetry = BackgroundResourceTelemetry(
    checkpointStore: PreferencesBackgroundCheckpointStore(),
    ownerKey: () => AnalyticsManager.currentIdentity ?? '',
    identityEpoch: () => AnalyticsManager.identityEpoch,
    enabled: () => AnalyticsManager.identityKnown && AnalyticsManager.trackingEnabled,
    emit: (eventName, properties) => PlatformManager.instance.analytics.track(eventName, properties: properties),
  );

  CaptureProvider? _captureProvider;
  DeviceProvider? _deviceProviderForQuickActions;
  CaptureProvider? _captureProviderForQuickActions;
  Timer? _announcementTimer;
  final List<Timer> _prewarmTimers = [];

  void _ensurePageInitialized(int pageIndex) {
    if (pageIndex < 0 || pageIndex >= _pages.length || _pages[pageIndex] != null) return;

    switch (pageIndex) {
      case 0:
        _pages[pageIndex] = HomeContentPage(key: _homeContentPageKey);
        break;
      case 1:
        _pages[pageIndex] = ConversationsPage(key: _conversationsPageKey);
        break;
      case 2:
        _pages[pageIndex] = ActionItemsPage(key: _actionItemsPageKey, onAddGoal: _addGoal);
        break;
      case 3:
        _pages[pageIndex] = AppsPage(key: _appsPageKey);
        break;
    }
  }

  void _schedulePageInitialization(int pageIndex) {
    if (pageIndex < 0 || pageIndex >= _pages.length || _pages[pageIndex] != null) return;
    if (!_scheduledPageInitializations.add(pageIndex)) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduledPageInitializations.remove(pageIndex);
      if (!mounted || _pages[pageIndex] != null) return;
      setState(() => _ensurePageInitialized(pageIndex));
    });
    // addPostFrameCallback does not schedule a frame by itself. Background
    // prewarming often runs while the UI is idle, so explicitly request one.
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _prewarmRemainingTabs(int selectedIndex) {
    for (final timer in _prewarmTimers) {
      timer.cancel();
    }
    _prewarmTimers.clear();
    var delay = const Duration(milliseconds: 350);
    for (var index = 0; index < _pages.length; index++) {
      if (index == selectedIndex) continue;
      final pageIndex = index;
      _prewarmTimers.add(
        Timer(delay, () {
          if (!mounted) return;
          _schedulePageInitialization(pageIndex);
        }),
      );
      delay += const Duration(milliseconds: 180);
    }
  }

  List<Widget> _buildPages(int selectedIndex) {
    return [
      for (var index = 0; index < _pages.length; index++)
        TickerMode(
          enabled: index == selectedIndex,
          child: RepaintBoundary(child: _pages[index] ?? _TabLoadingSkeleton(tabIndex: index)),
        ),
    ];
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
    _ensurePageInitialized(1);
    context.read<HomeProvider>().setIndex(1);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final conversationsState = _conversationsPageKey.currentState;
      if (conversationsState != null) {
        (conversationsState as dynamic).addGoal();
      }
    });
  }

  BackgroundResourceSnapshot _captureBackgroundResourceSnapshot({
    CaptureProvider? captureProvider,
    DeviceProvider? deviceProvider,
    bool foregroundTaskRunning = false,
    int backgroundDisconnectCount = 0,
    int connectionTimeoutCount = 0,
    int failToConnectCount = 0,
    int reconnectCount = 0,
    int maxReconnectDurationMs = 0,
    int reconnectionCountTotal = 0,
    int failToConnectCountTotal = 0,
    bool bleHistorySaturated = false,
    int nativeBackgroundBytesConsumed = 0,
    int nativeBackgroundPacketsConsumed = 0,
  }) {
    final capture = captureProvider ?? Provider.of<CaptureProvider>(context, listen: false);
    final devices = deviceProvider ?? Provider.of<DeviceProvider>(context, listen: false);
    final device = devices.connectedDevice ?? devices.pairedDevice;
    return BackgroundResourceSnapshot(
      bleBytesReceived: capture.lifetimeBleBytesReceived,
      websocketBytesSent: capture.lifetimeWsSocketBytesSent,
      recordingState: capture.recordingState.name,
      deviceConnected: devices.isConnected,
      deviceType: device?.type.name ?? 'none',
      batchModeEnabled: SharedPreferencesUtil().batchModeEnabled,
      foregroundTaskRunning: foregroundTaskRunning,
      backgroundDisconnectCount: backgroundDisconnectCount,
      connectionTimeoutCount: connectionTimeoutCount,
      failToConnectCount: failToConnectCount,
      reconnectCount: reconnectCount,
      maxReconnectDurationMs: maxReconnectDurationMs,
      reconnectionCountTotal: reconnectionCountTotal,
      failToConnectCountTotal: failToConnectCountTotal,
      bleHistorySaturated: bleHistorySaturated,
      nativeBackgroundBytesConsumed: nativeBackgroundBytesConsumed,
      nativeBackgroundPacketsConsumed: nativeBackgroundPacketsConsumed,
      diagnosticsDeviceId: device?.id,
    );
  }

  Future<BackgroundResourceSnapshot> _loadBackgroundResourceSnapshot(
    DateTime backgroundStartedAt,
    BackgroundResourceSnapshot startSnapshot,
  ) async {
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    final diagnosticsDeviceId = startSnapshot.diagnosticsDeviceId;
    var foregroundTaskRunning = false;
    try {
      foregroundTaskRunning = await FlutterForegroundTask.isRunningService;
    } catch (_) {}

    var backgroundDisconnectCount = 0;
    var connectionTimeoutCount = 0;
    var failToConnectCount = 0;
    var reconnectCount = 0;
    var maxReconnectDurationMs = 0;
    var reconnectionCountTotal = 0;
    var failToConnectCountTotal = 0;
    var bleHistorySaturated = false;
    var nativeBackgroundBytesConsumed = 0;
    var nativeBackgroundPacketsConsumed = 0;

    if (Platform.isIOS && diagnosticsDeviceId != null) {
      try {
        final diagnostics = await BleHostApi().getDeviceDiagnostics(diagnosticsDeviceId);
        final startMs = backgroundStartedAt.millisecondsSinceEpoch;
        final recentEvents =
            diagnostics.disconnectHistory.where((event) => event.timestamp >= startMs && !event.isManual).toList();
        final backgroundEvents =
            recentEvents.where((event) => event.appState == 'background' || event.appState == 'inactive').toList();
        backgroundDisconnectCount = backgroundEvents.where((event) => event.eventType == 'disconnect').length;
        failToConnectCount = backgroundEvents.where((event) => event.eventType == 'fail_to_connect').length;
        connectionTimeoutCount =
            backgroundEvents.where((event) => event.reason.toLowerCase().contains('timeout')).length;
        final reconnectedEvents = backgroundEvents.where((event) => event.timeToReconnectMs > 0).toList();
        reconnectCount = reconnectedEvents.length;
        for (final event in reconnectedEvents) {
          if (event.timeToReconnectMs > maxReconnectDurationMs) {
            maxReconnectDurationMs = event.timeToReconnectMs;
          }
        }
        reconnectionCountTotal = diagnostics.reconnectionCount;
        failToConnectCountTotal = diagnostics.failToConnectCount;
        bleHistorySaturated = diagnostics.disconnectHistory.length >= 20 &&
            diagnostics.disconnectHistory.every((event) => event.timestamp >= startMs);
        nativeBackgroundBytesConsumed = diagnostics.nativeBackgroundBytesConsumed;
        nativeBackgroundPacketsConsumed = diagnostics.nativeBackgroundPacketsConsumed;
      } catch (_) {}
    }

    return _captureBackgroundResourceSnapshot(
      captureProvider: captureProvider,
      deviceProvider: deviceProvider,
      foregroundTaskRunning: foregroundTaskRunning,
      backgroundDisconnectCount: backgroundDisconnectCount,
      connectionTimeoutCount: connectionTimeoutCount,
      failToConnectCount: failToConnectCount,
      reconnectCount: reconnectCount,
      maxReconnectDurationMs: maxReconnectDurationMs,
      reconnectionCountTotal: reconnectionCountTotal,
      failToConnectCountTotal: failToConnectCountTotal,
      bleHistorySaturated: bleHistorySaturated,
      nativeBackgroundBytesConsumed: nativeBackgroundBytesConsumed,
      nativeBackgroundPacketsConsumed: nativeBackgroundPacketsConsumed,
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    ListenClientState.instance.onLifecycle(state);
    String event = '';
    if (state == AppLifecycleState.paused) {
      event = 'App is paused';
      if (mounted) {
        _backgroundResourceTelemetry.onPaused(_captureBackgroundResourceSnapshot());
        Provider.of<CaptureProvider>(context, listen: false).setMetricsAppActive(false);
      }
    } else if (state == AppLifecycleState.resumed) {
      event = 'App is resumed';

      // Reload convos
      if (mounted) {
        Provider.of<ConversationProvider>(context, listen: false).refreshConversations();
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        captureProvider.setMetricsAppActive(true);
        unawaited(_backgroundResourceTelemetry.onResumed(_loadBackgroundResourceSnapshot));
        captureProvider.refreshInProgressConversations();
        // Heal phone-mic sessions that went silent while another app played
        // audio (Stage Manager / YouTube) without an AVAudioSession interrupt.
        captureProvider.onAppResumed();
        // Pick up any batch recordings the native layer wrote while backgrounded/closed.
        Provider.of<LocalRecordingsProvider>(context, listen: false).refresh();
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
    unawaited(_backgroundResourceTelemetry.recoverInterrupted());
    SharedPreferencesUtil().onboardingCompleted = true;
    if (!SharedPreferencesUtil().permissionsCompleted) {
      SharedPreferencesUtil().permissionsCompleted = true;
    }
    updateUserOnboardingState(completed: true);

    // A link the shell was opened with: select its tab now (parent), open its page after start-up.
    final initialLink = HomeDeepLink.parse(widget.navigateToRoute);
    final homePageIdx = initialLink?.tabIndex ?? 0;

    // Home controller
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    _ensurePageInitialized(homePageIdx);
    WidgetsBinding.instance.addObserver(this);
    _prewarmRemainingTabs(homePageIdx);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Android needs a foreground service to keep capture/location work alive.
      // On iOS this plugin boots a second Flutter engine; conversation location
      // is captured directly at recording start and first transcript instead.
      if (Platform.isAndroid) {
        final permission = await Geolocator.checkPermission();
        if (permission == LocationPermission.always || permission == LocationPermission.whileInUse) {
          await ForegroundUtil.initializeForegroundService();
          await ForegroundUtil.startForegroundTask();
        }
      } else if (Platform.isIOS) {
        // Stop a headless foreground-task engine persisted by an older build.
        // Native BLE/audio background modes continue to own active capture.
        await ForegroundUtil.stopForegroundTask();
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(
          context,
          listen: false,
        ).streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).capabilityNormalizedDevice);
      }

      if (!mounted || initialLink == null) return;
      await openHomeDeepLink(context, initialLink, openSettings: _openSettings);
    });

    HomeNavigation.register(_openRoute);
    _listenToMessagesFromNotification();
    _listenToFreemiumThreshold();
    _checkForAnnouncements();
    _registerAutoSyncCallback();
    _initQuickActions();
    // Toasts float above the tab bar (and the chat bar on Home) while this shell is the visible route.
    OmiFeedback.bottomClearance = (ctx) {
      final onHome = ctx.read<HomeProvider>().selectedIndex == 0;
      final clearance = onHome ? homeChatBarClearance(ctx) : bottomNavBarClearance(ctx);
      return clearance - bottomNavBarReservedInset(ctx);
    };
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  /// Opens a link inside this shell (notification taps, quick actions, app links): its tab first,
  /// then its page — never a second Home (nav #3, #18).
  Future<void> _openRoute(String route) async {
    final link = HomeDeepLink.parse(route);
    if (link == null || !mounted) return;
    final tab = link.tabIndex;
    if (tab != null) {
      _ensurePageInitialized(tab);
      context.read<HomeProvider>().setIndex(tab);
    }
    await openHomeDeepLink(context, link, openSettings: _openSettings);
  }

  /// Opens Settings, and once the reader is back on Home restarts capture if they changed the
  /// language, speech profile or transcription model (onboarding-home #25: compare after the sheet
  /// closes, not the moment it opens).
  Future<void> _openSettings() async {
    final prefs = SharedPreferencesUtil();
    final language = prefs.userPrimaryLanguage;
    final hasSpeech = prefs.hasSpeakerProfile;
    final transcriptModel = prefs.transcriptionModel;
    await SettingsDrawer.show(context);
    if (!mounted) return;
    if (language != prefs.userPrimaryLanguage ||
        hasSpeech != prefs.hasSpeakerProfile ||
        transcriptModel != prefs.transcriptionModel) {
      context.read<CaptureProvider>().onRecordProfileSettingChanged();
    }
  }

  /// Startup prompts (changelog, announcements, device tutorial, firmware notices) go through
  /// [PromptQueue]: one at a time, never while recording, on a call or during a firmware update.
  void _checkForAnnouncements() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _promptGate.attach(
        capture: Provider.of<CaptureProvider>(context, listen: false),
        device: Provider.of<DeviceProvider>(context, listen: false),
      );
      _announcementTimer?.cancel();
      _announcementTimer = Timer(const Duration(seconds: 2), () {
        if (!mounted) return;

        final announcementProvider = Provider.of<AnnouncementProvider>(context, listen: false);
        final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
        PromptQueue.instance.enqueue(
          'home-announcements',
          PromptPriority.normal,
          show: (_) async {
            if (!mounted) return;
            await AnnouncementService().checkAndShowAnnouncements(
              context,
              announcementProvider,
              connectedDevice: deviceProvider.connectedDevice,
            );
          },
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
    PromptQueue.instance.enqueue(
      'device-tutorial',
      PromptPriority.normal,
      // The tutorial needs the pendant in hand; wait while it is disconnected.
      canShowNow: () => mounted && context.read<DeviceProvider>().isConnected,
      show: (_) async {
        if (!mounted || SharedPreferencesUtil().deviceOnboardingCompleted) return;
        await routeToPage(context, const InteractiveDeviceOnboardingWrapper());
      },
    );
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

  void _onDeviceConnectedForAnnouncements(BtDevice device) {
    if (!mounted) return;

    final announcementProvider = Provider.of<AnnouncementProvider>(context, listen: false);
    PromptQueue.instance.enqueue(
      'firmware-announcements',
      PromptPriority.high,
      show: (_) async {
        if (!mounted) return;
        await AnnouncementService().showFirmwareUpdateAnnouncements(
          context,
          announcementProvider,
          device.firmwareRevision,
          device.modelNumber,
        );
      },
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

    _freemiumHandler.checkAndShowPaywall(context, _captureProvider!);
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
            if (isConnected) {
              Future.delayed(Duration.zero, () {
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
        child: Selector<HomeProvider, int>(
          selector: (_, homeProvider) => homeProvider.selectedIndex,
          builder: (context, selectedIndex, _) {
            // D6: Android back on another tab returns to Home before it leaves the app.
            return PopScope(
              canPop: selectedIndex == 0,
              onPopInvokedWithResult: (didPop, _) {
                if (didPop || selectedIndex == 0) return;
                OmiHaptics.selection();
                context.read<HomeProvider>().setIndex(0);
                _schedulePageInitialization(0);
              },
              child: Scaffold(
                backgroundColor: OmiColors.surface0,
                resizeToAvoidBottomInset: false,
                appBar: selectedIndex == 5 ? null : _buildAppBar(context),
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
                          if (selectedIndex > 1) const ActiveCallTopBar(),
                          Expanded(
                            child: IndexedStack(index: selectedIndex, children: _buildPages(selectedIndex)),
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
                                // Queue page construction after the current
                                // gesture frame. Building a destination directly
                                // in onTapDown makes the tap itself feel stuck.
                                onTabWarmup: _schedulePageInitialization,
                                onTabTap: (index, isRepeat) {
                                  if (isRepeat) {
                                    _scrollToTop(index);
                                  } else {
                                    // Change tabs immediately. If background
                                    // prewarming has not completed yet, the
                                    // destination paints a skeleton for one frame
                                    // and mounts its real content afterwards.
                                    home.setIndex(index);
                                    _schedulePageInitialization(index);
                                  }
                                },
                              ),
                              if (home.selectedIndex == 0)
                                Positioned(
                                  left: 16,
                                  right: 16,
                                  // Derived from the nav row's own geometry so the
                                  // two cannot drift: changing the row's height or
                                  // the inset it reserves moves this with it.
                                  bottom: bottomNavChatBarOffset(context),
                                  child: Row(
                                    children: [
                                      Expanded(child: _buildChatBar(context)),
                                      const SizedBox(width: 10),
                                      const HomeRecordButton(),
                                    ],
                                  ),
                                ),
                            ],
                          );
                        },
                      ),
                      // Merge action bar - floats above bottom nav when in selection mode
                      if (selectedIndex == 1) const Positioned(left: 0, right: 0, bottom: 0, child: MergeActionBar()),
                      // Task selection action bar - floats above bottom nav on the
                      // tasks tab when selection mode is active in ActionItemsProvider.
                      if (selectedIndex == 2)
                        const Positioned(left: 0, right: 0, bottom: 0, child: TaskSelectionActionBar()),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  /// D1: chat is a normal pushed page everywhere (back chevron, edge swipe), not a full-screen modal.
  void _openChat({bool voice = false}) {
    OmiHaptics.selection();
    PlatformManager.instance.analytics.bottomNavigationTabClicked(voice ? 'Chat Voice' : 'Chat');
    routeToPage(context, ChatPage(isPivotBottom: false, autoStartVoice: voice));
  }

  Widget _buildChatBar(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      label: context.l10n.askOmi,
      onTap: _openChat,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _openChat,
        child: Container(
          height: kHomeChatBarHeight,
          decoration: BoxDecoration(
            color: OmiColors.surface1,
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: OmiColors.border, width: 1),
          ),
          child: Row(
            children: [
              const SizedBox(width: 18),
              Expanded(
                child: ExcludeSemantics(
                  child: Text(
                    context.l10n.askOmi,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              GestureDetector(
                // The mic sits inside the chat bar's own tap target, so a near miss
                // does not do nothing: it opens text chat instead of voice. Own the
                // bar's full height and its rounded end, not just the 42pt circle.
                behavior: HitTestBehavior.opaque,
                onTap: () => _openChat(voice: true),
                child: Semantics(
                  container: true,
                  button: true,
                  label: context.l10n.voiceMode,
                  child: Container(
                    height: kHomeChatBarHeight,
                    padding: const EdgeInsets.only(left: 8, right: 6),
                    alignment: Alignment.center,
                    child: Container(
                      width: 42,
                      height: 42,
                      alignment: Alignment.center,
                      decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                      child: const FaIcon(FontAwesomeIcons.microphone, size: 15, color: OmiColors.onAccent),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: Theme.of(context).colorScheme.surface,
      // The trailing buttons paint 36pt circles inside 44pt touch targets, so the
      // title gives up the 4pt the last target overhangs by. The circles stay on
      // the 16pt margin the rest of the screen uses.
      titleSpacing: NavigationToolbar.kMiddleSpacing - (kMinTapTarget - kHeaderCircleDiameter) / 2,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const Padding(
            padding: EdgeInsets.only(left: (kMinTapTarget - kHeaderCircleDiameter) / 2),
            child: BatteryInfoWidget(),
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
                    return HeaderCircleButton(
                      semanticLabel: context.l10n.sync,
                      onTap: () {
                        OmiHaptics.selection();
                        final page = deviceProvider.supportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
                        routeToPage(context, page);
                      },
                      // Neutral while syncing (INV-UI-1); warning tint while files wait on the device.
                      color: isSyncing
                          ? OmiColors.surface3
                          : hasPendingOnDevice
                              ? OmiColors.warning.withValues(alpha: 0.15)
                              : OmiColors.surface1,
                      icon: Icon(
                        Icons.cloud_rounded,
                        size: 18,
                        color: isSyncing
                            ? OmiColors.textPrimary
                            : hasPendingOnDevice
                                ? OmiColors.warning
                                : OmiColors.textSecondary,
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
                        HeaderCircleButton(
                          semanticLabel: context.l10n.search,
                          color: homeProvider.showConvoSearchBar ? OmiColors.surface3 : OmiColors.surface1,
                          icon: const Icon(Icons.search, size: 18, color: OmiColors.textSecondary),
                          onTap: () {
                            OmiHaptics.light();
                            homeProvider.toggleConvoSearchBar();
                          },
                        ),
                      // Calendar button - only show when date filter is active
                      if (convoProvider.selectedStartDate != null)
                        HeaderCircleButton(
                          semanticLabel: context.l10n.filters,
                          color: OmiColors.surface3,
                          icon: const FaIcon(FontAwesomeIcons.calendarDay, size: 16, color: OmiColors.textPrimary),
                          onTap: () async {
                            OmiHaptics.selection();
                            await showConversationDateRangePicker(context);
                          },
                        ),
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
                      HeaderCircleButton(
                        semanticLabel: context.l10n.exportButton,
                        icon: const FaIcon(
                          FontAwesomeIcons.arrowUpFromBracket,
                          size: 16,
                          color: OmiColors.textSecondary,
                        ),
                        onTap: () {
                          OmiHaptics.selection();
                          PlatformManager.instance.analytics.exportTasksBannerClicked();
                          routeToPage(context, const TaskIntegrationsPage());
                        },
                      ),
                      // Completed toggle
                      HeaderCircleButton(
                        semanticLabel: context.l10n.completed,
                        color: showCompleted ? OmiColors.surface3 : OmiColors.surface1,
                        icon: FaIcon(
                          FontAwesomeIcons.solidCircleCheck,
                          size: 16,
                          color: showCompleted ? OmiColors.textPrimary : OmiColors.textSecondary,
                        ),
                        onTap: () {
                          OmiHaptics.light();
                          actionItemsProvider.toggleShowCompletedView();
                        },
                      ),
                    ],
                  );
                },
              ),
              // Apps tab — Create app pull-down menu (shown only on Apps tab, left of settings)
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  if (homeProvider.selectedIndex != 3) return const SizedBox.shrink();
                  return PullDownButton(
                    itemBuilder: (context) => [
                      PullDownMenuItem(
                        title: context.l10n.createAnApp,
                        subtitle: context.l10n.createAndShareYourApp,
                        iconWidget: const Icon(Icons.apps, size: 18),
                        onTap: () {
                          PlatformManager.instance.analytics.pageOpened('Submit App');
                          routeToPage(context, const AddAppPage());
                        },
                      ),
                      PullDownMenuItem(
                        title: context.l10n.addMcpServer,
                        subtitle: context.l10n.connectExternalAiTools,
                        iconWidget: const Icon(Icons.cable, size: 18),
                        onTap: () {
                          PlatformManager.instance.analytics.pageOpened('Add MCP Server');
                          routeToPage(context, const AddMcpServerPage());
                        },
                      ),
                    ],
                    buttonBuilder: (context, showMenu) => HeaderCircleButton(
                      semanticLabel: context.l10n.createAnApp,
                      icon: const Icon(Icons.add, size: 18, color: OmiColors.textSecondary),
                      onTap: () {
                        OmiHaptics.selection();
                        showMenu();
                      },
                    ),
                  );
                },
              ),
              // Settings button - always visible
              HeaderCircleButton(
                semanticLabel: context.l10n.settings,
                icon: const FaIcon(FontAwesomeIcons.gear, size: 16, color: OmiColors.textSecondary),
                onTap: () {
                  OmiHaptics.selection();
                  PlatformManager.instance.analytics.pageOpened('Settings');
                  unawaited(_openSettings());
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
    HomeNavigation.unregister(_openRoute);
    _promptGate.detach();
    // These prompts close over this Home; a later Home (after sign-out and sign-in) enqueues its own.
    for (final id in const ['home-announcements', 'device-tutorial', 'firmware-announcements']) {
      PromptQueue.instance.remove(id);
    }
    OmiFeedback.bottomClearance = null;
    _announcementTimer?.cancel();
    _announcementTimer = null;
    for (final timer in _prewarmTimers) {
      timer.cancel();
    }
    _prewarmTimers.clear();
    WidgetsBinding.instance.removeObserver(this);
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
    if (Platform.isAndroid) {
      ForegroundUtil.stopForegroundTask();
    }
    super.dispose();
  }
}

class _TabLoadingSkeleton extends StatelessWidget {
  const _TabLoadingSkeleton({required this.tabIndex});

  final int tabIndex;

  @override
  Widget build(BuildContext context) {
    final itemCount = tabIndex == 3 ? 6 : 5;
    return IgnorePointer(
      child: ListView.builder(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 120),
        itemCount: itemCount,
        itemBuilder: (context, index) => Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: ShimmerWithTimeout(
            baseColor: OmiColors.surface1,
            highlightColor: OmiColors.surface2,
            child: Container(
              height: index == 0 ? 34 : 76,
              width: double.infinity,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
            ),
          ),
        ),
      ),
    );
  }
}
