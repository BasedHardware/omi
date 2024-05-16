import 'dart:ui';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:share_plus/share_plus.dart';

import 'confirm_deletion_widget.dart';
import 'edit_memory_widget.dart';

class MemoryListItem extends StatefulWidget {
  final MemoryRecord memory;
  final Function(MemoryRecord) playAudio;
  final Function(MemoryRecord) pauseAudio;
  final Function(MemoryRecord) resumeAudio;
  final Function(MemoryRecord) stopAudio;
  final FocusNode unFocusNode;

  const MemoryListItem(
      {super.key,
      required this.memory,
      required this.unFocusNode,
      required this.playAudio,
      required this.pauseAudio,
      required this.resumeAudio,
      required this.stopAudio});

  @override
  State<MemoryListItem> createState() => _MemoryListItemState();
}

class _MemoryListItemState extends State<MemoryListItem> {
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 12),
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0x1AF7F4F4),
        borderRadius: BorderRadius.circular(24.0),
      ),
      child: Padding(
        padding: const EdgeInsetsDirectional.all(8),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              _getMemoryHeader(),
              _getMemoryText(),
              _noInsightsWidget(),
              // _getAudioPlayer(),
            ],
          ),
        ),
      ),
    );
  }

  _noInsightsWidget() {
    return widget.memory.isUseless
        ? const Padding(
            padding: EdgeInsets.only(left: 8, bottom: 4),
            child: Align(
              alignment: Alignment.bottomLeft,
              child: Text(
                'No insights',
                style: TextStyle(color: Colors.red, decoration: TextDecoration.underline),
              ),
            ),
          )
        : const SizedBox.shrink();
  }

  _getBoldStyle() {
    return TextStyle(
      fontWeight: FontWeight.bold,
      fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
      fontSize: FlutterFlowTheme.of(context).bodyMedium.fontSize,
    );
  }

  _getNormalStyle() {
    return TextStyle(
      fontWeight: FontWeight.normal,
      fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
      fontSize: FlutterFlowTheme.of(context).bodyMedium.fontSize,
    );
  }

  _getMemoryText() {
    List<TextSpan> buildStyledText(String text) {
      if (!text.contains('\n\nSummary:')) {
        text = text.replaceAll('\nSummary:', '\n\nSummary:');
      }
      List<TextSpan> spans = [];
      List<String> splitText = text.split('\n');
      for (String part in splitText) {
        if (part.startsWith("Title:")) {
          spans.add(TextSpan(text: part.substring(0, 6), style: _getBoldStyle()));
          spans.add(TextSpan(text: part.substring(6), style: _getNormalStyle()));
        } else if (part.startsWith("Summary:")) {
          spans.add(TextSpan(text: part.substring(0, 8), style: _getBoldStyle()));
          spans.add(TextSpan(text: part.substring(8), style: _getNormalStyle()));
        } else {
          spans.add(TextSpan(text: part, style: _getNormalStyle()));
        }
        // Add a newline between parts for spacing
        spans.add(TextSpan(text: '\n', style: _getNormalStyle()));
      }
      return spans;
    }

    String displayText = widget.memory.structuredMemory.isEmpty || widget.memory.structuredMemory.contains('N/A')
        ? widget.memory.rawMemory
        : widget.memory.structuredMemory;
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsetsDirectional.only(top: 8, bottom: 8, start: 4),
        child: SelectionArea(
          child: RichText(
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
      ),
    );
  }

  _getMemoryHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12, top: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            dateTimeFormat('MMM d, h:mm a', widget.memory.date),
            style: FlutterFlowTheme.of(context).bodyLarge,
          ),
          _getOperations(),
        ],
      ),
    );
  }

  _getOperations() {
    return Container(
      padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF515253),
        borderRadius: BorderRadius.circular(24.0),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Builder(
            builder: (context) => Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 10.0, 0.0),
              child: InkWell(
                splashColor: Colors.transparent,
                focusColor: Colors.transparent,
                hoverColor: Colors.transparent,
                highlightColor: Colors.transparent,
                onTap: () async {
                  await Share.share(
                    '${widget.memory.structuredMemory}  Created with https://www.aisama.co/',
                    sharePositionOrigin: getWidgetBoundingBox(context),
                  );
                  HapticFeedback.lightImpact();
                },
                child: FaIcon(
                  FontAwesomeIcons.share,
                  color: FlutterFlowTheme.of(context).secondaryText,
                  size: 20.0,
                ),
              ),
            ),
          ),
          Builder(
            builder: (context) => InkWell(
              splashColor: Colors.transparent,
              focusColor: Colors.transparent,
              hoverColor: Colors.transparent,
              highlightColor: Colors.transparent,
              onTap: () async {
                await showDialog(
                  context: context,
                  builder: (dialogContext) {
                    return Dialog(
                      elevation: 0,
                      insetPadding: EdgeInsets.zero,
                      backgroundColor: Colors.transparent,
                      alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                      child: GestureDetector(
                        onTap: () => widget.unFocusNode.canRequestFocus
                            ? FocusScope.of(context).requestFocus(widget.unFocusNode)
                            : FocusScope.of(context).unfocus(),
                        child: EditMemoryWidget(
                          memory: widget.memory,
                        ),
                      ),
                    );
                  },
                ).then((value) => setState(() {}));
              },
              child: Icon(
                Icons.edit,
                color: FlutterFlowTheme.of(context).secondaryText,
                size: 20.0,
              ),
            ),
          ),
          Builder(
            builder: (context) => Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(10.0, 0.0, 0.0, 0.0),
              child: InkWell(
                splashColor: Colors.transparent,
                focusColor: Colors.transparent,
                hoverColor: Colors.transparent,
                highlightColor: Colors.transparent,
                onTap: () async {
                  await showDialog(
                    context: context,
                    builder: (dialogContext) {
                      return Dialog(
                        elevation: 0,
                        insetPadding: EdgeInsets.zero,
                        backgroundColor: Colors.transparent,
                        alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                        child: GestureDetector(
                          onTap: () => widget.unFocusNode.canRequestFocus
                              ? FocusScope.of(context).requestFocus(widget.unFocusNode)
                              : FocusScope.of(context).unfocus(),
                          child: ConfirmDeletionWidget(
                            memory: widget.memory,
                          ),
                        ),
                      );
                    },
                  ).then((value) => setState(() {}));
                },
                child: Icon(
                  Icons.delete,
                  color: FlutterFlowTheme.of(context).secondaryText,
                  size: 20.0,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  _getAudioPlayer() {
    return (widget.memory.audioFileName?.isNotEmpty ?? false)
        ? Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('Recording:'),
              IconButton(
                icon: Icon(widget.memory.playerState == PlayerState.playing ? Icons.pause : Icons.play_arrow),
                onPressed: widget.memory.playerState == PlayerState.playing
                    ? () => widget.pauseAudio(widget.memory)
                    : widget.memory.playerState == PlayerState.paused
                        ? () => widget.resumeAudio(widget.memory)
                        : () => widget.playAudio(widget.memory),
              ),
              widget.memory.playerState != PlayerState.stopped
                  ? IconButton(
                      icon: const Icon(Icons.stop),
                      onPressed: widget.memory.playerState != PlayerState.stopped
                          ? () => widget.stopAudio(widget.memory)
                          : null,
                    )
                  : Container(),
            ],
          )
        : Container();
  }
}
