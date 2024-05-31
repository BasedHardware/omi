import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/device/page.dart';
import 'package:friend_private/pages/device/widgets/transcript.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

class HomePageWrapper extends StatefulWidget {
  final dynamic btDevice;

  const HomePageWrapper({super.key, this.btDevice});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> with WidgetsBindingObserver {
  GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey = GlobalKey();
  int _selectedIndex = 1;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox()];
  List<MemoryRecord> memories = [];

  _initiateMemories() async {
    memories = await MemoryStorage.getAllMemories();
    setState(() {});
  }

  void _onItemTapped(int index) {
    MixpanelManager().bottomNavigationTabClicked(['Memories', 'Device', 'Chat'][index]);
    setState(() {
      _selectedIndex = index;
    });
  }

  StreamSubscription<OnConnectionStateChangedEvent>? _connectionStateListener;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  BTDeviceStruct? _device;

  // ForegroundUtil foreground = ForegroundUtil();
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

  @override
  void initState() {
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      requestNotificationPermissions();
    });

    _initiateMemories();
    authenticateGCP();

    if (widget.btDevice != null) {
      // Only used when onboarding flow
      _device = BTDeviceStruct.maybeFromMap(widget.btDevice);
      _initiateConnectionListener();
      _initiateBleBatteryListener();
    } else {
      // default flow
      scanAndConnectDevice().then(_onConnected);
    }
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
          createNotification(
              title: 'Friend Device Disconnected', body: 'Please reconnect to continue using your Friend.');
          MixpanelManager().deviceDisconnected();
        },
        onConnected: ((d) => _onConnected(d, initiateConnectionListener: false)));
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
  }

  _initiateBleBatteryListener() async {
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await getBleBatteryLevelListener(_device!, onBatteryLevelChange: (int value) {
      setState(() {
        batteryLevel = value;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: IndexedStack(
          index: _selectedIndex,
          children: [
            MemoriesPage(
              memories: memories,
              refreshMemories: _initiateMemories,
            ),
            DevicePage(
              device: _device,
              refreshMemories: _initiateMemories,
              transcriptChildWidgetKey: transcriptChildWidgetKey,
              batteryLevel: batteryLevel,
            ),
            const ChatPage(),
          ],
        ),
      ),
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        title: Text(['Memories', 'Device', 'Chat'][_selectedIndex]),
        elevation: 2.0,
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(
              Icons.settings,
              color: Colors.white,
              size: 30,
            ),
            onPressed: () async {
              MixpanelManager().settingsOpened();
              var language = SharedPreferencesUtil().recordingsLanguage;
              var deepgram = SharedPreferencesUtil().deepgramApiKey;
              var useFriendApiKeys = SharedPreferencesUtil().useFriendApiKeys;

              await context.pushNamed('settings');

              if (language != SharedPreferencesUtil().recordingsLanguage ||
                  deepgram != SharedPreferencesUtil().deepgramApiKey ||
                  useFriendApiKeys != SharedPreferencesUtil().useFriendApiKeys) {
                transcriptChildWidgetKey.currentState?.resetState();
              }
            },
          )
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        elevation: 0,
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: Icon(Icons.history),
            label: 'Memories',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.bluetooth_connected),
            label: 'Device',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.chat),
            label: 'Chat',
          ),
        ],
        currentIndex: _selectedIndex,
        selectedItemColor: Colors.white,
        unselectedItemColor: Colors.grey.shade700,
        onTap: _onItemTapped,
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectionStateListener?.cancel();
    _bleBatteryLevelListener?.cancel();
    super.dispose();
  }
}
