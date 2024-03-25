import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/ble/blur/blur_widget.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
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

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'connecting'});
    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('CONNECTING_PAGE_connecting_ON_INIT_STATE');
      logFirebaseEvent('connecting_custom_action');
      _model.hasWrite = await actions.ble0connectDevice(
        BTDeviceStruct.maybeFromMap(widget.btdevice!)!,
      );
      logFirebaseEvent('connecting_wait__delay');
      await Future.delayed(const Duration(milliseconds: 1000));
      while (_model.connectedFraction < 1.0) {
        logFirebaseEvent('connecting_update_page_state');
        setState(() {
          _model.connectedFraction = _model.connectedFraction + .01;
        });
        logFirebaseEvent('connecting_wait__delay');
        await Future.delayed(const Duration(milliseconds: 25));
      }
      logFirebaseEvent('connecting_navigate_to');

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
              child: BlurWidget(),
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
                      style: FlutterFlowTheme.of(context).headlineLarge,
                    ),
                  ),
                  Align(
                    alignment: AlignmentDirectional(0.0, 0.0),
                    child: Text(
                      'Connecting',
                      style: FlutterFlowTheme.of(context).titleSmall,
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
