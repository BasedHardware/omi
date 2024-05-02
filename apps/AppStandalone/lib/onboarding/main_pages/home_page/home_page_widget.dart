import 'package:sama/components/memories/memory_list_item.dart';
import 'package:sama/onboarding/main_pages/home_page/bottom_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/header_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/summaries_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/memory_processing.dart';
import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/backend/schema/enums/enums.dart';
import '/components/empty_memories_widget.dart';
import '/components/summary_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/onboarding/main_pages/recording_stopped/recording_stopped_widget.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:provider/provider.dart';
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
      // TODO: migrate to preferences or sqlite eventually
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
              (currentUserDocument!.lastMonthlySummaryShown! <= functions.sinceLastMonth()!)) &&
          (_model.monthlyMemoriesQuery != null && (_model.monthlyMemoriesQuery)!.isNotEmpty) &&
          (_model.monthlyMemoriesQuery!.length > 100)) {
        logFirebaseEvent('homePage_backend_call');
        _model.monthlySummary = await requestSummary(
          functions.documentsToText(_model.monthlyMemoriesQuery!.toList()),
        );
        if (_model.weeklySummary != '') {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference1 = SummariesRecord.collection.doc();
          await summariesRecordReference1.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.monthly,
              summary: _model.monthlySummary ?? '',
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
              summary: _model.monthlySummary ?? '',
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
                alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
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
                'summaries': FieldValue.arrayUnion([_model.monthlysummaryCreated?.reference]),
                'lastMonthlySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
        }
      }
      if (((currentUserDocument?.lastWeeklySummaryShown == null) ||
              (currentUserDocument!.lastWeeklySummaryShown! <= functions.sinceLastWeek()!)) &&
          (_model.monthlyMemoriesQuery!.where((e) => e.date! > functions.sinceLastWeek()!).toList().isNotEmpty) &&
          (_model.monthlyMemoriesQuery!.length > 100)) {
        logFirebaseEvent('homePage_update_app_state');
        setState(() {
          FFAppState().test = 'true-condition';
        });
        logFirebaseEvent('homePage_backend_call');
        _model.weeklySummary = await requestSummary(
          functions.documentsToText(_model.monthlyMemoriesQuery!.toList()),
        );
        if (_model.weeklySummary != '') {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference2 = SummariesRecord.collection.doc();
          await summariesRecordReference2.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.weekly,
              summary: _model.weeklySummary ?? '',
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
              summary: _model.weeklySummary ?? '',
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
                'summaries': FieldValue.arrayUnion([_model.weeklysummaryCreated?.reference]),
                'lastWeeklySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
          if ((currentUserDocument?.lastMonthlySummaryShown == null) ||
              (currentUserDocument!.lastMonthlySummaryShown! < functions.since18hoursago()!)) {
            logFirebaseEvent('homePage_alert_dialog');
            await showDialog(
              context: context,
              builder: (dialogContext) {
                return Dialog(
                  elevation: 0,
                  insetPadding: EdgeInsets.zero,
                  backgroundColor: Colors.transparent,
                  alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context).requestFocus(_model.unfocusNode)
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
      if ((_model.monthlyMemoriesQuery != null && (_model.monthlyMemoriesQuery)!.isNotEmpty) &&
          ((currentUserDocument?.lastDailySummaryShown == null) ||
              (currentUserDocument!.lastDailySummaryShown! <= functions.since18hoursago()!)) &&
          (_model.monthlyMemoriesQuery!.length > 10)) {
        logFirebaseEvent('homePage_backend_call');
        _model.dailySummary = await requestSummary(
          functions.documentsToText(
              _model.monthlyMemoriesQuery!.where((e) => e.date! >= functions.sinceYesterday()!).toList().toList()),
        );
        if (_model.dailySummary != '') {
          logFirebaseEvent('homePage_backend_call');

          var summariesRecordReference3 = SummariesRecord.collection.doc();
          await summariesRecordReference3.set({
            ...createSummariesRecordData(
              user: currentUserReference,
              type: SummaryType.daily,
              summary: _model.dailySummary ?? '',
            ),
            ...mapToFirestore(
              {
                'date': FieldValue.serverTimestamp(),
              },
            ),
          });
          _model.summaryCreated = SummariesRecord.getDocumentFromData({
            ...createSummariesRecordData(
                user: currentUserReference, type: SummaryType.daily, summary: _model.dailySummary ?? ''),
            ...mapToFirestore(
              {
                'date': DateTime.now(),
              },
            ),
          }, summariesRecordReference3);
          logFirebaseEvent('homePage_backend_call');

          await currentUserReference?.update({
            ...mapToFirestore(
              {
                'summaries': FieldValue.arrayUnion([_model.summaryCreated?.reference]),
                'lastDailySummaryShown': FieldValue.serverTimestamp(),
              },
            ),
          });
          if ((currentUserDocument?.lastWeeklySummaryShown == null) ||
              (currentUserDocument!.lastWeeklySummaryShown! < functions.since18hoursago()!)) {
            logFirebaseEvent('homePage_alert_dialog');
            await showDialog(
              context: context,
              builder: (dialogContext) {
                return Dialog(
                  elevation: 0,
                  insetPadding: EdgeInsets.zero,
                  backgroundColor: Colors.transparent,
                  alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context).requestFocus(_model.unfocusNode)
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
                  alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                  child: GestureDetector(
                    onTap: () => _model.unfocusNode.canRequestFocus
                        ? FocusScope.of(context).requestFocus(_model.unfocusNode)
                        : FocusScope.of(context).unfocus(),
                    child: const RecordingStoppedWidget(),
                  ),
                );
              },
            ).then((value) => setState(() {}));

            logFirebaseEvent('homePage_trigger_push_notification');
            triggerPushNotification(
              notificationTitle: 'Sama',
              notificationText: 'Recording is disabled! Please restart audio recording',
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
            title: const HomePageHeaderButtons(),
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
                HomePageSummariesButtons(
                  model: _model,
                ),
                Expanded(
                  child: Stack(
                    alignment: const AlignmentDirectional(0.0, 1.0),
                    children: [
                      SingleChildScrollView(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (FFAppState().memoryCreationProcessing) MemoryProcessing(),
                            Padding(
                              padding: const EdgeInsetsDirectional.fromSTEB(16.0, 4.0, 16.0, 0.0),
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
                                child: FFAppState().memories.isEmpty
                                    ? Center(
                                        child: SizedBox(
                                          width: MediaQuery.sizeOf(context).width * 1.0,
                                          height: MediaQuery.sizeOf(context).height * 0.4,
                                          child: const EmptyMemoriesWidget(),
                                        ),
                                      )
                                    : ListView.builder(
                                        padding: EdgeInsets.zero,
                                        primary: false,
                                        shrinkWrap: true,
                                        scrollDirection: Axis.vertical,
                                        itemCount: FFAppState().memories.length,
                                        itemBuilder: (context, index) {
                                          return MemoryListItem(memory: FFAppState().memories[index], model: _model);
                                        },
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                HomePageBottomButtons(model: _model),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
