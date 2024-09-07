import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memories/widgets/date_list_item.dart';
import 'package:friend_private/pages/memories/widgets/processing_capture.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({
    super.key,
  });

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (Provider.of<MemoryProvider>(context, listen: false).memories.isEmpty) {
        await Provider.of<MemoryProvider>(context, listen: false).getInitialMemories();
      }
      // if (mounted) {
      //   Provider.of<MemoryProvider>(context, listen: false).initFilteredMemories();
      // }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    print('building memories page');
    super.build(context);
    return Consumer<MemoryProvider>(builder: (context, memoryProvider, child) {
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
              child: Consumer<HomeProvider>(builder: (context, home, child) {
                return TextField(
                  enabled: true,
                  controller: textController,
                  onChanged: (s) {
                    memoryProvider.filterMemories(s);
                  },
                  obscureText: false,
                  autofocus: false,
                  focusNode: home.memoryFieldFocusNode,
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
                              memoryProvider.initFilteredMemories();
                            },
                          ),
                  ),
                  style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
                );
              }),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const SizedBox(width: 1),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Text(
                        memoryProvider.displayDiscardMemories ? 'Hide Discarded' : 'Show Discarded',
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: () {
                          memoryProvider.toggleDiscardMemories();
                        },
                        icon: Icon(
                          memoryProvider.displayDiscardMemories ? Icons.cancel_outlined : Icons.filter_list,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  )
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: getMemoryCaptureWidget(),
          ),
          if (memoryProvider.memoriesWithDates.isEmpty && !memoryProvider.isLoadingMemories)
            const SliverToBoxAdapter(
              child: Center(
                child: Padding(
                  padding: EdgeInsets.only(top: 32.0),
                  child: EmptyMemoriesWidget(),
                ),
              ),
            )
          else if (memoryProvider.memoriesWithDates.isEmpty && memoryProvider.isLoadingMemories)
            const SliverToBoxAdapter(
              child: Center(
                child: Padding(
                  padding: EdgeInsets.only(top: 32.0),
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                ),
              ),
            )
          else
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (context, index) {
                  if (index == memoryProvider.memoriesWithDates.length) {
                    if (memoryProvider.isLoadingMemories) {
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.only(top: 32.0),
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        ),
                      );
                    }
                    // widget.loadMoreMemories(); // CALL this only when visible
                    return VisibilityDetector(
                      key: const Key('memory-loader'),
                      onVisibilityChanged: (visibilityInfo) {
                        if (visibilityInfo.visibleFraction > 0 && !memoryProvider.isLoadingMemories) {
                          memoryProvider.getMoreMemoriesFromServer();
                        }
                      },
                      child: const SizedBox(height: 80, width: double.maxFinite),
                    );
                  }

                  if (memoryProvider.memoriesWithDates[index].runtimeType == DateTime) {
                    return DateListItem(date: memoryProvider.memoriesWithDates[index] as DateTime, isFirst: index == 0);
                  }
                  var memory = memoryProvider.memoriesWithDates[index] as ServerMemory;
                  return MemoryListItem(
                    memoryIdx: memoryProvider.memoriesWithDates.indexOf(memory),
                    memory: memory,
                    updateMemory: memoryProvider.updateMemory,
                    deleteMemory: memoryProvider.deleteMemory,
                  );
                },
                childCount: memoryProvider.memoriesWithDates.length + 1,
              ),
            ),
          const SliverToBoxAdapter(
            child: SizedBox(height: 80),
          ),
        ],
      );
    });
  }
}
