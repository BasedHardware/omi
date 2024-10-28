import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
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
  Timer? _memoryNewStatusResetTimer;
  bool isNew = false;

  @override
  void dispose() {
    _memoryNewStatusResetTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Is new memory
    DateTime memorizedAt = widget.memory.createdAt;
    if (widget.memory.finishedAt != null && widget.memory.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = widget.memory.finishedAt!;
    }
    int seconds = (DateTime.now().millisecondsSinceEpoch - memorizedAt.millisecondsSinceEpoch) ~/ 1000;
    isNew = 0 < seconds && seconds < 60; // 1m
    if (isNew) {
      _memoryNewStatusResetTimer?.cancel();
      _memoryNewStatusResetTimer = Timer(const Duration(seconds: 60), () async {
        setState(() {
          isNew = false;
        });
      });
    }

    Structured structured = widget.memory.structured;
    return Consumer<MemoryProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          MixpanelManager().memoryListItemClicked(widget.memory, widget.memoryIdx);
          context.read<MemoryDetailProvider>().updateMemory(widget.memoryIdx, widget.date);
          String startingTitle = context.read<MemoryDetailProvider>().memory.structured.title;
          provider.onMemoryTap(widget.memoryIdx);

          await routeToPage(
            context,
            MemoryDetailPage(memory: widget.memory, isFromOnboarding: widget.isFromOnboarding),
          );
          String newTitle = context.read<MemoryDetailProvider>().memory.structured.title;
          if (startingTitle != newTitle) {
            widget.memory.structured.title = newTitle;
            provider.upsertMemory(widget.memory);
          }
        },
        child: Padding(
          padding:
              EdgeInsets.only(top: 12, left: widget.isFromOnboarding ? 0 : 16, right: widget.isFromOnboarding ? 0 : 16),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(
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
                              structured.title.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            ),
                      widget.memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                      widget.memory.discarded
                          ? const SizedBox.shrink()
                          : Text(
                              structured.overview.decodeString,
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
        ),
      );
    });
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
            child: isNew
                ? const Align(
                    alignment: Alignment.centerRight,
                    child: MemoryNewStatusIndicator(text: "New 🚀"),
                  )
                : Text(
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

class MemoryNewStatusIndicator extends StatefulWidget {
  final String text;

  const MemoryNewStatusIndicator({super.key, required this.text});

  @override
  State<MemoryNewStatusIndicator> createState() => _MemoryNewStatusIndicatorState();
}

class _MemoryNewStatusIndicatorState extends State<MemoryNewStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: Text(widget.text),
    );
  }
}
