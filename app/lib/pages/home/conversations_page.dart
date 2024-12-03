import 'package:flutter/material.dart';
import 'package:flutter_svg/svg.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:friend_private/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:friend_private/pages/conversations/widgets/empty_conversations.dart';
import 'package:friend_private/pages/conversations/widgets/processing_capture.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

class ConversationsPage extends StatelessWidget {
  const ConversationsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      onPopInvoked: (didPop) {
        context.read<ConversationProvider>().clearQueryAndCategory();
      },
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Conversations'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        body: Consumer<ConversationProvider>(
          builder: (context, convoProvider, child) {
            return RefreshIndicator(
              backgroundColor: Colors.black,
              color: Colors.white,
              onRefresh: () async {
                return await convoProvider.getInitialConversations();
              },
              child: CustomScrollView(
                slivers: [
                  SliverToBoxAdapter(
                      child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          height: 56,
                          width: MediaQuery.of(context).size.width * 0.76,
                          child: TextFormField(
                            onChanged: (value) {
                              convoProvider.searchConversations(value);
                            },
                            decoration: InputDecoration(
                              hintText: 'Search Conversations',
                              hintStyle: const TextStyle(color: Colors.white),
                              filled: true,
                              fillColor: Colors.grey[800],
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: BorderSide.none,
                              ),
                              // suffixIcon: GestureDetector(
                              //   onTap: () {},
                              //   child: const Icon(
                              //     Icons.close,
                              //     color: Colors.white,
                              //   ),
                              // ),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12),
                            ),
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                        const SizedBox(width: 10),
                        InkWell(
                          onTap: () {},
                          child: Container(
                            height: 48,
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.grey[800],
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: SvgPicture.asset(Assets.images.icCalendarSearch, width: 32, height: 32),
                          ),
                        ),
                        const SizedBox(width: 6),
                      ],
                    ),
                  )),
                  SliverToBoxAdapter(
                    child: Container(
                      height: 55,
                      margin: const EdgeInsets.only(bottom: 16),
                      padding: EdgeInsets.only(left: 10),
                      child: ListView(
                        shrinkWrap: true,
                        scrollDirection: Axis.horizontal,
                        children: convoProvider.convoCategories
                            .map(
                              (category) => Padding(
                                padding: const EdgeInsets.only(left: 8.0),
                                child: ChoiceChip(
                                  label: Text(category.capitalize()),
                                  selected: convoProvider.isCategorySelected(category),
                                  showCheckmark: true,
                                  backgroundColor: Colors.transparent,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  onSelected: (bool selected) {
                                    if (selected) {
                                      convoProvider.selectCategory(category);
                                    } else {
                                      convoProvider.deselectCategory();
                                    }
                                  },
                                ),
                              ),
                            )
                            .toList(),
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
                        childCount: convoProvider.groupedConversations.length + 1,
                        (context, index) {
                          if (index == convoProvider.groupedConversations.length) {
                            print('loading more conversations');
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
                              key: const Key('old-key'),
                              onVisibilityChanged: (visibilityInfo) {
                                if (visibilityInfo.visibleFraction > 0 && !convoProvider.isLoadingConversations) {
                                  if (convoProvider.queryAlreadyFetched) {
                                    print('query already fetched');
                                    return;
                                  } else {
                                    convoProvider.getMoreConversationsFromServer();
                                  }
                                }
                              },
                              child: const SizedBox(height: 20, width: double.maxFinite),
                            );
                          } else {
                            var date = convoProvider.groupedConversations.keys.elementAt(index);
                            List<ServerConversation> memoriesForDate = convoProvider.groupedConversations[date]!;
                            bool hasDiscarded = memoriesForDate.any((element) => element.discarded);
                            bool hasNonDiscarded = memoriesForDate.any((element) => !element.discarded);

                            return Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                ConversationsGroupWidget(
                                  isFirst: index == 0,
                                  conversations: memoriesForDate,
                                  date: date,
                                  hasNonDiscardedMemories: hasNonDiscarded,
                                  showDiscardedMemories: convoProvider.showDiscardedConversations,
                                  hasDiscardedMemories: hasDiscarded,
                                ),
                              ],
                            );
                          }
                        },
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
