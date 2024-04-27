import '/auth/firebase_auth/auth_util.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/instant_timer.dart';
import '/onboarding/main_pages/started_recording/started_recording_widget.dart';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;
import '/flutter_flow/permissions_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'start_stop_recording_model.dart';
export 'start_stop_recording_model.dart';

class StartStopRecordingWidget extends StatefulWidget {
  const StartStopRecordingWidget({super.key});

  @override
  State<StartStopRecordingWidget> createState() =>
      _StartStopRecordingWidgetState();
}

class _StartStopRecordingWidgetState extends State<StartStopRecordingWidget> {
  late StartStopRecordingModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => StartStopRecordingModel());

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

    return Column(
      mainAxisSize: MainAxisSize.max,
      children: [
        if (!FFAppState().isSpeechRunning)
          Builder(
            builder: (context) => FFButtonWidget(
              onPressed: () async {
                logFirebaseEvent('START_STOP_RECORDING_RECORD_BTN_ON_TAP');
                if (!FFAppState().firstIntroNotificationWasAlreadyCreated) {
                  logFirebaseEvent('Button_update_app_state');
                  setState(() {
                    FFAppState().chatHistory = functions.saveChatHistory(
                        FFAppState().chatHistory,
                        functions.convertToJSONRole('assistant',
                            'Great job activating me! I\'ll passively listen to your voice and will send you feedback. Just like this!')!)!;
                  });
                  logFirebaseEvent('Button_update_app_state');
                  FFAppState().firstIntroNotificationWasAlreadyCreated = true;
                }
                logFirebaseEvent('Button_request_permissions');
                await requestPermission(microphonePermission);
                // clear last transcript before starting
                logFirebaseEvent('Button_clearlasttranscriptbeforestarting');
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
                        width: MediaQuery.sizeOf(context).width * 0.85,
                        child: const StartedRecordingWidget(),
                      ),
                    );
                  },
                ).then((value) => setState(() {}));

                logFirebaseEvent('Button_trigger_push_notification');
                if (currentUserReference != null){
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
                }
                logFirebaseEvent('Button_stop_periodic_action');
                _model.instantTimer1?.cancel();
                logFirebaseEvent('Button_start_periodic_action');
                _model.instantTimer1 = InstantTimer.periodic(
                  duration: const Duration(milliseconds: 300000),
                  callback: (timer) async {
                    if (!FFAppState().isSpeechRunning &&
                        FFAppState().speechWasActivatedByUser &&
                        (FFAppState().testCountRunsOfNotifications <= 5)) {
                      logFirebaseEvent('Button_trigger_push_notification');
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
                            FFAppState().testCountRunsOfNotifications + 1;
                      });
                    }
                  },
                  startImmediately: true,
                );
              },
              text: 'Record',
              icon: const Icon(
                Icons.fiber_manual_record_rounded,
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
                      useGoogleFonts: GoogleFonts.asMap().containsKey(
                          FlutterFlowTheme.of(context).titleSmallFamily),
                    ),
                borderRadius: BorderRadius.circular(8.0),
              ),
            ),
          ),
        if (FFAppState().isSpeechRunning)
          FFButtonWidget(
            onPressed: () async {
              logFirebaseEvent('START_STOP_RECORDING_RECORDING_BTN_ON_TA');
              logFirebaseEvent('Button_update_app_state');
              setState(() {
                FFAppState().stopAction = true;
                FFAppState().isSpeechRunning = false;
                FFAppState().speechWasActivatedByUser = false;
              });
            },
            text: 'Recording',
            icon: const Icon(
              Icons.fiber_manual_record_rounded,
              size: 25.0,
            ),
            options: FFButtonOptions(
              height: 44.0,
              padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
              iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
              color: FlutterFlowTheme.of(context).error,
              textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                    fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                    color: FlutterFlowTheme.of(context).primaryText,
                    fontWeight: FontWeight.bold,
                    useGoogleFonts: GoogleFonts.asMap().containsKey(
                        FlutterFlowTheme.of(context).titleSmallFamily),
                  ),
              borderRadius: BorderRadius.circular(8.0),
            ),
          ),
      ],
    );
  }
}
