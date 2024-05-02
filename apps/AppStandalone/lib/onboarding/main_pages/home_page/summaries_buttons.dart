import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sama/backend/firebase_analytics/analytics.dart';
import 'package:sama/backend/schema/enums/enums.dart';
import 'package:sama/components/summary_widget.dart';
import 'package:sama/flutter_flow/flutter_flow_theme.dart';
import 'package:sama/flutter_flow/flutter_flow_widgets.dart';
import 'package:sama/onboarding/main_pages/home_page/home_page_model.dart';

class HomePageSummariesButtons extends StatefulWidget {
  final HomePageModel model;

  const HomePageSummariesButtons({super.key, required this.model});

  @override
  State<HomePageSummariesButtons> createState() => _HomePageSummariesButtonsState();
}

class _HomePageSummariesButtonsState extends State<HomePageSummariesButtons> {
  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: const AlignmentDirectional(0.0, 1.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          Builder(
            builder: (context) =>
                FFButtonWidget(
                  onPressed: () async {
                    logFirebaseEvent('HOME_PAGE_PAGE_DAILY_BTN_ON_TAP');
                    if (widget.model.querySummariesOnMemoryPage!
                        .where((e) => e.type == SummaryType.daily)
                        .toList()
                        .isNotEmpty) {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: SummaryWidget(
                                summary: widget.model.querySummariesOnMemoryPage
                                    ?.where((e) => e.type == SummaryType.daily)
                                    .toList()
                                    .last,
                              ),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    } else {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: const SummaryWidget(),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    }
                  },
                  text: 'Daily',
                  options: FFButtonOptions(
                    width: 112.0,
                    height: 40.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                    iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: const Color(0x1AF7F4F4),
                    textStyle: FlutterFlowTheme
                        .of(context)
                        .titleSmall
                        .override(
                      fontFamily: FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily,
                      color: const Color(0xFFF7F4F4),
                      fontWeight: FontWeight.bold,
                      useGoogleFonts:
                      GoogleFonts.asMap().containsKey(FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily),
                    ),
                    elevation: 3.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
          ),
          Builder(
            builder: (context) =>
                FFButtonWidget(
                  onPressed: () async {
                    logFirebaseEvent('HOME_PAGE_PAGE_WEEKLY_BTN_ON_TAP');
                    if (widget.model.querySummariesOnMemoryPage!
                        .where((e) => e.type == SummaryType.weekly)
                        .toList()
                        .isNotEmpty) {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: SummaryWidget(
                                summary: widget.model.querySummariesOnMemoryPage
                                    ?.where((e) => e.type == SummaryType.weekly)
                                    .toList()
                                    .last,
                              ),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    } else {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: const SummaryWidget(),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    }
                  },
                  text: 'Weekly',
                  options: FFButtonOptions(
                    width: 112.0,
                    height: 40.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                    iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: const Color(0x1AF7F4F4),
                    textStyle: FlutterFlowTheme
                        .of(context)
                        .titleSmall
                        .override(
                      fontFamily: FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily,
                      color: FlutterFlowTheme
                          .of(context)
                          .primaryText,
                      fontWeight: FontWeight.bold,
                      useGoogleFonts:
                      GoogleFonts.asMap().containsKey(FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily),
                    ),
                    elevation: 3.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
          ),
          Builder(
            builder: (context) =>
                FFButtonWidget(
                  onPressed: () async {
                    logFirebaseEvent('HOME_PAGE_PAGE_MONTHLY_BTN_ON_TAP');
                    if (widget.model.querySummariesOnMemoryPage!
                        .where((e) => e.type == SummaryType.monthly)
                        .toList()
                        .isNotEmpty) {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: SummaryWidget(
                                summary: widget.model.querySummariesOnMemoryPage
                                    ?.where((e) => e.type == SummaryType.monthly)
                                    .toList()
                                    .last,
                              ),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    } else {
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
                              onTap: () =>
                              widget.model.unfocusNode.canRequestFocus
                                  ? FocusScope.of(context).requestFocus(widget.model.unfocusNode)
                                  : FocusScope.of(context).unfocus(),
                              child: const SummaryWidget(),
                            ),
                          );
                        },
                      ).then((value) => setState(() {}));
                    }
                  },
                  text: 'Monthly',
                  options: FFButtonOptions(
                    width: 112.0,
                    height: 40.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                    iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: const Color(0x1AF7F4F4),
                    textStyle: FlutterFlowTheme
                        .of(context)
                        .titleSmall
                        .override(
                      fontFamily: FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily,
                      color: FlutterFlowTheme
                          .of(context)
                          .primaryText,
                      fontWeight: FontWeight.bold,
                      useGoogleFonts:
                      GoogleFonts.asMap().containsKey(FlutterFlowTheme
                          .of(context)
                          .titleSmallFamily),
                    ),
                    elevation: 3.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
          ),
        ],
      ),
    );
  }
}
