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
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
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
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/pages/conversation_capturing/page.dart';

import '../conversations/sync_page.dart';
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
      if (SharedPreferencesUtil().notificationsEnabled != await Permission.notification.isGranted) {
        SharedPreferencesUtil().notificationsEnabled = await Permission.notification.isGranted;
        AnalyticsManager().setUserAttribute('Notifications Enabled', SharedPreferencesUtil().notificationsEnabled);
      }
      if (SharedPreferencesUtil().notificationsEnabled) {
        NotificationService.instance.register();
      }
      if (SharedPreferencesUtil().locationEnabled != await Permission.location.isGranted) {
        SharedPreferencesUtil().locationEnabled = await Permission.location.isGranted;
        AnalyticsManager().setUserAttribute('Location Enabled', SharedPreferencesUtil().locationEnabled);
      }
      if (mounted) {
        context.read<DeviceProvider>().periodicConnect('coming from HomePageWrapper');
      }
      if (mounted) {
        await context.read<ConversationProvider>().getInitialConversations();
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

  PageController? _controller;

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

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {
    '/facts': const MemoriesPage(),
  };
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
    _controller = PageController(initialPage: homePageIdx);
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    context.read<HomeProvider>().onSelectedIndexChanged = (index) {
      _controller?.animateToPage(index, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
    };
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();

      // ForegroundUtil.requestPermissions();
      if (!PlatformService.isDesktop) {
        await ForegroundUtil.initializeForegroundService();
        await ForegroundUtil.startForegroundTask();
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Navigate
      switch (pageAlias) {
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
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const ChatPage(isPivotBottom: false),
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
        default:
      }
    });

    _listenToMessagesFromNotification();
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  void _listenToMessagesFromNotification() {
    NotificationService.instance.listenForServerMessages.listen((message) {
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
                      backgroundColor: const Color(0xFF424242), // Dark gray instead of red
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
              Future.delayed(Duration.zero, () {
                if (mounted) {
                  ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                  ScaffoldMessenger.of(ctx).showMaterialBanner(
                    MaterialBanner(
                      content: const Text(
                        'Internet connection is restored.',
                        style: TextStyle(color: Colors.white),
                      ),
                      backgroundColor: const Color(0xFF2E7D32), // Dark green instead of bright green
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
        child: Consumer<HomeProvider>(
          builder: (context, homeProvider, _) {
            return Scaffold(
              backgroundColor: Theme.of(context).colorScheme.primary,
              appBar: homeProvider.selectedIndex == 5 ? null : _buildAppBar(context),
              body: DefaultTabController(
                length: 4,
                initialIndex: _controller?.initialPage ?? 0,
                child: GestureDetector(
                  onTap: () {
                    primaryFocus?.unfocus();
                    // context.read<HomeProvider>().memoryFieldFocusNode.unfocus();
                    // context.read<HomeProvider>().chatFieldFocusNode.unfocus();
                  },
                  child: Stack(
                    children: [
                      Center(
                        child: PageView(
                          controller: _controller,
                          physics: const NeverScrollableScrollPhysics(),
                          children: const [
                            ConversationsPage(),
                            ActionItemsPage(),
                            MemoriesPage(),
                            AppsPage(),
                          ],
                        ),
                      ),
                      Consumer2<HomeProvider, DeviceProvider>(
                        builder: (context, home, deviceProvider, child) {
                          if (home.isChatFieldFocused || home.isConvoSearchFieldFocused || home.isAppsSearchFieldFocused || home.isMemoriesSearchFieldFocused) {
                            return const SizedBox.shrink();
                          } else {
                            // Check if OMI device is connected
                            bool isOmiDeviceConnected = deviceProvider.isConnected && deviceProvider.connectedDevice != null;

                            return Stack(
                              children: [
                                // Bottom Navigation Bar
                                Align(
                                  alignment: Alignment.bottomCenter,
                                  child: Container(
                                    width: double.infinity,
                                    height: 90,
                                    padding: const EdgeInsets.symmetric(horizontal: 20),
                                    decoration: const BoxDecoration(
                                      color: Color.fromARGB(255, 15, 15, 15),
                                    ),
                                    child: Row(
                                      children: [
                                        // Home tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              MixpanelManager().bottomNavigationTabClicked('Home');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 0) {
                                                return;
                                              }
                                              home.setIndex(0);
                                              _controller?.animateToPage(0, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                                            },
                                            child: Container(
                                              height: 90,
                                              child: Padding(
                                                padding: const EdgeInsets.only(bottom: 15),
                                                child: Column(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(
                                                      FontAwesomeIcons.house,
                                                      color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                                                      size: 24,
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        // Action Items tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              MixpanelManager().bottomNavigationTabClicked('Action Items');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 1) {
                                                return;
                                              }
                                              home.setIndex(1);
                                              _controller?.animateToPage(1, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                                            },
                                            child: Container(
                                              height: 90,
                                              child: Padding(
                                                padding: const EdgeInsets.only(bottom: 15),
                                                child: Column(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(
                                                      FontAwesomeIcons.listCheck,
                                                      color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                                                      size: 24,
                                                    ),
                                                  ],
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
                                              MixpanelManager().bottomNavigationTabClicked('Memories');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 2) {
                                                return;
                                              }
                                              home.setIndex(2);
                                              _controller?.animateToPage(2, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                                            },
                                            child: Container(
                                              height: 90,
                                              child: Padding(
                                                padding: const EdgeInsets.only(bottom: 15),
                                                child: Column(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(
                                                      FontAwesomeIcons.brain,
                                                      color: home.selectedIndex == 2 ? Colors.white : Colors.grey,
                                                      size: 24,
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                        // Apps tab
                                        Expanded(
                                          child: InkWell(
                                            onTap: () {
                                              MixpanelManager().bottomNavigationTabClicked('Explore');
                                              primaryFocus?.unfocus();
                                              if (home.selectedIndex == 3) {
                                                return;
                                              }
                                              home.setIndex(3);
                                              _controller?.animateToPage(3, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                                            },
                                            child: Container(
                                              height: 90,
                                              child: Padding(
                                                padding: const EdgeInsets.only(bottom: 15),
                                                child: Column(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(
                                                      FontAwesomeIcons.search,
                                                      color: home.selectedIndex == 3 ? Colors.white : Colors.grey,
                                                      size: 24,
                                                    ),
                                                  ],
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
                                        bool isInitializing = captureProvider.recordingState == RecordingState.initialising;
                                        return GestureDetector(
                                          onTap: () async {
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
                                // Floating Chat Button - Only show on home page (index 0)
                                if (home.selectedIndex == 0)
                                  Positioned(
                                    right: 20,
                                    bottom: 110, // Position above the bottom navbar
                                    child: GestureDetector(
                                      onTap: () {
                                        // Navigate to chat page
                                        Navigator.push(
                                          context,
                                          MaterialPageRoute(
                                            builder: (context) => const ChatPage(isPivotBottom: false),
                                          ),
                                        );
                                      },
                                      child: Container(
                                        height: 56,
                                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                                        decoration: BoxDecoration(
                                          color: Colors.black,
                                          borderRadius: BorderRadius.circular(28),
                                          boxShadow: [
                                            BoxShadow(
                                              color: Colors.black.withOpacity(0.3),
                                              spreadRadius: 1,
                                              blurRadius: 8,
                                              offset: const Offset(0, 2),
                                            ),
                                          ],
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Container(
                                              width: 32,
                                              height: 32,
                                              decoration: const BoxDecoration(
                                                color: Colors.white,
                                                shape: BoxShape.circle,
                                              ),
                                              child: const Icon(
                                                FontAwesomeIcons.solidCommentDots,
                                                color: Colors.black,
                                                size: 16,
                                              ),
                                            ),
                                            const SizedBox(width: 12),
                                            const Text(
                                              'Chat',
                                              style: TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
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
        var topConvoId = (captureProvider.conversationProvider?.conversations ?? []).isNotEmpty ? captureProvider.conversationProvider!.conversations.first.id : null;
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
      toolbarHeight: PlatformService.isDesktop ? 80 : null,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const BatteryInfoWidget(),
          Consumer<HomeProvider>(builder: (context, provider, child) {
            if (provider.selectedIndex == 0) {
              return Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
                if (convoProvider.missingWalsInSeconds >= 120) {
                  return GestureDetector(
                    onTap: () {
                      routeToPage(context, const SyncPage());
                    },
                    child: Container(
                      padding: const EdgeInsets.only(left: 12),
                      child: const Icon(Icons.download, color: Colors.white, size: 28),
                    ),
                  );
                } else {
                  return const SizedBox.shrink();
                }
              });
            } else {
              return const SizedBox.shrink();
            }
          }),
          // Top Title App Bar
          Consumer<HomeProvider>(
            builder: (context, provider, child) {
              if (provider.selectedIndex == 1) {
                return const Expanded(
                  child: Center(
                    child: Text(
                      'Actions',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                );
              } else if (provider.selectedIndex == 2) {
                return const Expanded(
                  child: Center(
                    child: Text(
                      'Memories',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                );
              } else if (provider.selectedIndex == 3) {
                return Center(
                  child: Padding(
                    padding: EdgeInsets.only(right: MediaQuery.sizeOf(context).width * 0.10),
                    child: const Text('Apps',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                        )),
                  ),
                );
              } else {
                return const Expanded(
                  child: Center(
                    child: Text(
                      '',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                );
              }
            },
          ),
          Row(
            children: [
              Container(
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.transparent,
                ),
                child: IconButton(
                  padding: const EdgeInsets.fromLTRB(2.0, 2.0, 0, 2.0),
                  icon: SvgPicture.asset(
                    Assets.images.icSettingPersona,
                    width: 36,
                    height: 36,
                  ),
                  onPressed: () {
                    MixpanelManager().pageOpened('Settings');
                    String language = SharedPreferencesUtil().userPrimaryLanguage;
                    bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                    String transcriptModel = SharedPreferencesUtil().transcriptionModel;
                    SettingsDrawer.show(context);
                    if (language != SharedPreferencesUtil().userPrimaryLanguage || hasSpeech != SharedPreferencesUtil().hasSpeakerProfile || transcriptModel != SharedPreferencesUtil().transcriptionModel) {
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
    ForegroundUtil.stopForegroundTask();
    if (_controller != null) {
      _controller!.dispose();
      _controller = null;
    }
    super.dispose();
  }
}
