import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/notifications/daily_reflection_notification.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:flutter/cupertino.dart';
import 'package:calendar_date_picker2/calendar_date_picker2.dart';

import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';

import 'widgets/battery_info_widget.dart';

class HomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  final String? autoMessage;
  const HomePageWrapper({super.key, this.navigateToRoute, this.autoMessage});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  String? _navigateToRoute;
  String? _autoMessage;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        context.read<DeviceProvider>().periodicConnect('coming from HomePageWrapper', boundDeviceOnly: true);
      }
      if (SharedPreferencesUtil().notificationsEnabled) {
        NotificationService.instance.register();
        NotificationService.instance.saveNotificationToken();

        // Schedule daily reflection notification if enabled
        if (SharedPreferencesUtil().dailyReflectionEnabled) {
          DailyReflectionNotification.scheduleDailyNotification(channelKey: 'channel');
        }
      }
    });
    _navigateToRoute = widget.navigateToRoute;
    _autoMessage = widget.autoMessage;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return HomePage(navigateToRoute: _navigateToRoute, autoMessage: _autoMessage);
  }
}

class HomePage extends StatefulWidget {
  final String? navigateToRoute;
  final String? autoMessage;
  const HomePage({super.key, this.navigateToRoute, this.autoMessage});

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
  final GlobalKey<State<MemoriesPage>> _memoriesPageKey = GlobalKey<State<MemoriesPage>>();
  final GlobalKey<AppsPageState> _appsPageKey = GlobalKey<AppsPageState>();
  late final List<Widget> _pages;

  // Freemium switch handler for auto-switch dialogs
  final FreemiumSwitchHandler _freemiumHandler = FreemiumSwitchHandler();

  void _initiateApps() {
    context.read<AppProvider>().getApps();
    context.read<AppProvider>().getPopularApps();
  }

  void _scrollToTop(int pageIndex) {
    switch (pageIndex) {
      case 0:
        final conversationsState = _conversationsPageKey.currentState;
        if (conversationsState != null) {
          (conversationsState as dynamic).scrollToTop();
        }
        break;
      case 1:
        final actionItemsState = _actionItemsPageKey.currentState;
        if (actionItemsState != null) {
          (actionItemsState as dynamic).scrollToTop();
        }
        break;
      case 2:
        final memoriesState = _memoriesPageKey.currentState;
        if (memoriesState != null) {
          (memoriesState as dynamic).scrollToTop();
        }
        break;
      case 3:
        final appsState = _appsPageKey.currentState;
        if (appsState != null) {
          appsState.scrollToTop();
        }
        break;
    }
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
    PlatformManager.instance.crashReporter.logInfo(event);
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {
    '/facts': const MemoriesPage(),
  };
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
      ConversationsPage(key: _conversationsPageKey),
      ActionItemsPage(key: _actionItemsPageKey),
      MemoriesPage(key: _memoriesPageKey),
      AppsPage(key: _appsPageKey),
    ];
    SharedPreferencesUtil().onboardingCompleted = true;

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
          homePageIdx = 2;
          break;
        case "apps":
          homePageIdx = 3;
          break;
      }
    }

    // Home controller
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();

      // ForegroundUtil.requestPermissions();
      if (!PlatformService.isDesktop) {
        if (SharedPreferencesUtil().locationEnabled) {
          await ForegroundUtil.initializeForegroundService();
          await ForegroundUtil.startForegroundTask();
        } else {
          debugPrint('Skipping foreground service: location is not enabled');
        }
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false)
            .streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Navigate
      switch (pageAlias) {
        case "apps":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            var app = await context.read<AppProvider>().getAppFromId(detailPageId);
            if (app != null && mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => AppDetailPage(app: app),
                ),
              );
            }
          }
          break;
        case "chat":
          print('inside chat alias $detailPageId');
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
          // If there's an auto-message (e.g., from daily reflection notification), send it
          final autoMessageToSend = widget.autoMessage;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => ChatPage(
                    isPivotBottom: false,
                    autoMessage: autoMessageToSend,
                  ),
                ),
              );
            }
          });
          break;
        case "settings":
          // Use context from the current widget instead of navigator key for bottom sheet
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              SettingsDrawer.show(context);
            }
          });
          if (detailPageId == 'data-privacy') {
            MyApp.navigatorKey.currentState?.push(
              MaterialPageRoute(
                builder: (context) => const DataPrivacyPage(),
              ),
            );
          }
          break;
        case "facts":
          MyApp.navigatorKey.currentState?.push(
            MaterialPageRoute(
              builder: (context) => const MemoriesPage(),
            ),
          );
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
                    builder: (context) => ConversationDetailPage(
                      conversation: conversation,
                      openShareToContactsOnLoad: shouldOpenShare,
                    ),
                  ),
                );
              } else {
                debugPrint('Conversation not found: $conversationId');
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
                  MaterialPageRoute(
                    builder: (context) => DailySummaryDetailPage(summaryId: detailPageId!),
                  ),
                );
              }
            });
          }
