import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/facts/page.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/home/widgets/speech_language_sheet.dart';
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
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/upgrade_alert.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';

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
  ForegroundUtil foregroundUtil = ForegroundUtil();
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
    '/facts': const FactsPage(),
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
      await ForegroundUtil.initializeForegroundService();
      ForegroundUtil.startForegroundTask();
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
              builder: (context) => const FactsPage(),
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
              appBar: homeProvider.selectedIndex == 3 ? null : _buildAppBar(context),
              body: DefaultTabController(
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
                        child: PageView(
                          controller: _controller,
                          physics: const NeverScrollableScrollPhysics(),
                          children: const [
                            ConversationsPage(),
                            ChatPage(isPivotBottom: false),
                            AppsPage(),
                            PersonaProfilePage(bottomMargin: 120),
                          ],
                        ),
                      ),
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
            );
          },
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
                      child: const Icon(Icons.download, color: Colors.white, size: 24),
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
          Consumer<HomeProvider>(
            builder: (context, provider, child) {
              if (provider.selectedIndex == 1) {
                return ChatAppsDropdownWidget(
                  controller: _controller!,
                );
              } else if (provider.selectedIndex == 2) {
                return Padding(
                  padding: EdgeInsets.only(right: MediaQuery.sizeOf(context).width * 0.16),
                  child: const Text('Explore', style: TextStyle(color: Colors.white, fontSize: 18)),
                );
              } else {
                return Expanded(
                  child: Row(
                    children: [
                      const Spacer(),
                      SpeechLanguageSheet(
                        recordingLanguage: provider.recordingLanguage,
                        setRecordingLanguage: (language) {
                          provider.setRecordingLanguage(language);
                          // Notify capture provider
                          if (context.mounted) {
                            context.read<CaptureProvider>().onRecordProfileSettingChanged();
                          }
                        },
                        availableLanguages: provider.availableLanguages,
                      ),
                    ],
                  ),
                );
              }
            },
          ),
          Row(
            children: [
              IconButton(
                  padding: const EdgeInsets.all(8.0),
                  icon: SvgPicture.asset(
                    Assets.images.icPersonaProfile.path,
                    width: 28,
                    height: 28,
                  ),
                  onPressed: () {
                    MixpanelManager().pageOpened('Persona Profile');

                    // Set routing in provider
                    var personaProvider = Provider.of<PersonaProvider>(context, listen: false);
                    personaProvider.setRouting(PersonaProfileRouting.home);

                    // Navigate
                    var homeProvider = Provider.of<HomeProvider>(context, listen: false);
                    homeProvider.setIndex(3);
                    if (homeProvider.onSelectedIndexChanged != null) {
                      homeProvider.onSelectedIndexChanged!(3);
                    }
                  }),
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
