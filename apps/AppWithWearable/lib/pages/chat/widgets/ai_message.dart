import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:google_fonts/google_fonts.dart';

class AIMessage extends StatelessWidget {
  final Message message;
  // final VoidCallback onShowMemoriesPressed;

  // const AIMessage({
  //   Key? key,
  //   required this.message,
  //   required this.onShowMemoriesPressed,
  // }) : super(key: key);

    const AIMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    // return Column(
    //   crossAxisAlignment: CrossAxisAlignment.start,
      return Row(
      mainAxisSize: MainAxisSize.max,
      children: [
        Column(
          mainAxisSize: MainAxisSize.max,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              constraints: BoxConstraints(
                maxWidth: () {
                  if (MediaQuery.sizeOf(context).width >= 1170.0) {
                    return 700.0;
                  } else if (MediaQuery.sizeOf(context).width <= 470.0) {
                    return 330.0;
                  } else {
                    return 530.0;
                  }
                }(),
              ),
              decoration: BoxDecoration(
                color: const Color(0x1AF7F4F4),
                boxShadow: const [
                  BoxShadow(
                    blurRadius: 3.0,
                    color: Color(0x33000000),
                    offset: Offset(0.0, 1.0),
                  )
                ],
                borderRadius: BorderRadius.circular(12.0),
                border: Border.all(
                  color: FlutterFlowTheme.of(context).primary,
                  width: 1.0,
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectionArea(
                        child: AutoSizeText(
                      message.text.replaceAll(r'\n', '\n'),
                      style: FlutterFlowTheme.of(context).titleMedium.override(
                            fontFamily: FlutterFlowTheme.of(context).titleMediumFamily,
                            color: FlutterFlowTheme.of(context).secondary,
                            fontSize: 14.0,
                            fontWeight: FontWeight.w500,
                            useGoogleFonts:
                                GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleMediumFamily),
                            lineHeight: 1.5,
                          ),
                    )),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
              child: InkWell(
                splashColor: Colors.transparent,
                focusColor: Colors.transparent,
                hoverColor: Colors.transparent,
                highlightColor: Colors.transparent,
                onTap: () async {
                  await Clipboard.setData(ClipboardData(text: message.text));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        'Response copied to clipboard.',
                        style: FlutterFlowTheme.of(context).bodyMedium.override(
                              fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                              color: Color.fromARGB(255, 255, 255, 255),
                              fontSize: 12.0,
                              useGoogleFonts:
                                  GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                            ),
                      ),
                      duration: const Duration(milliseconds: 2000),
                      backgroundColor: const Color.fromARGB(255, 70, 70, 70),
                    ),
                  );
                },
                child: Row(
                  mainAxisSize: MainAxisSize.max,
                  children: [
                    Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 4.0, 0.0),
                      child: Icon(
                        Icons.content_copy,
                        color: FlutterFlowTheme.of(context).primary,
                        size: 10.0,
                      ),
                    ),
                    Text(
                      'Copy response',
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                            fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                            color: FlutterFlowTheme.of(context).primary,
                            fontSize: 10.0,
                            useGoogleFonts:
                                GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        // ),
        // if (message.memoryIds != null && message.memoryIds!.isNotEmpty)
        //   ElevatedButton(
        //     onPressed: onShowMemoriesPressed,
        //     child: const Text('Show Memories'),
          ),
      ],
    );
  }
}