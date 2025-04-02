import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:omi/pages/connectivity/connectivity.dart';
import 'package:omi/pages/home/widgets/build_app_bar.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/settings/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/execution_gaurd.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:responsive_framework/responsive_framework.dart';
import 'package:upgrader/upgrader.dart';

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
      if (mounted) {
        context.read<AppProvider>().setSelectedChatAppId(null);
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
  ForegroundUtil? foregroundUtil = (!ExecutionGuard.isWeb) ? ForegroundUtil() : null;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox(), const SizedBox()];

  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;

  PageController? _controller;

  void _initiateApps() {
    context.read<AppProvider>().getApps();
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
        debugPrint('Reload convos');
        Provider.of<ConversationProvider>(context, listen: false).fetchNewConversations();
      }
    } else if (state == AppLifecycleState.hidden) {
      event = 'App is hidden';
    } else if (state == AppLifecycleState.detached) {
      event = 'App is detached';
    } else {
      return;
    }
    debugPrint(event);
    InstabugLog.logInfo(event);
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {
    '/settings': const SettingsPage(),
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
          homePageIdx = 0;
          break;
        case "chat":
          homePageIdx = 1;
        case "apps":
          homePageIdx = 2;
          break;
      }
    }

    // Home controler
    _controller = PageController(initialPage: homePageIdx);
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    context.read<HomeProvider>().onSelectedIndexChanged = (index) {
      _controller?.animateToPage(index, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
    };
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();

      // ForegroundUtil.requestPermissions();

      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false)
            .streamDeviceRecording(device: Provider.of<DeviceProvider>(context, listen: false).connectedDevice);
      }

      // Navigate
      switch (pageAlias) {
        case "chat":
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
          break;
        case "settings":
          MyApp.navigatorKey.currentState?.push(
            MaterialPageRoute(
              builder: (context) => const SettingsPage(),
            ),
          );
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

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        if (context.read<ConversationProvider>().conversations.isEmpty) {
          await context.read<ConversationProvider>().getInitialConversations();
        }
      }
      if (mounted) {
        if (context.read<MessageProvider>().messages.isEmpty) {
          await context.read<MessageProvider>().refreshMessages();
        }
      }
    });
    super.initState();

    // After init
    if (!ExecutionGuard.isWeb) {
      _initForegroundUtil();
      _listenToMessagesFromNotification();
      FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
    }
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

  final totalTabs = ['Memories', 'Chat', 'Explore'];

  @override
  Widget build(BuildContext context) {
    final connectivityProvider = context.watch<ConnectivityProvider>();
    connectionCheck(connectivityProvider, context);
    return MyUpgradeAlert(
      upgrader: _upgrader,
      dialogStyle: ExecutionGuard.isIOS ? UpgradeDialogStyle.cupertino : UpgradeDialogStyle.material,
      child: Consumer<HomeProvider>(
        builder: (context, homeProvider, _) {
          return Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar:
                ResponsiveBreakpoints.of(context).largerOrEqualTo(DESKTOP) ? null : buildAppBar(context, _controller),
            body: Row(
              children: [
                if (ResponsiveBreakpoints.of(context).largerOrEqualTo(DESKTOP))
                  Drawer(
                    elevation: 4,
                    backgroundColor: Colors.black,
                    child: Container(
                      margin: const EdgeInsets.all(8),
                      decoration: const BoxDecoration(
                        color: Colors.black,
                        borderRadius: BorderRadius.all(Radius.circular(16)),
                        border: GradientBoxBorder(
                          gradient: LinearGradient(colors: [
                            Color.fromARGB(127, 208, 208, 208),
                            Color.fromARGB(127, 188, 99, 121),
                            Color.fromARGB(127, 86, 101, 182),
                            Color.fromARGB(127, 126, 190, 236)
                          ]),
                          width: 2,
                        ),
                        shape: BoxShape.rectangle,
                      ),
                      child: ListView.builder(
                        itemCount: totalTabs.length,
                        itemBuilder: (context, index) {
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            child: TextButton(
                              style: TextButton.styleFrom(
                                fixedSize: const Size.fromHeight(50),
                              ),
                              onPressed: () {
                                MixpanelManager().bottomNavigationTabClicked(['Memories', 'Chat', 'Explore'][index]);
                                primaryFocus?.unfocus();
                                if (homeProvider.selectedIndex == index) {
                                  return;
                                }
                                homeProvider.setIndex(index);
                                _controller?.animateToPage(index,
                                    duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                              },
                              child: Text(
                                totalTabs[index],
                                style: TextStyle(
                                  color: homeProvider.selectedIndex == index ? Colors.white : Colors.grey,
                                  fontSize: MediaQuery.sizeOf(context).width < 410 ? 13 : 15,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                Expanded(
                  child: DefaultTabController(
                    length: 3,
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
                            child: Padding(
                              padding: const EdgeInsets.all(8.0),
                              child: PageView(
                                scrollDirection: Axis.horizontal,
                                controller: _controller,
                                physics: const NeverScrollableScrollPhysics(),
                                children: [
                                  const ConversationsPage(),
                                  ChatPage(isPivotBottom: false, pageController: _controller),
                                  const AppsPage(),
                                  const PersonaProfilePage(bottomMargin: 120),
                                ],
                              ),
                            ),
                          ),
                          if (!ResponsiveBreakpoints.of(context).largerOrEqualTo(DESKTOP))
                            Consumer<HomeProvider>(
                              builder: (context, home, child) {
                                if (home.chatFieldFocusNode.hasFocus ||
                                    home.convoSearchFieldFocusNode.hasFocus ||
                                    home.appsSearchFieldFocusNode.hasFocus) {
                                  return const SizedBox.shrink();
                                } else {
                                  return Align(
                                    alignment: Alignment.bottomCenter,
                                    child: Container(
                                      margin: const EdgeInsets.fromLTRB(20, 16, 20, 42),
                                      decoration: const BoxDecoration(
                                        color: Colors.black,
                                        borderRadius: BorderRadius.all(Radius.circular(16)),
                                        border: GradientBoxBorder(
                                          gradient: LinearGradient(colors: [
                                            Color.fromARGB(127, 208, 208, 208),
                                            Color.fromARGB(127, 188, 99, 121),
                                            Color.fromARGB(127, 86, 101, 182),
                                            Color.fromARGB(127, 126, 190, 236)
                                          ]),
                                          width: 2,
                                        ),
                                        shape: BoxShape.rectangle,
                                      ),
                                      child: TabBar(
                                        labelPadding: const EdgeInsets.only(top: 4, bottom: 4),
                                        indicatorPadding: EdgeInsets.zero,
                                        onTap: (index) {
                                          MixpanelManager()
                                              .bottomNavigationTabClicked(['Memories', 'Chat', 'Explore'][index]);
                                          primaryFocus?.unfocus();
                                          if (home.selectedIndex == index) {
                                            return;
                                          }
                                          home.setIndex(index);
                                          _controller?.animateToPage(index,
                                              duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                                        },
                                        indicatorColor: Colors.transparent,
                                        tabs: [
                                          Tab(
                                            child: Text(
                                              'Home',
                                              style: TextStyle(
                                                color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                                                fontSize: MediaQuery.sizeOf(context).width < 410 ? 13 : 15,
                                              ),
                                            ),
                                          ),
                                          Tab(
                                            child: Text(
                                              'Chat',
                                              style: TextStyle(
                                                color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                                                fontSize: MediaQuery.sizeOf(context).width < 410 ? 13 : 15,
                                              ),
                                            ),
                                          ),
                                          Tab(
                                            child: Text(
                                              'Explore',
                                              style: TextStyle(
                                                color: home.selectedIndex == 2 ? Colors.white : Colors.grey,
                                                fontSize: MediaQuery.sizeOf(context).width < 410 ? 13 : 15,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                }
                              },
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  void connectionCheck(ConnectivityProvider connectivityProvider, BuildContext context) async {
    bool isConnected = connectivityProvider.isConnected;
    previousConnection ??= true;
    if (previousConnection != isConnected && connectivityProvider.isInitialized) {
      previousConnection = isConnected;
      if (!isConnected) {
        Future.delayed(const Duration(seconds: 2), () {
          if (mounted && !connectivityProvider.isConnected) {
            showNoConnectionDialog(connectivityProvider, context, mounted);
          }
        });
      } else {
        Future.delayed(Duration.zero, () {
          showConnectionRestoredDialoag(context, mounted);
          WidgetsBinding.instance.addPostFrameCallback((_) async {
            if (mounted) {
              if (context.read<ConversationProvider>().conversations.isEmpty) {
                await context.read<ConversationProvider>().getInitialConversations();
              }
              if (context.read<MessageProvider>().messages.isEmpty) {
                await context.read<MessageProvider>().refreshMessages();
              }
            }
          });
        });
      }
    }
  }

  void _initForegroundUtil() async {
    await ForegroundUtil.initializeForegroundService();
    ForegroundUtil.startForegroundTask();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (!ExecutionGuard.isWeb) ForegroundUtil.stopForegroundTask();
    if (_controller != null) {
      _controller!.dispose();
      _controller = null;
    }
    super.dispose();
  }
}
