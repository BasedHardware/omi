import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class SyncedMemoryListItem extends StatefulWidget {
  final DateTime date;
  final int memoryIdx;
  final ServerMemory memory;
  final bool showReprocess;

  const SyncedMemoryListItem({
    super.key,
    required this.memory,
    required this.date,
    required this.memoryIdx,
    this.showReprocess = false,
  });

  @override
  State<SyncedMemoryListItem> createState() => _SyncedMemoryListItemState();
}

class _SyncedMemoryListItemState extends State<SyncedMemoryListItem> {
  bool isReprocessing = false;
  late ServerMemory memory;

  void setReprocessing(bool value) {
    isReprocessing = value;
    setState(() {});
  }

  @override
  void initState() {
    setState(() {
      memory = widget.memory;
    });
    super.initState();
  }

  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Is new memory
    DateTime memorizedAt = memory.createdAt;
    if (memory.finishedAt != null && memory.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = memory.finishedAt!;
    }

    return GestureDetector(
      onTap: () async {
        context.read<MemoryDetailProvider>().updateMemory(widget.memoryIdx, widget.date);
        Provider.of<MemoryProvider>(context, listen: false).onMemoryTap(widget.memoryIdx);
        routeToPage(
          context,
          MemoryDetailPage(memory: widget.memory, isFromOnboarding: false),
        );
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: BorderRadius.circular(16.0),
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.all(16),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _getMemoryHeader(),
                      const SizedBox(height: 16),
                      memory.discarded
                          ? Text(
                              memory.transcriptSegments.first.text.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            )
                          : Text(
                              memory.structured.title.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            ),
                      memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                    ],
                  ),
                ),
                widget.showReprocess || memory.discarded
                    ? GestureDetector(
                        onTap: () async {
                          setReprocessing(true);
                          var mem = await reProcessMemoryServer(memory.id);
                          if (mem != null) {
                            setState(() {
                              memory = mem;
                            });
                            context.read<MemoryProvider>().updateSyncedMemory(mem);
                          }
                          setReprocessing(false);
                        },
                        child: isReprocessing
                            ? const Center(
                                child: Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(
                                      color: Colors.white,
                                    ),
                                  ),
                                ),
                              )
                            : Padding(
                                padding: const EdgeInsets.all(8.0),
                                child: Icon(
                                  Icons.refresh_outlined,
                                  color: Colors.grey.shade400,
                                ),
                              ),
                      )
                    : const SizedBox.shrink(),
              ],
            ),
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
          memory.discarded
              ? const SizedBox.shrink()
              : Text(memory.structured.getEmoji(),
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
          memory.structured.category.isNotEmpty && !memory.discarded
              ? const SizedBox(width: 12)
              : const SizedBox.shrink(),
          memory.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    color: memory.getTagColor(),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    memory.getTag(),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: memory.getTagTextColor()),
                    maxLines: 1,
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(
            width: 16,
          ),
          Expanded(
            child: Text(
              dateTimeFormat('MMM d, h:mm a', memory.startedAt ?? memory.createdAt),
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
