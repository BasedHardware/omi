import 'package:friend_private/backend/storage/memories.dart';
import 'package:uuid/uuid.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'edit_memory_model.dart';

class EditMemoryWidget extends StatefulWidget {
  final Function(String)? onMemoryEdited;

  const EditMemoryWidget({
    super.key,
    this.memory,
    this.onMemoryEdited,
  });

  final MemoryRecord? memory;

  @override
  State<EditMemoryWidget> createState() => _EditMemoryWidgetState();
}

class _EditMemoryWidgetState extends State<EditMemoryWidget> {
  late EditMemoryModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => EditMemoryModel());

    _model.textController ??= TextEditingController(text: widget.memory?.structuredMemory);
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
        padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 12.0),
        child: Container(
          width: double.infinity,
          height: 500.0,
          constraints: const BoxConstraints(
            maxHeight: 800.0,
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
            padding: const EdgeInsetsDirectional.fromSTEB(8.0, 24.0, 8.0, 0.0),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  TextFormField(
                    controller: _model.textController,
                    focusNode: _model.textFieldFocusNode,
                    autofocus: true,
                    obscureText: false,
                    decoration: InputDecoration(
                      labelText: 'Edit Memory...',
                      labelStyle: FlutterFlowTheme.of(context).labelMedium,
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
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                          fontSize: 16.0,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                        ),
                    maxLines: null,
                    minLines: 1,
                    keyboardType: TextInputType.multiline,
                    validator: _model.textControllerValidator.asValidator(context),
                  ),
                  Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(24.0, 12.0, 24.0, 0.0),
                    child: Row(
                      mainAxisSize: MainAxisSize.max,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.max,
                          children: [
                            Padding(
                              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 12.0, 0.0),
                              child: FFButtonWidget(
                                onPressed: () async {
                                  Navigator.pop(context);
                                },
                                text: 'Cancel',
                                options: FFButtonOptions(
                                  height: 40.0,
                                  padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 0.0),
                                  iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                                  color: FlutterFlowTheme.of(context).secondaryBackground,
                                  textStyle: FlutterFlowTheme.of(context).bodyLarge.override(
                                        fontFamily: FlutterFlowTheme.of(context).bodyLargeFamily,
                                        color: FlutterFlowTheme.of(context).primary,
                                        fontWeight: FontWeight.bold,
                                        useGoogleFonts: GoogleFonts.asMap()
                                            .containsKey(FlutterFlowTheme.of(context).bodyLargeFamily),
                                      ),
                                  elevation: 0.0,
                                  borderRadius: BorderRadius.circular(40.0),
                                ),
                              ),
                            ),
                            if (!_model.textFieldEmpty)
                              FFButtonWidget(
                                onPressed: () async {
                                  Navigator.pop(context);
                                  if ((widget.memory != null) == true) {
                                    await MemoryStorage.updateMemory(widget.memory!.id, _model.textController.text);
                                  } else {
                                    var memory = MemoryRecord(
                                        id: const Uuid().v4(),
                                        date: DateTime.now(),
                                        rawMemory: 'User-added memory',
                                        structuredMemory: _model.textController.text,
                                        isEmpty: false,
                                        isUseless: false);
                                    await MemoryStorage.addMemory(memory);
                                    _model.createdMemoryManually = memory;
                                  }
                                  widget.onMemoryEdited?.call(_model.textController.text);
                                  setState(() {});
                                },
                                text: 'Save',
                                options: FFButtonOptions(
                                  height: 40.0,
                                  padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 0.0),
                                  iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                                  color: const Color(0xFF379700),
                                  textStyle: FlutterFlowTheme.of(context).bodyLarge.override(
                                        fontFamily: FlutterFlowTheme.of(context).bodyLargeFamily,
                                        color: FlutterFlowTheme.of(context).primary,
                                        fontWeight: FontWeight.bold,
                                        useGoogleFonts: GoogleFonts.asMap()
                                            .containsKey(FlutterFlowTheme.of(context).bodyLargeFamily),
                                      ),
                                  elevation: 0.0,
                                  borderRadius: BorderRadius.circular(40.0),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
