import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';
import 'package:friend_private/pages/memories/widgets/structured_memory.dart';

class MemoryListItem extends StatefulWidget {
  final MemoryRecord memory;
  final Function(MemoryRecord) playAudio;
  final Function(MemoryRecord) pauseAudio;
  final Function(MemoryRecord) resumeAudio;
  final Function(MemoryRecord) stopAudio;
  final FocusNode unFocusNode;
  final Function loadMemories;

  const MemoryListItem(
      {super.key,
      required this.memory,
      required this.unFocusNode,
      required this.playAudio,
      required this.pauseAudio,
      required this.resumeAudio,
      required this.stopAudio,
      required this.loadMemories});

  @override
  State<MemoryListItem> createState() => _MemoryListItemState();
}

class _MemoryListItemState extends State<MemoryListItem> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        debugPrint('Tapped memory: ${widget.memory.id}');
        await context.pushNamed(
          'memoryDetailPage',
          queryParameters: {
            'memory': serializeParam(
              widget.memory,
              ParamType.JSON,
            ),
          }.withoutNulls,
        );
        widget.loadMemories();
      },
      child: Container(
        margin: const EdgeInsets.only(top: 12),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: const Color(0x1AF7F4F4),
          borderRadius: BorderRadius.circular(24.0),
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.all(8),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              _getMemoryHeader(),
              getStructuredMemoryWidget(context, widget.memory),
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
          getMemoryOperations(widget.memory, widget.unFocusNode, setState),
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
