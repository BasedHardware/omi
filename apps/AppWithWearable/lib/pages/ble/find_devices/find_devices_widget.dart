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

class _FindDevicesWidgetState extends State<FindDevicesWidget> {
  late FindDevicesModel _model;

  @override
  void initState() {
    super.initState();
    _model = FindDevicesModel();
    _fetchDevices();
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
        _model.connectedDevices = _model.fetchedConnectedDevices!.toList().cast<BTDeviceStruct>();
      });
      _model.devices = await actions.ble0findDevices();
      setState(() {
        _model.connectedDevices = _model.devices!.toList().cast<BTDeviceStruct>();
        _model.isFetchingDevices = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              'finding devices....',
              style: TextStyle(
                color: FlutterFlowTheme.of(context).primary,
              ),
            ),
          duration: Duration(milliseconds: 4000),
          backgroundColor: FlutterFlowTheme.of(context).secondary,
        ),
      );
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FlutterFlowTheme.of(context).primary,
      body: Stack(
        children: [
          BlurBotWidget(),
          SafeArea(
            child: Column(
              children: [
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Image.asset(
                          'assets/images/favicon.png',
                          width: 90,
                          height: 60,
                          fit: BoxFit.fitHeight,
                        ),
                        SizedBox(height: 16),
                        Text(
                          'Find your device',
                          style: FlutterFlowTheme.of(context).displaySmall,
                        ),
                        SizedBox(height: 32),
                        FFButtonWidget(
                          onPressed: () async {
                            _model.devicesScanCopy = await actions.ble0findDevices();
                            setState(() {
                              _model.foundDevices = _model.devicesScanCopy!.toList().cast<BTDeviceStruct>();
                            });
                          },
                          text: 'Scan Devices',
                          options: FFButtonOptions(
                            height: 60,
                            padding: EdgeInsets.symmetric(horizontal: 40),
                            color: FlutterFlowTheme.of(context).secondary,
                            textStyle: FlutterFlowTheme.of(context).titleSmall.copyWith(
                                  color: FlutterFlowTheme.of(context).primary,
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                ),
                            borderSide: BorderSide(
                              color: FlutterFlowTheme.of(context).secondary,
                              width: 1,
                            ),
                            borderRadius: BorderRadius.circular(30),
                          ),
                        ),
                        SizedBox(height: 16),
                        Expanded(
                          child: ListView.separated(
                            itemCount: _model.foundDevices.length,
                            separatorBuilder: (_, __) => SizedBox(height: 16),
                            itemBuilder: (context, index) {
                              final device = _model.foundDevices[index];
                              return InkWell(
                                onTap: () {
                                  context.pushNamed(
                                    'connecting',
                                    queryParameters: {
                                      'btdevice': serializeParam(device.toMap(), ParamType.JSON),
                                    },
                                  );
                                },
                                child: Container(
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(color: FlutterFlowTheme.of(context).secondary),
                                  ),
                                  padding: EdgeInsets.all(16),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(device.name),
                                          Text(device.id),
                                        ],
                                      ),
                                      Icon(Icons.navigate_next),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
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