break;
        case "wrapped":
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const Wrapped2025Page(),
                ),
              );
            }
          });
          break;
        default:
      }
    });

    _listenToMessagesFromNotification();
    _listenToFreemiumThreshold();
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  void _listenToFreemiumThreshold() {
    // Listen to capture provider for freemium threshold events
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      captureProvider.addListener(_onCaptureProviderChanged);
      // Connect freemium session reset callback
      captureProvider.onFreemiumSessionReset = () {
        _freemiumHandler.resetDialogFlag();
      };
    });
  }

  void _onCaptureProviderChanged() {
    if (!mounted) return;

    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    _freemiumHandler.checkAndShowDialog(context, captureProvider).catchError((e) {
      debugPrint('[Freemium] Error checking dialog: $e');
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
              appBar: homeProvider.selectedIndex == 5 ? null : _buildAppBar(context),
              body: DefaultTabController(
                length: 4,
                initialIndex: homeProvider.selectedIndex,
                child: GestureDetector(
                  onTap: () {
                    primaryFocus?.unfocus();
                    // context.read<HomeProvider>().memoryFieldFocusNode.unfocus();
                    // context.read<HomeProvider>().chatFieldFocusNode.unfocus();
                  },
                  child: Stack(
                    children: [
                      Column(
                        children: [
                          Expanded(
                            child: IndexedStack(
                              index: context.watch<HomeProvider>().selectedIndex,
                              children: _pages,
                            ),
                          ),
                        ],
                      ),
                      Consumer2<HomeProvider, DeviceProvider>(
                        builder: (context, home, deviceProvider, child) {
                          if (home.isChatFieldFocused ||
                              home.isAppsSearchFieldFocused ||
                              home.isMemoriesSearchFieldFocused) {
                            return const SizedBox.shrink();
                          } else {
                            // Check if OMI device is connected
                            bool isOmiDeviceConnected =
                                deviceProvider.isConnected && deviceProvider.connectedDevice != null;

                            return Stack(
                              children: [
                                // Bottom Navigation Bar
                                Align(
                                  alignment: Alignment.bottomCenter,
                                  child: Container(
                                    width: double.infinity,
                                    height: 100,
                                    padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                                    decoration: const BoxDecoration(
                                      gradient: LinearGradient(
                                        begin: Alignment.topCenter,
                                        end: Alignment.bottomCenter,
                                        stops: [0.0, 0.30, 1.0],
                                        colors: [
                                          Colors.transparent,
                                          Color.fromARGB(255, 15, 15, 15),
                                          Color.fromARGB(255, 15, 15, 15),
                                        ],
                                      ),
                                    ),
                                    child: Row(
                                      children: [
                                        // Home tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              HapticFeedback.mediumImpact();
                                              MixpanelManager().bottomNavigationTabClicked('Home');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 0) {
                                                _scrollToTop(0);
                                                return;
                                              }
                                              home.setIndex(0);
                                            },
                                            child: SizedBox(
                                              height: 90,
                                              child: Center(
                                                child: Icon(
                                                  FontAwesomeIcons.house,
                                                  color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                                                  size: 26,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        // Action Items tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              HapticFeedback.mediumImpact();
                                              MixpanelManager().bottomNavigationTabClicked('Action Items');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 1) {
                                                _scrollToTop(1);
                                                return;
                                              }
                                              home.setIndex(1);
                                            },
                                            child: SizedBox(
                                              height: 90,
                                              child: Center(
                                                child: Icon(
                                                  FontAwesomeIcons.listCheck,
                                                  color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                                                  size: 26,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        // Center space for record button - only when no OMI device is connected
                                        if (!isOmiDeviceConnected) const SizedBox(width: 80),
                                        // Memories tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              HapticFeedback.mediumImpact();
                                              MixpanelManager().bottomNavigationTabClicked('Memories');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 2) {
                                                _scrollToTop(2);
                                                return;
                                              }
                                              home.setIndex(2);
                                            },
                                            child: SizedBox(
                                              height: 90,
                                              child: Center(
                                                child: Icon(
                                                  FontAwesomeIcons.brain,
                                                  color: home.selectedIndex == 2 ? Colors.white : Colors.grey,
                                                  size: 26,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        // Apps tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              HapticFeedback.mediumImpact();
                                              MixpanelManager().bottomNavigationTabClicked('Apps');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 3) {
                                                _scrollToTop(3);
                                                return;
                                              }
                                              home.setIndex(3);
                                            },
                                            child: SizedBox(
                                              height: 90,
                                              child: Center(
                                                child: Icon(
                                                  FontAwesomeIcons.puzzlePiece,
                                                  color: home.selectedIndex == 3 ? Colors.white : Colors.grey,
                                                  size: 26,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                // Central Record Button - Only show when no OMI device is connected
                                if (!isOmiDeviceConnected)
                                  Positioned(
                                    left: MediaQuery.of(context).size.width / 2 - 40,
                                    bottom: 40, // Position it to protrude above the taller navbar (90px height)
                                    child: Consumer<CaptureProvider>(
                                      builder: (context, captureProvider, child) {
                                        bool isRecording = captureProvider.recordingState == RecordingState.record;
                                        bool isInitializing =
                                            captureProvider.recordingState == RecordingState.initialising;
                                        return GestureDetector(
                                          onTap: () async {
                                            HapticFeedback.heavyImpact();
                                            if (isInitializing) return;
                                            await _handleRecordButtonPress(context, captureProvider);
                                          },
                                          child: Container(
                                            width: 80,
                                            height: 80,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: isRecording ? Colors.red : Colors.deepPurple,
                                              border: Border.all(
                                                color: Colors.black,
                                                width: 5,
                                              ),
                                            ),
                                            child: isInitializing
                                                ? const CircularProgressIndicator(
                                                    color: Colors.white,
                                                    strokeWidth: 2,
                                                  )
                                                : Icon(
                                                    isRecording ? FontAwesomeIcons.stop : FontAwesomeIcons.microphone,
                                                    color: Colors.white,
                                                    size: 24,
                                                  ),
                                          ),
                                        );
                                      },
                                    ),
                                  ),
                                // Floating Chat Button - Bottom Right (only on homepage)
                                if (home.selectedIndex == 0)
                                  Positioned(
                                    right: 20,
                                    bottom: 100, // Position above the bottom navigation bar
                                    child: GestureDetector(
                                      onTap: () {
                                        HapticFeedback.mediumImpact();
                                        MixpanelManager().bottomNavigationTabClicked('Chat');
                                        // Navigate to chat page
                                        Navigator.push(
                                          context,
                                          MaterialPageRoute(
                                            builder: (context) => const ChatPage(isPivotBottom: false),
                                          ),
                                        );
                                      },
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                                        decoration: BoxDecoration(
                                          borderRadius: BorderRadius.circular(32),
                                          color: Colors.deepPurple,
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(
                                              FontAwesomeIcons.solidComment,
                                              size: 22,
                                              color: Colors.white,
                                            ),
                                            const SizedBox(width: 10),
                                            Text(
                                              context.l10n.askOmi,
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontSize: 17,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            );
                          }
                        },
                      ),
                      // Merge action bar - floats above bottom nav when in selection mode
                      if (homeProvider.selectedIndex == 0)
                        const Positioned(
                          left: 0,
                          right: 0,
                          bottom: 0,
                          child: MergeActionBar(),
                        ),
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

  Future<void> _handleRecordButtonPress(BuildContext context, CaptureProvider captureProvider) async {
    var recordingState = captureProvider.recordingState;

    if (recordingState == RecordingState.record) {
      // Stop recording and summarize conversation
      await captureProvider.stopStreamRecording();
      captureProvider.forceProcessingCurrentConversation();
      MixpanelManager().phoneMicRecordingStopped();
    } else if (recordingState == RecordingState.initialising) {
      // Already initializing, do nothing
      debugPrint('initialising, have to wait');
    } else {
      // Start recording directly without dialog
      await captureProvider.streamRecording();
      MixpanelManager().phoneMicRecordingStarted();

      // Navigate to conversation capturing page
      if (context.mounted) {
        var topConvoId = (captureProvider.conversationProvider?.conversations ?? []).isNotEmpty
            ? captureProvider.conversationProvider!.conversations.first.id
            : null;
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => ConversationCapturingPage(topConversationId: topConvoId),
          ),
        );
      }
    }
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
              Consumer2<DeviceProvider, SyncProvider>(
                builder: (context, deviceProvider, syncProvider, child) {
                  final device = deviceProvider.pairedDevice;
                  // Only show orange indicator for files still on device (SD card or Limitless)
                  final hasPendingOnDevice = syncProvider.missingWalsOnDevice.isNotEmpty;
                  final isSyncing = syncProvider.isSyncing;

                  // Show sync icon if there's a paired device OR if there are pending files on device
                  if (device != null || hasPendingOnDevice) {
                    return GestureDetector(
                      onTap: () {
                        HapticFeedback.mediumImpact();
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (context) => const SyncPage()),
                        );
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
                  // Only show search and calendar buttons on home page (index 0)
                  if (homeProvider.selectedIndex != 0) {
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
                            icon: const Icon(
                              Icons.search,
                              size: 18,
                              color: Colors.white70,
                            ),
                            onPressed: () {
                              HapticFeedback.mediumImpact();
                              // Toggle search bar visibility
                              homeProvider.toggleConvoSearchBar();
                            },
                          ),
                        ),
                      if (shouldShowSearchButton) const SizedBox(width: 8),
                      // Calendar button
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: convoProvider.selectedDate != null
                              ? Colors.deepPurple.withValues(alpha: 0.5)
                              : const Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: Icon(
                            convoProvider.selectedDate != null
                                ? FontAwesomeIcons.calendarDay
                                : FontAwesomeIcons.calendarDays,
                            size: 16,
                            color: Colors.white70,
                          ),
                          onPressed: () async {
                            HapticFeedback.mediumImpact();
                            if (convoProvider.selectedDate != null) {
                              await convoProvider.clearDateFilter();
                              MixpanelManager().calendarFilterCleared();
                            } else {
                              // Open date picker
                              DateTime selectedDate = DateTime.now();
                              await showCupertinoModalPopup<void>(
                                context: context,
                                builder: (BuildContext context) {
                                  return Container(
                                    height: 420,
                                    padding: const EdgeInsets.only(top: 6.0),
                                    margin: EdgeInsets.only(
                                      bottom: MediaQuery.of(context).viewInsets.bottom,
                                    ),
                                    color: const Color(0xFF1F1F25),
                                    child: SafeArea(
                                      top: false,
                                      child: Column(
                                        children: [
                                          // Header with Cancel and Done buttons
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                                            decoration: const BoxDecoration(
                                              color: Color(0xFF1F1F25),
                                              border: Border(
                                                bottom: BorderSide(
                                                  color: Color(0xFF35343B),
                                                  width: 0.5,
                                                ),
                                              ),
                                            ),
                                            child: Row(
                                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                              children: [
                                                CupertinoButton(
                                                  padding: EdgeInsets.zero,
                                                  onPressed: () => Navigator.of(context).pop(),
                                                  child: Text(
                                                    context.l10n.cancel,
                                                    style: const TextStyle(
                                                      color: Colors.white,
                                                      fontSize: 16,
                                                    ),
                                                  ),
                                                ),
                                                const Spacer(),
                                                CupertinoButton(
                                                  padding: EdgeInsets.zero,
                                                  onPressed: () async {
                                                    Navigator.of(context).pop();
                                                    if (context.mounted) {
                                                      final provider =
                                                          Provider.of<ConversationProvider>(context, listen: false);
                                                      await provider.filterConversationsByDate(selectedDate);
                                                      MixpanelManager().calendarFilterApplied(selectedDate);
                                                    }
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
                                          // Date picker
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
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                  );
                },
              ),
              // Action items page buttons - export and completed toggle
              Consumer2<HomeProvider, ActionItemsProvider>(
                builder: (context, homeProvider, actionItemsProvider, _) {
                  if (homeProvider.selectedIndex != 1) {
                    return const SizedBox.shrink();
                  }
                  final showCompleted = actionItemsProvider.showCompletedView;
                  return Row(
                    children: [
                      // Export button
                      Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          color: Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: const Icon(
                            Icons.ios_share,
                            size: 18,
                            color: Colors.white70,
                          ),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (context) => const TaskIntegrationsPage(),
                              ),
                            );
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
                            showCompleted ? Icons.check_circle : Icons.check_circle_outline,
                            size: 18,
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
              // Settings button - always visible
              Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(
                  color: Color(0xFF1F1F25),
                  shape: BoxShape.circle,
                ),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: const Icon(
                    FontAwesomeIcons.gear,
                    size: 16,
                    color: Colors.white70,
                  ),
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
    // Cancel stream subscription to prevent memory leak
    _notificationStreamSubscription?.cancel();
    // Remove capture provider listener
    try {
      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      captureProvider.removeListener(_onCaptureProviderChanged);
      captureProvider.onFreemiumSessionReset = null;
    } catch (_) {}
    // Clean up freemium handler
    _freemiumHandler.dispose();
    // Remove foreground task callback to prevent memory leak
    FlutterForegroundTask.removeTaskDataCallback(_onReceiveTaskData);
    ForegroundUtil.stopForegroundTask();
    super.dispose();
  }
}
