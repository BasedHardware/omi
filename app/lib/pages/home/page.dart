import 'dart:async';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/home/device.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_provider.dart' as mp;
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
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

class HomePageWrapper extends StatefulWidget {
  const HomePageWrapper({super.key});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (SharedPreferencesUtil().notificationsEnabled != await Permission.notification.isGranted) {
        SharedPreferencesUtil().notificationsEnabled = await Permission.notification.isGranted;
        AnalyticsManager().setUserAttribute('Notifications Enabled', SharedPreferencesUtil().notificationsEnabled);
      }
      if (SharedPreferencesUtil().notificationsEnabled) {
        await NotificationService.instance.register();
      }
      if (SharedPreferencesUtil().locationEnabled != await Permission.location.isGranted) {
        SharedPreferencesUtil().locationEnabled = await Permission.location.isGranted;
        AnalyticsManager().setUserAttribute('Location Enabled', SharedPreferencesUtil().locationEnabled);
      }
      context.read<DeviceProvider>().periodicConnect('coming from HomePageWrapper');
      await context.read<mp.MemoryProvider>().getInitialMemories();
      context.read<PluginProvider>().setSelectedChatPluginId(null);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return const HomePage();
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox(), const SizedBox()];

  GlobalKey<ChatPageState> chatPageKey = GlobalKey();

  final _upgrader = MyUpgrader(debugLogging: false, debugDisplayOnce: false);
  bool scriptsInProgress = false;

  void _initiatePlugins() {
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
    if (mounted) {
      setState(() => scriptsInProgress = true);
    }
    // await scriptMigrateMemoriesToBack();
    if (mounted) {
      await context.read<mp.MemoryProvider>().getInitialMemories();
    }
    if (mounted) {
      setState(() => scriptsInProgress = false);
    }
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {'/settings': const SettingsPage()};
  bool? previousConnection;

  @override
  void initState() {
    SharedPreferencesUtil().pageToShowFromNotification = 0; // TODO: whatisit
    SharedPreferencesUtil().onboardingCompleted = true;

    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _initiatePlugins();
      // ForegroundUtil.requestPermissions();
      await ForegroundUtil.initializeForegroundService();
      ForegroundUtil.startForegroundTask();
      if (mounted) {
        await context.read<HomeProvider>().setUserPeople();

        // Start stream recording
        await Provider.of<CaptureProvider>(context, listen: false)
            .streamDeviceRecording(device: context.read<DeviceProvider>().connectedDevice);
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

  @override
  Widget build(BuildContext context) {
    return MyUpgradeAlert(
      upgrader: _upgrader,
      dialogStyle: Platform.isIOS ? UpgradeDialogStyle.cupertino : UpgradeDialogStyle.material,
      child: Consumer<ConnectivityProvider>(builder: (ctx, connectivityProvider, child) {
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

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: DefaultTabController(
            length: 2,
            initialIndex: SharedPreferencesUtil().pageToShowFromNotification,
            child: GestureDetector(
              onTap: () {
                primaryFocus?.unfocus();
                context.read<HomeProvider>().memoryFieldFocusNode.unfocus();
                context.read<HomeProvider>().chatFieldFocusNode.unfocus();
              },
              child: Stack(
                children: [
                  Center(
                    child: TabBarView(
                      // controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        const MemoriesPage(),
                        ChatPage(
                          key: chatPageKey,
                        ),
                      ],
                    ),
                  ),
                  Consumer<HomeProvider>(builder: (context, home, child) {
                    if (home.chatFieldFocusNode.hasFocus || home.memoryFieldFocusNode.hasFocus) {
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
                              MixpanelManager().bottomNavigationTabClicked(['Memories', 'Chat'][index]);
                              primaryFocus?.unfocus();
                              home.setIndex(index);
                            },
                            indicatorColor: Colors.transparent,
                            tabs: [
                              Tab(
                                child: Text(
                                  'Memories',
                                  style: TextStyle(
                                    color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                                    fontSize: 16,
                                  ),
                                ),
                              ),
                              Tab(
                                child: Text(
                                  'Chat',
                                  style: TextStyle(
                                    color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                                    fontSize: 16,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }
                  }),
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
                Consumer2<DeviceProvider, HomeProvider>(builder: (context, deviceProvider, home, child) {
                  bool isMemoriesPage = home.selectedIndex == 0;

                  var deviceText = "";
                  if (deviceProvider.connectedDevice != null) {
                    var deviceName = deviceProvider.connectedDevice?.name ?? SharedPreferencesUtil().deviceName;
                    // var deviceShortId = deviceProvider.connectedDevice?.getShortId() ??
                    //     SharedPreferencesUtil().btDeviceStruct.getShortId();
                    deviceText = deviceName;
                  }
                  if (deviceProvider.connectedDevice != null && deviceProvider.batteryLevel != -1) {
                    return GestureDetector(
                      onTap: deviceProvider.connectedDevice == null
                          ? null
                          : () {
                              routeToPage(
                                context,
                                const ConnectedDevice(),
                              );
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
                            crossAxisAlignment: CrossAxisAlignment.center,
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
                              isMemoriesPage
                                  ? Text(
                                      deviceText,
                                      style: const TextStyle(color: Colors.white, fontSize: 14),
                                    )
                                  : const SizedBox.shrink(),
                              isMemoriesPage ? const SizedBox(width: 8) : const SizedBox.shrink(),
                              Text(
                                '${deviceProvider.batteryLevel.toString()}%',
                                style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                              ),
                            ],
                          )),
                    );
                  } else {
                    return GestureDetector(
                      onTap: () async {
                        if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                          routeToPage(context, const ConnectDevicePage());
                          MixpanelManager().connectFriendClicked();
                        } else {
                          await routeToPage(context, const ConnectedDevice());
                        }
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        // backgroundColor: Colors.transparent,
                        decoration: BoxDecoration(
                          color: Colors.transparent,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: Colors.grey, width: 1),
                        ),
                        child: Row(
                          children: [
                            Image.asset('assets/images/logo_transparent.png', width: 25, height: 25),
                            isMemoriesPage ? const SizedBox(width: 8) : const SizedBox.shrink(),
                            deviceProvider.isConnecting && isMemoriesPage
                                ? Text(
                                    "Connecting",
                                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                                  )
                                : isMemoriesPage
                                    ? Text(
                                        "No device found",
                                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                                      )
                                    : const SizedBox.shrink(),
                          ],
                        ),
                      ),
                    );
                  }
                }),
                Consumer2<PluginProvider, HomeProvider>(
                  builder: (context, provider, home, child) {
                    if (home.selectedIndex != 1) {
                      return const SizedBox(
                        width: 16,
                      );
                    }
                    return Padding(
                      padding: const EdgeInsets.only(left: 0),
                      child: provider.plugins.where((p) => p.enabled).isEmpty
                          ? GestureDetector(
                              onTap: () {
                                MixpanelManager().pageOpened('Chat Plugins');
                                routeToPage(context, const PluginsPage(filterChatOnly: true));
                              },
                              child: const Row(
                                children: [
                                  Icon(size: 20, Icons.chat, color: Colors.white),
                                  SizedBox(width: 10),
                                  Text(
                                    'Enable Plugins',
                                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                                  ),
                                ],
                              ),
                            )
                          : Container(
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              child: DropdownButton<String>(
                                menuMaxHeight: 350,
                                value: provider.selectedChatPluginId,
                                onChanged: (s) async {
                                  if ((s == 'no_selected' && provider.plugins.where((p) => p.enabled).isEmpty) ||
                                      s == 'enable') {
                                    routeToPage(context, const PluginsPage(filterChatOnly: true));
                                    MixpanelManager().pageOpened('Chat Plugins');
                                    return;
                                  }
                                  if (s == null || s == provider.selectedChatPluginId) return;
                                  provider.setSelectedChatPluginId(s);
                                  var plugin = provider.getSelectedPlugin();
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
        );
      }),
    );
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
                CachedNetworkImage(
                  imageUrl: plugin.getImageUrl(),
                  imageBuilder: (context, imageProvider) {
                    return CircleAvatar(
                      backgroundColor: Colors.white,
                      radius: 12,
                      backgroundImage: imageProvider,
                    );
                  },
                  errorWidget: (context, url, error) {
                    return const CircleAvatar(
                      backgroundColor: Colors.white,
                      radius: 12,
                      child: Icon(Icons.error_outline_rounded),
                    );
                  },
                  progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                    backgroundColor: Colors.white,
                    radius: 12,
                    child: CircularProgressIndicator(
                      value: progress.progress,
                      valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  ),
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
    ForegroundUtil.stopForegroundTask();
    super.dispose();
  }
}
