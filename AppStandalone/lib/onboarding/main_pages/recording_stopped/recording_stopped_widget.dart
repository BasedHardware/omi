import '/auth/firebase_auth/auth_util.dart';
import '/backend/backend.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/instant_timer.dart';
import '/onboarding/main_pages/started_recording/started_recording_widget.dart';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/permissions_util.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'recording_stopped_model.dart';
export 'recording_stopped_model.dart';

class RecordingStoppedWidget extends StatefulWidget {
  const RecordingStoppedWidget({super.key});

  @override
  State<RecordingStoppedWidget> createState() => _RecordingStoppedWidgetState();
}

class _RecordingStoppedWidgetState extends State<RecordingStoppedWidget>
    with TickerProviderStateMixin {
  late RecordingStoppedModel _model;

  final animationsMap = {
    'buttonOnPageLoadAnimation': AnimationInfo(
      trigger: AnimationTrigger.onPageLoad,
      effects: [
        ShimmerEffect(
          curve: Curves.easeInOut,
          delay: 2000.ms,
          duration: 1580.ms,
          color: const Color(0x80FFFFFF),
          angle: 0.524,
        ),
      ],
    ),
  };

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => RecordingStoppedModel());

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.maybeDispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();

    return Align(
      alignment: const AlignmentDirectional(0.0, 0.0),
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
        child: Container(
          width: double.infinity,
          constraints: const BoxConstraints(
            maxWidth: 530.0,
          ),
          decoration: BoxDecoration(
            color: FlutterFlowTheme.of(context).primary,
            boxShadow: const [
              BoxShadow(
                blurRadius: 3.0,
                color: Color(0x33000000),
                offset: Offset(0.0, 1.0),
              )
            ],
            borderRadius: BorderRadius.circular(24.0),
            border: Border.all(
              color: const Color(0x00F1F4F8),
            ),
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 12.0),
            child: Column(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Align(
                  alignment: const AlignmentDirectional(1.0, -1.0),
                  child: Padding(
                    padding:
                        const EdgeInsetsDirectional.fromSTEB(0.0, 10.0, 10.0, 0.0),
                    child: InkWell(
                      splashColor: Colors.transparent,
                      focusColor: Colors.transparent,
                      hoverColor: Colors.transparent,
                      highlightColor: Colors.transparent,
                      onTap: () async {
                        logFirebaseEvent(
                            'RECORDING_STOPPED_Icon_4fdwwmpg_ON_TAP');
                        logFirebaseEvent('Icon_close_dialog,_drawer,_etc');
                        Navigator.pop(context);
                        logFirebaseEvent('Icon_action_block');
                        await _model.popupclosing(context);
                      },
                      child: Icon(
                        Icons.close,
                        color: FlutterFlowTheme.of(context).secondaryText,
                        size: 30.0,
                      ),
                    ),
                  ),
                ),
                Align(
                  alignment: const AlignmentDirectional(0.0, 0.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.max,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(
                            0.0, 12.0, 0.0, 12.0),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8.0),
                          child: Image.asset(
                            'assets/images/vector.png',
                            width: 200.0,
                            height: 80.0,
                            fit: BoxFit.contain,
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(
                            0.0, 12.0, 0.0, 12.0),
                        child: Text(
                          'Recording Stopped',
                          style: FlutterFlowTheme.of(context)
                              .bodyMedium
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .bodyMediumFamily,
                                fontSize: 20.0,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .bodyMediumFamily),
                              ),
                        ),
                      ),
                      Padding(
                        padding:
                            const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 24.0),
                        child: Text(
                          'Start the recording to add your memories.',
                          style: FlutterFlowTheme.of(context)
                              .bodyMedium
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .bodyMediumFamily,
                                fontSize: 14.0,
                                fontWeight: FontWeight.w500,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .bodyMediumFamily),
                              ),
                        ),
                      ),
                      Container(
                        decoration: const BoxDecoration(),
                      ),
                    ],
                  ),
                ),
                if (!FFAppState().isSpeechRunning)
                  Align(
                    alignment: const AlignmentDirectional(0.0, 0.0),
                    child: Builder(
                      builder: (context) => FFButtonWidget(
                        onPressed: () async {
                          logFirebaseEvent(
                              'RECORDING_STOPPED_COMP_RECORD_BTN_ON_TAP');
                          if (!FFAppState()
                              .firstIntroNotificationWasAlreadyCreated) {
                            logFirebaseEvent('Button_backend_call');

                            var memoriesRecordReference =
                                MemoriesRecord.collection.doc();
                            await memoriesRecordReference.set({
                              ...createMemoriesRecordData(
                                user: currentUserReference,
                                feedback:
                                    'Great job activating me! I\'ll passively listen to your voice and will send you feedback. Just like this! Say \"Hey Sama, <any command>\" whenever you want a question answered.',
                                toShowToUserShowHide: 'Show',
                                emptyMemory: false,
                                isUselessMemory: false,
                                structuredMemory:
                                    'Great job activating me! I\'ll passively listen to your voice and will send you  memories. Just like this!',
                              ),
                              ...mapToFirestore(
                                {
                                  'date': FieldValue.serverTimestamp(),
                                },
                              ),
                            });
                            _model.createdIntroNotifCopy =
                                MemoriesRecord.getDocumentFromData({
                              ...createMemoriesRecordData(
                                user: currentUserReference,
                                feedback:
                                    'Great job activating me! I\'ll passively listen to your voice and will send you feedback. Just like this! Say \"Hey Sama, <any command>\" whenever you want a question answered.',
                                toShowToUserShowHide: 'Show',
                                emptyMemory: false,
                                isUselessMemory: false,
                                structuredMemory:
                                    'Great job activating me! I\'ll passively listen to your voice and will send you  memories. Just like this!',
                              ),
                              ...mapToFirestore(
                                {
                                  'date': DateTime.now(),
                                },
                              ),
                            }, memoriesRecordReference);
                            logFirebaseEvent('Button_update_app_state');
                            FFAppState()
                                .firstIntroNotificationWasAlreadyCreated = true;
                          }
                          logFirebaseEvent('Button_request_permissions');
                          await requestPermission(microphonePermission);
                          logFirebaseEvent('Button_close_dialog,_drawer,_etc');
                          Navigator.pop(context);
                          logFirebaseEvent('Button_update_app_state');
                          setState(() {
                            FFAppState().lastTranscript = '';
                          });
                          logFirebaseEvent('Button_custom_action');
                          await actions.speechToTextWithChunk(
                            120,
                            () async {
                              logFirebaseEvent('_action_block');
                              await action_blocks.periodicAction(context);
                            },
                            () async {
                              logFirebaseEvent('_action_block');
                              await action_blocks.onFinishAction(context);
                            },
                            () async {},
                          );
                          logFirebaseEvent('Button_google_analytics_event');
                          logFirebaseEvent(
                            'StartButtonClick',
                            parameters: {
                              'user': currentUserEmail,
                            },
                          );
                          logFirebaseEvent('Button_request_permissions');
                          await requestPermission(notificationsPermission);
                          logFirebaseEvent('Button_update_app_state');
                          FFAppState().isSpeechRunning = true;
                          FFAppState().speechWasActivatedByUser = true;
                          FFAppState().stopAction = false;
                          FFAppState().testCountRunsOfNotifications = 0;
                          logFirebaseEvent('Button_alert_dialog');
                          await showDialog(
                            context: context,
                            builder: (dialogContext) {
                              return Dialog(
                                elevation: 0,
                                insetPadding: EdgeInsets.zero,
                                backgroundColor: Colors.transparent,
                                alignment: const AlignmentDirectional(0.0, 0.0)
                                    .resolve(Directionality.of(context)),
                                child: SizedBox(
                                  height: 500.0,
                                  width:
                                      MediaQuery.sizeOf(context).width * 0.85,
                                  child: const StartedRecordingWidget(),
                                ),
                              );
                            },
                          ).then((value) => setState(() {}));

                          logFirebaseEvent('Button_trigger_push_notification');
                          triggerPushNotification(
                            notificationTitle: 'Sama',
                            notificationText:
                                'Great job activating me! I\'ll passively listen to you and will send you my feedback, just like this! Make sure that the microphone is activated! ',
                            userRefs: [currentUserReference!],
                            initialPageName: 'chat',
                            parameterData: {
                              'test': 'test1',
                            },
                          );
                          logFirebaseEvent('Button_stop_periodic_action');
                          _model.instantTimer13?.cancel();
                          logFirebaseEvent('Button_start_periodic_action');
                          _model.instantTimer13 = InstantTimer.periodic(
                            duration: const Duration(milliseconds: 300000),
                            callback: (timer) async {
                              if (!FFAppState().isSpeechRunning &&
                                  FFAppState().speechWasActivatedByUser &&
                                  (FFAppState().testCountRunsOfNotifications <=
                                      5)) {
                                logFirebaseEvent(
                                    'Button_trigger_push_notification');
                                triggerPushNotification(
                                  notificationTitle: 'Sama',
                                  notificationText:
                                      'Recording is disabled! Please restart audio recording',
                                  userRefs: [currentUserReference!],
                                  initialPageName: 'chat',
                                  parameterData: {},
                                );
                                logFirebaseEvent('Button_update_app_state');
                                setState(() {
                                  FFAppState().testCountRunsOfNotifications =
                                      FFAppState()
                                              .testCountRunsOfNotifications +
                                          1;
                                });
                              }
                            },
                            startImmediately: true,
                          );

                          setState(() {});
                        },
                        text: 'Record',
                        icon: const Icon(
                          Icons.fiber_manual_record_rounded,
                          size: 25.0,
                        ),
                        options: FFButtonOptions(
                          height: 44.0,
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              24.0, 0.0, 24.0, 0.0),
                          iconPadding: const EdgeInsetsDirectional.fromSTEB(
                              0.0, 0.0, 0.0, 0.0),
                          color: const Color(0x1AF7F4F4),
                          textStyle: FlutterFlowTheme.of(context)
                              .titleSmall
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .titleSmallFamily,
                                color: FlutterFlowTheme.of(context).primaryText,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .titleSmallFamily),
                              ),
                          elevation: 3.0,
                          borderSide: const BorderSide(
                            width: 1.0,
                          ),
                          borderRadius: BorderRadius.circular(24.0),
                        ),
                      ).animateOnPageLoad(
                          animationsMap['buttonOnPageLoadAnimation']!),
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
