import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';

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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _getMemoryHeader(),
              const SizedBox(height: 12),
              Text(widget.memory.structured.overview,
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.2)),
              if (widget.memory.structured.actionItems.isNotEmpty) ...[
                const SizedBox(height: 20),
                const Text('Action Items:',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                ..._getActionItems(),
              ],
              const SizedBox(height: 8),
              Text(
                ' ~ ${dateTimeFormat('MMM d, h:mm a', widget.memory.createdAt)}',
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              ),
              const SizedBox(height: 8),
            ],
          ),
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
      padding: const EdgeInsets.only(left: 4.0, right: 12, top: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
              child: Text(widget.memory.structured.title,
                  style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600))),
          getMemoryOperations(widget.memory, setState),
        ],
      ),
    );
  }
}
