import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

import 'package:omi/ui/organisms/action_item.dart';
import 'widgets/desktop_action_group.dart';

class DesktopActionsPage extends StatefulWidget {
  const DesktopActionsPage({super.key});

  @override
  State<DesktopActionsPage> createState() => DesktopActionsPageState();
}

class DesktopActionsPageState extends State<DesktopActionsPage>
    with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  bool _showGroupedView = false;

  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  @override
  void dispose() {
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _animationsInitialized = true;

    (() async {
      MixpanelManager().actionItemsPageOpened();

      _fadeController.forward();
      _slideController.forward();
    }).withPostFrameCallback();
  }

  // Get all action items as a flat list
  List<ActionItemData> _getFlattenedActionItems(Map<ServerConversation, List<ActionItem>> itemsByConversation) {
    final result = <ActionItemData>[];

    for (final entry in itemsByConversation.entries) {
      for (final item in entry.value) {
        if (item.deleted) continue;
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
      builder: (context, convoProvider, _) {
        final Map<ServerConversation, List<ActionItem>> itemsByConversation =
            convoProvider.conversationsWithActiveActionItems;

        // Sort conversations by date (most recent first)
        final sortedEntries = itemsByConversation.entries.toList()
          ..sort((a, b) => b.key.createdAt.compareTo(a.key.createdAt));

        // Get flattened list for non-grouped view
        final flattenedItems = _getFlattenedActionItems(itemsByConversation);

        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                ResponsiveHelper.backgroundPrimary,
                ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
              ],
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Stack(
              children: [
                _buildAnimatedBackground(),
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.02),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    children: [
                      _buildHeader(flattenedItems),
                      Expanded(
                        child: _animationsInitialized
                            ? FadeTransition(
                                opacity: _fadeAnimation,
                                child: SlideTransition(
                                  position: _slideAnimation,
                                  child: _buildActionsContent(convoProvider, sortedEntries, flattenedItems),
                                ),
                              )
                            : _buildActionsContent(convoProvider, sortedEntries, flattenedItems),
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

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withOpacity(0.05),
              Colors.transparent,
            ],
          ),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topRight,
              radius: 2.0,
              colors: [
                ResponsiveHelper.purplePrimary.withOpacity(0.05 + _pulseAnimation.value * 0.03),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeader(List<ActionItemData> flattenedItems) {
    final incompleteCount = flattenedItems.where((item) => !item.actionItem.completed).length;

    return Container(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          // Title section
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(
                      FontAwesomeIcons.listCheck,
                      color: ResponsiveHelper.textSecondary,
                      size: 18,
                    ),
                    SizedBox(width: 12),
                    Text(
                      'Action Items',
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '$incompleteCount pending tasks',
                  style: const TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),

          // View toggle button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                setState(() {
                  _showGroupedView = !_showGroupedView;
                });
                MixpanelManager().actionItemsViewToggled(_showGroupedView);
              },
              borderRadius: BorderRadius.circular(12),
              child: Container(
                height: 44,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _showGroupedView
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                      : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(12),
                  border: _showGroupedView
                      ? Border.all(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                          width: 1,
                        )
                      : null,
                ),
                child: Icon(
                  _showGroupedView ? FontAwesomeIcons.layerGroup : FontAwesomeIcons.list,
                  color: _showGroupedView ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  size: 16,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionsContent(
    ConversationProvider convoProvider,
    List<MapEntry<ServerConversation, List<ActionItem>>> sortedEntries,
    List<ActionItemData> flattenedItems,
  ) {
    if (convoProvider.isLoadingConversations && sortedEntries.isEmpty) {
      return _buildModernLoadingState();
    }

    if (sortedEntries.isEmpty) {
      return _buildModernEmptyState();
    }

    return CustomScrollView(
      slivers: [
        // Pending tasks section
        if (flattenedItems.any((item) => !item.actionItem.completed))
          _showGroupedView ? _buildGroupedView(sortedEntries, false) : _buildFlatView(flattenedItems, false),

        // Completed tasks section
        if (flattenedItems.any((item) => item.actionItem.completed)) ...[
          SliverToBoxAdapter(
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
              child: Row(
                children: [
                  const Text(
                    'Completed',
                    style: TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${flattenedItems.where((item) => item.actionItem.completed).length}',
                      style: const TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          _showGroupedView ? _buildGroupedView(sortedEntries, true) : _buildFlatView(flattenedItems, true),
        ] else ...[
          SliverToBoxAdapter(
            child: Container(
              margin: const EdgeInsets.fromLTRB(20, 24, 20, 0),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Row(
                children: [
                  Icon(
                    FontAwesomeIcons.circleCheck,
                    color: ResponsiveHelper.textTertiary,
                    size: 16,
                  ),
                  SizedBox(width: 12),
                  Text(
                    'No completed items yet',
                    style: TextStyle(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],

        const SliverPadding(padding: EdgeInsets.only(bottom: 20)),
      ],
    );
  }

  Widget _buildModernLoadingState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.1),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _animationsInitialized
                ? AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, child) {
                      return Transform.scale(
                        scale: 1.0 + (_pulseAnimation.value * 0.1),
                        child: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.purplePrimary,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            strokeWidth: 2,
                          ),
                        ),
                      );
                    },
                  )
                : Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      strokeWidth: 2,
                    ),
                  ),
            const SizedBox(height: 16),
            const Text(
              'Loading your action items...',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModernEmptyState() {
    Widget content = Container(
      padding: const EdgeInsets.all(40),
      margin: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _animationsInitialized
              ? AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: 1.0 + (_pulseAnimation.value * 0.05),
                      child: Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Icon(
                          FontAwesomeIcons.circleCheck,
                          size: 48,
                          color: ResponsiveHelper.purplePrimary,
                        ),
                      ),
                    );
                  },
                )
              : Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(
                    FontAwesomeIcons.circleCheck,
                    size: 48,
                    color: ResponsiveHelper.purplePrimary,
                  ),
                ),
          const SizedBox(height: 24),
          const Text(
            '✅ No Action Items',
            style: TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Tasks and to-dos from your conversations will appear here once they are created.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 14,
              height: 1.5,
            ),
          ),
        ],
      ),
    );

    return Center(
      child: _animationsInitialized
          ? FadeTransition(
              opacity: _fadeAnimation,
              child: content,
            )
          : content,
    );
  }

  Widget _buildGroupedView(List<MapEntry<ServerConversation, List<ActionItem>>> sortedEntries, bool showCompleted) {
    final filteredEntries = sortedEntries.where((entry) {
      final items = entry.value.where((item) => !item.deleted && item.completed == showCompleted).toList();
      return items.isNotEmpty;
    }).toList();

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final entry = filteredEntries[index];
          final filteredItems = entry.value.where((item) => !item.deleted && item.completed == showCompleted).toList();

          Widget groupWidget = DesktopActionGroup(
            conversation: entry.key,
            actionItems: filteredItems,
          );

          return AnimatedContainer(
            duration: Duration(milliseconds: 300 + (index * 50)),
            curve: Curves.easeOutCubic,
            child: _animationsInitialized
                ? FadeTransition(
                    opacity: _fadeAnimation,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: Offset(0, 0.1 + (index * 0.02)),
                        end: Offset.zero,
                      ).animate(CurvedAnimation(
                        parent: _slideController,
                        curve: Interval(
                          (index * 0.1).clamp(0.0, 0.8),
                          1.0,
                          curve: Curves.easeOutCubic,
                        ),
                      )),
                      child: groupWidget,
                    ),
                  )
                : groupWidget,
          );
        },
        childCount: filteredEntries.length,
      ),
    );
  }

  Widget _buildFlatView(List<ActionItemData> items, bool showCompleted) {
    final filteredItems = items.where((item) => item.actionItem.completed == showCompleted).toList();

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final item = filteredItems[index];

          Widget itemWidget = DesktopActionItem(
            actionItem: item.actionItem,
            conversation: item.conversation,
            itemIndex: item.itemIndex,
          );

          return AnimatedContainer(
            duration: Duration(milliseconds: 300 + (index * 50)),
            curve: Curves.easeOutCubic,
            child: _animationsInitialized
                ? FadeTransition(
                    opacity: _fadeAnimation,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: Offset(0, 0.1 + (index * 0.02)),
                        end: Offset.zero,
                      ).animate(CurvedAnimation(
                        parent: _slideController,
                        curve: Interval(
                          (index * 0.1).clamp(0.0, 0.8),
                          1.0,
                          curve: Curves.easeOutCubic,
                        ),
                      )),
                      child: itemWidget,
                    ),
                  )
                : itemWidget,
          );
        },
        childCount: filteredItems.length,
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

extension PostFrameCallback on Function {
  void withPostFrameCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) => this());
  }
}
