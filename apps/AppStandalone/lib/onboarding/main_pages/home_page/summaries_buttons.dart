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
  final String? dailySummary;
  final String? weeklySummary;
  final String? monthlySummary;

  const HomePageSummariesButtons(
      {super.key, required this.model, this.dailySummary, this.weeklySummary, this.monthlySummary});

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
            builder: (context) => FFButtonWidget(
              onPressed: () async {
                _displayDialog(widget.dailySummary, SummaryType.daily);
              },
              text: 'Daily',
              options: FFButtonOptions(
                width: 112.0,
                height: 40.0,
                padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                color: const Color(0x1AF7F4F4),
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                      color: const Color(0xFFF7F4F4),
                      fontWeight: FontWeight.bold,
                      useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
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
            builder: (context) => FFButtonWidget(
              onPressed: () async {
                logFirebaseEvent('HOME_PAGE_PAGE_WEEKLY_BTN_ON_TAP');
                _displayDialog(widget.weeklySummary, SummaryType.weekly);
              },
              text: 'Weekly',
              options: FFButtonOptions(
                width: 112.0,
                height: 40.0,
                padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                color: const Color(0x1AF7F4F4),
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                      color: FlutterFlowTheme.of(context).primaryText,
                      fontWeight: FontWeight.bold,
                      useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
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
            builder: (context) => FFButtonWidget(
              onPressed: () async {
                logFirebaseEvent('HOME_PAGE_PAGE_MONTHLY_BTN_ON_TAP');
                _displayDialog(widget.monthlySummary, SummaryType.monthly);
              },
              text: 'Monthly',
              options: FFButtonOptions(
                width: 112.0,
                height: 40.0,
                padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                color: const Color(0x1AF7F4F4),
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                      color: FlutterFlowTheme.of(context).primaryText,
                      fontWeight: FontWeight.bold,
                      useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
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

  _displayDialog(String? summary, SummaryType type) {
    showDialog(
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
            child: SummaryWidget(
              summary: summary,
              type: type,
            ),
          ),
        );
      },
    ).then((value) => setState(() {}));
  }
}
