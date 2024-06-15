import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/page.dart';
import 'package:friend_private/pages/capture/widgets/transcript.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/pages/settings/page.dart';
import 'package:friend_private/scripts.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/dfu.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/utils/foreground.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:upgrader/upgrader.dart';

class HomePageWrapper extends StatefulWidget {
  final dynamic btDevice;

  const HomePageWrapper({super.key, this.btDevice});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();
  TabController? _controller;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox()];

  List<Memory> memories = [];

  FocusNode chatTextFieldFocusNode = FocusNode(canRequestFocus: true);
  FocusNode memoriesTextFieldFocusNode = FocusNode(canRequestFocus: true);

  GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey = GlobalKey();
  StreamSubscription<OnConnectionStateChangedEvent>? _connectionStateListener;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;

  int batteryLevel = -1;
  BTDeviceStruct? _device;

  final _upgrader = Upgrader(debugLogging: false, debugDisplayOnce: false);

  _initiateMemories() async {
    // memories = await MemoryStorage.getAllMemories(includeDiscarded: displayDiscardMemories);
    memories = (await MemoryProvider().getMemoriesOrdered(includeDiscarded: true)).reversed.toList();
    setState(() {});
    // FocusScope.of(context).unfocus();
    // chatTextFieldFocusNode.unfocus();
  }

  _setupHasSpeakerProfile() async {
    SharedPreferencesUtil().hasSpeakerProfile = await userHasSpeakerProfile(SharedPreferencesUtil().uid);
  }

  Future<void> _initiatePlugins() async {
    var plugins = await retrievePlugins();
    SharedPreferencesUtil().pluginsList = plugins;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.paused) {
      addEventToContext('App is paused');
    } else if (state == AppLifecycleState.resumed) {
      addEventToContext('App is resumed');
    } else if (state == AppLifecycleState.hidden) {
      addEventToContext('App is hidden');
    }
  }

  _migrationScripts() async {
    await migrateMemoriesCategoriesAndEmojis();
    await migrateMemoriesToObjectBox();
    _initiateMemories();
  }

  @override
  void initState() {
    _controller = TabController(length: 3, vsync: this, initialIndex: 1);
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      requestNotificationPermissions();
      foregroundUtil.requestPermissionForAndroid();
    });
    Upgrader.clearSavedSettings();

    _initiateMemories();
    _initiatePlugins();
    _setupHasSpeakerProfile();
    _migrationScripts();
    authenticateGCP();
    scanAndConnectDevice().then(_onConnected);
    super.initState();
  }

  _initiateConnectionListener() async {
    if (_connectionStateListener != null) return;
    _connectionStateListener = getConnectionStateListener(
        deviceId: _device!.id,
        onDisconnected: () {
          transcriptChildWidgetKey.currentState?.resetState(restartBytesProcessing: false);
          setState(() {
            _device = null;
          });
          InstabugLog.logWarn('Friend Device Disconnected');
          if (SharedPreferencesUtil().reconnectNotificationIsChecked) {
            createNotification(
                title: 'Friend Device Disconnected', body: 'Please reconnect to continue using your Friend.');
          }
          MixpanelManager().deviceDisconnected();
          foregroundUtil.stopForegroundTask();
        },
        onConnected: ((d) => _onConnected(d, initiateConnectionListener: false)));
  }

  _startForeground() async {
    if (!Platform.isAndroid) return;
    await foregroundUtil.initForegroundTask();
    var result = await foregroundUtil.startForegroundTask();
    debugPrint('_startForeground: $result');
  }

  _onConnected(BTDeviceStruct? connectedDevice, {bool initiateConnectionListener = true}) {
    if (connectedDevice == null) return;
    clearNotification(1);
    setState(() {
      _device = connectedDevice;
    });
    if (initiateConnectionListener) _initiateConnectionListener();
    _initiateBleBatteryListener();
    transcriptChildWidgetKey.currentState?.resetState(restartBytesProcessing: true, btDevice: connectedDevice);
    MixpanelManager().deviceConnected();
    SharedPreferencesUtil().deviceId = _device!.id;
    _startForeground();
  }

  _initiateBleBatteryListener() async {
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await getBleBatteryLevelListener(_device!, onBatteryLevelChange: (int value) {
      setState(() {
        batteryLevel = value;
      });
    });
  }

  _tabChange(int index) {
    MixpanelManager().bottomNavigationTabClicked(['Memories', 'Device', 'Chat'][index]);
    FocusScope.of(context).unfocus();
    setState(() {
      _controller!.index = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return WithForegroundTask(
        child: UpgradeAlert(
      upgrader: _upgrader,
      cupertinoButtonTextStyle: const TextStyle(color: Colors.white),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.surface,
        body: GestureDetector(
          onTap: () {
            FocusScope.of(context).unfocus();
            chatTextFieldFocusNode.unfocus();
            memoriesTextFieldFocusNode.unfocus();
          },
          child: Stack(
            children: [
              Center(
                child: TabBarView(
                  controller: _controller,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    MemoriesPage(
                        memories: memories,
                        refreshMemories: _initiateMemories,
                        textFieldFocusNode: memoriesTextFieldFocusNode),
                    CapturePage(
                      device: _device,
                      refreshMemories: _initiateMemories,
                      transcriptChildWidgetKey: transcriptChildWidgetKey,
                      // batteryLevel: batteryLevel,
                    ),
                    ChatPage(
                      textFieldFocusNode: chatTextFieldFocusNode,
                      memories: memories,
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
                              child: Text('Memories',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      color: _controller!.index == 0 ? Colors.white : Colors.grey, fontSize: 16)),
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
                              child: Text('Capture',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      color: _controller!.index == 1 ? Colors.white : Colors.grey, fontSize: 16)),
                            ),
                          ),
                        ),
                        Expanded(
                          child: MaterialButton(
                            onPressed: () => _tabChange(2),
                            child: Padding(
                              padding: const EdgeInsets.only(top: 20, bottom: 20),
                              child: Text('Chat',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      color: _controller!.index == 2 ? Colors.white : Colors.grey, fontSize: 16)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                )
            ],
          ),
        ),
        appBar: AppBar(
          automaticallyImplyLeading: false,
          backgroundColor: Theme.of(context).colorScheme.surface,
          title: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
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
                        color: batteryLevel > 75
                            ? const Color.fromARGB(255, 0, 255, 8)
                            : batteryLevel > 20
                                ? Colors.yellow.shade700
                                : Colors.red,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8.0),
                    Text(
                      '${batteryLevel.toString()}%',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
              // Text(['Memories', 'Device', 'Chat'][_selectedIndex]),
              IconButton(
                // TODO: Show the button only if a device is connected
                // and there's a new firmware available
                icon: const Icon(
                  Icons.download,
                  color: Colors.white,
                  size: 30,
                ),
                onPressed: () async {
                  if (_device != null) {
                    MixpanelManager().firmwareUpdateButtonClick();
                    await startDfu(_device!, '');
                  }
                },
              ),
              IconButton(
                icon: const Icon(
                  Icons.settings,
                  color: Colors.white,
                  size: 30,
                ),
                onPressed: () async {
                  MixpanelManager().settingsOpened();
                  var language = SharedPreferencesUtil().recordingsLanguage;
                  var useFriendApiKeys = SharedPreferencesUtil().useFriendApiKeys;
                  Navigator.of(context).push(MaterialPageRoute(builder: (c) => const SettingsPage()));
                  if (language != SharedPreferencesUtil().recordingsLanguage ||
                      useFriendApiKeys != SharedPreferencesUtil().useFriendApiKeys) {
                    transcriptChildWidgetKey.currentState?.resetState();
                  }
                },
              )
            ],
          ),
          elevation: 0,
          centerTitle: true,
        ),
      ),
    ));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectionStateListener?.cancel();
    _bleBatteryLevelListener?.cancel();
    _controller?.dispose();
    super.dispose();
  }
}
