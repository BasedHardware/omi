import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'widgets/action_item_tile_widget.dart';
import 'widgets/action_item_shimmer_widget.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/platform/platform_service.dart';

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  bool _showGroupedView = false;
  final ScrollController _scrollController = ScrollController();
  Set<String> _exportedToAppleReminders = <String>{};

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      MixpanelManager().actionItemsPageOpened();
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      if (provider.actionItems.isEmpty) {
        provider.fetchActionItems(showShimmer: true);
      }
      _checkExistingAppleReminders();
    });
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _checkExistingAppleReminders() async {
    if (!PlatformService.isApple) return;

    try {
      final service = AppleRemindersService();
      final existingReminders = await service.getExistingReminders();

      if (mounted) {
        setState(() {
          _exportedToAppleReminders = existingReminders.toSet();
        });
      }
    } catch (e) {
      print('Error checking existing Apple Reminders: $e');
    }
  }

  void _onScroll() {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      if (!provider.isFetching && provider.hasMore) {
        provider.loadMoreActionItems();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        // Get incomplete and complete items
        final incompleteItems = provider.incompleteItems;
        final completedItems = provider.completedItems;

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: RefreshIndicator(
            onRefresh: () => provider.forceRefreshActionItems(),
            color: Colors.deepPurpleAccent,
            backgroundColor: Colors.white,
            child: CustomScrollView(
              controller: _scrollController,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
              // Main Content
              if (provider.isLoading && provider.actionItems.isEmpty) ...[
                // Header shimmer
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16.0, 24.0, 16.0, 16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              'To-Do\'s',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Container(
                              width: 32,
                              height: 32,
                              decoration: BoxDecoration(
                                color: Colors.grey[800]?.withOpacity(0.5),
                                borderRadius: BorderRadius.circular(8),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Tap to edit • Checkbox to toggle • Swipe for actions',
                          style: TextStyle(
                            color: Colors.grey.shade500,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                // Shimmer list
                _showGroupedView 
                  ? const ActionItemsGroupedShimmerList()
                  : const ActionItemsShimmerList(),
              ]
              else if (provider.actionItems.isEmpty)
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
                            Row(
                              children: [
                                const Text(
                                  'To-Do\'s',
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
                                    '${incompleteItems.length}',
                                    style: const TextStyle(
                                      color: Colors.grey,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                                
                              ],
                            ),
                            GestureDetector(
                                  onTap: () {
                                    setState(() {
                                      _showGroupedView = !_showGroupedView;
                                    });
                                    MixpanelManager().actionItemsViewToggled(_showGroupedView);
                                  },
                                  child: Container(
                                    width: 32,
                                    height: 32,
                                    decoration: BoxDecoration(
                                      color: _showGroupedView 
                                        ? Colors.deepPurpleAccent.withOpacity(0.2)
                                        : Colors.grey[800]?.withOpacity(0.5),
                                      borderRadius: BorderRadius.circular(8),
                                      border: _showGroupedView 
                                        ? Border.all(color: Colors.deepPurpleAccent, width: 1)
                                        : null,
                                    ),
                                    child: Icon(
                                      _showGroupedView ? Icons.view_agenda : Icons.view_list,
                                      size: 16,
                                      color: _showGroupedView ? Colors.deepPurpleAccent : Colors.white70,
                                    ),
                                  ),
                                ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        // Help text for editing
                        Text(
                          'Tap to edit • Checkbox to toggle • Swipe for actions',
                          style: TextStyle(
                            color: Colors.grey.shade500,
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                ),

              // Incomplete Items
              if (provider.actionItems.isNotEmpty)
                _showGroupedView 
                  ? _buildGroupedIncompleteItems(incompleteItems, provider)
                  : _buildFlatIncompleteItems(incompleteItems, provider),

              // Completed Section Header
              if (provider.actionItems.isNotEmpty)
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
                                    '${completedItems.length}',
                                    style: const TextStyle(
                                      color: Colors.grey,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

              // Completed Items
              if (provider.actionItems.isNotEmpty && completedItems.isNotEmpty)
                _showGroupedView 
                  ? _buildGroupedCompletedItems(completedItems, provider)
                  : _buildFlatCompletedItems(completedItems, provider)
              else if (provider.actionItems.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16.0),
                    child: Container(
                      height: 52,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
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

              // Loading shimmer for pagination
              if (provider.isFetching)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: List.generate(3, (index) => const Padding(
                        padding: EdgeInsets.symmetric(vertical: 4),
                        child: ActionItemShimmerWidget(),
                      )),
                    ),
                  ),
                ),

              // Load More button (fallback for manual loading)
              if (!provider.isFetching && provider.hasMore && provider.actionItems.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Center(
                      child: ElevatedButton(
                        onPressed: () => provider.loadMoreActionItems(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.deepPurpleAccent,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: const Text('Load More'),
                      ),
                    ),
                  ),
                ),

              const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
            ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFlatIncompleteItems(List<ActionItemWithMetadata> items, ActionItemsProvider provider) {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          if (index < items.length) {
            final item = items[index];
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: _buildDismissibleActionItem(
                item: item,
                provider: provider,
              ),
            );
          }
          return null;
        },
        childCount: items.length,
      ),
    );
  }

  Widget _buildGroupedIncompleteItems(List<ActionItemWithMetadata> items, ActionItemsProvider provider) {
    // Group items by conversation title
    final Map<String, List<ActionItemWithMetadata>> groupedItems = {};
    for (final item in items) {
      groupedItems.putIfAbsent(item.conversationTitle, () => []).add(item);
    }

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, groupIndex) {
          final conversationTitle = groupedItems.keys.elementAt(groupIndex);
          final conversationItems = groupedItems[conversationTitle]!;

          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Conversation group header
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.grey[800]?.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    conversationTitle,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                // Action items for this conversation
                ...conversationItems.map((item) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: _buildDismissibleActionItem(
                    item: item,
                    provider: provider,
                  ),
                )),
              ],
            ),
          );
        },
        childCount: groupedItems.length,
      ),
    );
  }

  Widget _buildFlatCompletedItems(List<ActionItemWithMetadata> items, ActionItemsProvider provider) {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          if (index < items.length) {
            final item = items[index];
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: _buildDismissibleActionItem(
                item: item,
                provider: provider,
              ),
            );
          }
          return null;
        },
        childCount: items.length,
      ),
    );
  }

  Widget _buildGroupedCompletedItems(List<ActionItemWithMetadata> items, ActionItemsProvider provider) {
    // Group items by conversation title
    final Map<String, List<ActionItemWithMetadata>> groupedItems = {};
    for (final item in items) {
      groupedItems.putIfAbsent(item.conversationTitle, () => []).add(item);
    }

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, groupIndex) {
          final conversationTitle = groupedItems.keys.elementAt(groupIndex);
          final conversationItems = groupedItems[conversationTitle]!;

          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Conversation group header
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.grey[800]?.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    conversationTitle,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                // Action items for this conversation
                ...conversationItems.map((item) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: _buildDismissibleActionItem(
                    item: item,
                    provider: provider,
                  ),
                )),
              ],
            ),
          );
        },
        childCount: groupedItems.length,
      ),
    );
  }

  Widget _buildDismissibleActionItem({
    required ActionItemWithMetadata item,
    required ActionItemsProvider provider,
  }) {
    return Dismissible(
      key: Key(item.id),
      // Swipe right background - Mark as completed
      background: Container(
        margin: const EdgeInsets.symmetric(vertical: 2),
        decoration: BoxDecoration(
          color: item.completed ? Colors.orange : Colors.green,
          borderRadius: BorderRadius.circular(16),
        ),
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: 20),
        child: Icon(
              item.completed ? Icons.undo : Icons.check,
              color: Colors.white,
              size: 24,
            ),
      ),
      // Swipe left background - Delete
      secondaryBackground: Container(
        margin: const EdgeInsets.symmetric(vertical: 2),
        decoration: BoxDecoration(
          color: Colors.red,
          borderRadius: BorderRadius.circular(16),
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(
              Icons.delete,
              color: Colors.white,
              size: 24,
            ),
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          // Swipe right - Toggle completion
          await provider.updateActionItemState(item, !item.completed);
          
          // Show feedback
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  item.completed 
                    ? 'Action item marked as incomplete' 
                    : 'Action item completed'
                ),
                backgroundColor: item.completed ? Colors.orange : Colors.green,
                duration: const Duration(seconds: 2),
              ),
            );
          }
          return false;
        } else {
          // Swipe left - Show delete confirmation
          return await _showDeleteConfirmationDialog(item);
        }
      },
      onDismissed: (direction) async {
        // Only called for delete action (swipe left)
        if (direction == DismissDirection.endToStart) {
          await _deleteActionItem(item, provider);
        }
      },
      child: ActionItemTileWidget(
        actionItem: item,
        onToggle: (newState) => provider.updateActionItemState(item, newState),
        exportedToAppleReminders: _exportedToAppleReminders,
        onExportedToAppleReminders: _checkExistingAppleReminders,
      ),
    );
  }

  Future<bool?> _showDeleteConfirmationDialog(ActionItemWithMetadata item) async {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 340),
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 20,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Header with icon
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
                  child: Column(
                    children: [
                      Container(
                        width: 56,
                        height: 56,
                        decoration: BoxDecoration(
                          color: Colors.red.withOpacity(0.1),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          Icons.delete_outline,
                          color: Colors.red,
                          size: 28,
                        ),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'Delete Action Item?',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.w600,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
                
                // Content
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                  child: Column(
                    children: [
                      Text(
                        'Are you sure you want to delete this action item?',
                        style: TextStyle(
                          color: Colors.grey[300],
                          fontSize: 16,
                          height: 1.4,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      
                      // Action item preview
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.grey[800]?.withOpacity(0.3),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.grey[700]!.withOpacity(0.3),
                            width: 1,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              Icons.assignment_outlined,
                              color: Colors.grey[400],
                              size: 20,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                item.description,
                                style: TextStyle(
                                  color: Colors.grey[200],
                                  fontSize: 14,
                                  height: 1.3,
                                ),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                      
                      const SizedBox(height: 16),
                      
                      // Warning text with better styling
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.orange.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: Colors.orange.withOpacity(0.3),
                            width: 1,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.warning_amber_rounded,
                              color: Colors.orange[300],
                              size: 16,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'This action cannot be undone',
                              style: TextStyle(
                                color: Colors.orange[300],
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                      
                      const SizedBox(height: 24),
                      
                      // Action buttons
                      Row(
                        children: [
                          Expanded(
                            child: TextButton(
                              onPressed: () => Navigator.of(context).pop(false),
                              style: TextButton.styleFrom(
                                padding: const EdgeInsets.symmetric(vertical: 14),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              child: Text(
                                'Cancel',
                                style: TextStyle(
                                  color: Colors.grey[300],
                                  fontSize: 16,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: () => Navigator.of(context).pop(true),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.red,
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(vertical: 14),
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              child: const Text(
                                'Delete',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _deleteActionItem(ActionItemWithMetadata item, ActionItemsProvider provider) async {
    final success = await provider.deleteActionItem(item);
    
    if (mounted) {
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Action item "${item.description}" deleted'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
            action: SnackBarAction(
              label: 'Undo',
              textColor: Colors.white,
              onPressed: () {
                // For now, show that undo is not implemented
                // In the future, you could implement an undo mechanism
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Undo functionality not implemented yet'),
                    backgroundColor: Colors.orange,
                  ),
                );
              },
            ),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to delete action item'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
}