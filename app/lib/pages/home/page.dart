import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/capture/page.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/home/device.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/page.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_provider.dart' as mp;
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/foreground.dart';
import 'package:friend_private/utils/connectivity_controller.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/upgrade_alert.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:provider/provider.dart';
import 'package:upgrader/upgrader.dart';

GlobalKey<CapturePageState> capturePageKey = GlobalKey();

class HomePageWrapper extends StatefulWidget {
  const HomePageWrapper({super.key});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      context.read<DeviceProvider>().periodicConnect('coming from HomePageWrapper');
      await context.read<mp.MemoryProvider>().getInitialMemories();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => HomeProvider(),
      child: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();
  TabController? _controller;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox()];

  FocusNode chatTextFieldFocusNode = FocusNode(canRequestFocus: true);
  FocusNode memoriesTextFieldFocusNode = FocusNode(canRequestFocus: true);

  GlobalKey<ChatPageState> chatPageKey = GlobalKey();
  
  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;

  Future<void> _initiatePlugins() async {
    context.read<PluginProvider>().getPlugins();
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

  _migrationScripts() async {
    setState(() => scriptsInProgress = true);
    // await scriptMigrateMemoriesToBack();
    if (mounted) {
      await context.read<mp.MemoryProvider>().getInitialMemories();
    }
    setState(() => scriptsInProgress = false);
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {'/settings': const SettingsPage()};
  ConnectivityController connectivityController = ConnectivityController();
  bool? previousConnection;

  @override
  void initState() {
    // TODO: Being triggered multiple times during navigation. It ideally shouldn't
    connectivityController.init();
    _controller = TabController(
      length: 3,
      vsync: this,
      initialIndex: SharedPreferencesUtil().pageToShowFromNotification,
    );
    SharedPreferencesUtil().pageToShowFromNotification = 1;
    SharedPreferencesUtil().onboardingCompleted = true;

    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiatePlugins();
      ForegroundUtil.requestPermissions();
      await ForegroundUtil.initializeForegroundService();
      ForegroundUtil.startForegroundTask();
      if (mounted) {
        await context.read<HomeProvider>().setupHasSpeakerProfile();
        await context.read<HomeProvider>().setUserPeople();
      }
    });

    // _migrationScripts(); not for now, we don't have scripts
    authenticateGCP();

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
  }

  void _listenToMessagesFromNotification() {
    NotificationService.instance.listenForServerMessages.listen((message) {
      context.read<MessageProvider>().addMessage(message);
      chatPageKey.currentState?.scrollToBottom();
    });
  }

  _tabChange(int index) {
    MixpanelManager().bottomNavigationTabClicked(['Memories', 'Device', 'Chat'][index]);
    FocusScope.of(context).unfocus();
    context.read<HomeProvider>().setIndex(index);
    _controller!.animateTo(index);
  }

  @override
  Widget build(BuildContext context) {
    return WithForegroundTask(
        child: MyUpgradeAlert(
      upgrader: _upgrader,
      dialogStyle: Platform.isIOS ? UpgradeDialogStyle.cupertino : UpgradeDialogStyle.material,
      child: ValueListenableBuilder(
          valueListenable: connectivityController.isConnected,
          builder: (ctx, isConnected, child) {
            previousConnection ??= true;
            if (previousConnection != isConnected) {
              previousConnection = isConnected;
              if (!isConnected) {
                Future.delayed(Duration.zero, () {
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
                });
              } else {
                Future.delayed(Duration.zero, () {
                  ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                  ScaffoldMessenger.of(ctx).showMaterialBanner(
                    MaterialBanner(
                      content: const Text('Internet connection is restored.'),
                      backgroundColor: Colors.green,
                      actions: [
                        TextButton(
                          onPressed: () {
                            ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                          },
                          child: const Text('Dismiss'),
                        ),
                      ],
                      onVisible: () => Future.delayed(const Duration(seconds: 3), () {
                        ScaffoldMessenger.of(ctx).hideCurrentMaterialBanner();
                      }),
                    ),

                  );

                  WidgetsBinding.instance.addPostFrameCallback((_) async {
                    if (mounted) {
                      if (context.read<mp.MemoryProvider>().memories.isEmpty) {
                        await context.read<mp.MemoryProvider>().getInitialMemories();
                      }
                      if (context.read<MessageProvider>().messages.isEmpty) {
                        await context.read<MessageProvider>().refreshMessages();
                      }
                    }
                  });
                });
              }
            }

            return Scaffold(
              backgroundColor: Theme.of(context).colorScheme.primary,
              body: GestureDetector(
                onTap: () {
                  FocusScope.of(context).unfocus();
                  chatTextFieldFocusNode.unfocus();
                  memoriesTextFieldFocusNode.unfocus();
                },
                child: Consumer2<HomeProvider, mp.MemoryProvider>(builder: (context, provider, memProvider, child) {
                  return Stack(
                    children: [
                      Center(
                        child: TabBarView(
                          controller: _controller,
                          physics: const NeverScrollableScrollPhysics(),
                          children: [
                            MemoriesPage(
                              textFieldFocusNode: memoriesTextFieldFocusNode,
                            ),
                            CapturePage(
                              key: capturePageKey,
                            ),
                            ChatPage(
                              key: chatPageKey,
                              textFieldFocusNode: chatTextFieldFocusNode,
                              updateMemory: (ServerMemory memory) {
                                memProvider.updateMemory(memory);
                              },
                            ),
                          ],
                        ),
                      ),
                      if (chatTextFieldFocusNode.hasFocus || memoriesTextFieldFocusNode.hasFocus)
                        const SizedBox.shrink()
                      else
                        Align(
                          alignment: Alignment.bottomCenter,
                          child: Container(
                            margin: const EdgeInsets.fromLTRB(16, 16, 16, 40),
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
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Expanded(
                                  child: MaterialButton(
                                    onPressed: () => _tabChange(0),
                                    child: Padding(
                                      padding: const EdgeInsets.only(top: 20, bottom: 20),
                                      child: Text(
                                        'Memories',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          color: provider.selectedIndex == 0 ? Colors.white : Colors.grey,
                                          fontSize: 16,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                Expanded(
                                  child: MaterialButton(
                                    onPressed: () => _tabChange(1),
                                    child: Padding(
                                      padding: const EdgeInsets.only(
                                        top: 20,
                                        bottom: 20,
                                      ),
                                      child: Text(
                                        'Capture',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          color: provider.selectedIndex == 1 ? Colors.white : Colors.grey,
                                          fontSize: 16,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                Expanded(
                                  child: MaterialButton(
                                    onPressed: () => _tabChange(2),
                                    child: Padding(
                                      padding: const EdgeInsets.only(top: 20, bottom: 20),
                                      child: Text(
                                        'Chat',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          color: provider.selectedIndex == 2 ? Colors.white : Colors.grey,
                                          fontSize: 16,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
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
                  );
                }),
              ),
              appBar: AppBar(
                automaticallyImplyLeading: false,
                backgroundColor: Theme.of(context).colorScheme.surface,
                title: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Consumer<DeviceProvider>(builder: (context, deviceProvider, child) {
                      if (deviceProvider.connectedDevice != null && deviceProvider.batteryLevel != -1) {
                        return GestureDetector(
                          onTap: deviceProvider.connectedDevice == null
                              ? null
                              : () {
                                  Navigator.of(context).push(MaterialPageRoute(
                                      builder: (c) => ConnectedDevice(
                                            device: deviceProvider.connectedDevice!,
                                            batteryLevel: deviceProvider.batteryLevel,
                                          )));
                                  MixpanelManager().batteryIndicatorClicked();
                                },
                          child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                              decoration: BoxDecoration(
                                color: Colors.transparent,
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(
                                  color: Colors.grey,
                                  width: 1,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Container(
                                    width: 10,
                                    height: 10,
                                    decoration: BoxDecoration(
                                      color: deviceProvider.batteryLevel > 75
                                          ? const Color.fromARGB(255, 0, 255, 8)
                                          : deviceProvider.batteryLevel > 20
                                              ? Colors.yellow.shade700
                                              : Colors.red,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                  const SizedBox(width: 8.0),
                                  Text(
                                    '${deviceProvider.batteryLevel.toString()}%',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 12,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              )),
                        );
                      } else {
                        print(deviceProvider.connectedDevice?.id);
                        return TextButton(
                          onPressed: () async {
                            if (SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
                              routeToPage(context, const ConnectDevicePage());
                              MixpanelManager().connectFriendClicked();
                            } else {
                              await routeToPage(
                                  context,
                                  ConnectedDevice(
                                      device: deviceProvider.connectedDevice,
                                      batteryLevel: deviceProvider.batteryLevel));
                            }
                            // setState(() {});
                          },
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            backgroundColor: Colors.transparent,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                              side: const BorderSide(color: Colors.white, width: 1),
                            ),
                          ),
                          child: Image.asset('assets/images/logo_transparent.png', width: 25, height: 25),
                        );
                      }
                    }),
                    _controller!.index == 2
                        ? Consumer<PluginProvider>(builder: (context, provider, child) {
                            return Padding(
                              padding: const EdgeInsets.only(left: 0),
                              child: Container(
                                // decoration: BoxDecoration(
                                //   border: Border.all(color: Colors.grey),
                                //   borderRadius: BorderRadius.circular(30),
                                // ),
                                padding: const EdgeInsets.symmetric(horizontal: 16),
                                child: DropdownButton<String>(
                                  menuMaxHeight: 350,
                                  value: SharedPreferencesUtil().selectedChatPluginId,
                                  onChanged: (s) async {
                                    if ((s == 'no_selected' && provider.plugins.where((p) => p.enabled).isEmpty) ||
                                        s == 'enable') {
                                      await routeToPage(context, const PluginsPage(filterChatOnly: true));
                                      return;
                                    }
                                    print('Selected: $s prefs: ${SharedPreferencesUtil().selectedChatPluginId}');
                                    if (s == null || s == SharedPreferencesUtil().selectedChatPluginId) return;

                                    SharedPreferencesUtil().selectedChatPluginId = s;
                                    var plugin = provider.plugins.firstWhereOrNull((p) => p.id == s);
                                    chatPageKey.currentState?.sendInitialPluginMessage(plugin);
                                  },
                                  icon: Container(),
                                  alignment: Alignment.center,
                                  dropdownColor: Colors.black,
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                  underline: Container(height: 0, color: Colors.transparent),
                                  isExpanded: false,
                                  itemHeight: 48,
                                  padding: EdgeInsets.zero,
                                  items: _getPluginsDropdownItems(context, provider),
                                ),
                              ),
                            );
                          })
                        : const SizedBox(width: 16),
                    IconButton(
                      icon: const Icon(Icons.settings, color: Colors.white, size: 30),
                      onPressed: () async {

                        MixpanelManager().settingsOpened();
                        String language = SharedPreferencesUtil().recordingsLanguage;
                        bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                        await routeToPage(context, const SettingsPage());
                        // TODO: this fails like 10 times, connects reconnects, until it finally works.
                        if (language != SharedPreferencesUtil().recordingsLanguage ||
                            hasSpeech != SharedPreferencesUtil().hasSpeakerProfile) {
                          context.read<DeviceProvider>().restartWebSocket();
                        }
                      },
                    )
                  ],
                ),
                elevation: 0,
                centerTitle: true,
              ),
            );
          }),
    ));
  }

  _getPluginsDropdownItems(BuildContext context, PluginProvider provider) {
    var items = [
          DropdownMenuItem<String>(
            value: 'no_selected',
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const Icon(size: 20, Icons.chat, color: Colors.white),
                const SizedBox(width: 10),
                Text(
                  provider.plugins.where((p) => p.enabled).isEmpty ? 'Enable Plugins   ' : 'Select a plugin',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                )
              ],
            ),
          )
        ] +
        provider.plugins.where((p) => p.enabled && p.worksWithChat()).map<DropdownMenuItem<String>>((Plugin plugin) {
          return DropdownMenuItem<String>(
            value: plugin.id,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              mainAxisAlignment: MainAxisAlignment.start,
              children: [
                CircleAvatar(
                  backgroundColor: Colors.white,
                  maxRadius: 12,
                  backgroundImage: NetworkImage(plugin.getImageUrl()),
                ),
                const SizedBox(width: 8),
                Text(
                  plugin.name.length > 18
                      ? '${plugin.name.substring(0, 18)}...'
                      : plugin.name + ' ' * (18 - plugin.name.length),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                )
              ],
            ),
          );
        }).toList();
    if (provider.plugins.where((p) => p.enabled).isNotEmpty) {
      items.add(const DropdownMenuItem<String>(
        value: 'enable',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            CircleAvatar(
              backgroundColor: Colors.transparent,
              maxRadius: 12,
              child: Icon(Icons.star, color: Colors.purpleAccent),
            ),
            SizedBox(width: 8),
            Text('Enable Plugins   ', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16))
          ],
        ),
      ));
    }
    return items;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    connectivityController.isConnected.dispose();
    _controller?.dispose();
    ForegroundUtil.stopForegroundTask();
    super.dispose();
  }
}
