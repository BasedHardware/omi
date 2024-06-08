import 'dart:math';

import 'package:flutter/material.dart';
import 'package:fonnx/onnx/ort_ffi_bindings.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/utils/temp.dart';

class MemoryListItem extends StatefulWidget {
  final int memoryIdx;
  final MemoryRecord memory;
  final Function loadMemories;

  const MemoryListItem({super.key, required this.memory, required this.loadMemories, required this.memoryIdx});

  @override
  State<MemoryListItem> createState() => _MemoryListItemState();
}

class _MemoryListItemState extends State<MemoryListItem> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        debugPrint('Tapped memory: ${widget.memory.id}');
        MixpanelManager().memoryListItemClicked(widget.memory, widget.memoryIdx);
        await Navigator.of(context).push(MaterialPageRoute(
            builder: (c) => MemoryDetailPage(
                  memory: widget.memory.toJson(),
                )));
        widget.loadMemories();
      },
      child: Container(
        margin: EdgeInsets.only(top: 12),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.all(16),
          child: !widget.memory.discarded
              ? Column(
                  mainAxisSize: MainAxisSize.max,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _getMemoryHeader(),
                    const SizedBox(height: 16),
                    Text(
                      widget.memory.structured.title,
                      style: Theme.of(context).textTheme.titleLarge,
                      maxLines: 1,
                    ),
                    SizedBox(height: 8),
                    Text(
                      widget.memory.structured.overview,
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                      maxLines: 2,
                    ),
                  ],
                )
              : Column(mainAxisSize: MainAxisSize.max, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 4.0, right: 12, top: 4),
                    child: Text(
                        widget.memory.transcript.length > 150
                            ? '${widget.memory.transcript.substring(0, 150)}...'
                            : widget.memory.transcript,
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.2)),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Text(
                        ' ~ ${dateTimeFormat('MMM d, h:mm a', widget.memory.createdAt)}',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '~',
                        style: TextStyle(color: Colors.grey.shade400),
                      ),
                      const SizedBox(width: 8),
                      widget.memory.discarded
                          ? Icon(Icons.mood_bad_outlined, color: Colors.grey.shade400, size: 18)
                          // ? const Text('Transcript')
                          : const SizedBox.shrink()
                    ],
                  ),
                  const SizedBox(height: 8),
                ]),
        ),
      ),
    );
  }

  List<Widget> _getActionItems() {
    return widget.memory.structured.actionItems.map((actionItem) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8.0),
        child: Text(
          '- $actionItem',
          style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.2),
        ),
      );
    }).toList();
  }

  _getMemoryHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
              child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(['🚀', '🤔', '📚', '🏃‍♂️', '📞'][Random().nextInt(5)],
                  style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
              const SizedBox(
                width: 12,
              ),
              Container(
                decoration: BoxDecoration(
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(16),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Text('Work', style: Theme.of(context).textTheme.bodyMedium),
              )
            ],
          )),
          const SizedBox(
            width: 8,
          ),
          Text(
            ' ~ ${dateTimeFormat('MMM d, h:mm a', widget.memory.createdAt)}',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
          )
        ],
      ),
    );
  }
}
