import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/permissions_util.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'find_devices_model.dart';

export 'find_devices_model.dart';

class FindDevicesWidget extends StatefulWidget {
  const FindDevicesWidget({super.key});

  @override
  _FindDevicesWidgetState createState() => _FindDevicesWidgetState();
}

class _FindDevicesWidgetState extends State<FindDevicesWidget>
    with SingleTickerProviderStateMixin {
  late FindDevicesModel _model;
  late AnimationController _animationController;
  late Animation<double> _animation;
  BTDeviceStruct? _friendDevice;
  String _stringStatus1 = 'Looking for Friend wearable';
  String _stringStatus2 =
      'Locating your Friend device. Keep it near your phone for pairing';
  bool _isConnected = false;

  @override
  void initState() {
    super.initState();
    _model = FindDevicesModel();
    _fetchDevices();

    _animationController = AnimationController(
      vsync: this,
      duration: Duration(seconds: 5),
    );

    _animation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: Curves.fastLinearToSlowEaseIn,
      ),
    );

    _animationController.forward();

    // Automatically scan for devices when the screen loads
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _scanDevices();
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _fetchDevices() async {
    if (await getPermissionStatus(bluetoothPermission)) {
      setState(() {
        _model.isFetchingDevices = true;
        _model.isFetchingConnectedDevices = true;
      });
      _model.fetchedConnectedDevices = await actions.ble0getConnectedDevices();
      setState(() {
        _model.isFetchingConnectedDevices = false;
        _model.connectedDevices =
            _model.fetchedConnectedDevices!.toList().cast<BTDeviceStruct>();
      });
      _model.devices = await actions.ble0findDevices();
      setState(() {
        _model.connectedDevices =
            _model.devices!.toList().cast<BTDeviceStruct>();
        _model.isFetchingDevices = false;
      });
    } else {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Error'),
          content: Text('Bluetooth off'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text('OK'),
            ),
          ],
        ),
      );
    }
  }

  Future<void> _scanDevices() async {
    while (true) {
      _model.devicesScanCopy = await actions.ble0findDevices();
      setState(() {
        _model.foundDevices =
            _model.devicesScanCopy!.toList().cast<BTDeviceStruct>();
      });

      try {
        final friendDevice = _model.foundDevices.firstWhere(
          (device) => device.name == 'Friend' || device.name == 'Super',
        );

        // Connect to the device in the background
        bool hasWrite = await actions.ble0connectDevice(friendDevice);

        // Set _isConnected to true when connected
        setState(() {
          _isConnected = true;
          _friendDevice = friendDevice;
          _stringStatus1 = 'Friend Wearable';
          _stringStatus2 =
              'Successfully connected and ready to accelerate your journey with AI';
        });
        break;
      } catch (e) {
        // No matching device found, continue scanning
      }

      await Future.delayed(Duration(seconds: 2));

    }
  }

  void _navigateToConnecting() {
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
    final screenHeight = MediaQuery.of(context).size.height;
    double getGifSize(double screenHeight) {
      if (screenHeight <= 667) {
        return 200.0; // iPhone SE, iPhone 8 and earlier
      } else if (screenHeight <= 736) {
        return 250.0; // iPhone 8 Plus
      } else if (screenHeight <= 844) {
        return 300.0; // iPhone 12, iPhone 13
      } else if (screenHeight <= 896) {
        return 350.0; // iPhone XR, iPhone 11
      } else if (screenHeight <= 926) {
        return 400.0; // iPhone 12 Pro Max, iPhone 13 Pro Max
      } else {
        return 450.0; // iPhone 14 Pro Max and larger devices
      }
    }
    final gifSize = getGifSize(screenHeight);

    return Scaffold(
      backgroundColor: Color.fromARGB(255, 0, 0, 0),
      body: Stack(
        children: [
          SafeArea(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Padding(
                  padding: EdgeInsets.only(top: 16.0),
                  child: Text(
                    'Pairing',
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: 'SF Pro Display',
                          color: Colors.white,
                          fontSize: 30.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w700,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey('SF Pro Display'),
                          lineHeight: 1.2,
                        ),
                    textAlign: TextAlign.center,
                  ),
                ),
                SizedBox(height: 16.0),
                AnimatedOpacity(
                  duration: Duration(milliseconds: 500),
                  opacity: _isConnected ? 1.0 : 0.0,
                  child: Padding(
                    padding:
                        EdgeInsets.symmetric(vertical: 8.0, horizontal: 32.0),
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        borderRadius: BorderRadius.circular(30),
                        border: Border.all(
                          color: Colors.white,
                          width: 2,
                        ),
                      ),
                      padding: EdgeInsets.all(8.0),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              color: Color.fromARGB(255, 0, 255, 8),
                              shape: BoxShape.circle,
                            ),
                          ),
                          SizedBox(width: 8.0),
                          Text(
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
                SizedBox(height: 16.0),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      SizedBox(
                        width: gifSize,
                        height: gifSize,
                        child: AnimatedBuilder(
                          animation: _animation,
                          builder: (context, child) {
                            return Transform.scale(
                              scale: _animation.value,
                              child: Container(
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: Color.fromARGB(0, 89, 255, 0),
                                ),
                                child: ClipOval(
                                  child: Image.asset(
                                    'assets/images/sphere.gif',
                                    fit: BoxFit.cover,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                      SizedBox(height: 16.0),
                      Padding(
                        padding: EdgeInsets.symmetric(horizontal: 30.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Text(
                              _stringStatus1,
                              style: FlutterFlowTheme.of(context)
                                  .bodyMedium
                                  .override(
                                    fontFamily: 'SF Pro Display',
                                    color: Colors.white,
                                    fontSize: 32.0,
                                    letterSpacing: 0.0,
                                    fontWeight: FontWeight.w700,
                                    useGoogleFonts: GoogleFonts.asMap()
                                        .containsKey('SF Pro Display'),
                                    lineHeight: 1.2,
                                  ),
                              textAlign: TextAlign.center,
                            ),
                            SizedBox(height: 8.0),
                            Text(
                              _stringStatus2,
                              style: TextStyle(
                                color: Color.fromARGB(255, 255, 255, 255),
                                fontSize: 16.0,
                                fontWeight: FontWeight.w500,
                                height: 1.5,
                              ),
                              textAlign: TextAlign.center,
                            ),
                            SizedBox(height: 16.0),
                            AnimatedOpacity(
                              duration: Duration(milliseconds: 500),
                              opacity: _isConnected ? 1.0 : 0.0,
                              child: Padding(
                                padding: EdgeInsets.all(16.0),
                                child: FFButtonWidget(
                                  onPressed: _navigateToConnecting,
                                  text: 'Continue',
                                  options: FFButtonOptions(
                                    height: 50,
                                    padding:
                                        EdgeInsets.symmetric(horizontal: 30),
                                    color:
                                        FlutterFlowTheme.of(context).secondary,
                                    textStyle: FlutterFlowTheme.of(context)
                                        .titleSmall
                                        .copyWith(
                                          color: FlutterFlowTheme.of(context)
                                              .primary,
                                          fontSize: 24,
                                          fontWeight: FontWeight.w600,
                                        ),
                                    borderSide: BorderSide(
                                      color: FlutterFlowTheme.of(context)
                                          .secondary,
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