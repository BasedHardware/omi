import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'widgets/action_item_tile_widget.dart';
import 'widgets/action_item_shimmer_widget.dart';
import 'widgets/action_item_form_sheet.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  Set<String> _exportedToAppleReminders = <String>{};
  final AppReviewService _appReviewService = AppReviewService();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
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

  // checks if it's the first action item completed
  Future<void> _onActionItemCompleted() async {
    final hasCompletedFirst = await _appReviewService.hasCompletedFirstActionItem();

    if (!hasCompletedFirst) {
      await _appReviewService.markFirstActionItemCompleted();

      if (mounted) {
        await _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: false);
      }
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

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0.0,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOutCubic,
      );
    }
  }

  void _showCreateActionItemSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const ActionItemFormSheet(),
    );
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
          appBar: provider.isSelectionMode ? _buildSelectionAppBar(provider) : null,
          body: RefreshIndicator(
            onRefresh: () async {
              HapticFeedback.mediumImpact();
              return provider.forceRefreshActionItems();
            },
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
                            'Tap to edit • Long press to select • Swipe for actions',
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
                  const ActionItemsShimmerList(),
                ] else if (provider.actionItems.isEmpty)
                  SliverFillRemaining(
                    child: _buildSmartEmptyState(provider),
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
                              // Create icon
                              IconButton(
                                onPressed: _showCreateActionItemSheet,
                                icon: const Icon(
                                  Icons.add,
                                  color: Colors.white,
                                  size: 18,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          // Help text for editing
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Tap to edit • Long press to select • Swipe for actions',
                                style: TextStyle(
                                  color: Colors.grey.shade500,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                        ],
                      ),
                    ),
                  ),

                // Incomplete Items
                if (provider.actionItems.isNotEmpty) _buildFlatIncompleteItems(incompleteItems, provider),

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
                  _buildFlatCompletedItems(completedItems, provider)
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
                if (provider.isFetching || provider.isLoading)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        children: List.generate(
                            3,
                            (index) => const Padding(
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

  Widget _buildDismissibleActionItem({
    required ActionItemWithMetadata item,
    required ActionItemsProvider provider,
  }) {
    return Dismissible(
      key: Key(item.id),
      // Swipe right background - Mark as completed
      background: provider.isSelectionMode
          ? null
          : Container(
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
      secondaryBackground: provider.isSelectionMode
          ? null
          : Container(
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
        // Disable swipe gestures when in selection mode
        if (provider.isSelectionMode) {
          return false;
        }

        if (direction == DismissDirection.startToEnd) {
          // Swipe right - Toggle completion
          await provider.updateActionItemState(item, !item.completed);

          // Show feedback
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(item.completed ? 'Action item marked as incomplete' : 'Action item completed'),
                backgroundColor: item.completed ? Colors.orange : Colors.green,
                duration: const Duration(seconds: 2),
              ),
            );
          }
          return false;
        } else {
          // Swipe left - Show delete confirmation
          await _deleteActionItem(item, provider);
          return false;
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
        onToggle: (newState) {
          provider.updateActionItemState(item, newState);
          if (newState) {
            _onActionItemCompleted();
          }
        },
        exportedToAppleReminders: _exportedToAppleReminders,
        onExportedToAppleReminders: _checkExistingAppleReminders,
        isSelectionMode: provider.isSelectionMode,
        isSelected: provider.isItemSelected(item.id),
        onLongPress: () => _handleItemLongPress(item, provider),
        onSelectionToggle: () => provider.toggleItemSelection(item.id),
      ),
    );
  }

  void _handleItemLongPress(ActionItemWithMetadata item, ActionItemsProvider provider) {
    if (!provider.isSelectionMode) {
      // Enter selection mode and select the long-pressed item
      provider.startSelection();
      provider.selectItem(item.id);
      HapticFeedback.mediumImpact();
    }
  }

  PreferredSizeWidget _buildSelectionAppBar(ActionItemsProvider provider) {
    return AppBar(
      backgroundColor: Colors.black.withValues(alpha: 0.05),
      elevation: 0,
      foregroundColor: Colors.white,
      leading: IconButton(
        icon: const Icon(Icons.close, size: 20),
        onPressed: () => provider.endSelection(),
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(),
      ),
      title: Text(
        '${provider.selectedCount} selected',
        style: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w500,
        ),
      ),
      actions: [
        if (provider.selectedCount < provider.actionItems.length)
          IconButton(
            icon: const FaIcon(FontAwesomeIcons.squareCheck, size: 18),
            tooltip: 'Select all',
            onPressed: () => provider.selectAllItems(),
            padding: const EdgeInsets.symmetric(horizontal: 8),
          ),
        if (provider.hasSelection)
          IconButton(
            icon: const FaIcon(FontAwesomeIcons.trash, size: 20),
            tooltip: 'Delete selected',
            onPressed: () => _deleteSelectedItems(provider),
            padding: const EdgeInsets.symmetric(horizontal: 8),
          ),
      ],
    );
  }

  Future<void> _deleteSelectedItems(ActionItemsProvider provider) async {
    final selectedCount = provider.selectedCount;
    if (selectedCount == 0) return;

    final prefs = SharedPreferencesUtil();

    // Check if user has opted out of delete confirmations
    if (!prefs.showActionItemDeleteConfirmation) {
      // Skip confirmation and proceed with bulk deletion
      await _performBulkDelete(provider);
      return;
    }

    // Show confirmation dialog for bulk delete
    final result = await OmiConfirmDialog.showWithSkipOption(
      context,
      title: 'Delete Selected Items',
      message: 'Are you sure you want to delete $selectedCount selected action item${selectedCount > 1 ? 's' : ''}?',
    );

    if (result != null && result.confirmed) {
      // Update preference if user chose to skip future confirmations
      if (result.skipFutureConfirmations) {
        prefs.showActionItemDeleteConfirmation = false;
      }

      await _performBulkDelete(provider);
    }
  }

  Future<void> _performBulkDelete(ActionItemsProvider provider) async {
    final selectedCount = provider.selectedCount;

    try {
      final success = await provider.deleteSelectedItems();

      if (mounted && success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('$selectedCount action item${selectedCount > 1 ? 's' : ''} deleted'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
          ),
        );
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to delete some items'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to delete items'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _deleteActionItem(ActionItemWithMetadata item, ActionItemsProvider provider) async {
    final prefs = SharedPreferencesUtil();

    // Check if user has opted out of delete confirmations
    if (!prefs.showActionItemDeleteConfirmation) {
      // Skip confirmation and proceed with deletion
      await _performDeleteActionItem(item, provider);
      return;
    }

    final result = await OmiConfirmDialog.showWithSkipOption(
      context,
      title: 'Delete Action Item',
      message: 'Are you sure you want to delete this action item?',
    );

    if (result?.confirmed == true) {
      // Update preference if user chose to skip future confirmations
      if (result!.skipFutureConfirmations) {
        prefs.showActionItemDeleteConfirmation = false;
      }

      await _performDeleteActionItem(item, provider);
    }
  }

  Future<void> _performDeleteActionItem(ActionItemWithMetadata item, ActionItemsProvider provider) async {
    final success = await provider.deleteActionItem(item);

    if (mounted) {
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Action item "${item.description}" deleted'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
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

  Widget _buildSmartEmptyState(ActionItemsProvider provider) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: const EdgeInsets.all(32.0),
        child: _buildFirstTimeEmptyState(),
      ),
    );
  }

  Widget _buildFirstTimeEmptyState() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 96,
          height: 96,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                const Color(0xFF8B5CF6).withOpacity(0.1),
                const Color(0xFFA855F7).withOpacity(0.05),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: const Color(0xFF8B5CF6).withOpacity(0.2),
              width: 1,
            ),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Icon(
                Icons.assignment_outlined,
                size: 40,
                color: const Color(0xFF8B5CF6).withOpacity(0.6),
              ),
              Positioned(
                right: 24,
                bottom: 24,
                child: Container(
                  width: 20,
                  height: 20,
                  decoration: const BoxDecoration(
                    color: Color(0xFF10B981),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.check,
                    size: 12,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 28),

        // Welcome heading
        const Text(
          'Ready for Action Items',
          style: TextStyle(
            color: Color(0xFFFFFFFF),
            fontSize: 28,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.8,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 16),

        // Educational description
        const Text(
          'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Color(0xFFB0B0B0),
            fontSize: 16,
            height: 1.6,
            fontWeight: FontWeight.w400,
          ),
        ),

        const SizedBox(height: 32),

        // Subtle feature hints
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFF2A2A2A),
              width: 1,
            ),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: const BoxDecoration(
                      color: Color(0xFF8B5CF6),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Automatically extracted from conversations',
                      style: TextStyle(
                        color: Color(0xFFE5E5E5),
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: const BoxDecoration(
                      color: Color(0xFF8B5CF6),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Tap to edit, swipe to complete or delete',
                      style: TextStyle(
                        color: Color(0xFFE5E5E5),
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: const BoxDecoration(
                      color: Color(0xFF8B5CF6),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Filter and organize by date ranges',
                      style: TextStyle(
                        color: Color(0xFFE5E5E5),
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}
