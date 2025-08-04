import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'widgets/action_item_title_widget.dart';
import 'widgets/convo_action_items_group_widget.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
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
  Set<String> _exportedToAppleReminders = <String>{};

  // Selection state
  bool _isSelectionMode = false;
  Set<String> _selectedItems = <String>{}; // Using action item description as unique key

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      MixpanelManager().actionItemsPageOpened();
      _checkExistingAppleReminders();
    });
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

  // Selection methods
  void _enterSelectionMode(String itemDescription) {
    HapticFeedback.mediumImpact();
    setState(() {
      _isSelectionMode = true;
      _selectedItems.add(itemDescription);
    });
  }

  void _toggleItemSelection(String itemDescription) {
    HapticFeedback.lightImpact();
    setState(() {
      if (_selectedItems.contains(itemDescription)) {
        _selectedItems.remove(itemDescription);
        if (_selectedItems.isEmpty) {
          _isSelectionMode = false;
        }
      } else {
        _selectedItems.add(itemDescription);
      }
    });
  }

  void _clearSelection() {
    setState(() {
      _isSelectionMode = false;
      _selectedItems.clear();
    });
  }

  void _selectAll(List<ActionItemData> items) {
    setState(() {
      _selectedItems.addAll(items.map((item) => item.actionItem.description));
    });
  }

  // Mass operations
  Future<void> _massMarkAsCompleted(List<ActionItemData> allItems) async {
    final selectedData = allItems.where((item) => _selectedItems.contains(item.actionItem.description)).toList();
    final provider = Provider.of<ConversationProvider>(context, listen: false);

    for (final item in selectedData) {
      if (!item.actionItem.completed) {
        try {
          await provider.updateGlobalActionItemState(
            item.conversation,
            item.actionItem.description,
            true,
          );

          // Sync with Apple Reminders if exported
          if (_exportedToAppleReminders.contains(item.actionItem.description) && PlatformService.isApple) {
            try {
              final service = AppleRemindersService();
              await service.completeReminder(item.actionItem.description);
            } catch (e) {
              debugPrint('Error syncing completion to Apple Reminders: $e');
            }
          }
        } catch (e) {
          debugPrint('Error marking item as completed: $e');
        }
      }
    }

    _clearSelection();

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${selectedData.length} items marked as completed'),
          backgroundColor: Colors.green,
        ),
      );
    }
  }

  Future<void> _massDelete(List<ActionItemData> allItems) async {
    final selectedData = allItems.where((item) => _selectedItems.contains(item.actionItem.description)).toList();

    // Show confirmation dialog
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Action Items'),
        content: Text('Are you sure you want to delete ${selectedData.length} action items?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      final provider = Provider.of<ConversationProvider>(context, listen: false);

      // Delete Apple Reminders first (to avoid conflicts)
      if (PlatformService.isApple) {
        for (final item in selectedData) {
          if (_exportedToAppleReminders.contains(item.actionItem.description)) {
            try {
              final service = AppleRemindersService();
              await service.deleteActionItem(item.actionItem.description);
              debugPrint('Deleted reminder from Apple Reminders: ${item.actionItem.description}');
            } catch (e) {
              debugPrint('Error deleting reminder from Apple Reminders: $e');
            }
          }
        }
      }

      // Delete locally using the safer method (no indices needed - no sorting required!)
      for (final item in selectedData) {
        try {
          await provider.deleteActionItemSafely(
            item.conversation.id,
            item.actionItem,
          );
        } catch (e) {
          debugPrint('Error deleting action item: $e');
        }
      }

      _clearSelection();
      await _checkExistingAppleReminders(); // Refresh exported state

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${selectedData.length} items deleted'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _massExportToAppleReminders(List<ActionItemData> allItems) async {
    if (!PlatformService.isApple) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Apple Reminders is only available on iOS and macOS'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    final selectedData = allItems.where((item) => _selectedItems.contains(item.actionItem.description)).toList();
    final service = AppleRemindersService();

    int successCount = 0;

    for (final item in selectedData) {
      if (!_exportedToAppleReminders.contains(item.actionItem.description)) {
        try {
          final result = await service.addActionItem(item.actionItem.description);
          if (result.isSuccess) {
            successCount++;
          }
        } catch (e) {
          debugPrint('Error exporting item to Apple Reminders: $e');
        }
      }
    }

    _clearSelection();
    await _checkExistingAppleReminders(); // Refresh exported state

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$successCount of ${selectedData.length} items exported to Apple Reminders'),
          backgroundColor: const Color(0xFF8B5CF6),
        ),
      );
    }
  }

  // Get all action items as a flat list
  List<ActionItemData> _getFlattenedActionItems(Map<ServerConversation, List<ActionItem>> itemsByConversation) {
    final result = <ActionItemData>[];

    for (final entry in itemsByConversation.entries) {
      // CRITICAL FIX: Get the correct index from the full conversation list
      // itemsByConversation contains only non-deleted items, but we need the index from the full list
      final fullActionItemsList = entry.key.structured.actionItems;

      for (final item in entry.value) {
        if (item.deleted) continue;

        // Find the ACTUAL index in the full conversation's action items list
        // This is crucial because deleteActionItemAndUpdateLocally expects the real index
        final actualIndex = fullActionItemsList.indexOf(item);

        if (actualIndex == -1) {
          // This should never happen, but log it just in case
          debugPrint('WARNING: Could not find action item in full list: ${item.description}');
          continue;
        }

        result.add(
          ActionItemData(
            actionItem: item,
            conversation: entry.key,
            itemIndex: actualIndex, // This is the correct index for deletion
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

        return PopScope(
          canPop: !_isSelectionMode,
          onPopInvoked: (didPop) {
            if (_isSelectionMode && !didPop) {
              _clearSelection();
            }
          },
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: _isSelectionMode ? _buildSelectionAppBar(flattenedItems) : null,
            floatingActionButton: _isSelectionMode ? _buildSelectAllFAB(flattenedItems) : null,
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
                                      '${flattenedItems.where((item) => !item.actionItem.completed).length}',
                                      style: const TextStyle(
                                        color: Colors.grey,
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const Row(
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
                                  // Group/Ungroup toggle button hidden for now
                                  // Container(
                                  //   width: 44,
                                  //   height: 44,
                                  //   decoration: BoxDecoration(
                                  //     color: _showGroupedView
                                  //         ? Colors.deepPurpleAccent.withOpacity(0.3)
                                  //         : Colors.grey.shade700.withOpacity(0.3),
                                  //     borderRadius: BorderRadius.circular(12),
                                  //     border: _showGroupedView
                                  //         ? Border.all(color: Colors.deepPurpleAccent, width: 1.5)
                                  //         : null,
                                  //   ),
                                  //   child: IconButton(
                                  //     icon: Icon(
                                  //       _showGroupedView ? Icons.view_agenda_outlined : Icons.view_list_outlined,
                                  //       size: 20,
                                  //     ),
                                  //     color: _showGroupedView ? Colors.deepPurpleAccent : Colors.white,
                                  //     onPressed: () {
                                  //       setState(() {
                                  //         _showGroupedView = !_showGroupedView;
                                  //       });
                                  //       MixpanelManager().actionItemsViewToggled(_showGroupedView);
                                  //     },
                                  //   ),
                                  // ),
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
                              // Text(
                              //   'Hide',
                              //   style: TextStyle(
                              //     color: Colors.grey.shade400,
                              //     fontSize: 14,
                              //     fontWeight: FontWeight.w500,
                              //   ),
                              // ),
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
                              exportedToAppleReminders: _exportedToAppleReminders,
                              onExportedToAppleReminders: _checkExistingAppleReminders,
                              isSelectionMode: _isSelectionMode,
                              isSelected: _selectedItems.contains(item.actionItem.description),
                              onLongPress: () => _enterSelectionMode(item.actionItem.description),
                              onSelectionToggle: () => _toggleItemSelection(item.actionItem.description),
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

                const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
              ],
            ),
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
            exportedToAppleReminders: _exportedToAppleReminders,
            onExportedToAppleReminders: _checkExistingAppleReminders,
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
              exportedToAppleReminders: _exportedToAppleReminders,
              onExportedToAppleReminders: _checkExistingAppleReminders,
              isSelectionMode: _isSelectionMode,
              isSelected: _selectedItems.contains(item.actionItem.description),
              onLongPress: () => _enterSelectionMode(item.actionItem.description),
              onSelectionToggle: () => _toggleItemSelection(item.actionItem.description),
            ),
          );
        },
        childCount: incompleteItems.length,
      ),
    );
  }

  AppBar _buildSelectionAppBar(List<ActionItemData> allItems) {
    return AppBar(
      backgroundColor: const Color(0xFF8B5CF6),
      title: Text('${_selectedItems.length} selected'),
      leading: IconButton(
        icon: const Icon(Icons.close),
        onPressed: _clearSelection,
      ),
      actions: [
        // Complete selected items
        IconButton(
          icon: const Icon(Icons.check_circle),
          onPressed: _selectedItems.isNotEmpty ? () => _massMarkAsCompleted(allItems) : null,
          tooltip: 'Mark as completed',
        ),
        // Export to Apple Reminders
        if (PlatformService.isApple)
          IconButton(
            icon: SizedBox(
              width: 24,
              height: 24,
              child: Stack(
                children: [
                  Center(
                    child: Image.asset(
                      'assets/images/apple-reminders-logo.png',
                      width: 20,
                      height: 20,
                    ),
                  ),
                  // Yellow circle with plus symbol
                  Positioned(
                    bottom: 0,
                    right: 0,
                    child: Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: Colors.yellow,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: const Color(0xFF8B5CF6),
                          width: 1,
                        ),
                      ),
                      child: const Icon(
                        Icons.add,
                        size: 8,
                        color: Colors.black,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            onPressed: _selectedItems.isNotEmpty ? () => _massExportToAppleReminders(allItems) : null,
            tooltip: 'Export to Apple Reminders',
          ),
        // Delete selected items
        IconButton(
          icon: const Icon(Icons.delete),
          onPressed: _selectedItems.isNotEmpty ? () => _massDelete(allItems) : null,
          tooltip: 'Delete',
        ),
      ],
    );
  }

  Widget _buildSelectAllFAB(List<ActionItemData> allItems) {
    final allSelected = allItems.every((item) => _selectedItems.contains(item.actionItem.description));

    return FloatingActionButton.extended(
      onPressed: () {
        if (allSelected) {
          _clearSelection();
        } else {
          _selectAll(allItems);
        }
      },
      label: Text(allSelected ? 'Deselect All' : 'Select All'),
      icon: Icon(allSelected ? Icons.deselect : Icons.select_all),
      backgroundColor: allSelected ? Colors.grey : const Color(0xFF8B5CF6),
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
