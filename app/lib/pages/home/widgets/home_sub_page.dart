import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/conversations/widgets/conversation_list_item.dart';
import 'package:friend_private/pages/conversations/widgets/empty_conversations.dart';
import 'package:friend_private/pages/conversations/widgets/local_sync.dart';
import 'package:friend_private/pages/conversations/widgets/processing_capture.dart';
import 'package:friend_private/pages/home/conversations_page.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class HomeSubPage extends StatefulWidget {
  const HomeSubPage({super.key});

  @override
  State<HomeSubPage> createState() => _HomeSubPageState();
}

class _HomeSubPageState extends State<HomeSubPage> {
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
            const SliverToBoxAdapter(child: LocalSyncWidget()),
            const SliverToBoxAdapter(child: MemoryCaptureWidget()),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(8.0, 16, 8, 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    InkWell(
                      onTap: () {
                        routeToPage(context, ConversationsPage());
                      },
                      child: Container(
                        width: MediaQuery.sizeOf(context).width * 0.44,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(12.0),
                        ),
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SvgPicture.asset(Assets.images.icConvo, width: 42, height: 42),
                            const SizedBox(height: 10),
                            const Text("Conversations", style: TextStyle(color: Colors.white, fontSize: 16)),
                            const SizedBox(height: 6),
                            Text(
                              "Manage your conversations",
                              style: TextStyle(color: Colors.grey.shade200, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Container(
                      width: MediaQuery.sizeOf(context).width * 0.44,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(12.0),
                      ),
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SvgPicture.asset(Assets.images.icCheck, width: 42, height: 42),
                          const SizedBox(height: 10),
                          const Text("Action Items", style: TextStyle(color: Colors.white, fontSize: 16)),
                          const SizedBox(height: 6),
                          Text(
                            "Review and complete tasks",
                            style: TextStyle(color: Colors.grey.shade200, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    const Text(
                      'Recent Conversations',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Container(
                        height: 1,
                        color: Colors.grey.shade800,
                      ),
                    )
                  ],
                ),
              ),
            ),
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
                  childCount: convoProvider.recentConversations.length,
                  (context, index) {
                    return ConversationListItem(
                      memory: convoProvider.recentConversations[index].$3,
                      memoryIdx: convoProvider.recentConversations[index].$2,
                      date: convoProvider.recentConversations[index].$1,
                    );
                  },
                ),
              ),
            const SliverToBoxAdapter(
              child: SizedBox(height: 120),
            ),
          ],
        ),
      );
    });
  }
}
