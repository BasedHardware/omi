import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class MemoryListItem extends StatefulWidget {
  final bool isFromOnboarding;
  final DateTime date;
  final int memoryIdx;
  final ServerMemory memory;

  const MemoryListItem({
    super.key,
    required this.memory,
    required this.date,
    required this.memoryIdx,
    this.isFromOnboarding = false,
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
        context.read<MemoryDetailProvider>().updateMemory(widget.memoryIdx, widget.date);
        routeToPage(
          context,
          MemoryDetailPage(memory: widget.memory, isFromOnboarding: widget.isFromOnboarding),
        );
        // if (result != null && result['deleted'] == true) widget.deleteMemory(widget.memory, widget.memoryIdx);
      },
      child: Consumer<MemoryProvider>(builder: (context, provider, child) {
        return Padding(
          padding:
              EdgeInsets.only(top: 12, left: widget.isFromOnboarding ? 0 : 16, right: widget.isFromOnboarding ? 0 : 16),
          child: Container(
            width: double.maxFinite,
            decoration: widget.memory.isNew
                ? BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                    border: Border.all(
                      color: Colors.lightBlue,
                      width: 1,
                    ))
                : BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(16.0),
                  ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16.0),
              child: Dismissible(
                key: Key(widget.memory.id),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20.0),
                  color: Colors.red,
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                onDismissed: (direction) {
                  var memory = widget.memory;
                  var memoryIdx = widget.memoryIdx;
                  provider.deleteMemoryLocally(memory, memoryIdx, widget.date);
                  ScaffoldMessenger.of(context)
                      .showSnackBar(
                        SnackBar(
                          content: const Text('Memory deleted successfully 🗑️'),
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                          action: SnackBarAction(
                            label: 'Undo',
                            textColor: Colors.white,
                            onPressed: () {
                              provider.undoDeleteMemory(memory.id, memoryIdx);
                            },
                          ),
                        ),
                      )
                      .closed
                      .then((reason) {
                    if (reason != SnackBarClosedReason.action) {
                      if (provider.memoriesToDelete.containsKey(memory.id)) {
                        provider.deleteMemoryOnServer(memory.id);
                      }
                    }
                  });
                },
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
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium!
                                  .copyWith(color: Colors.grey.shade300, height: 1.3),
                              maxLines: 2,
                            ),
                      widget.memory.discarded
                          ? Text(
                              widget.memory.getTranscript(maxCount: 100),
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium!
                                  .copyWith(color: Colors.grey.shade300, height: 1.3),
                            )
                          : const SizedBox(height: 8),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      }),
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
              ? const SizedBox(width: 12)
              : const SizedBox.shrink(),
          widget.memory.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    color: widget.memory.getTagColor(),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    widget.memory.getTag(),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: widget.memory.getTagTextColor()),
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
