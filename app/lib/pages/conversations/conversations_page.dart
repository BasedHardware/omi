import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/search_result_header_widget.dart';
import 'package:omi/pages/conversations/widgets/search_widget.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_conversations.dart';
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
    return Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
      return RefreshIndicator(
        backgroundColor: Colors.black,
        color: Colors.white,
        onRefresh: () async {
          return await convoProvider.getInitialConversations();
        },
        child: CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 26)),
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            const SliverToBoxAdapter(child: ConversationCaptureWidget()),
            const SliverToBoxAdapter(child: SizedBox(height: 16)),
            const SliverToBoxAdapter(child: SearchWidget()),
            const SliverToBoxAdapter(child: SizedBox(height: 16)),
            const SliverToBoxAdapter(child: SearchResultHeaderWidget()),
            getProcessingConversationsWidget(convoProvider.processingConversations),
            if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.only(top: 32.0),
                    child: EmptyConversationsWidget(),
                  ),
                ),
              )
            else if (convoProvider.groupedConversations.isEmpty && convoProvider.isLoadingConversations)
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
                  childCount: convoProvider.groupedConversations.length + 1,
                  (context, index) {
                    if (index == convoProvider.groupedConversations.length) {
                      debugPrint('loading more conversations');
                      if (convoProvider.isLoadingConversations) {
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
                        key: const Key('conversations-key'),
                        onVisibilityChanged: (visibilityInfo) {
                          var provider = Provider.of<ConversationProvider>(context, listen: false);
                          if (provider.previousQuery.isNotEmpty) {
                            if (visibilityInfo.visibleFraction > 0 &&
                                !provider.isLoadingConversations &&
                                (provider.totalSearchPages > provider.currentSearchPage)) {
                              provider.searchMoreConversations();
                            }
                          } else {
                            if (visibilityInfo.visibleFraction > 0 && !convoProvider.isLoadingConversations) {
                              convoProvider.getMoreConversationsFromServer();
                            }
                          }
                        },
                        child: const SizedBox(height: 20, width: double.maxFinite),
                      );
                    } else {
                      var date = convoProvider.groupedConversations.keys.elementAt(index);
                      List<ServerConversation> memoriesForDate = convoProvider.groupedConversations[date]!;
                      return Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (index == 0) const SizedBox(height: 10),
                          ConversationsGroupWidget(
                            isFirst: index == 0,
                            conversations: memoriesForDate,
                            date: date,
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
