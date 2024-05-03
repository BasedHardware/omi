import 'package:sama/backend/storage/memories.dart';
import 'package:sama/onboarding/main_pages/home_page/memory_list_item.dart';
import 'package:sama/onboarding/main_pages/home_page/bottom_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/header_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/summaries_buttons.dart';
import 'package:sama/onboarding/main_pages/home_page/memory_processing.dart';
import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/components/empty_memories_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/onboarding/main_pages/recording_stopped/recording_stopped_widget.dart';
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
  String? dailySummary;
  String? weeklySummary;
  String? monthlySummary;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  _dailySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesByDay(DateTime.now());
    dailySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  _weeklySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesOfLastWeek();
    weeklySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  _monthlySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesOfLastMonth();
    monthlySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => HomePageModel());
    _dailySummary();
    _weeklySummary();
    _monthlySummary();
    SchedulerBinding.instance.addPostFrameCallback((_) async {
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

            if (currentUserReference != null) {
              triggerPushNotification(
                notificationTitle: 'Sama',
                notificationText: 'Recording is disabled! Please restart audio recording',
                userRefs: [currentUserReference!],
                initialPageName: 'chat',
                parameterData: {},
              );
            }
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
                  dailySummary: dailySummary,
                  weeklySummary: weeklySummary,
                  monthlySummary: monthlySummary,
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
                                child: (FFAppState().memories.isEmpty && !FFAppState().memoryCreationProcessing)
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
