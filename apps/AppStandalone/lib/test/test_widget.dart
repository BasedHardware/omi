import 'package:sama/backend/storage/memories.dart';

import '/auth/firebase_auth/auth_util.dart';
import '/backend/backend.dart';
import '/components/confirm_deletion_widget.dart';
import '/components/empty_memories_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:share_plus/share_plus.dart';
import 'test_model.dart';
export 'test_model.dart';

class TestWidget extends StatefulWidget {
  const TestWidget({super.key});

  @override
  State<TestWidget> createState() => _TestWidgetState();
}

class _TestWidgetState extends State<TestWidget> {
  late TestModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => TestModel());

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'test'});
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
        body: Align(
          alignment: const AlignmentDirectional(0.0, 1.0),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(8.0, 32.0, 8.0, 20.0),
                child: Row(
                  mainAxisSize: MainAxisSize.max,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 8.0, 0.0),
                      child: FFButtonWidget(
                        onPressed: () {
                          print('Button pressed ...');
                        },
                        text: '',
                        icon: const Icon(
                          Icons.discord_sharp,
                          size: 15.0,
                        ),
                        options: FFButtonOptions(
                          height: 48.0,
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
                    ),
                    FFButtonWidget(
                      onPressed: () {
                        print('Button pressed ...');
                      },
                      text: 'Memories',
                      options: FFButtonOptions(
                        height: 48.0,
                        padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
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
                    FFButtonWidget(
                      onPressed: () {
                        print('Button pressed ...');
                      },
                      text: '',
                      icon: const Icon(
                        Icons.settings_sharp,
                        size: 15.0,
                      ),
                      options: FFButtonOptions(
                        height: 48.0,
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
                        borderRadius: BorderRadius.circular(48.0),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Container(
                  decoration: const BoxDecoration(
                    shape: BoxShape.rectangle,
                  ),
                  child: Stack(
                    children: [
                      StreamBuilder<List<MemoriesRecord>>(
                        stream: queryMemoriesRecord(
                          queryBuilder: (memoriesRecord) => memoriesRecord
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
                        builder: (context, snapshot) {
                          // Customize what your widget looks like when it's loading.
                          if (!snapshot.hasData) {
                            return Center(
                              child: SizedBox(
                                width: 50.0,
                                height: 50.0,
                                child: CircularProgressIndicator(
                                  valueColor: AlwaysStoppedAnimation<Color>(
                                    FlutterFlowTheme.of(context).primary,
                                  ),
                                ),
                              ),
                            );
                          }
                          List<MemoriesRecord> listViewMemoriesRecordList = snapshot.data!;
                          if (listViewMemoriesRecordList.isEmpty) {
                            return Center(
                              child: SizedBox(
                                width: MediaQuery.sizeOf(context).width * 1.0,
                                height: MediaQuery.sizeOf(context).height * 0.4,
                                child: const EmptyMemoriesWidget(),
                              ),
                            );
                          }
                          return ListView.builder(
                            padding: EdgeInsets.zero,
                            primary: false,
                            shrinkWrap: true,
                            scrollDirection: Axis.vertical,
                            itemCount: listViewMemoriesRecordList.length,
                            itemBuilder: (context, listViewIndex) {
                              final listViewMemoriesRecord = listViewMemoriesRecordList[listViewIndex];
                              return Padding(
                                padding: const EdgeInsetsDirectional.fromSTEB(12.0, 12.0, 12.0, 0.0),
                                child: Container(
                                  width: double.infinity,
                                  decoration: BoxDecoration(
                                    color: const Color(0x1AF7F4F4),
                                    borderRadius: BorderRadius.circular(24.0),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
                                    child: SingleChildScrollView(
                                      child: Column(
                                        mainAxisSize: MainAxisSize.max,
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Padding(
                                            padding: const EdgeInsetsDirectional.fromSTEB(4.0, 0.0, 4.0, 0.0),
                                            child: Container(
                                              decoration: BoxDecoration(
                                                color: const Color(0xFF515253),
                                                borderRadius: BorderRadius.circular(24.0),
                                              ),
                                              child: Padding(
                                                padding: const EdgeInsetsDirectional.fromSTEB(0.0, 4.0, 0.0, 4.0),
                                                child: Row(
                                                  mainAxisSize: MainAxisSize.max,
                                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                  children: [
                                                    Row(
                                                      mainAxisSize: MainAxisSize.min,
                                                      children: [
                                                        Padding(
                                                          padding:
                                                              const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                                                          child: FaIcon(
                                                            FontAwesomeIcons.solidClock,
                                                            color: FlutterFlowTheme.of(context).secondary,
                                                            size: 16.0,
                                                          ),
                                                        ),
                                                        Padding(
                                                          padding:
                                                              const EdgeInsetsDirectional.fromSTEB(4.0, 4.0, 8.0, 4.0),
                                                          child: Text(
                                                            dateTimeFormat('jm', listViewMemoriesRecord.date!),
                                                            style: FlutterFlowTheme.of(context).bodyMedium,
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                    Row(
                                                      mainAxisSize: MainAxisSize.max,
                                                      children: [
                                                        Builder(
                                                          builder: (context) => Padding(
                                                            padding: const EdgeInsetsDirectional.fromSTEB(
                                                                0.0, 0.0, 8.0, 0.0),
                                                            child: InkWell(
                                                              splashColor: Colors.transparent,
                                                              focusColor: Colors.transparent,
                                                              hoverColor: Colors.transparent,
                                                              highlightColor: Colors.transparent,
                                                              onTap: () async {
                                                                logFirebaseEvent('TEST_PAGE_Icon_5cigllip_ON_TAP');
                                                                logFirebaseEvent('Icon_share');
                                                                await Share.share(
                                                                  '${listViewMemoriesRecord.structuredMemory} Created with https://www.aisama.co/',
                                                                  sharePositionOrigin: getWidgetBoundingBox(context),
                                                                );
                                                                logFirebaseEvent('Icon_haptic_feedback');
                                                                HapticFeedback.lightImpact();
                                                              },
                                                              child: FaIcon(
                                                                FontAwesomeIcons.share,
                                                                color: FlutterFlowTheme.of(context).secondaryText,
                                                                size: 24.0,
                                                              ),
                                                            ),
                                                          ),
                                                        ),
                                                        Align(
                                                          alignment: const AlignmentDirectional(1.0, -1.0),
                                                          child: Builder(
                                                            builder: (context) => Padding(
                                                              padding: const EdgeInsetsDirectional.fromSTEB(
                                                                  0.0, 0.0, 5.0, 0.0),
                                                              child: InkWell(
                                                                splashColor: Colors.transparent,
                                                                focusColor: Colors.transparent,
                                                                hoverColor: Colors.transparent,
                                                                highlightColor: Colors.transparent,
                                                                onTap: () async {
                                                                  logFirebaseEvent('TEST_PAGE_Icon_cr2gc5g2_ON_TAP');
                                                                  logFirebaseEvent('Icon_alert_dialog');
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
                                                                          onTap: () =>
                                                                              _model.unfocusNode.canRequestFocus
                                                                                  ? FocusScope.of(context)
                                                                                      .requestFocus(_model.unfocusNode)
                                                                                  : FocusScope.of(context).unfocus(),
                                                                          child: ConfirmDeletionWidget(
                                                                            memory: MemoryRecord.fromJson(
                                                                                {}), // FIXME: Handle new MemoryRecord object
                                                                          ),
                                                                        ),
                                                                      );
                                                                    },
                                                                  ).then((value) => setState(() {}));
                                                                },
                                                                child: Icon(
                                                                  Icons.delete,
                                                                  color: FlutterFlowTheme.of(context).secondaryText,
                                                                  size: 24.0,
                                                                ),
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
                                          Padding(
                                            padding: const EdgeInsetsDirectional.fromSTEB(8.0, 4.0, 0.0, 8.0),
                                            child: SelectionArea(
                                                child: Text(
                                              listViewMemoriesRecord.structuredMemory,
                                              style: FlutterFlowTheme.of(context).bodyMedium.override(
                                                    fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                                                    fontWeight: FontWeight.w500,
                                                    useGoogleFonts: GoogleFonts.asMap()
                                                        .containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                                                    lineHeight: 1.5,
                                                  ),
                                            )),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            },
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ),
              Container(
                width: MediaQuery.sizeOf(context).width * 1.0,
                height: 100.0,
                decoration: BoxDecoration(
                  color: FlutterFlowTheme.of(context).primary,
                ),
                child: Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 20.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.max,
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      FFButtonWidget(
                        onPressed: () {
                          print('Button pressed ...');
                        },
                        text: 'Chat',
                        icon: const Icon(
                          Icons.chat_bubble_rounded,
                          size: 20.0,
                        ),
                        options: FFButtonOptions(
                          width: MediaQuery.sizeOf(context).width * 0.44,
                          height: 52.0,
                          padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                          iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                          color: FlutterFlowTheme.of(context).primaryText,
                          textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                                fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                                color: FlutterFlowTheme.of(context).primary,
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
                      FFButtonWidget(
                        onPressed: () {
                          print('Button pressed ...');
                        },
                        text: 'Record',
                        icon: const Icon(
                          Icons.fiber_manual_record,
                          size: 15.0,
                        ),
                        options: FFButtonOptions(
                          width: MediaQuery.sizeOf(context).width * 0.44,
                          height: 52.0,
                          padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
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
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
