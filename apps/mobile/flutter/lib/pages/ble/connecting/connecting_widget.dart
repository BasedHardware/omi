import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'connecting_model.dart';

export 'connecting_model.dart';

class ConnectingWidget extends StatefulWidget {
  const ConnectingWidget({
    super.key,
    required this.btdevice,
  });

  final dynamic btdevice;

  @override
  State<ConnectingWidget> createState() => _ConnectingWidgetState();
}

class _ConnectingWidgetState extends State<ConnectingWidget> {
  late ConnectingModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ConnectingModel());

    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      _model.hasWrite = await actions.ble0connectDevice(
        BTDeviceStruct.maybeFromMap(widget.btdevice!)!,
      );
      await Future.delayed(const Duration(milliseconds: 1000));
      while (_model.connectedFraction < 1.0) {
        setState(() {
          _model.connectedFraction = _model.connectedFraction + .01;
        });
        await Future.delayed(const Duration(milliseconds: 25));
      }

      context.pushNamed(
        'connectDevice',
        queryParameters: {
          'btdevice': serializeParam(
            widget.btdevice,
            ParamType.JSON,
          ),
        }.withoutNulls,
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
              child: BlurBotWidget(),
            ),
            Align(
              alignment: AlignmentDirectional(0.0, 0.0),
              child: Column(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Align(
                    alignment: AlignmentDirectional(0.0, 0.0),
                    child: Text(
                      formatNumber(
                        _model.connectedFraction,
                        formatType: FormatType.percent,
                      ),
                      style:
                          FlutterFlowTheme.of(context).headlineLarge.override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .headlineLargeFamily,
                                letterSpacing: 0.0,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .headlineLargeFamily),
                              ),
                    ),
                  ),
                  Align(
                    alignment: AlignmentDirectional(0.0, 0.0),
                    child: Text(
                      'Connecting',
                      style: FlutterFlowTheme.of(context).titleSmall.override(
                            fontFamily:
                                FlutterFlowTheme.of(context).titleSmallFamily,
                            letterSpacing: 0.0,
                            useGoogleFonts: GoogleFonts.asMap().containsKey(
                                FlutterFlowTheme.of(context).titleSmallFamily),
                          ),
                    ),
                  ),
                ].divide(SizedBox(height: 16.0)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
