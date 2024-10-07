import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memories/sync_page.dart';
import 'package:friend_private/pages/memories/widgets/date_list_item.dart';
import 'package:friend_private/pages/memories/widgets/processing_capture.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

String secondsToHumanReadable(int seconds) {
  if (seconds < 60) {
    return '$seconds secs';
  } else if (seconds < 3600) {
    var minutes = (seconds / 60).floor();
    var remainingSeconds = seconds % 60;
    if (remainingSeconds == 0) {
      return '$minutes mins';
    } else {
      return '$minutes mins $remainingSeconds secs';
    }
  } else if (seconds < 86400) {
    var hours = (seconds / 3600).floor();
    var remainingMinutes = (seconds % 3600 / 60).floor();
    if (remainingMinutes == 0) {
      return '$hours hours';
    } else {
      return '$hours hours $remainingMinutes mins';
    }
  } else {
    var days = (seconds / 86400).floor();
    var remainingHours = (seconds % 86400 / 3600).floor();
    if (remainingHours == 0) {
      return '$days days';
    } else {
      return '$days days $remainingHours hours';
    }
  }
}

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
            SliverToBoxAdapter(
              child: memoryProvider.missingWals.isNotEmpty
                  ? GestureDetector(
                      onTap: () {
                        routeToPage(context, const SyncPage());
                      },
                      child: Container(
                        width: double.maxFinite,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: const BorderRadius.all(Radius.circular(12)),
                        ),
                        margin: const EdgeInsets.fromLTRB(16, 18, 16, 0),
                        padding: const EdgeInsets.all(16),
                        child: ListTile(
                          leading: const Icon(Icons.record_voice_over_rounded),
                          title: Text(
                            'You have ${secondsToHumanReadable(memoryProvider.missingWals.map((val) => val.seconds).reduce((a, b) => a + b))} of conversation locally, sync now?',
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
            const SliverToBoxAdapter(child: SizedBox(height: 26)),
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            const SliverToBoxAdapter(child: MemoryCaptureWidget()),
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
                      print('loading more memories');
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
