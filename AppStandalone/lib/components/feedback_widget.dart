import '/auth/firebase_auth/auth_util.dart';
import '/backend/backend.dart';
import '/components/empty_home_page_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'feedback_model.dart';
export 'feedback_model.dart';

class FeedbackWidget extends StatefulWidget {
  const FeedbackWidget({super.key});

  @override
  State<FeedbackWidget> createState() => _FeedbackWidgetState();
}

class _FeedbackWidgetState extends State<FeedbackWidget> {
  late FeedbackModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => FeedbackModel());

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.maybeDispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: const AlignmentDirectional(0.0, 0.0),
      child: StreamBuilder<List<MemoriesRecord>>(
        stream: queryMemoriesRecord(
          queryBuilder: (memoriesRecord) => memoriesRecord
              .where(
                'user',
                isEqualTo: currentUserReference,
              )
              .where(
                'ToShowToUser_Show_Hide',
                isEqualTo: 'Show',
              )
              .where(
                'isUselessMemory',
                isEqualTo: false,
              )
              .orderBy('date', descending: true),
          limit: 20,
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
                height: double.infinity,
                child: const EmptyHomePageWidget(),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 8.0),
            reverse: true,
            shrinkWrap: true,
            scrollDirection: Axis.vertical,
            itemCount: listViewMemoriesRecordList.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8.0),
            itemBuilder: (context, listViewIndex) {
              final listViewMemoriesRecord =
                  listViewMemoriesRecordList[listViewIndex];
              return Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 40.0, 0.0),
                child: Container(
                  width: double.infinity,
                  constraints: const BoxConstraints(
                    maxWidth: 300.0,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0x34F7F4F4),
                    borderRadius: BorderRadius.circular(12.0),
                  ),
                  child: Padding(
                    padding:
                        const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 12.0),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              0.0, 4.0, 0.0, 0.0),
                          child: Container(
                            decoration: BoxDecoration(
                              color: const Color(0xFF515253),
                              borderRadius: BorderRadius.circular(24.0),
                            ),
                            child: Padding(
                              padding: const EdgeInsetsDirectional.fromSTEB(
                                  4.0, 4.0, 4.0, 4.0),
                              child: Row(
                                mainAxisSize: MainAxisSize.max,
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Row(
                                    mainAxisSize: MainAxisSize.max,
                                    children: [
                                      Icon(
                                        Icons.blur_on,
                                        color: FlutterFlowTheme.of(context)
                                            .secondary,
                                        size: 24.0,
                                      ),
                                      Padding(
                                        padding: const EdgeInsetsDirectional.fromSTEB(
                                            8.0, 0.0, 0.0, 0.0),
                                        child: SelectionArea(
                                            child: Text(
                                          'Sama',
                                          style: FlutterFlowTheme.of(context)
                                              .labelMedium
                                              .override(
                                                fontFamily:
                                                    FlutterFlowTheme.of(context)
                                                        .labelMediumFamily,
                                                color:
                                                    FlutterFlowTheme.of(context)
                                                        .secondary,
                                                fontWeight: FontWeight.w500,
                                                useGoogleFonts: GoogleFonts
                                                        .asMap()
                                                    .containsKey(
                                                        FlutterFlowTheme.of(
                                                                context)
                                                            .labelMediumFamily),
                                              ),
                                        )),
                                      ),
                                    ],
                                  ),
                                  Padding(
                                    padding: const EdgeInsetsDirectional.fromSTEB(
                                        0.0, 0.0, 4.0, 0.0),
                                    child: SelectionArea(
                                        child: Text(
                                      dateTimeFormat('M/d h:mm a',
                                          listViewMemoriesRecord.date!),
                                      textAlign: TextAlign.end,
                                      style: FlutterFlowTheme.of(context)
                                          .bodyMedium
                                          .override(
                                            fontFamily:
                                                FlutterFlowTheme.of(context)
                                                    .bodyMediumFamily,
                                            color: FlutterFlowTheme.of(context)
                                                .secondary,
                                            useGoogleFonts: GoogleFonts.asMap()
                                                .containsKey(
                                                    FlutterFlowTheme.of(context)
                                                        .bodyMediumFamily),
                                          ),
                                    )),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              4.0, 4.0, 0.0, 0.0),
                          child: SelectionArea(
                              child: Text(
                            listViewMemoriesRecord.feedback,
                            style: FlutterFlowTheme.of(context)
                                .labelMedium
                                .override(
                                  fontFamily: FlutterFlowTheme.of(context)
                                      .labelMediumFamily,
                                  color: FlutterFlowTheme.of(context).secondary,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
                                          .labelMediumFamily),
                                ),
                          )),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
