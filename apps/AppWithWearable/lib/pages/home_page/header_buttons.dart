import 'package:flutter/material.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:google_fonts/google_fonts.dart';

class HomePageHeaderButtons extends StatefulWidget {
  const HomePageHeaderButtons({super.key});

  @override
  State<HomePageHeaderButtons> createState() => _HomePageHeaderButtonsState();
}

class _HomePageHeaderButtonsState extends State<HomePageHeaderButtons> {
  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: const AlignmentDirectional(0.0, 0.0),
      child: Container(
        width: MediaQuery.sizeOf(context).width * 1.0,
        decoration: const BoxDecoration(),
        child: Align(
          alignment: const AlignmentDirectional(0.0, 0.0),
          child: Row(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [

              FFButtonWidget(
                onPressed: () async {
                  context.safePop();
                },
                text: '',
                icon: const Icon(
                  Icons.arrow_back_rounded,
                  size: 24.0,
                ),
                options: FFButtonOptions(
                  width: 44.0,
                  height: 44.0,
                  padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                  iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                  color: const Color(0x1AF7F4F4),
                  textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                    fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    useGoogleFonts:
                    GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                  ),
                  elevation: 3.0,
                  borderSide: const BorderSide(
                    color: Colors.transparent,
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.circular(24.0),
                ),
              ),
              const Text('Memories'),
              FFButtonWidget(
                onPressed: () async {
                  context.pushNamed('chatPage');
                },
                text: '',
                icon: const Icon(
                  Icons.chat_bubble_rounded,
                  size: 20.0,
                ),
                options: FFButtonOptions(
                  width: 44.0,
                  height: 44.0,
                  padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                  iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                  color: const Color(0x1AF7F4F4),
                  textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                        fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                      ),
                  elevation: 3.0,
                  borderSide: const BorderSide(
                    color: Colors.transparent,
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.circular(48.0),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
