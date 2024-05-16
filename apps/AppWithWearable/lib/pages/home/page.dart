import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:friend_private/pages/home/settings.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:friend_private/widgets/scanning_animation.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:google_fonts/google_fonts.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'widgets/transcript.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.btDevice,
  });

  final dynamic btDevice;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  GlobalKey<TranscriptWidgetState> childWidgetKey = GlobalKey();
  BTDeviceStruct? _device;
  bool deepgramApiIsVisible = false;
  bool openaiApiIsVisible = false;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  final _gcpCredentialsController = TextEditingController();
  final _gcpBucketNameController = TextEditingController();
  final _customWebsocketUrlController = TextEditingController();
  bool _useFriendApiKeys = true;
  bool _areApiKeysSet = false;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  String _selectedLanguage = 'en';
  final unFocusNode = FocusNode();

  StreamSubscription<BluetoothConnectionState>? connectionStateListener;
  StreamSubscription? bleBatteryLevelListener;
  int batteryLevel = -1;

  @override
  void initState() {
    super.initState();
    if (widget.btDevice != null) {
      _device = BTDeviceStruct.maybeFromMap(widget.btDevice);
      _initiateConnectionListener();
      _initiateBleBatteryListener();
    } else {
      scanAndConnectDevice().then((friendDevice) {
        if (friendDevice != null) {
          setState(() {
            _device = friendDevice;
          });
          _initiateConnectionListener();
          _initiateBleBatteryListener();
        }
      });
    }
    authenticateGCP();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      requestNotificationPermissions();
      // Check if the API keys are set
      final prefs = SharedPreferencesUtil();
      if ((prefs.deepgramApiKey.isNotEmpty && prefs.openAIApiKey.isNotEmpty) || prefs.useFriendApiKeys) {
        // If both API keys are set, initialize the page and enable the DeviceDataWidget
        setState(() {
          _areApiKeysSet = true;
        });
      } else {
        // If any of the API keys are not set, show the settings bottom sheet
        _showSettingsBottomSheet();
      }
    });
  }

  _initiateBleBatteryListener() async {
    if (bleBatteryLevelListener != null) return;
    bleBatteryLevelListener = await getBleBatteryLevelListener(_device!, onBatteryLevelChange: (int value) {
      setState(() {
        batteryLevel = value;
      });
    });
  }

  _initiateConnectionListener() async {
    connectionStateListener = getConnectionStateListener(_device!.id, () {
      // when bluetooth disconnected we don't want to reset the BLE connection as there's no point, no device connected
      // we don't want either way to trigger the websocket closed event, because it's closed on purpose
      // and we don't want to retry the websocket connection or something
      childWidgetKey.currentState?.resetState(resetBLEConnection: false);
      setState(() {
        _device = null;
      });
      bleBatteryLevelListener?.cancel();
      bleBatteryLevelListener = null;
      // Sentry.captureMessage('Friend Device Disconnected', level: SentryLevel.warning);
      createNotification(title: 'Friend Device Disconnected', body: 'Please reconnect to continue using your Friend.');
      scanAndConnectDevice().then((friendDevice) {
        if (friendDevice != null) {
          setState(() {
            _device = friendDevice;
          });
          clearNotification(1);
          _initiateBleBatteryListener();
        }
      });
    }, () {
      childWidgetKey.currentState?.resetState(resetBLEConnection: true);
    });
  }

  @override
  void dispose() {
    _deepgramApiKeyController.dispose();
    _openaiApiKeyController.dispose();
    _gcpCredentialsController.dispose();
    _gcpBucketNameController.dispose();
    _customWebsocketUrlController.dispose();
    unFocusNode.dispose();
    connectionStateListener?.cancel();
    bleBatteryLevelListener?.cancel();
    super.dispose();
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
            canPop: _areApiKeysSet,
            child: StatefulBuilder(
              builder: (context, StateSetter setModalState) {
                return SettingsBottomSheet(
                  areApiKeysSet: _areApiKeysSet,
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
    prefs.deepgramApiKey = _deepgramApiKeyController.text.trim();
    prefs.gcpCredentials = _gcpCredentialsController.text.trim();
    prefs.gcpBucketName = _gcpBucketNameController.text.trim();
    prefs.useFriendApiKeys = _useFriendApiKeys;
    prefs.recordingsLanguage = _selectedLanguage;
    prefs.customWebsocketUrl = _customWebsocketUrlController.text.trim();

    bool requiresReset = false;
    if (_selectedLanguage != prefs.getString('recordingsLanguage')) {
      requiresReset = true;
    }
    if (_deepgramApiKeyController.text != prefs.getString('deepgramApiKey')) {
      requiresReset = true;
    }
    if (_customWebsocketUrlController.text != prefs.getString('customWebsocketUrl')) {
      requiresReset = true;
    }
    if (requiresReset) childWidgetKey.currentState?.resetState();

    if (_gcpCredentialsController.text.isNotEmpty && _gcpBucketNameController.text.isNotEmpty) {
      authenticateGCP();
    }
    setState(() {
      _areApiKeysSet = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => unFocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(unFocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        appBar: _getAppBar(),
        body: Stack(
          children: [
            const BlurBotWidget(),
            ListView(children: [
              ..._getConnectedDeviceWidgets(),
              _areApiKeysSet && _device != null
                  ? TranscriptWidget(
                      btDevice: _device!,
                      key: childWidgetKey,
                    )
                  : const SizedBox.shrink(),
            ]),
          ],
        ),
      ),
    );
  }

  _getAppBar() {
    return AppBar(
      backgroundColor: FlutterFlowTheme.of(context).primary,
      automaticallyImplyLeading: false,
      title: FFButtonWidget(
        onPressed: () async {
          context.pushNamed('memoriesPage');
        },
        text: 'Memories ↗',
        options: FFButtonOptions(
          padding: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 0.0),
          iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
          color: FlutterFlowTheme.of(context).primary,
          textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                color: const Color(0xFFF7F4F4),
                fontSize: 18.0,
                fontWeight: FontWeight.bold,
                useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
              ),
          elevation: 0.0,
          borderSide: const BorderSide(
            color: Colors.transparent,
            width: 0.0,
          ),
          borderRadius: BorderRadius.circular(24.0),
        ),
      ),
      actions: [
        IconButton(
          icon: const Icon(
            Icons.settings,
            color: Colors.white,
            size: 30,
          ),
          onPressed: _showSettingsBottomSheet,
        ),
      ],
      centerTitle: false,
      elevation: 2.0,
    );
  }

  _getConnectedDeviceWidgets() {
    if (_device == null) {
      return [
        const SizedBox(height: 64),
        const ScanningAnimation(),
        const ScanningUI(
          string1: 'Looking for Friend wearable',
          string2: 'Locating your Friend device. Keep it near your phone for pairing',
        ),
      ];
    }
    return [
      const SizedBox(height: 64),
      const Center(
          child: ScanningAnimation(
        sizeMultiplier: 0.4,
      )),
      const SizedBox(height: 16),
      Center(
          child: Text(
        'Connected Device',
        style: FlutterFlowTheme.of(context).bodyMedium.override(
              fontFamily: 'SF Pro Display',
              color: Colors.white,
              fontSize: 29.0,
              letterSpacing: 0.0,
              fontWeight: FontWeight.w700,
              useGoogleFonts: GoogleFonts.asMap().containsKey('SF Pro Display'),
              lineHeight: 1.2,
            ),
        textAlign: TextAlign.center,
      )),
      const SizedBox(height: 8),
      Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            '${_device?.name ?? 'Friend'} ~ ${_device?.id.split('-').last.substring(0, 6)}',
            style: const TextStyle(
              color: Color.fromARGB(255, 255, 255, 255),
              fontSize: 16.0,
              fontWeight: FontWeight.w500,
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
          batteryLevel == -1 ? const SizedBox.shrink() : const SizedBox(width: 16.0),
          batteryLevel == -1
              ? const SizedBox.shrink()
              : Container(
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(30),
                    border: Border.all(
                      color: Colors.white,
                      width: 1,
                    ),
                  ),
                  padding: const EdgeInsets.all(8.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${batteryLevel.toString()}%',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(width: 8.0),
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
                    ],
                  ),
                )
        ],
      ),
      const SizedBox(height: 64),
    ];
  }
}
