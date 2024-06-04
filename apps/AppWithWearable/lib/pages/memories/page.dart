import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

import 'package:flutter/material.dart';
import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  final List<MemoryRecord> memories;
  final Function refreshMemories;

  const MemoriesPage({super.key, required this.memories, required this.refreshMemories});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> {
  String? dailySummary;
  String? weeklySummary;
  String? monthlySummary;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        const BlurBotWidget(),
        ListView(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: (widget.memories.isEmpty)
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.only(top: 32.0),
                        child: EmptyMemoriesWidget(),
                      ),
                    )
                  : ListView.builder(
                      itemCount: widget.memories.length,
                      primary: false,
                      shrinkWrap: true,
                      scrollDirection: Axis.vertical,
                      itemBuilder: (context, index) {
                        return MemoryListItem(
                          memoryIdx: index,
                          memory: widget.memories[index],
                          loadMemories: widget.refreshMemories,
                        );
                      },
                    ),
            ),
          ],
        )
      ],
    );
  }
}
