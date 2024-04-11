import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'import_apple_model.dart';
export 'import_apple_model.dart';

class ImportAppleWidget extends StatefulWidget {
  const ImportAppleWidget({super.key});

  @override
  State<ImportAppleWidget> createState() => _ImportAppleWidgetState();
}

class _ImportAppleWidgetState extends State<ImportAppleWidget> {
  late ImportAppleModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ImportAppleModel());

    _model.textController ??= TextEditingController();
    _model.textFieldFocusNode ??= FocusNode();

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
                            'IMPORT_APPLE_COMP_Icon_ubme5fup_ON_TAP');
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
                            'assets/images/b6cde81d1c489b0e20d85a6e06c5f8f9.png',
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
                          'Steps to Import your Apple Note:',
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
                      Align(
                        alignment: const AlignmentDirectional(0.0, 0.0),
                        child: Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              0.0, 0.0, 0.0, 24.0),
                          child: Text(
                            '1. Open Apple Notes App\n2. Open the Note you wish to import\n3.\tClick “Share” \n4.\tSelect “Copy” \n5.\tPaste as text below\n',
                            style: FlutterFlowTheme.of(context)
                                .bodyMedium
                                .override(
                                  fontFamily: FlutterFlowTheme.of(context)
                                      .bodyMediumFamily,
                                  fontSize: 16.0,
                                  fontWeight: FontWeight.w500,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
                                          .bodyMediumFamily),
                                ),
                          ),
                        ),
                      ),
                      Container(
                        decoration: const BoxDecoration(),
                      ),
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(
                            20.0, 0.0, 20.0, 0.0),
                        child: TextFormField(
                          controller: _model.textController,
                          focusNode: _model.textFieldFocusNode,
                          autofocus: true,
                          obscureText: false,
                          decoration: InputDecoration(
                            labelText: 'Paste text here',
                            labelStyle:
                                FlutterFlowTheme.of(context).labelMedium,
                            hintStyle: FlutterFlowTheme.of(context).labelMedium,
                            enabledBorder: OutlineInputBorder(
                              borderSide: BorderSide(
                                color: FlutterFlowTheme.of(context).alternate,
                                width: 2.0,
                              ),
                              borderRadius: BorderRadius.circular(8.0),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderSide: BorderSide(
                                color: FlutterFlowTheme.of(context).primary,
                                width: 2.0,
                              ),
                              borderRadius: BorderRadius.circular(8.0),
                            ),
                            errorBorder: OutlineInputBorder(
                              borderSide: BorderSide(
                                color: FlutterFlowTheme.of(context).error,
                                width: 2.0,
                              ),
                              borderRadius: BorderRadius.circular(8.0),
                            ),
                            focusedErrorBorder: OutlineInputBorder(
                              borderSide: BorderSide(
                                color: FlutterFlowTheme.of(context).error,
                                width: 2.0,
                              ),
                              borderRadius: BorderRadius.circular(8.0),
                            ),
                          ),
                          style: FlutterFlowTheme.of(context)
                              .bodyMedium
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .bodyMediumFamily,
                                fontSize: 16.0,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .bodyMediumFamily),
                              ),
                          maxLines: null,
                          minLines: 1,
                          keyboardType: TextInputType.multiline,
                          validator: _model.textControllerValidator
                              .asValidator(context),
                        ),
                      ),
                    ],
                  ),
                ),
                Align(
                  alignment: const AlignmentDirectional(0.0, 0.0),
                  child: Padding(
                    padding:
                        const EdgeInsetsDirectional.fromSTEB(0.0, 10.0, 20.0, 0.0),
                    child: FFButtonWidget(
                      onPressed: () async {
                        logFirebaseEvent('IMPORT_APPLE_COMP_SAVE_BTN_ON_TAP');
                        logFirebaseEvent('Button_close_dialog,_drawer,_etc');
                        Navigator.pop(context);
                        logFirebaseEvent('Button_backend_call');
                        _model.vectorized = await VectorizeCall.call(
                          input: _model.textController.text,
                        );
                        logFirebaseEvent('Button_backend_call');

                        var memoriesRecordReference =
                            MemoriesRecord.collection.doc();
                        await memoriesRecordReference.set({
                          ...createMemoriesRecordData(
                            user: currentUserReference,
                            structuredMemory: _model.textController.text,
                            memory: 'User-added memory',
                            emptyMemory: false,
                            toShowToUserShowHide: 'Show',
                            isUselessMemory: false,
                          ),
                          ...mapToFirestore(
                            {
                              'date': FieldValue.serverTimestamp(),
                              'vector': VectorizeCall.embedding(
                                (_model.vectorized?.jsonBody ?? ''),
                              ),
                            },
                          ),
                        });
                        _model.createdMemoryManually =
                            MemoriesRecord.getDocumentFromData({
                          ...createMemoriesRecordData(
                            user: currentUserReference,
                            structuredMemory: _model.textController.text,
                            memory: 'User-added memory',
                            emptyMemory: false,
                            toShowToUserShowHide: 'Show',
                            isUselessMemory: false,
                          ),
                          ...mapToFirestore(
                            {
                              'date': DateTime.now(),
                              'vector': VectorizeCall.embedding(
                                (_model.vectorized?.jsonBody ?? ''),
                              ),
                            },
                          ),
                        }, memoriesRecordReference);
                        if ((_model.vectorized?.succeeded ?? true)) {
                          logFirebaseEvent('Button_backend_call');
                          _model.addedVector =
                              await CreateVectorPineconeCall.call(
                            id: _model.createdMemoryManually?.reference.id,
                            structuredMemory:
                                _model.createdMemoryManually?.structuredMemory,
                            vectorList: VectorizeCall.embedding(
                              (_model.vectorized?.jsonBody ?? ''),
                            ),
                          );
                        } else {
                          logFirebaseEvent('Button_show_snack_bar');
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                'We are updating smth... back soon!',
                                style: TextStyle(
                                  color: FlutterFlowTheme.of(context).primary,
                                ),
                              ),
                              duration: const Duration(milliseconds: 4000),
                              backgroundColor:
                                  FlutterFlowTheme.of(context).secondary,
                            ),
                          );
                        }

                        setState(() {});
                      },
                      text: 'Save',
                      options: FFButtonOptions(
                        height: 40.0,
                        padding: const EdgeInsetsDirectional.fromSTEB(
                            20.0, 0.0, 20.0, 0.0),
                        iconPadding:
                            const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                        color: FlutterFlowTheme.of(context).secondary,
                        textStyle: FlutterFlowTheme.of(context)
                            .bodyLarge
                            .override(
                              fontFamily:
                                  FlutterFlowTheme.of(context).bodyLargeFamily,
                              color: FlutterFlowTheme.of(context).primary,
                              fontWeight: FontWeight.bold,
                              useGoogleFonts: GoogleFonts.asMap().containsKey(
                                  FlutterFlowTheme.of(context).bodyLargeFamily),
                            ),
                        elevation: 0.0,
                        borderRadius: BorderRadius.circular(40.0),
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
