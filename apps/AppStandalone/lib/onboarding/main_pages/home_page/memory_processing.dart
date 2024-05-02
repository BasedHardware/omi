import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sama/flutter_flow/flutter_flow_theme.dart';

class MemoryProcessing extends StatelessWidget {
  const MemoryProcessing({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
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
                        MediaQuery
                            .sizeOf(context)
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
                            FlutterFlowTheme
                                .of(context)
                                .bodyMedium
                                .override(
                              fontFamily:
                              FlutterFlowTheme
                                  .of(
                                  context)
                                  .bodyMediumFamily,
                              fontSize: 16.0,
                              fontWeight:
                              FontWeight.w500,
                              useGoogleFonts: GoogleFonts
                                  .asMap()
                                  .containsKey(
                                  FlutterFlowTheme
                                      .of(
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
    );
  }
}
