import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:google_fonts/google_fonts.dart';

_getBoldStyle(BuildContext context) {
  return TextStyle(
    fontWeight: FontWeight.bold,
    fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
    fontSize: FlutterFlowTheme.of(context).bodyMedium.fontSize,
  );
}

_getNormalStyle(BuildContext context) {
  return TextStyle(
    fontWeight: FontWeight.normal,
    fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
    fontSize: FlutterFlowTheme.of(context).bodyMedium.fontSize,
  );
}

getStructuredMemoryWidget(BuildContext context, MemoryRecord memory, {bool includePadding = true}) {
  List<TextSpan> buildStyledText(String text) {
    if (!text.contains('\n\nSummary:')) {
      text = text.replaceAll('\nSummary:', '\n\nSummary:');
    }
    List<TextSpan> spans = [];
    List<String> splitText = text.split('\n');
    for (String part in splitText) {
      if (part.startsWith("Title:")) {
        spans.add(TextSpan(text: part.substring(0, 6), style: _getBoldStyle(context)));
        spans.add(TextSpan(text: part.substring(6), style: _getNormalStyle(context)));
      } else if (part.startsWith("Summary:")) {
        spans.add(TextSpan(text: part.substring(0, 8), style: _getBoldStyle(context)));
        spans.add(TextSpan(text: part.substring(8), style: _getNormalStyle(context)));
      } else {
        spans.add(TextSpan(text: part, style: _getNormalStyle(context)));
      }
      // Add a newline between parts for spacing
      spans.add(TextSpan(text: '\n', style: _getNormalStyle(context)));
    }
    return spans;
  }

  String displayText = memory.structuredMemory.isEmpty || memory.structuredMemory.contains('N/A')
      ? memory.rawMemory
      : memory.structuredMemory;
  return Align(
    alignment: Alignment.centerLeft,
    child: Padding(
      padding: includePadding ? const EdgeInsetsDirectional.only(top: 8, bottom: 8, start: 4): EdgeInsets.zero,
      child: RichText(
        // SelectionArea
        textAlign: TextAlign.start,
        text: TextSpan(
          children: buildStyledText(displayText.trim()),
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                lineHeight: 1.5,
              ),
        ),
      ),
    ),
  );
}
