import '/auth/firebase_auth/auth_util.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/revenue_cat_util.dart' as revenue_cat;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'login_page_model.dart';
export 'login_page_model.dart';

class LoginPageWidget extends StatefulWidget {
  const LoginPageWidget({super.key});

  @override
  State<LoginPageWidget> createState() => _LoginPageWidgetState();
}

class _LoginPageWidgetState extends State<LoginPageWidget> {
  late LoginPageModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => LoginPageModel());

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'loginPage'});
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
          child: Align(
            alignment: const AlignmentDirectional(0.0, 1.0),
            child: Column(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Align(
                  alignment: const AlignmentDirectional(0.0, 0.0),
                  child: InkWell(
                    splashColor: Colors.transparent,
                    focusColor: Colors.transparent,
                    hoverColor: Colors.transparent,
                    highlightColor: Colors.transparent,
                    onTap: () async {
                      logFirebaseEvent('LOGIN_PAGE_PAGE_Image_b61zsgn8_ON_TAP');
                      logFirebaseEvent('Image_navigate_to');

                      context.pushNamed('Auth1');
                    },
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(8.0),
                      child: Image.asset(
                        'assets/images/vector.png',
                        width: 60.0,
                        height: 60.0,
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(0.0, 20.0, 0.0, 40.0),
                  child: Text(
                    'Comind',
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: 'SF Pro Display',
                          fontSize: 24.0,
                          fontWeight: FontWeight.w800,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey('SF Pro Display'),
                        ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(40.0),
                  child: Text(
                    'The AI companion that helps you remember everything.',
                    textAlign: TextAlign.center,
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: 'SF Pro Display',
                          fontSize: 24.0,
                          fontWeight: FontWeight.bold,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey('SF Pro Display'),
                          lineHeight: 1.5,
                        ),
                  ),
                ),
                isAndroid
                    ? Container()
                    : Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(
                            0.0, 20.0, 0.0, 20.0),
                        child: InkWell(
                          splashColor: Colors.transparent,
                          focusColor: Colors.transparent,
                          hoverColor: Colors.transparent,
                          highlightColor: Colors.transparent,
                          onDoubleTap: () async {
                            logFirebaseEvent(
                                'LOGIN_CONTINUE_WITH_APPLE_BTN_ON_DOUBLE_');
                            logFirebaseEvent('Button_navigate_to');

                            context.pushNamed('Auth1');
                          },
                          onLongPress: () async {
                            logFirebaseEvent(
                                'LOGIN_CONTINUE_WITH_APPLE_BTN_ON_LONG_PR');
                            logFirebaseEvent('Button_navigate_to');

                            context.pushNamed('chat');
                          },
                          child: FFButtonWidget(
                            onPressed: () async {
                              logFirebaseEvent(
                                  'LOGIN_CONTINUE_WITH_APPLE_BTN_ON_TAP');
                              logFirebaseEvent('Button_auth');
                              GoRouter.of(context).prepareAuthEvent();
                              final user =
                                  await authManager.signInWithApple(context);
                              if (user == null) {
                                return;
                              }
                              logFirebaseEvent('Button_revenue_cat');
                              final isEntitled = await revenue_cat.isEntitled(
                                      'Sama AI Monthly Subscription') ??
                                  false;
                              if (!isEntitled) {
                                await revenue_cat.loadOfferings();
                              }

                              if (isEntitled) {
                                logFirebaseEvent('Button_navigate_to');

                                context.pushNamedAuth(
                                    'homePage', context.mounted);
                              } else {
                                logFirebaseEvent('Button_navigate_to');

                                context.pushNamedAuth(
                                    'paymentPage', context.mounted);
                              }
                            },
                            text: 'Continue With Apple',
                            options: FFButtonOptions(
                              height: 60.0,
                              padding: const EdgeInsetsDirectional.fromSTEB(
                                  40.0, 0.0, 40.0, 0.0),
                              iconPadding: const EdgeInsetsDirectional.fromSTEB(
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
                      const EdgeInsetsDirectional.fromSTEB(40.0, 20.0, 40.0, 4.0),
                  child: InkWell(
                    splashColor: Colors.transparent,
                    focusColor: Colors.transparent,
                    hoverColor: Colors.transparent,
                    highlightColor: Colors.transparent,
                    onTap: () async {
                      logFirebaseEvent('LOGIN_PAGE_PAGE_Text_wr8spryx_ON_TAP');
                      logFirebaseEvent('Text_launch_u_r_l');
                      await launchURL(
                          'https://samaprivacypolicy.notion.site/samaprivacypolicy/Sama-AI-Privacy-Policy-bfbbee90f18d4b8b9a0111d2d62cca54');
                    },
                    child: Text(
                      'By clicking continue, I agree to the Privacy Policy.',
                      textAlign: TextAlign.center,
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
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
                      const EdgeInsetsDirectional.fromSTEB(40.0, 0.0, 40.0, 40.0),
                  child: InkWell(
                    splashColor: Colors.transparent,
                    focusColor: Colors.transparent,
                    hoverColor: Colors.transparent,
                    highlightColor: Colors.transparent,
                    onTap: () async {
                      logFirebaseEvent('LOGIN_PAGE_PAGE_Text_wvypzkmi_ON_TAP');
                      logFirebaseEvent('Text_launch_u_r_l');
                      await launchURL(
                          'https://coda.io/d/_dNtSv1z5gNh/END-USER-LICENSE-AGREEMENT_suK7N');
                    },
                    child: Text(
                      'I also agree to the Terms of Service (EULA).',
                      textAlign: TextAlign.center,
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
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
        ),
      ),
    );
  }
}
