import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/conversations/widgets/local_sync.dart';
import 'package:friend_private/pages/conversations/widgets/processing_capture.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_memories.dart';
import 'widgets/conversations_group_widget.dart';

class ConversationsPage extends StatefulWidget {
  const ConversationsPage({super.key});

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (Provider.of<ConversationProvider>(context, listen: false).conversations.isEmpty) {
        await Provider.of<ConversationProvider>(context, listen: false).getInitialConversations();
      }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('building conversations page');
    super.build(context);
    return Consumer<ConversationProvider>(builder: (context, memoryProvider, child) {
      return RefreshIndicator(
        backgroundColor: Colors.black,
        color: Colors.white,
        onRefresh: () async {
          return await memoryProvider.getInitialConversations();
        },
        child: CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 26)),
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            const SliverToBoxAdapter(child: LocalSyncWidget()),
            const SliverToBoxAdapter(child: MemoryCaptureWidget()),
            getProcessingConversationsWidget(memoryProvider.processingConversations),
            if (memoryProvider.groupedConversations.isEmpty && !memoryProvider.isLoadingConversations)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.only(top: 32.0),
                    child: EmptyMemoriesWidget(),
                  ),
                ),
              )
            else if (memoryProvider.groupedConversations.isEmpty && memoryProvider.isLoadingConversations)
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
                  childCount: memoryProvider.groupedConversations.length + 1,
                  (context, index) {
                    if (index == memoryProvider.groupedConversations.length) {
                      print('loading more conversations');
                      if (memoryProvider.isLoadingConversations) {
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
                          if (visibilityInfo.visibleFraction > 0 && !memoryProvider.isLoadingConversations) {
                            memoryProvider.getMoreConversationsFromServer();
                          }
                        },
                        child: const SizedBox(height: 20, width: double.maxFinite),
                      );
                    } else {
                      var date = memoryProvider.groupedConversations.keys.elementAt(index);
                      List<ServerConversation> memoriesForDate = memoryProvider.groupedConversations[date]!;
                      bool hasDiscarded = memoriesForDate.any((element) => element.discarded);
                      bool hasNonDiscarded = memoriesForDate.any((element) => !element.discarded);

                      return Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (index == 0) const SizedBox(height: 16),
                          ConversationsgroupWidget(
                            isFirst: index == 0,
                            memories: memoriesForDate,
                            date: date,
                            hasNonDiscardedMemories: hasNonDiscarded,
                            showDiscardedMemories: memoryProvider.showDiscardedConversations,
                            hasDiscardedMemories: hasDiscarded,
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
