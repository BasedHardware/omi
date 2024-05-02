import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sama/backend/firebase_analytics/analytics.dart';
import 'package:sama/components/start_stop_recording_widget.dart';
import 'package:sama/flutter_flow/flutter_flow_theme.dart';
import 'package:sama/flutter_flow/flutter_flow_widgets.dart';
import 'package:sama/onboarding/main_pages/edit_memory/edit_memory_widget.dart';
import 'package:sama/onboarding/main_pages/home_page/home_page_model.dart';
import '/flutter_flow/flutter_flow_util.dart';

class HomePageBottomButtons extends StatefulWidget {
  final HomePageModel model;

  const HomePageBottomButtons({super.key, required this.model});

  @override
  State<HomePageBottomButtons> createState() => _HomePageBottomButtonsState();
}

class _HomePageBottomButtonsState extends State<HomePageBottomButtons> {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 10.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Align(
            alignment: const AlignmentDirectional(0.0, -1.0),
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 24.0, 0.0),
              child: wrapWithModel(
                model: widget.model.startStopRecordingModel,
                updateCallback: () => setState(() {}),
                child: const StartStopRecordingWidget(),
              ),
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.max,
            children: [
              Align(
                alignment: const AlignmentDirectional(0.0, -1.0),
                child: Builder(
                  builder: (context) => FFButtonWidget(
                    onPressed: () async {
                      logFirebaseEvent('HOME_PAGE_PAGE_ADD_BTN_ON_TAP');
                      logFirebaseEvent('Button_alert_dialog');
                      await showDialog(
                        context: context,
                        builder: (dialogContext) {
                          return Dialog(
                            elevation: 0,
                            insetPadding: EdgeInsets.zero,
                            backgroundColor: Colors.transparent,
                            alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                            child: GestureDetector(
                              onTap: () => widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: const EditMemoryWidget(),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    },
                    text: 'Add',
                    icon: const Icon(
                      Icons.add_box,
                      size: 25.0,
                    ),
                    options: FFButtonOptions(
                      height: 44.0,
                      padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                      iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                      color: const Color(0x1AF7F4F4),
                      textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                            fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                            color: FlutterFlowTheme.of(context).primaryText,
                            fontWeight: FontWeight.bold,
                            useGoogleFonts:
                                GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                          ),
                      borderRadius: BorderRadius.circular(8.0),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
