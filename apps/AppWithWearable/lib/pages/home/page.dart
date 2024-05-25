import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/device/page.dart';
import 'package:friend_private/pages/home/settings.dart';
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
  bool deepgramApiIsVisible = false;
  bool openaiApiIsVisible = false;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  final _gcpCredentialsController = TextEditingController();
  final _gcpBucketNameController = TextEditingController();
  final _customWebsocketUrlController = TextEditingController();
  bool _useFriendApiKeys = true;
  String _selectedLanguage = 'en';

  _initiateMemories() async {
    memories = await MemoryStorage.getAllMemories();
    setState(() {});
  }

  Future<void> _showSettingsBottomSheet() async {
    // Load API keys from shared preferences
    final prefs = SharedPreferencesUtil();
    _deepgramApiKeyController.text = prefs.deepgramApiKey;
    _openaiApiKeyController.text = prefs.openAIApiKey;
    _gcpCredentialsController.text = prefs.gcpCredentials;
    _gcpBucketNameController.text = prefs.gcpBucketName;
    _customWebsocketUrlController.text = SharedPreferencesUtil().customWebsocketUrl;
    _selectedLanguage = prefs.recordingsLanguage;
    _useFriendApiKeys = prefs.useFriendApiKeys;

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20.0),
          topRight: Radius.circular(20.0),
        ),
      ),
      builder: (BuildContext context) {
        return PopScope(
            canPop: true,
            child: StatefulBuilder(
              builder: (context, StateSetter setModalState) {
                return SettingsBottomSheet(
                  deepgramApiKeyController: _deepgramApiKeyController,
                  openaiApiKeyController: _openaiApiKeyController,
                  deepgramApiIsVisible: deepgramApiIsVisible,
                  openaiApiIsVisible: openaiApiIsVisible,
                  gcpCredentialsController: _gcpCredentialsController,
                  gcpBucketNameController: _gcpBucketNameController,
                  customWebsocketUrlController: _customWebsocketUrlController,
                  selectedLanguage: _selectedLanguage,
                  onLanguageSelected: (String value) {
                    setModalState(() {
                      _selectedLanguage = value;
                    });
                  },
                  useFriendAPIKeys: _useFriendApiKeys,
                  onUseFriendAPIKeysChanged: (bool? value) {
                    setModalState(() {
                      _useFriendApiKeys = value ?? true;
                    });
                  },
                  deepgramApiVisibilityCallback: () {
                    setModalState(() {
                      deepgramApiIsVisible = !deepgramApiIsVisible;
                    });
                  },
                  openaiApiVisibilityCallback: () {
                    setModalState(() {
                      openaiApiIsVisible = !openaiApiIsVisible;
                    });
                  },
                  saveSettings: _saveSettings,
                );
              },
            ));
      },
    );
  }

  void _saveSettings() async {
    final prefs = SharedPreferencesUtil();
    prefs.openAIApiKey = _openaiApiKeyController.text.trim();
    prefs.gcpCredentials = _gcpCredentialsController.text.trim();
    prefs.gcpBucketName = _gcpBucketNameController.text.trim();

    bool requiresReset = false;
    if (_selectedLanguage != prefs.recordingsLanguage) {
      prefs.recordingsLanguage = _selectedLanguage;
      requiresReset = true;
    }
    if (_deepgramApiKeyController.text != prefs.deepgramApiKey) {
      prefs.deepgramApiKey = _deepgramApiKeyController.text.trim();
      requiresReset = true;
    }
    if (_customWebsocketUrlController.text != prefs.customWebsocketUrl) {
      prefs.customWebsocketUrl = _customWebsocketUrlController.text.trim();
      requiresReset = true;
    }
    if (_useFriendApiKeys != prefs.useFriendApiKeys) {
      requiresReset = true;
      prefs.useFriendApiKeys = _useFriendApiKeys;
    }
    if (requiresReset) transcriptChildWidgetKey.currentState?.resetState();

    if (_gcpCredentialsController.text.isNotEmpty && _gcpBucketNameController.text.isNotEmpty) {
      authenticateGCP();
    }
  }

  void _onItemTapped(int index) {
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

  _initiateBleBatteryListener() async {
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await getBleBatteryLevelListener(_device!, onBatteryLevelChange: (int value) {
      setState(() {
        batteryLevel = value;
      });
    });
  }

  _initiateConnectionListener() async {
    _connectionStateListener = getConnectionStateListener(
        deviceId: _device!.id,
        onDisconnected: () {
          // when bluetooth disconnected we don't want to reset the BLE connection as there's no point, no device connected
          // we don't want either way to trigger the websocket closed event, because it's closed on purpose
          // and we don't want to retry the websocket connection or something
          transcriptChildWidgetKey.currentState?.resetState(resetBLEConnection: false);
          setState(() {
            _device = null;
          });
          InstabugLog.logWarn('Friend Device Disconnected');
          // foreground.stopForegroundTask();
          createNotification(
              title: 'Friend Device Disconnected', body: 'Please reconnect to continue using your Friend.');
        },
        onConnected: (BTDeviceStruct connectedDevice) {
          debugPrint('BLE onConnected');
          clearNotification(1);
          setState(() {
            _device = connectedDevice;
          });
          _initiateBleBatteryListener();
          transcriptChildWidgetKey.currentState?.resetState(resetBLEConnection: true, btDevice: connectedDevice);
          // foreground.startForegroundTask();
        });
  }

  @override
  void initState() {
    WidgetsBinding.instance.addObserver(this);
    _initiateMemories();
    // foreground.requestPermissionForAndroid();
    // foreground.initForegroundTask();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      requestNotificationPermissions();
    });
    if (widget.btDevice != null) {
      _device = BTDeviceStruct.maybeFromMap(widget.btDevice);
      _initiateConnectionListener();
      _initiateBleBatteryListener();
      // foreground.startForegroundTask();
    } else {
      scanAndConnectDevice().then((friendDevice) {
        if (friendDevice != null) {
          setState(() {
            _device = friendDevice;
          });
          _initiateConnectionListener();
          _initiateBleBatteryListener();
          transcriptChildWidgetKey.currentState?.resetState(resetBLEConnection: true, btDevice: friendDevice);
          // foreground.startForegroundTask();
        }
      });
    }
    authenticateGCP();
    super.initState();
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
            onPressed: _showSettingsBottomSheet,
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
    _deepgramApiKeyController.dispose();
    _openaiApiKeyController.dispose();
    _gcpCredentialsController.dispose();
    _gcpBucketNameController.dispose();
    _customWebsocketUrlController.dispose();
    _connectionStateListener?.cancel();
    _bleBatteryLevelListener?.cancel();
    super.dispose();
  }
}
