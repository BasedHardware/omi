import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/instant_timer.dart';
import '/pages/ble/blur/blur_widget.dart';
import '/pages/ble/device_data/device_data_widget.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'connect_device_model.dart';
export 'connect_device_model.dart';

class ConnectDeviceWidget extends StatefulWidget {
  const ConnectDeviceWidget({
    super.key,
    required this.btdevice,
  });

  final dynamic btdevice;

  @override
  State<ConnectDeviceWidget> createState() => _ConnectDeviceWidgetState();
}

class _ConnectDeviceWidgetState extends State<ConnectDeviceWidget> {
  late ConnectDeviceModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ConnectDeviceModel());

    logFirebaseEvent('screen_view',
        parameters: {'screen_name': 'connectDevice'});
    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('CONNECT_DEVICE_connectDevice_ON_INIT_STA');
      logFirebaseEvent('connectDevice_update_page_state');
      setState(() {
        _model.currentRssi = BTDeviceStruct.maybeFromMap(widget.btdevice)?.rssi;
      });
      logFirebaseEvent('connectDevice_start_periodic_action');
      _model.rssiUpdateTimer = InstantTimer.periodic(
        duration: Duration(milliseconds: 2000),
        callback: (timer) async {
          logFirebaseEvent('connectDevice_custom_action');
          _model.updatedRssi = await actions.ble0getRssi(
            BTDeviceStruct.maybeFromMap(widget.btdevice!)!,
          );
          logFirebaseEvent('connectDevice_update_page_state');
          setState(() {
            _model.currentRssi = _model.updatedRssi;
          });
        },
        startImmediately: true,
      );
    });

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _model.unfocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(_model.unfocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        body: Stack(
          children: [
            wrapWithModel(
              model: _model.blurModel,
              updateCallback: () => setState(() {}),
              child: BlurWidget(),
            ),
            Align(
              alignment: AlignmentDirectional(0.0, 0.0),
              child: Column(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.max,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(24.0),
                        child: Image.network(
                          'https://images.unsplash.com/photo-1589128777073-263566ae5e4d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w0NTYyMDF8MHwxfHNlYXJjaHwyfHxuZWNrbGFjZXxlbnwwfHx8fDE3MTEyMDQxNTF8MA&ixlib=rb-4.0.3&q=80&w=1080',
                          width: 120.0,
                          height: 120.0,
                          fit: BoxFit.cover,
                          alignment: Alignment(0.0, 1.0),
                        ),
                      ),
                      Align(
                        alignment: AlignmentDirectional(0.0, 0.0),
                        child: Text(
                          'Connected Device',
                          style: FlutterFlowTheme.of(context)
                              .headlineLarge
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .headlineLargeFamily,
                                fontSize: 24.0,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .headlineLargeFamily),
                              ),
                        ),
                      ),
                      Column(
                        mainAxisSize: MainAxisSize.max,
                        children: [
                          Align(
                            alignment: AlignmentDirectional(0.0, 0.0),
                            child: Text(
                              valueOrDefault<String>(
                                BTDeviceStruct.maybeFromMap(widget.btdevice)
                                    ?.name,
                                '-',
                              ),
                              style: FlutterFlowTheme.of(context).titleSmall,
                            ),
                          ),
                          Align(
                            alignment: AlignmentDirectional(0.0, 0.0),
                            child: Text(
                              valueOrDefault<String>(
                                BTDeviceStruct.maybeFromMap(widget.btdevice)
                                    ?.id,
                                '-',
                              ),
                              style: FlutterFlowTheme.of(context).titleSmall,
                            ),
                          ),
                        ].divide(SizedBox(height: 8.0)),
                      ),
                    ].divide(SizedBox(height: 16.0)),
                  ),
                  Expanded(
                    child: Align(
                      alignment: AlignmentDirectional(0.0, 0.0),
                      child: wrapWithModel(
                        model: _model.deviceDataModel,
                        updateCallback: () => setState(() {}),
                        updateOnChange: true,
                        child: DeviceDataWidget(
                          btdevice:
                              BTDeviceStruct.maybeFromMap(widget.btdevice!)!,
                        ),
                      ),
                    ),
                  ),
                ]
                    .divide(SizedBox(height: 32.0))
                    .addToStart(SizedBox(height: 48.0))
                    .addToEnd(SizedBox(height: 48.0)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
