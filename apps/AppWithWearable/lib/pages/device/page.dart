import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
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
import 'widgets/transcript.dart';

class DevicePage extends StatefulWidget {
  final Function refreshMemories;
  final dynamic btDevice;
  final GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey;

  const DevicePage({
    super.key,
    required this.btDevice,
    required this.refreshMemories,
    required this.transcriptChildWidgetKey,
  });

  @override
  State<DevicePage> createState() => _DevicePageState();
}

class _DevicePageState extends State<DevicePage> {
  BTDeviceStruct? _device;

  final scaffoldKey = GlobalKey<ScaffoldState>();
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
      widget.transcriptChildWidgetKey.currentState?.resetState(resetBLEConnection: false);
      setState(() {
        _device = null;
      });
      bleBatteryLevelListener?.cancel();
      bleBatteryLevelListener = null;
      // Sentry.captureMessage('Friend Device Disconnected', level: SentryLevel.warning);
      // TODO: retry connecting 5 times every 10 seconds

      // SHOUDLNT reconnect be happening already?
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
      widget.transcriptChildWidgetKey.currentState?.resetState(resetBLEConnection: true);
    });
  }

  @override
  void dispose() {
    unFocusNode.dispose();
    connectionStateListener?.cancel();
    bleBatteryLevelListener?.cancel();
    super.dispose();
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
        body: Stack(
          children: [
            const BlurBotWidget(),
            ListView(children: [
              ..._getConnectedDeviceWidgets(),
              _device != null
                  ? TranscriptWidget(
                      btDevice: _device!,
                      key: widget.transcriptChildWidgetKey,
                      refreshMemories: widget.refreshMemories,
                    )
                  : const SizedBox.shrink(),
            ]),
          ],
        ),
      ),
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
