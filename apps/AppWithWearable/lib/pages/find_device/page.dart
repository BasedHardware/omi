import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/utils/scan.dart';
import 'package:friend_private/widgets/scanning_animation.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '/backend/schema/structs/index.dart';
import '/utils/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/permissions_util.dart';

class FindDevicesPage extends StatefulWidget {
  const FindDevicesPage({super.key});

  @override
  _FindDevicesPageState createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage> with SingleTickerProviderStateMixin {
  BTDeviceStruct? _friendDevice;
  String _stringStatus1 = 'Looking for Friend wearable';
  String _stringStatus2 = 'Locating your Friend device. Keep it near your phone for pairing';
  bool _isConnected = false;

  @override
  void initState() {
    super.initState();

    _fetchDevices(); // meaningless?
    // Automatically scan for devices when the screen loads
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _scanDevices();
    });
  }

  Future<void> _fetchDevices() async {
    // TODO: handle permission asking better
    if (await getPermissionStatus(bluetoothPermission)) {
      // List<BTDeviceStruct> fetchedConnectedDevices = await actions.ble0getConnectedDevices();
      // setState(() {
      //   _model.connectedDevices = fetchedConnectedDevices.toList().cast<BTDeviceStruct>();
      // });
      // _model.devices = await actions.ble0findDevices();
      // setState(() {
      //   _model.connectedDevices = _model.devices!.toList().cast<BTDeviceStruct>();
      // });
    } else {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Error'),
          content: const Text('Bluetooth off'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    }
  }

  Future<void> _scanDevices() async {
    BTDeviceStruct? friendDevice = await scanAndConnectDevice();
    if (friendDevice != null) {
      setState(() {
        _isConnected = true;
        _friendDevice = friendDevice;
        _stringStatus1 = 'Friend Wearable';
        _stringStatus2 = 'Successfully connected and ready to accelerate your journey with AI';
      });
    }
  }

  void _navigateToConnecting() async {
    if (_friendDevice == null) return;
    SharedPreferences prefs = await SharedPreferences.getInstance();
    prefs.setBool('onboardingCompleted', true);

    context.pushNamed(
      'connectDevice',
      queryParameters: {
        'btdevice': serializeParam(
          _friendDevice!.toMap(),
          ParamType.JSON,
        ),
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color.fromARGB(255, 0, 0, 0),
      body: Stack(
        children: [
          SafeArea(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 16.0),
                  child: Text(
                    'Pairing',
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: 'SF Pro Display',
                          color: Colors.white,
                          fontSize: 30.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w700,
                          useGoogleFonts: GoogleFonts.asMap().containsKey('SF Pro Display'),
                          lineHeight: 1.2,
                        ),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 16.0),
                AnimatedOpacity(
                  duration: const Duration(milliseconds: 500),
                  opacity: _isConnected ? 1.0 : 0.0,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 32.0),
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        borderRadius: BorderRadius.circular(30),
                        border: Border.all(
                          color: Colors.white,
                          width: 2,
                        ),
                      ),
                      padding: const EdgeInsets.all(8.0),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: const BoxDecoration(
                              color: Color.fromARGB(255, 0, 255, 8),
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8.0),
                          const Text(
                            'Friend Connected',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16.0),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const ScanningAnimation(),
                      const SizedBox(height: 16.0),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 30.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            ScanningUI(
                              string1: _stringStatus1,
                              string2: _stringStatus2,
                            ),
                            AnimatedOpacity(
                              duration: const Duration(milliseconds: 500),
                              opacity: _isConnected ? 1.0 : 0.0,
                              child: Padding(
                                padding: const EdgeInsets.all(16.0),
                                child: FFButtonWidget(
                                  onPressed: _navigateToConnecting,
                                  text: 'Continue',
                                  options: FFButtonOptions(
                                    height: 50,
                                    padding: const EdgeInsets.symmetric(horizontal: 30),
                                    color: FlutterFlowTheme.of(context).secondary,
                                    textStyle: FlutterFlowTheme.of(context).titleSmall.copyWith(
                                          color: FlutterFlowTheme.of(context).primary,
                                          fontSize: 24,
                                          fontWeight: FontWeight.w600,
                                        ),
                                    borderSide: BorderSide(
                                      color: FlutterFlowTheme.of(context).secondary,
                                      width: 1,
                                    ),
                                    borderRadius: BorderRadius.circular(30),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
