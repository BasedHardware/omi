import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:friend_private/pages/home/widgets/speech_language_sheet.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/pages/apps/page.dart';
import 'package:friend_private/pages/settings/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_provider.dart' as mp;
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/utils/analytics/analytics_manager.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/foreground.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/upgrade_alert.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';

import 'widgets/battery_info_widget.dart';

class HomePageWrapper extends StatefulWidget {
  final bool openAppFromNotification;
  const HomePageWrapper({super.key, this.openAppFromNotification = false});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  late bool _openAppFromNotification;
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
      context.read<DeviceProvider>().periodicConnect('coming from HomePageWrapper');
      await context.read<mp.MemoryProvider>().getInitialMemories();
      if (mounted) {
        context.read<AppProvider>().setSelectedChatAppId(null);
      }
    });
    _openAppFromNotification = widget.openAppFromNotification;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return HomePage(openAppFromNotification: _openAppFromNotification);
  }
}

class HomePage extends StatefulWidget {
  final bool openAppFromNotification;
  const HomePage({super.key, this.openAppFromNotification = false});

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
  final Map<String, Widget> screensWithRespectToPath = {'/settings': const SettingsPage()};
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
    if (widget.openAppFromNotification) {
      context.read<HomeProvider>().selectedIndex = SharedPreferencesUtil().pageToShowFromNotification;
      _controller = PageController(initialPage: SharedPreferencesUtil().pageToShowFromNotification);
      if (SharedPreferencesUtil().pageToShowFromNotification == 1) {
        WidgetsBinding.instance.addPostFrameCallback((_) async {
          await context.read<MessageProvider>().refreshMessages();
        });
      }
      SharedPreferencesUtil().pageToShowFromNotification = 0;
    } else {
      _controller = PageController();
    }
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiateApps();
      // ForegroundUtil.requestPermissions();
      await ForegroundUtil.initializeForegroundService();
      ForegroundUtil.startForegroundTask();
      if (mounted) {
        await context.read<HomeProvider>().setUserPeople();

        // Start stream recording
        if (mounted) {
          await Provider.of<CaptureProvider>(context, listen: false)
              .streamDeviceRecording(device: context.read<DeviceProvider>().connectedDevice);
        }
      }
    });

    // _migrationScripts(); not for now, we don't have scripts
    // authenticateGCP();

    _listenToMessagesFromNotification();
    if (SharedPreferencesUtil().subPageToShowFromNotification != '') {
      final subPageRoute = SharedPreferencesUtil().subPageToShowFromNotification;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        MyApp.navigatorKey.currentState?.push(
          MaterialPageRoute(
            builder: (context) => screensWithRespectToPath[subPageRoute] as Widget,
          ),
        );
      });
      SharedPreferencesUtil().subPageToShowFromNotification = '';
    }
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  void _listenToMessagesFromNotification() {
    NotificationService.instance.listenForServerMessages.listen((message) {
      context.read<MessageProvider>().addMessage(message);
      // chatPageKey.currentState?.scrollToBottom();
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
          if (previousConnection != isConnected) {
            previousConnection = isConnected;
            if (!isConnected) {
              Future.delayed(Duration.zero, () {
                if (mounted) {
                  ScaffoldMessenger.of(ctx).showMaterialBanner(
                    MaterialBanner(
                      content: const Text('No internet connection. Please check your connection.'),
                      backgroundColor: Colors.red,
                      actions: [
                        TextButton(
                          onPressed: () {
                            ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                          },
                          child: const Text('Dismiss'),
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
                      content: const Text('Internet connection is restored.'),
                      backgroundColor: Colors.green,
                      actions: [
                        TextButton(
                          onPressed: () {
                            if (mounted) {
                              ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                            }
                          },
                          child: const Text('Dismiss'),
                        ),
                      ],
                      onVisible: () => Future.delayed(const Duration(seconds: 3), () {
                        ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                      }),
                    ),
                  );
                }

                WidgetsBinding.instance.addPostFrameCallback((_) async {
                  if (mounted) {
                    if (ctx.read<mp.MemoryProvider>().memories.isEmpty) {
                      await ctx.read<mp.MemoryProvider>().getInitialMemories();
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
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: DefaultTabController(
            length: 3,
            initialIndex: SharedPreferencesUtil().pageToShowFromNotification,
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
                        MemoriesPage(),
                        ChatPage(),
                        AppsPage(),
                      ],
                    ),
                  ),
                  Consumer<HomeProvider>(
                    builder: (context, home, child) {
                      if (home.chatFieldFocusNode.hasFocus ||
                          home.memoryFieldFocusNode.hasFocus ||
                          home.appsSearchFieldFocusNode.hasFocus) {
                        return const SizedBox.shrink();
                      } else {
                        return Align(
                          alignment: Alignment.bottomCenter,
                          child: Container(
                            margin: const EdgeInsets.fromLTRB(32, 16, 32, 40),
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
                              padding: const EdgeInsets.only(top: 4, bottom: 4),
                              onTap: (index) {
                                MixpanelManager().bottomNavigationTabClicked(['Memories', 'Chat', 'Apps'][index]);
                                primaryFocus?.unfocus();
                                home.setIndex(index);
                                _controller?.animateToPage(index,
                                    duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                              },
                              indicatorColor: Colors.transparent,
                              tabs: [
                                Tab(
                                  child: Text(
                                    'Memories',
                                    style: TextStyle(
                                      color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                                      fontSize: MediaQuery.sizeOf(context).width < 410 ? 14 : 16,
                                    ),
                                  ),
                                ),
                                Tab(
                                  child: Text(
                                    'Chat',
                                    style: TextStyle(
                                      color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                                      fontSize: MediaQuery.sizeOf(context).width < 410 ? 14 : 16,
                                    ),
                                  ),
                                ),
                                Tab(
                                  child: Text(
                                    'Apps',
                                    style: TextStyle(
                                      color: home.selectedIndex == 2 ? Colors.white : Colors.grey,
                                      fontSize: MediaQuery.sizeOf(context).width < 410 ? 14 : 16,
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
                  if (scriptsInProgress)
                    Center(
                      child: Container(
                        height: 150,
                        width: 250,
                        decoration: BoxDecoration(
                          color: Colors.black,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.white, width: 2),
                        ),
                        child: const Column(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                            SizedBox(height: 16),
                            Center(
                                child: Text(
                              'Running migration, please wait! 🚨',
                              style: TextStyle(color: Colors.white, fontSize: 16),
                              textAlign: TextAlign.center,
                            )),
                          ],
                        ),
                      ),
                    )
                  else
                    const SizedBox.shrink(),
                ],
              ),
            ),
          ),
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: Theme.of(context).colorScheme.surface,
            title: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const BatteryInfoWidget(),
                Consumer<HomeProvider>(
                  builder: (context, provider, child) {
                    if (provider.selectedIndex == 1) {
                      return const ChatAppsDropdownWidget();
                    } else if (provider.selectedIndex == 2) {
                      return const Text('Apps', style: TextStyle(color: Colors.white, fontSize: 18));
                    } else {
                      return Flexible(
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
                    Consumer2<MemoryProvider, HomeProvider>(builder: (context, memoryProvider, home, child) {
                      if (home.selectedIndex != 0 ||
                          !memoryProvider.hasNonDiscardedMemories ||
                          memoryProvider.isLoadingMemories) {
                        return const SizedBox.shrink();
                      }
                      return IconButton(
                          onPressed: memoryProvider.toggleDiscardMemories,
                          icon: Icon(
                            SharedPreferencesUtil().showDiscardedMemories
                                ? Icons.filter_list_off_sharp
                                : Icons.filter_list,
                            color: Colors.white,
                            size: 24,
                          ));
                    }),
                    IconButton(
                      icon: const Icon(Icons.settings, color: Colors.white, size: 30),
                      onPressed: () async {
                        MixpanelManager().pageOpened('Settings');
                        String language = SharedPreferencesUtil().recordingsLanguage;
                        bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                        String transcriptModel = SharedPreferencesUtil().transcriptionModel;
                        await routeToPage(context, const SettingsPage());

                        if (language != SharedPreferencesUtil().recordingsLanguage ||
                            hasSpeech != SharedPreferencesUtil().hasSpeakerProfile ||
                            transcriptModel != SharedPreferencesUtil().transcriptionModel) {
                          if (context.mounted) {
                            context.read<CaptureProvider>().onRecordProfileSettingChanged();
                          }
                        }
                      },
                    ),
                  ],
                )
              ],
            ),
            elevation: 0,
            centerTitle: true,
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    ForegroundUtil.stopForegroundTask();
    super.dispose();
  }
}
