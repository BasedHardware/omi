import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/backend/schema/enums/enums.dart';
import '/components/confirm_deletion_widget.dart';
import '/components/empty_memories_widget.dart';
import '/components/start_stop_recording_widget.dart';
import '/components/summary_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/instant_timer.dart';
import '/onboarding/main_pages/edit_memory/edit_memory_widget.dart';
import '/onboarding/main_pages/recording_stopped/recording_stopped_widget.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'home_page_model.dart';
export 'home_page_model.dart';

class HomePageWidget extends StatefulWidget {
  const HomePageWidget({super.key});

  @override
  State<HomePageWidget> createState() => _HomePageWidgetState();
}

class _HomePageWidgetState extends State<HomePageWidget> {
  late HomePageModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => HomePageModel());

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'homePage'});
    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('HOME_PAGE_PAGE_homePage_ON_INIT_STATE');
      logFirebaseEvent('homePage_firestore_query');
      _model.querySummariesOnMemoryPage = await querySummariesRecordOnce(
        queryBuilder: (summariesRecord) => summariesRecord
            .where(
              'user',
              isEqualTo: currentUserReference,
            )
            .orderBy('date', descending: true),
      );
      logFirebaseEvent('homePage_firestore_query');
      _model.monthlyMemoriesQuery = await queryMemoriesRecordOnce(
        queryBuilder: (memoriesRecord) => memoriesRecord
            .where(
              'user',
              isEqualTo: currentUserReference,
            )
            .where(
              'date',
              isGreaterThanOrEqualTo: functions.sinceLastMonth(),
            ),
      );
      if (((currentUserDocument?.lastMonthlySummaryShown == null) ||
              (currentUserDocument!.lastMonthlySummaryShown! <=
                  functions.sinceLastMonth()!)) &&
          (_model.monthlyMemoriesQuery != null &&
              (_model.monthlyMemoriesQuery)!.isNotEmpty) &&
          (_model.monthlyMemoriesQuery!.length > 100)) {
        logFirebaseEvent('homePage_backend_call');
        _model.monthlySummary = await SummariesCall.call(
          structuredMemories:
              functions.documentsToText(_model.monthlyMemoriesQuery!.toList()),
        );
        if ((_model.weeklySummary?.succeeded ?? true)) {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference1 = SummariesRecord.collection.doc();
          await summariesRecordReference1.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.monthly,
              summary: SummariesCall.responsegpt(
                (_model.monthlySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': FieldValue.serverTimestamp(),
              },
            ),
          });
          _model.monthlysummaryCreated = SummariesRecord.getDocumentFromData({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.monthly,
              summary: SummariesCall.responsegpt(
                (_model.monthlySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': DateTime.now(),
              },
            ),
          }, summariesRecordReference1);
          logFirebaseEvent('homePage_alert_dialog');
          await showDialog(
            context: context,
            builder: (dialogContext) {
              return Dialog(
                elevation: 0,
                insetPadding: EdgeInsets.zero,
                backgroundColor: Colors.transparent,
                alignment: const AlignmentDirectional(0.0, 0.0)
                    .resolve(Directionality.of(context)),
                child: GestureDetector(
                  onTap: () => _model.unfocusNode.canRequestFocus
                      ? FocusScope.of(context).requestFocus(_model.unfocusNode)
                      : FocusScope.of(context).unfocus(),
                  child: SummaryWidget(
                    summary: _model.monthlysummaryCreated,
                  ),
                ),
              );
            },
          ).then((value) => setState(() {}));

          logFirebaseEvent('homePage_backend_call');

          await currentUserReference!.update({
            ...mapToFirestore(
              {
                'summaries': FieldValue.arrayUnion(
                    [_model.monthlysummaryCreated?.reference]),
                'lastMonthlySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
        }
      }
      if (((currentUserDocument?.lastWeeklySummaryShown == null) ||
              (currentUserDocument!.lastWeeklySummaryShown! <=
                  functions.sinceLastWeek()!)) &&
          (_model.monthlyMemoriesQuery!
              .where((e) => e.date! > functions.sinceLastWeek()!)
              .toList()
              .isNotEmpty) &&
          (_model.monthlyMemoriesQuery!.length > 100)) {
        logFirebaseEvent('homePage_update_app_state');
        setState(() {
          FFAppState().test = 'true-condition';
        });
        logFirebaseEvent('homePage_backend_call');
        _model.weeklySummary = await SummariesCall.call(
          structuredMemories:
              functions.documentsToText(_model.monthlyMemoriesQuery!.toList()),
        );
        if ((_model.weeklySummary?.succeeded ?? true)) {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference2 = SummariesRecord.collection.doc();
          await summariesRecordReference2.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.weekly,
              summary: SummariesCall.responsegpt(
                (_model.weeklySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': FieldValue.serverTimestamp(),
              },
            ),
          });
          _model.weeklysummaryCreated = SummariesRecord.getDocumentFromData({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.weekly,
              summary: SummariesCall.responsegpt(
                (_model.weeklySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': DateTime.now(),
              },
            ),
          }, summariesRecordReference2);
          logFirebaseEvent('homePage_backend_call');

          await currentUserReference!.update({
            ...mapToFirestore(
              {
                'summaries': FieldValue.arrayUnion(
                    [_model.weeklysummaryCreated?.reference]),
                'lastWeeklySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
          if ((currentUserDocument?.lastMonthlySummaryShown == null) ||
              (currentUserDocument!.lastMonthlySummaryShown! <
                  functions.since18hoursago()!)) {
            logFirebaseEvent('homePage_alert_dialog');
            await showDialog(
              context: context,
              builder: (dialogContext) {
                return Dialog(
                  elevation: 0,
                  insetPadding: EdgeInsets.zero,
                  backgroundColor: Colors.transparent,
                  alignment: const AlignmentDirectional(0.0, 0.0)
                      .resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context)
                            .requestFocus(_model.unfocusNode)
                        : FocusScope.of(context).unfocus(),
                    child: SummaryWidget(
                      summary: _model.weeklysummaryCreated,
                    ),
                  ),
                );
              },
            ).then((value) => setState(() {}));
          }
        }
      }
      if ((_model.monthlyMemoriesQuery != null &&
              (_model.monthlyMemoriesQuery)!.isNotEmpty) &&
          ((currentUserDocument?.lastDailySummaryShown == null) ||
              (currentUserDocument!.lastDailySummaryShown! <=
                  functions.since18hoursago()!)) &&
          (_model.monthlyMemoriesQuery!.length > 10)) {
        logFirebaseEvent('homePage_backend_call');
        _model.dailySummary = await SummariesCall.call(
          structuredMemories: functions.documentsToText(_model
              .monthlyMemoriesQuery!
              .where((e) => e.date! >= functions.sinceYesterday()!)
              .toList()
              .toList()),
        );
        if ((_model.dailySummary?.succeeded ?? true)) {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference3 = SummariesRecord.collection.doc();
          await summariesRecordReference3.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.daily,
              summary: SummariesCall.responsegpt(
                (_model.dailySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': FieldValue.serverTimestamp(),
              },
            ),
          });
          _model.summaryCreated = SummariesRecord.getDocumentFromData({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.daily,
              summary: SummariesCall.responsegpt(
                (_model.dailySummary?.jsonBody ?? ''),
              ),
            ),
            ...mapToFirestore(
              {
                'date': DateTime.now(),
              },
            ),
          }, summariesRecordReference3);
          logFirebaseEvent('homePage_backend_call');

          await currentUserReference!.update({
            ...mapToFirestore(
              {
                'summaries':
                    FieldValue.arrayUnion([_model.summaryCreated?.reference]),
                'lastDailySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
          if ((currentUserDocument?.lastWeeklySummaryShown == null) ||
              (currentUserDocument!.lastWeeklySummaryShown! <
                  functions.since18hoursago()!)) {
            logFirebaseEvent('homePage_alert_dialog');
            await showDialog(
              context: context,
              builder: (dialogContext) {
                return Dialog(
                  elevation: 0,
                  insetPadding: EdgeInsets.zero,
                  backgroundColor: Colors.transparent,
                  alignment: const AlignmentDirectional(0.0, 0.0)
                      .resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context)
                            .requestFocus(_model.unfocusNode)
                        : FocusScope.of(context).unfocus(),
                    child: SummaryWidget(
                      summary: _model.summaryCreated,
                    ),
                  ),
                );
              },
            ).then((value) => setState(() {}));
          }
        }
      }
      logFirebaseEvent('homePage_start_periodic_action');
      _model.instantTimerAction = InstantTimer.periodic(
        duration: const Duration(milliseconds: 1000),
        callback: (timer) async {
          if ((FFAppState().isSpeechRunning == false) &&
              FFAppState().speechWasActivatedByUser &&
              !FFAppState().RecordingPopupIsShown) {
            logFirebaseEvent('homePage_update_app_state');
            FFAppState().RecordingPopupIsShown = true;
            FFAppState().stopAction = true;
            logFirebaseEvent('homePage_alert_dialog');
            await showDialog(
              context: context,
              builder: (dialogContext) {
                return Dialog(
                  elevation: 0,
                  insetPadding: EdgeInsets.zero,
                  backgroundColor: Colors.transparent,
                  alignment: const AlignmentDirectional(0.0, 0.0)
                      .resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context)
                            .requestFocus(_model.unfocusNode)
                        : FocusScope.of(context).unfocus(),
                    child: const RecordingStoppedWidget(),
                  ),
                );
              },
            ).then((value) => setState(() {}));

            logFirebaseEvent('homePage_trigger_push_notification');
            triggerPushNotification(
              notificationTitle: 'Sama',
              notificationText:
                  'Recording is disabled! Please restart audio recording',
              userRefs: [currentUserReference!],
              initialPageName: 'chat',
              parameterData: {},
            );
          }
        },
        startImmediately: true,
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
    context.watch<FFAppState>();

    return Builder(
      builder: (context) => GestureDetector(
        onTap: () => _model.unfocusNode.canRequestFocus
            ? FocusScope.of(context).requestFocus(_model.unfocusNode)
            : FocusScope.of(context).unfocus(),
        child: Scaffold(
          key: scaffoldKey,
          backgroundColor: FlutterFlowTheme.of(context).primary,
          appBar: AppBar(
            backgroundColor: FlutterFlowTheme.of(context).primary,
            automaticallyImplyLeading: false,
            title: Align(
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
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              8.0, 0.0, 0.0, 0.0),
                          iconPadding: const EdgeInsetsDirectional.fromSTEB(
                              0.0, 0.0, 0.0, 0.0),
                          color: const Color(0x1AF7F4F4),
                          textStyle: FlutterFlowTheme.of(context)
                              .titleSmall
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .titleSmallFamily,
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .titleSmallFamily),
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
                          logFirebaseEvent(
                              'HOME_PAGE_PAGE_CHAT_↗_BTN_ON_LONG_PRESS');
                          logFirebaseEvent('Button_navigate_to');

                          context.pushNamed('testNew');
                        },
                        child: FFButtonWidget(
                          onPressed: () async {
                            logFirebaseEvent(
                                'HOME_PAGE_PAGE_CHAT_↗_BTN_ON_TAP');
                            logFirebaseEvent('Button_navigate_to');

                            context.pushNamed('chat');
                          },
                          text: 'Chat ↗',
                          options: FFButtonOptions(
                            width: MediaQuery.sizeOf(context).width * 0.25,
                            height: 44.0,
                            padding: const EdgeInsetsDirectional.fromSTEB(
                                12.0, 0.0, 12.0, 0.0),
                            iconPadding: const EdgeInsetsDirectional.fromSTEB(
                                0.0, 0.0, 0.0, 0.0),
                            color: FlutterFlowTheme.of(context).primary,
                            textStyle: FlutterFlowTheme.of(context)
                                .titleSmall
                                .override(
                                  fontFamily: FlutterFlowTheme.of(context)
                                      .titleSmallFamily,
                                  color: const Color(0xFFF7F4F4),
                                  fontSize: 16.0,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
                                          .titleSmallFamily),
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
                          logFirebaseEvent('HOME_PAGE_PAGE__BTN_ON_TAP');
                          logFirebaseEvent('Button_navigate_to');

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
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              8.0, 0.0, 0.0, 0.0),
                          iconPadding: const EdgeInsetsDirectional.fromSTEB(
                              0.0, 0.0, 0.0, 0.0),
                          color: const Color(0x1AF7F4F4),
                          textStyle: FlutterFlowTheme.of(context)
                              .titleSmall
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .titleSmallFamily,
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .titleSmallFamily),
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
            ),
            actions: const [],
            centerTitle: false,
            toolbarHeight: 66.0,
            elevation: 0.0,
          ),
          body: SafeArea(
            top: true,
            child: Column(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.start,
              children: [
                Align(
                  alignment: const AlignmentDirectional(0.0, 1.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.max,
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      Builder(
                        builder: (context) => FFButtonWidget(
                          onPressed: () async {
                            logFirebaseEvent('HOME_PAGE_PAGE_DAILY_BTN_ON_TAP');
                            if (_model.querySummariesOnMemoryPage!
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
                                          : FocusScope.of(context).unfocus(),
                                      child: SummaryWidget(
                                        summary: _model
                                            .querySummariesOnMemoryPage
                                            ?.where((e) =>
                                                e.type == SummaryType.daily)
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
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
                                  color: const Color(0xFFF7F4F4),
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
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
                        builder: (context) => FFButtonWidget(
                          onPressed: () async {
                            logFirebaseEvent(
                                'HOME_PAGE_PAGE_WEEKLY_BTN_ON_TAP');
                            if (_model.querySummariesOnMemoryPage!
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
                                          : FocusScope.of(context).unfocus(),
                                      child: SummaryWidget(
                                        summary: _model
                                            .querySummariesOnMemoryPage
                                            ?.where((e) =>
                                                e.type == SummaryType.weekly)
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
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
                                  color:
                                      FlutterFlowTheme.of(context).primaryText,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
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
                        builder: (context) => FFButtonWidget(
                          onPressed: () async {
                            logFirebaseEvent(
                                'HOME_PAGE_PAGE_MONTHLY_BTN_ON_TAP');
                            if (_model.querySummariesOnMemoryPage!
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
                                          : FocusScope.of(context).unfocus(),
                                      child: SummaryWidget(
                                        summary: _model
                                            .querySummariesOnMemoryPage
                                            ?.where((e) =>
                                                e.type == SummaryType.monthly)
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
                                    alignment: const AlignmentDirectional(0.0, 0.0)
                                        .resolve(Directionality.of(context)),
                                    child: GestureDetector(
                                      onTap: () => _model
                                              .unfocusNode.canRequestFocus
                                          ? FocusScope.of(context)
                                              .requestFocus(_model.unfocusNode)
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
                                  color:
                                      FlutterFlowTheme.of(context).primaryText,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
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
                ),
                Stack(
                  alignment: const AlignmentDirectional(0.0, 1.0),
                  children: [
                    SingleChildScrollView(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (FFAppState().memoryCreationProcessing)
                            Padding(
                              padding: const EdgeInsetsDirectional.fromSTEB(
                                  12.0, 12.0, 12.0, 0.0),
                              child: Container(
                                width: double.infinity,
                                decoration: BoxDecoration(
                                  color: const Color(0x1AF7F4F4),
                                  borderRadius: BorderRadius.circular(24.0),
                                ),
                                child: Align(
                                  alignment: const AlignmentDirectional(0.0, 0.0),
                                  child: Padding(
                                    padding: const EdgeInsetsDirectional.fromSTEB(
                                        8.0, 8.0, 8.0, 8.0),
                                    child: SingleChildScrollView(
                                      child: Column(
                                        mainAxisSize: MainAxisSize.max,
                                        crossAxisAlignment:
                                            CrossAxisAlignment.center,
                                        children: [
                                          Align(
                                            alignment:
                                                const AlignmentDirectional(0.0, 0.0),
                                            child: Padding(
                                              padding: const EdgeInsetsDirectional
                                                  .fromSTEB(4.0, 0.0, 4.0, 0.0),
                                              child: Container(
                                                width:
                                                    MediaQuery.sizeOf(context)
                                                            .width *
                                                        0.5,
                                                decoration: BoxDecoration(
                                                  color: const Color(0xFF515253),
                                                  borderRadius:
                                                      BorderRadius.circular(
                                                          24.0),
                                                ),
                                                alignment: const AlignmentDirectional(
                                                    0.0, 0.0),
                                                child: const Align(
                                                  alignment:
                                                      AlignmentDirectional(
                                                          0.0, 0.0),
                                                  child: Padding(
                                                    padding:
                                                        EdgeInsetsDirectional
                                                            .fromSTEB(0.0, 4.0,
                                                                0.0, 4.0),
                                                    child: Row(
                                                      mainAxisSize:
                                                          MainAxisSize.min,
                                                      mainAxisAlignment:
                                                          MainAxisAlignment
                                                              .center,
                                                      children: [],
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ),
                                          ),
                                          Align(
                                            alignment:
                                                const AlignmentDirectional(-1.0, 0.0),
                                            child: Padding(
                                              padding: const EdgeInsetsDirectional
                                                  .fromSTEB(
                                                      12.0, 12.0, 0.0, 12.0),
                                              child: SelectionArea(
                                                  child: Text(
                                                'Memory being created...',
                                                textAlign: TextAlign.start,
                                                style:
                                                    FlutterFlowTheme.of(context)
                                                        .bodyMedium
                                                        .override(
                                                          fontFamily:
                                                              FlutterFlowTheme.of(
                                                                      context)
                                                                  .bodyMediumFamily,
                                                          fontSize: 16.0,
                                                          fontWeight:
                                                              FontWeight.w500,
                                                          useGoogleFonts: GoogleFonts
                                                                  .asMap()
                                                              .containsKey(
                                                                  FlutterFlowTheme.of(
                                                                          context)
                                                                      .bodyMediumFamily),
                                                          lineHeight: 1.5,
                                                        ),
                                              )),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          Padding(
                            padding: const EdgeInsetsDirectional.fromSTEB(
                                16.0, 4.0, 16.0, 0.0),
                            child: Container(
                              width: double.infinity,
                              height: MediaQuery.sizeOf(context).height * 0.7,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12.0),
                                shape: BoxShape.rectangle,
                                border: Border.all(
                                  color: const Color(0x00E0E3E7),
                                ),
                              ),
                              child: StreamBuilder<List<MemoriesRecord>>(
                                stream: _model.allmemories(
                                  requestFn: () => queryMemoriesRecord(
                                    queryBuilder: (memoriesRecord) =>
                                        memoriesRecord
                                            .where(
                                              'user',
                                              isEqualTo: currentUserReference,
                                            )
                                            .where(
                                              'emptyMemory',
                                              isEqualTo: false,
                                            )
                                            .where(
                                              'isUselessMemory',
                                              isEqualTo: false,
                                            )
                                            .orderBy('date', descending: true),
                                    limit: 100,
                                  ),
                                ),
                                builder: (context, snapshot) {
                                  // Customize what your widget looks like when it's loading.
                                  if (!snapshot.hasData) {
                                    return Center(
                                      child: SizedBox(
                                        width: 50.0,
                                        height: 50.0,
                                        child: CircularProgressIndicator(
                                          valueColor:
                                              AlwaysStoppedAnimation<Color>(
                                            FlutterFlowTheme.of(context)
                                                .primary,
                                          ),
                                        ),
                                      ),
                                    );
                                  }
                                  List<MemoriesRecord>
                                      listViewMemoriesRecordList =
                                      snapshot.data!;
                                  if (listViewMemoriesRecordList.isEmpty) {
                                    return Center(
                                      child: SizedBox(
                                        width:
                                            MediaQuery.sizeOf(context).width *
                                                1.0,
                                        height:
                                            MediaQuery.sizeOf(context).height *
                                                0.4,
                                        child: const EmptyMemoriesWidget(),
                                      ),
                                    );
                                  }
                                  return ListView.builder(
                                    padding: EdgeInsets.zero,
                                    primary: false,
                                    shrinkWrap: true,
                                    scrollDirection: Axis.vertical,
                                    itemCount:
                                        listViewMemoriesRecordList.length,
                                    itemBuilder: (context, listViewIndex) {
                                      final listViewMemoriesRecord =
                                          listViewMemoriesRecordList[
                                              listViewIndex];
                                      return Padding(
                                        padding: const EdgeInsetsDirectional.fromSTEB(
                                            0.0, 12.0, 0.0, 0.0),
                                        child: Container(
                                          width: double.infinity,
                                          decoration: BoxDecoration(
                                            color: const Color(0x1AF7F4F4),
                                            borderRadius:
                                                BorderRadius.circular(24.0),
                                          ),
                                          child: Align(
                                            alignment:
                                                const AlignmentDirectional(0.0, 0.0),
                                            child: Padding(
                                              padding: const EdgeInsetsDirectional
                                                  .fromSTEB(8.0, 8.0, 8.0, 8.0),
                                              child: SingleChildScrollView(
                                                child: Column(
                                                  mainAxisSize:
                                                      MainAxisSize.max,
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.center,
                                                  children: [
                                                    Align(
                                                      alignment:
                                                          const AlignmentDirectional(
                                                              0.0, 0.0),
                                                      child: Padding(
                                                        padding:
                                                            const EdgeInsetsDirectional
                                                                .fromSTEB(
                                                                    4.0,
                                                                    0.0,
                                                                    4.0,
                                                                    0.0),
                                                        child: Container(
                                                          width:
                                                              MediaQuery.sizeOf(
                                                                          context)
                                                                      .width *
                                                                  0.5,
                                                          decoration:
                                                              BoxDecoration(
                                                            color: const Color(
                                                                0xFF515253),
                                                            borderRadius:
                                                                BorderRadius
                                                                    .circular(
                                                                        24.0),
                                                          ),
                                                          alignment:
                                                              const AlignmentDirectional(
                                                                  0.0, 0.0),
                                                          child: Align(
                                                            alignment:
                                                                const AlignmentDirectional(
                                                                    0.0, 0.0),
                                                            child: Padding(
                                                              padding:
                                                                  const EdgeInsetsDirectional
                                                                      .fromSTEB(
                                                                          0.0,
                                                                          4.0,
                                                                          0.0,
                                                                          4.0),
                                                              child: Row(
                                                                mainAxisSize:
                                                                    MainAxisSize
                                                                        .min,
                                                                mainAxisAlignment:
                                                                    MainAxisAlignment
                                                                        .center,
                                                                children: [
                                                                  Row(
                                                                    mainAxisSize:
                                                                        MainAxisSize
                                                                            .min,
                                                                    mainAxisAlignment:
                                                                        MainAxisAlignment
                                                                            .center,
                                                                    children: [
                                                                      Align(
                                                                        alignment: const AlignmentDirectional(
                                                                            0.0,
                                                                            0.0),
                                                                        child:
                                                                            Padding(
                                                                          padding: const EdgeInsetsDirectional.fromSTEB(
                                                                              4.0,
                                                                              4.0,
                                                                              8.0,
                                                                              4.0),
                                                                          child:
                                                                              Text(
                                                                            dateTimeFormat('M/d h:mm a',
                                                                                listViewMemoriesRecord.date!),
                                                                            style:
                                                                                FlutterFlowTheme.of(context).bodyMedium,
                                                                          ),
                                                                        ),
                                                                      ),
                                                                      Builder(
                                                                        builder:
                                                                            (context) =>
                                                                                Padding(
                                                                          padding: const EdgeInsetsDirectional.fromSTEB(
                                                                              0.0,
                                                                              0.0,
                                                                              10.0,
                                                                              0.0),
                                                                          child:
                                                                              InkWell(
                                                                            splashColor:
                                                                                Colors.transparent,
                                                                            focusColor:
                                                                                Colors.transparent,
                                                                            hoverColor:
                                                                                Colors.transparent,
                                                                            highlightColor:
                                                                                Colors.transparent,
                                                                            onTap:
                                                                                () async {
                                                                              logFirebaseEvent('HOME_PAGE_PAGE_Icon_354g89my_ON_TAP');
                                                                              logFirebaseEvent('Icon_share');
                                                                              await Share.share(
                                                                                '${listViewMemoriesRecord.structuredMemory}  Created with https://www.aisama.co/',
                                                                                sharePositionOrigin: getWidgetBoundingBox(context),
                                                                              );
                                                                              logFirebaseEvent('Icon_haptic_feedback');
                                                                              HapticFeedback.lightImpact();
                                                                            },
                                                                            child:
                                                                                FaIcon(
                                                                              FontAwesomeIcons.share,
                                                                              color: FlutterFlowTheme.of(context).secondaryText,
                                                                              size: 20.0,
                                                                            ),
                                                                          ),
                                                                        ),
                                                                      ),
                                                                      Builder(
                                                                        builder:
                                                                            (context) =>
                                                                                InkWell(
                                                                          splashColor:
                                                                              Colors.transparent,
                                                                          focusColor:
                                                                              Colors.transparent,
                                                                          hoverColor:
                                                                              Colors.transparent,
                                                                          highlightColor:
                                                                              Colors.transparent,
                                                                          onTap:
                                                                              () async {
                                                                            logFirebaseEvent('HOME_PAGE_PAGE_Icon_s7ft79xx_ON_TAP');
                                                                            logFirebaseEvent('Icon_alert_dialog');
                                                                            await showDialog(
                                                                              context: context,
                                                                              builder: (dialogContext) {
                                                                                return Dialog(
                                                                                  elevation: 0,
                                                                                  insetPadding: EdgeInsets.zero,
                                                                                  backgroundColor: Colors.transparent,
                                                                                  alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                                                                                  child: GestureDetector(
                                                                                    onTap: () => _model.unfocusNode.canRequestFocus ? FocusScope.of(context).requestFocus(_model.unfocusNode) : FocusScope.of(context).unfocus(),
                                                                                    child: EditMemoryWidget(
                                                                                      memory: listViewMemoriesRecord,
                                                                                    ),
                                                                                  ),
                                                                                );
                                                                              },
                                                                            ).then((value) =>
                                                                                setState(() {}));
                                                                          },
                                                                          child:
                                                                              Icon(
                                                                            Icons.edit,
                                                                            color:
                                                                                FlutterFlowTheme.of(context).secondaryText,
                                                                            size:
                                                                                20.0,
                                                                          ),
                                                                        ),
                                                                      ),
                                                                      Builder(
                                                                        builder:
                                                                            (context) =>
                                                                                Padding(
                                                                          padding: const EdgeInsetsDirectional.fromSTEB(
                                                                              10.0,
                                                                              0.0,
                                                                              0.0,
                                                                              0.0),
                                                                          child:
                                                                              InkWell(
                                                                            splashColor:
                                                                                Colors.transparent,
                                                                            focusColor:
                                                                                Colors.transparent,
                                                                            hoverColor:
                                                                                Colors.transparent,
                                                                            highlightColor:
                                                                                Colors.transparent,
                                                                            onTap:
                                                                                () async {
                                                                              logFirebaseEvent('HOME_PAGE_PAGE_Icon_0n4bjs4f_ON_TAP');
                                                                              logFirebaseEvent('Icon_alert_dialog');
                                                                              await showDialog(
                                                                                context: context,
                                                                                builder: (dialogContext) {
                                                                                  return Dialog(
                                                                                    elevation: 0,
                                                                                    insetPadding: EdgeInsets.zero,
                                                                                    backgroundColor: Colors.transparent,
                                                                                    alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                                                                                    child: GestureDetector(
                                                                                      onTap: () => _model.unfocusNode.canRequestFocus ? FocusScope.of(context).requestFocus(_model.unfocusNode) : FocusScope.of(context).unfocus(),
                                                                                      child: ConfirmDeletionWidget(
                                                                                        memory: listViewMemoriesRecord.reference,
                                                                                      ),
                                                                                    ),
                                                                                  );
                                                                                },
                                                                              ).then((value) => setState(() {}));
                                                                            },
                                                                            child:
                                                                                Icon(
                                                                              Icons.delete,
                                                                              color: FlutterFlowTheme.of(context).secondaryText,
                                                                              size: 20.0,
                                                                            ),
                                                                          ),
                                                                        ),
                                                                      ),
                                                                    ],
                                                                  ),
                                                                ],
                                                              ),
                                                            ),
                                                          ),
                                                        ),
                                                      ),
                                                    ),
                                                    Align(
                                                      alignment:
                                                          const AlignmentDirectional(
                                                              -1.0, 0.0),
                                                      child: Padding(
                                                        padding:
                                                            const EdgeInsetsDirectional
                                                                .fromSTEB(
                                                                    8.0,
                                                                    8.0,
                                                                    0.0,
                                                                    8.0),
                                                        child: SelectionArea(
                                                            child: Text(
                                                          listViewMemoriesRecord
                                                              .structuredMemory,
                                                          textAlign:
                                                              TextAlign.start,
                                                          style: FlutterFlowTheme
                                                                  .of(context)
                                                              .bodyMedium
                                                              .override(
                                                                fontFamily: FlutterFlowTheme.of(
                                                                        context)
                                                                    .bodyMediumFamily,
                                                                fontWeight:
                                                                    FontWeight
                                                                        .bold,
                                                                useGoogleFonts: GoogleFonts
                                                                        .asMap()
                                                                    .containsKey(
                                                                        FlutterFlowTheme.of(context)
                                                                            .bodyMediumFamily),
                                                                lineHeight: 1.5,
                                                              ),
                                                        )),
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      );
                                    },
                                  );
                                },
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                Expanded(
                  child: Padding(
                    padding:
                        const EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 10.0),
                    child: Row(
                      mainAxisSize: MainAxisSize.max,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Align(
                          alignment: const AlignmentDirectional(0.0, -1.0),
                          child: Padding(
                            padding: const EdgeInsetsDirectional.fromSTEB(
                                0.0, 0.0, 24.0, 0.0),
                            child: wrapWithModel(
                              model: _model.startStopRecordingModel,
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
                                    logFirebaseEvent(
                                        'HOME_PAGE_PAGE_ADD_BTN_ON_TAP');
                                    logFirebaseEvent('Button_alert_dialog');
                                    await showDialog(
                                      context: context,
                                      builder: (dialogContext) {
                                        return Dialog(
                                          elevation: 0,
                                          insetPadding: EdgeInsets.zero,
                                          backgroundColor: Colors.transparent,
                                          alignment: const AlignmentDirectional(
                                                  0.0, 0.0)
                                              .resolve(
                                                  Directionality.of(context)),
                                          child: GestureDetector(
                                            onTap: () => _model
                                                    .unfocusNode.canRequestFocus
                                                ? FocusScope.of(context)
                                                    .requestFocus(
                                                        _model.unfocusNode)
                                                : FocusScope.of(context)
                                                    .unfocus(),
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
                                    padding: const EdgeInsetsDirectional.fromSTEB(
                                        24.0, 0.0, 24.0, 0.0),
                                    iconPadding: const EdgeInsetsDirectional.fromSTEB(
                                        0.0, 0.0, 0.0, 0.0),
                                    color: const Color(0x1AF7F4F4),
                                    textStyle: FlutterFlowTheme.of(context)
                                        .titleSmall
                                        .override(
                                          fontFamily:
                                              FlutterFlowTheme.of(context)
                                                  .titleSmallFamily,
                                          color: FlutterFlowTheme.of(context)
                                              .primaryText,
                                          fontWeight: FontWeight.bold,
                                          useGoogleFonts: GoogleFonts.asMap()
                                              .containsKey(
                                                  FlutterFlowTheme.of(context)
                                                      .titleSmallFamily),
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
