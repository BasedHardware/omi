import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sama/flutter_flow/flutter_flow_theme.dart';
import 'package:sama/flutter_flow/flutter_flow_util.dart';
import 'package:sama/flutter_flow/flutter_flow_widgets.dart';

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
                  logFirebaseEvent('HOME_PAGE_PAGE__BTN_ON_TAP');
                  logFirebaseEvent('Button_launch_u_r_l');
                  await launchURL('https://discord.gg/EPDPMZgBgf');
                },
                text: '',
                icon: const Icon(
                  Icons.discord_sharp,
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
                        useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                      ),
                  elevation: 3.0,
                  borderSide: const BorderSide(
                    color: Colors.transparent,
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.circular(24.0),
                ),
              ),
              InkWell(
                splashColor: Colors.transparent,
                focusColor: Colors.transparent,
                hoverColor: Colors.transparent,
                highlightColor: Colors.transparent,
                onLongPress: () async {
                  context.pushNamed('testNew');
                },
                child: FFButtonWidget(
                  onPressed: () async {
                    context.pushNamed('chat');
                  },
                  text: 'Chat ↗',
                  options: FFButtonOptions(
                    width: MediaQuery.sizeOf(context).width * 0.25,
                    height: 44.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 0.0),
                    iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: FlutterFlowTheme.of(context).primary,
                    textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                          fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                          color: const Color(0xFFF7F4F4),
                          fontSize: 16.0,
                          fontWeight: FontWeight.bold,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                        ),
                    elevation: 0.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 0.0,
                    ),
                    borderRadius: BorderRadius.circular(24.0),
                  ),
                ),
              ),
              FFButtonWidget(
                onPressed: () async {
                  context.pushNamed('settingsPage');
                },
                text: '',
                icon: const Icon(
                  Icons.settings_sharp,
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
