import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memories/widgets/date_list_item.dart';
import 'package:friend_private/pages/memories/widgets/processing_capture.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

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
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    print('building memories page');
    super.build(context);
    return Consumer<MemoryProvider>(builder: (context, memoryProvider, child) {
      return RefreshIndicator(
        backgroundColor: Colors.black,
        color: Colors.white,
        onRefresh: () async {
          return await memoryProvider.getInitialMemories();
        },
        child: CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 32)),
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            SliverToBoxAdapter(child: MemoryCaptureWidget(memory: memoryProvider.inProgressMemory)),
            getProcessingMemoriesWidget(memoryProvider.processingMemories),
            if (memoryProvider.groupedMemories.isEmpty && !memoryProvider.isLoadingMemories)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.only(top: 32.0),
                    child: EmptyMemoriesWidget(),
                  ),
                ),
              )
            else if (memoryProvider.groupedMemories.isEmpty && memoryProvider.isLoadingMemories)
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
                  childCount: memoryProvider.groupedMemories.length + 1,
                  (context, index) {
                    if (index == memoryProvider.groupedMemories.length) {
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
                        child: const SizedBox(height: 20, width: double.maxFinite),
                      );
                    } else {
                      var date = memoryProvider.groupedMemories.keys.elementAt(index);
                      List<ServerMemory> memoriesForDate = memoryProvider.groupedMemories[date]!;

                      return Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (index == 0) const SizedBox(height: 16),
                          DateListItem(date: date, isFirst: index == 0),
                          ...memoriesForDate.map(
                            (memory) => MemoryListItem(
                              memory: memory,
                              memoryIdx: memoryProvider.groupedMemories[date]!.indexOf(memory),
                              date: date,
                            ),
                          ),
                        ],
                      );
                    }
                  },
                ),
              ),
            const SliverToBoxAdapter(
              child: SizedBox(height: 80),
            ),
          ],
        ),
      );
    });
  }
}
