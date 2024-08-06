import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';

class MemoryListItem extends StatefulWidget {
  final int memoryIdx;
  final ServerMemory memory;
  final Function(ServerMemory, int) updateMemory;
  final Function(ServerMemory, int) deleteMemory;

  const MemoryListItem({
    super.key,
    required this.memory,
    required this.updateMemory,
    required this.memoryIdx,
    required this.deleteMemory,
  });

  @override
  State<MemoryListItem> createState() => _MemoryListItemState();
}

class _MemoryListItemState extends State<MemoryListItem> {
  @override
  Widget build(BuildContext context) {
    Structured structured = widget.memory.structured;
    return GestureDetector(
      onTap: () async {
        MixpanelManager().memoryListItemClicked(widget.memory, widget.memoryIdx);
        var result = await Navigator.of(context).push(MaterialPageRoute(
          builder: (c) => MemoryDetailPage(memory: widget.memory),
        ));
        print('MemoryListItem: result: $result');
        if (result != null && result['deleted'] == true) widget.deleteMemory(widget.memory, widget.memoryIdx);

        // widget.updateMemory();
        // TODO: restore me (how to modify the memory details, without http request)
        // temporal prefs, ? ~ PROBABLY "most_recent_modified_memory" ~ memory json, handled in memory detail page.¬
        // reload list ~ NO
        // get memory by i ~ NO
      },
      child: Container(
        margin: const EdgeInsets.only(top: 12, left: 8, right: 8),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _getMemoryHeader(),
              const SizedBox(height: 16),
              widget.memory.discarded
                  ? const SizedBox.shrink()
                  : Text(
                      structured.title,
                      style: Theme.of(context).textTheme.titleLarge,
                      maxLines: 1,
                    ),
              widget.memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
              widget.memory.discarded
                  ? const SizedBox.shrink()
                  : Text(
                      structured.overview,
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                      maxLines: 2,
                    ),
              widget.memory.discarded
                  ? Text(
                      widget.memory.getTranscript(maxCount: 100),
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                    )
                  : const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  _getMemoryHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          widget.memory.discarded
              ? const SizedBox.shrink()
              : Text(widget.memory.structured.getEmoji(),
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
          widget.memory.structured.category.isNotEmpty && !widget.memory.discarded
              ? const SizedBox(
                  width: 12,
                )
              : const SizedBox.shrink(),
          widget.memory.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    color: widget.memory.source == MemorySource.screenpipe ? Colors.white : Colors.grey.shade800,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    widget.memory.discarded
                        ? 'Discarded'
                        : widget.memory.source == MemorySource.openglass
                            ? 'Openglass'
                            : widget.memory.source == MemorySource.screenpipe
                                ? 'Screenpipe'
                                : widget.memory.structured.category,
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                          color: widget.memory.source == MemorySource.screenpipe ? Colors.deepPurple : Colors.white,
                        ),
                    maxLines: 1,
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(
            width: 16,
          ),
          Expanded(
            child: Text(
              dateTimeFormat('MMM d, h:mm a', widget.memory.startedAt ?? widget.memory.createdAt),
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              maxLines: 1,
              textAlign: TextAlign.end,
            ),
          )
        ],
      ),
    );
  }
}
