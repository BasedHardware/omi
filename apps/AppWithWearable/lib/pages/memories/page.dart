import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  final List<Memory> memories;
  final Function refreshMemories;
  final bool displayDiscardMemories;
  final VoidCallback toggleDiscardMemories;

  const MemoriesPage(
      {super.key,
      required this.memories,
      required this.refreshMemories,
      required this.displayDiscardMemories,
      required this.toggleDiscardMemories});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 16),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18.0),
          child: Text(
            'Welcome back.',
            style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey, fontSize: 20),
          ),
        ),
        const SizedBox(height: 16),
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text(
              widget.displayDiscardMemories ? 'Hide Discarded' : 'Show Discarded',
              style: const TextStyle(color: Colors.white, fontSize: 16),
            ),
            const SizedBox(width: 8),
            IconButton(
                onPressed: () {
                  widget.toggleDiscardMemories();
                },
                icon: Icon(
                  widget.displayDiscardMemories ? Icons.cancel_outlined : Icons.filter_list,
                  color: Colors.white,
                )),
          ],
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
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
        const SizedBox(height: 80),
      ],
    );
  }
}
