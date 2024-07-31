import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/pages/memories/widgets/date_list_item.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  final List<Memory> memories;
  final Function refreshMemories;
  final FocusNode textFieldFocusNode;

  const MemoriesPage({
    super.key,
    required this.memories,
    required this.refreshMemories,
    required this.textFieldFocusNode,
  });

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  FocusNode textFieldFocusNode = FocusNode();
  bool loading = false;
  bool displayDiscardMemories = false;

  changeLoadingState() {
    setState(() {
      loading = !loading;
    });
  }

  _toggleDiscardMemories() async {
    MixpanelManager().showDiscardedMemoriesToggled(!displayDiscardMemories);
    setState(() => displayDiscardMemories = !displayDiscardMemories);
  }

  @override
  bool get wantKeepAlive => true;

  // void _onAddButtonPressed() {
  //   MixpanelManager().addManualMemoryClicked();
  //   showDialog(
  //     context: context,
  //     builder: (BuildContext context) {
  //       return AddMemoryDialog(
  //         onMemoryAdded: (Memory memory) {
  //           widget.memories.insert(0, memory);
  //           setState(() {});
  //         },
  //       );
  //     },
  //   );
  // }

  @override
  Widget build(BuildContext context) {
    var memories =
        displayDiscardMemories ? widget.memories : widget.memories.where((memory) => !memory.discarded).toList();
    memories = textController.text.isEmpty
        ? memories
        : memories
            .where(
              (memory) => (memory.transcript + memory.structured.target!.title + memory.structured.target!.overview)
                  .toLowerCase()
                  .contains(textController.text.toLowerCase()),
            )
            .toList();

    var memoriesWithDates = [];
    for (var i = 0; i < memories.length; i++) {
      if (i == 0) {
        memoriesWithDates.add(memories[i].createdAt);
        memoriesWithDates.add(memories[i]);
      } else {
        if (memories[i].createdAt.day != memories[i - 1].createdAt.day) {
          memoriesWithDates.add(memories[i].createdAt);
        }
        memoriesWithDates.add(memories[i]);
      }
    }

    return CustomScrollView(
      slivers: [
        const SliverToBoxAdapter(child: SizedBox(height: 32)),
        SliverToBoxAdapter(
          child: Container(
            width: double.maxFinite,
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
            margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
            decoration: const BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.all(Radius.circular(16)),
              border: GradientBoxBorder(
                gradient: LinearGradient(colors: [
                  Color.fromARGB(127, 208, 208, 208),
                  Color.fromARGB(127, 188, 99, 121),
                  Color.fromARGB(127, 86, 101, 182),
                  Color.fromARGB(127, 126, 190, 236)
                ]),
                width: 1,
              ),
              shape: BoxShape.rectangle,
            ),
            child: TextField(
              enabled: true,
              controller: textController,
              onChanged: (s) {
                setState(() {});
              },
              obscureText: false,
              autofocus: false,
              focusNode: widget.textFieldFocusNode,
              decoration: InputDecoration(
                hintText: 'Search for memories...',
                hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                suffixIcon: textController.text.isEmpty
                    ? const SizedBox.shrink()
                    : IconButton(
                        icon: const Icon(
                          Icons.cancel,
                          color: Color(0xFFF7F4F4),
                          size: 28.0,
                        ),
                        onPressed: () {
                          textController.clear();
                          setState(() {});
                        },
                      ),
              ),
              style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
            ),
          ),
        ),
        const SliverToBoxAdapter(child: SizedBox(height: 16)),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // IconButton(
                //     onPressed: _onAddButtonPressed,
                //     icon: const Icon(
                //       Icons.add_circle_outline,
                //       size: 24,
                //       color: Colors.white,
                //     )),
                const SizedBox(width: 1),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Text(
                      displayDiscardMemories ? 'Hide Discarded' : 'Show Discarded',
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      onPressed: () {
                        _toggleDiscardMemories();
                      },
                      icon: Icon(
                        displayDiscardMemories ? Icons.cancel_outlined : Icons.filter_list,
                        color: Colors.white,
                      ),
                    ),
                  ],
                )
              ],
            ),
          ),
        ),
        if (memories.isEmpty)
          const SliverToBoxAdapter(
            child: Center(
              child: Padding(
                padding: EdgeInsets.only(top: 32.0),
                child: EmptyMemoriesWidget(),
              ),
            ),
          )
        else
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (context, index) {
                if (memoriesWithDates[index].runtimeType == DateTime) {
                  return DateListItem(date: memoriesWithDates[index] as DateTime, isFirst: index == 0);
                }
                return MemoryListItem(
                  memoryIdx: index,
                  memory: memoriesWithDates[index] as Memory,
                  loadMemories: widget.refreshMemories,
                );
              },
              childCount: memoriesWithDates.length,
            ),
          ),
        const SliverToBoxAdapter(
          child: SizedBox(height: 80),
        ),
      ],
    );
  }
}
