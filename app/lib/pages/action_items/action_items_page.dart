import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'widgets/action_item_title_widget.dart';
import 'widgets/convo_action_items_group_widget.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  bool _showGroupedView = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Initial data load handled by ConversationProvider
    });
  }

  // Get all action items as a flat list
  List<ActionItemData> _getFlattenedActionItems(Map<ServerConversation, List<ActionItem>> itemsByConversation) {
    final result = <ActionItemData>[];

    for (final entry in itemsByConversation.entries) {
      for (final item in entry.value) {
        result.add(
          ActionItemData(
            actionItem: item,
            conversation: entry.key,
            itemIndex: entry.key.structured.actionItems.indexOf(item),
          ),
        );
      }
    }

    // Sort by completion status (incomplete first)
    result.sort((a, b) {
      if (a.actionItem.completed == b.actionItem.completed) return 0;
      return a.actionItem.completed ? 1 : -1;
    });

    return result;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<ConversationProvider>(
      builder: (context, convoProvider, child) {
        final Map<ServerConversation, List<ActionItem>> itemsByConversation =
            convoProvider.conversationsWithActiveActionItems;

        // Sort conversations by date (most recent first)
        final sortedEntries = itemsByConversation.entries.toList()
          ..sort((a, b) => b.key.createdAt.compareTo(a.key.createdAt));

        // Get flattened list for non-grouped view
        final flattenedItems = _getFlattenedActionItems(itemsByConversation);

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // Main Content
              if (convoProvider.isLoadingConversations && sortedEntries.isEmpty)
                const SliverFillRemaining(
                  child: Center(
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  ),
                )
              else if (sortedEntries.isEmpty)
                SliverFillRemaining(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24.0),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.check_circle_outline,
                            size: 72,
                            color: Colors.grey.shade400,
                          ),
                          const SizedBox(height: 24),
                          Text(
                            'No Action Items',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.bold,
                                ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Tasks and to-dos from your conversations will appear here once they are created.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 16,
                              height: 1.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              else
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16.0, 24.0, 16.0, 0.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'To-Do\'s (${flattenedItems.where((item) => !item.actionItem.completed).length})',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 24,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Row(
                              children: [
                                // Settings button
                                // TODO: Add settings once we have more stuff for action items
                                // Container(
                                //   width: 44,
                                //   height: 44,
                                //   margin: const EdgeInsets.only(right: 8),
                                //   decoration: BoxDecoration(
                                //     color: Colors.grey.shade700.withOpacity(0.3),
                                //     borderRadius: BorderRadius.circular(12),
                                //   ),
                                //   child: IconButton(
                                //     icon: const Icon(Icons.tune, size: 20),
                                //     color: Colors.white,
                                //     onPressed: () {
                                //       // Filter settings
                                //     },
                                //   ),
                                // ),
                                // Group/Ungroup toggle button
                                Container(
                                  width: 44,
                                  height: 44,
                                  decoration: BoxDecoration(
                                    color: _showGroupedView
                                        ? Colors.deepPurpleAccent.withOpacity(0.3)
                                        : Colors.grey.shade700.withOpacity(0.3),
                                    borderRadius: BorderRadius.circular(12),
                                    border: _showGroupedView
                                        ? Border.all(color: Colors.deepPurpleAccent, width: 1.5)
                                        : null,
                                  ),
                                  child: IconButton(
                                    icon: Icon(
                                      _showGroupedView ? Icons.view_agenda_outlined : Icons.view_list_outlined,
                                      size: 20,
                                    ),
                                    color: _showGroupedView ? Colors.deepPurpleAccent : Colors.white,
                                    onPressed: () {
                                      setState(() {
                                        _showGroupedView = !_showGroupedView;
                                      });
                                    },
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                ),

              if (sortedEntries.isNotEmpty)
                _showGroupedView ? _buildGroupedView(sortedEntries) : _buildFlatView(flattenedItems),

              if (sortedEntries.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16.0, 24.0, 16.0, 8.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Row(
                              children: [
                                const Text(
                                  'Completed',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.grey[800],
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Text(
                                    '${flattenedItems.where((item) => item.actionItem.completed).length}',
                                    style: const TextStyle(
                                      color: Colors.grey,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            Text(
                              'Hide',
                              style: TextStyle(
                                color: Colors.grey.shade400,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

              if (sortedEntries.isNotEmpty && flattenedItems.any((item) => item.actionItem.completed))
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final completedItems = flattenedItems.where((item) => item.actionItem.completed).toList();
                      if (index < completedItems.length) {
                        final item = completedItems[index];
                        // Simple container for proper spacing
                        return Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                          child: ActionItemTileWidget(
                            actionItem: item.actionItem,
                            conversationId: item.conversation.id,
                            itemIndexInConversation: item.itemIndex,
                          ),
                        );
                      }
                      return null;
                    },
                    childCount: flattenedItems.where((item) => item.actionItem.completed).length,
                  ),
                )
              else if (sortedEntries.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16.0),
                    child: Container(
                      height: 52,
                      decoration: BoxDecoration(
                        color: Colors.grey[900],
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Center(
                        child: Text(
                          'No completed items yet',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 14,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),

              const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGroupedView(List<MapEntry<ServerConversation, List<ActionItem>>> sortedEntries) {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final entry = sortedEntries[index];
          return ConversationActionItemsGroupWidget(
            conversation: entry.key,
            actionItems: entry.value,
          );
        },
        childCount: sortedEntries.length,
      ),
    );
  }

  Widget _buildFlatView(List<ActionItemData> items) {
    final incompleteItems = items.where((item) => !item.actionItem.completed).toList();

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final item = incompleteItems[index];
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: ActionItemTileWidget(
              actionItem: item.actionItem,
              conversationId: item.conversation.id,
              itemIndexInConversation: item.itemIndex,
            ),
          );
        },
        childCount: incompleteItems.length,
      ),
    );
  }
}

class ActionItemData {
  final ActionItem actionItem;
  final ServerConversation conversation;
  final int itemIndex;

  ActionItemData({
    required this.actionItem,
    required this.conversation,
    required this.itemIndex,
  });
}
