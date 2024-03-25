import '/components/logo/logo_main/logo_main_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'welcome_model.dart';
export 'welcome_model.dart';

class WelcomeWidget extends StatefulWidget {
  const WelcomeWidget({super.key});

  @override
  State<WelcomeWidget> createState() => _WelcomeWidgetState();
}

class _WelcomeWidgetState extends State<WelcomeWidget> {
  late WelcomeModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => WelcomeModel());

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'welcome'});
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
        body: SafeArea(
          top: true,
          child: Stack(
            children: [
              wrapWithModel(
                model: _model.blurBotModel,
                updateCallback: () => setState(() {}),
                child: BlurBotWidget(),
              ),
              Align(
                alignment: AlignmentDirectional(0.0, 1.0),
                child: Column(
                  mainAxisSize: MainAxisSize.max,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Align(
                      alignment: AlignmentDirectional(0.0, 0.0),
                      child: wrapWithModel(
                        model: _model.logoMainModel,
                        updateCallback: () => setState(() {}),
                        child: LogoMainWidget(),
                      ),
                    ),
                    Padding(
                      padding:
                          EdgeInsetsDirectional.fromSTEB(0.0, 20.0, 0.0, 0.0),
                      child: Text(
                        'Lumina',
                        style: FlutterFlowTheme.of(context).bodyMedium.override(
                              fontFamily: 'SF Pro Display',
                              fontSize: 24.0,
                              fontWeight: FontWeight.bold,
                              useGoogleFonts: GoogleFonts.asMap()
                                  .containsKey('SF Pro Display'),
                            ),
                      ),
                    ),
                    Padding(
                      padding: EdgeInsets.all(40.0),
                      child: Text(
                        'The AI companion that helps you remember everything.',
                        textAlign: TextAlign.center,
                        style: FlutterFlowTheme.of(context).bodyMedium.override(
                              fontFamily: 'SF Pro Display',
                              color: Color(0xCCF7F4F4),
                              fontSize: 20.0,
                              fontWeight: FontWeight.w500,
                              useGoogleFonts: GoogleFonts.asMap()
                                  .containsKey('SF Pro Display'),
                              lineHeight: 1.5,
                            ),
                      ),
                    ),
                    Padding(
                      padding:
                          EdgeInsetsDirectional.fromSTEB(0.0, 20.0, 0.0, 20.0),
                      child: InkWell(
                        splashColor: Colors.transparent,
                        focusColor: Colors.transparent,
                        hoverColor: Colors.transparent,
                        highlightColor: Colors.transparent,
                        onDoubleTap: () async {
                          logFirebaseEvent(
                              'WELCOME_LOGIN_WITH_EMAIL_BTN_ON_DOUBLE_T');
                          logFirebaseEvent('Button_navigate_to');

                          context.pushNamed('login');
                        },
                        child: FFButtonWidget(
                          onPressed: () async {
                            logFirebaseEvent(
                                'WELCOME_PAGE_LOGIN_WITH_EMAIL_BTN_ON_TAP');
                            logFirebaseEvent('Button_navigate_to');

                            context.pushNamed('login');
                          },
                          text: 'Login with email',
                          options: FFButtonOptions(
                            height: 60.0,
                            padding: EdgeInsetsDirectional.fromSTEB(
                                40.0, 0.0, 40.0, 0.0),
                            iconPadding: EdgeInsetsDirectional.fromSTEB(
                                0.0, 0.0, 0.0, 0.0),
                            color: FlutterFlowTheme.of(context).secondary,
                            textStyle: FlutterFlowTheme.of(context)
                                .titleSmall
                                .override(
                                  fontFamily: 'SF Pro Display',
                                  color: FlutterFlowTheme.of(context).primary,
                                  fontSize: 20.0,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey('SF Pro Display'),
                                ),
                            elevation: 3.0,
                            borderSide: BorderSide(
                              color: FlutterFlowTheme.of(context).secondary,
                              width: 1.0,
                            ),
                            borderRadius: BorderRadius.circular(30.0),
                          ),
                        ),
                      ),
                    ),
                    Padding(
                      padding:
                          EdgeInsetsDirectional.fromSTEB(40.0, 20.0, 40.0, 4.0),
                      child: InkWell(
                        splashColor: Colors.transparent,
                        focusColor: Colors.transparent,
                        hoverColor: Colors.transparent,
                        highlightColor: Colors.transparent,
                        onTap: () async {
                          logFirebaseEvent('WELCOME_PAGE_Text_wr8spryx_ON_TAP');
                          logFirebaseEvent('Text_launch_u_r_l');
                          await launchURL(
                              'https://samaprivacypolicy.notion.site/samaprivacypolicy/Sama-AI-Privacy-Policy-bfbbee90f18d4b8b9a0111d2d62cca54');
                        },
                        child: Text(
                          'By clicking continue, I agree to the Privacy Policy.',
                          textAlign: TextAlign.center,
                          style:
                              FlutterFlowTheme.of(context).bodyMedium.override(
                                    fontFamily: 'SF Pro Display',
                                    fontSize: 12.0,
                                    fontWeight: FontWeight.w500,
                                    decoration: TextDecoration.underline,
                                    useGoogleFonts: GoogleFonts.asMap()
                                        .containsKey('SF Pro Display'),
                                    lineHeight: 1.5,
                                  ),
                        ),
                      ),
                    ),
                    Padding(
                      padding:
                          EdgeInsetsDirectional.fromSTEB(40.0, 0.0, 40.0, 40.0),
                      child: InkWell(
                        splashColor: Colors.transparent,
                        focusColor: Colors.transparent,
                        hoverColor: Colors.transparent,
                        highlightColor: Colors.transparent,
                        onTap: () async {
                          logFirebaseEvent('WELCOME_PAGE_Text_wvypzkmi_ON_TAP');
                          logFirebaseEvent('Text_launch_u_r_l');
                          await launchURL(
                              'https://coda.io/d/_dNtSv1z5gNh/END-USER-LICENSE-AGREEMENT_suK7N');
                        },
                        child: Text(
                          'I also agree to the Terms of Service (EULA).',
                          textAlign: TextAlign.center,
                          style:
                              FlutterFlowTheme.of(context).bodyMedium.override(
                                    fontFamily: 'SF Pro Display',
                                    fontSize: 12.0,
                                    fontWeight: FontWeight.w500,
                                    decoration: TextDecoration.underline,
                                    useGoogleFonts: GoogleFonts.asMap()
                                        .containsKey('SF Pro Display'),
                                    lineHeight: 1.5,
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
      ),
    );
  }
}
