import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'desktop_conversation_detail_page.dart';
import 'widgets/desktop_conversation_card.dart';
import 'widgets/desktop_daily_score_widget.dart';
import 'widgets/desktop_empty_conversations.dart';
import 'widgets/desktop_goals_widget.dart';
import 'widgets/desktop_search_widget.dart';
import 'widgets/desktop_search_result_header.dart';
import 'widgets/desktop_recording_widget.dart';
import 'widgets/desktop_today_tasks_widget.dart';

class DesktopConversationsPage extends StatefulWidget {
  const DesktopConversationsPage({
    super.key,
  });

  @override
  State<DesktopConversationsPage> createState() => _DesktopConversationsPageState();
}

class _DesktopConversationsPageState extends State<DesktopConversationsPage>
    with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  bool _isReloading = false;
  late FocusNode _focusNode;
  late ScrollController _scrollController;

  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  // State for inline conversation detail viewing
  bool _showingConversationDetail = false;
  ServerConversation? _selectedConversation;
  ConversationDetailProvider? _conversationDetailProvider;

  // State for expanded recording view
  bool _showExpandedRecording = false;

  @override
  void initState() {
    super.initState();

    _focusNode = FocusNode();
    _scrollController = ScrollController();

    // Initialize animations
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    ));

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (Provider.of<ConversationProvider>(context, listen: false).conversations.isEmpty) {
        await Provider.of<ConversationProvider>(context, listen: false).getInitialConversations();
      }
      _fadeController.forward();
    });
  }

  Future<void> _handleReload() async {
    if (_isReloading) return;

    setState(() {
      _isReloading = true;
    });

    // Scroll to top
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }

    if (mounted) {
      final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);

      if (conversationProvider.previousQuery.isNotEmpty) {
        conversationProvider.previousQuery = "";
        conversationProvider.resetGroupedConvos();
        await conversationProvider.getInitialConversations();
      } else {
        await conversationProvider.forceRefreshConversations();
      }
    }

    if (mounted) {
      setState(() {
        _isReloading = false;
      });
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _requestFocusIfPossible();
  }

  void _requestFocusIfPossible() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _focusNode.canRequestFocus) {
        _focusNode.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _conversationDetailProvider?.dispose();
    _focusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _navigateToConversationDetail(ServerConversation conversation, int index, DateTime date) async {
    // Create and setup the conversation detail provider
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
    final appProvider = Provider.of<AppProvider>(context, listen: false);

    final detailProvider = ConversationDetailProvider();
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.appProvider = appProvider;
    detailProvider.updateConversation(conversation.id, date);

    await detailProvider.initConversation();

    // If conversation has no app results, update details
    if (detailProvider.conversation.appResults.isEmpty) {
      await conversationProvider.updateSearchedConvoDetails(
          detailProvider.conversation.id, date, index);
      detailProvider.updateConversation(detailProvider.conversation.id, date);
    }

    setState(() {
      _showingConversationDetail = true;
      _selectedConversation = conversation;
      _conversationDetailProvider = detailProvider;
    });
  }

  void _navigateBackToConversationsList() {
    setState(() {
      _showingConversationDetail = false;
      _selectedConversation = null;
      _conversationDetailProvider?.dispose();
      _conversationDetailProvider = null;
    });
  }

  void _showExpandedRecordingView() {
    setState(() {
      _showExpandedRecording = true;
    });
  }

  void _hideExpandedRecordingView() {
    setState(() {
      _showExpandedRecording = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return VisibilityDetector(
        key: const Key('desktop_conversations_page'),
        onVisibilityChanged: (visibilityInfo) {
          if (visibilityInfo.visibleFraction > 0.1) {
            _requestFocusIfPossible();
          }
        },
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.keyR, meta: true): _handleReload,
          },
          child: Focus(
            focusNode: _focusNode,
            autofocus: true,
            child: GestureDetector(
              onTap: () {
                if (!_focusNode.hasFocus) {
                  _focusNode.requestFocus();
                }
              },
              child: Consumer3<ConversationProvider, CaptureProvider, DeviceProvider>(
                builder: (context, convoProvider, captureProvider, deviceProvider, child) {
                  final recordingState = captureProvider.recordingState;
                  final isRecording = recordingState == RecordingState.systemAudioRecord;
                  final isInitializing = recordingState == RecordingState.initialising;
                  final isRecordingOrInitializing = isRecording || isInitializing || captureProvider.isPaused;
                  final isSearchActive = convoProvider.previousQuery.isNotEmpty;
                  final hasAnyConversationsInSystem = convoProvider.conversations.isNotEmpty;

                  // Auto-hide expanded recording when recording stops
                  if (!isRecordingOrInitializing && _showExpandedRecording) {
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      _hideExpandedRecordingView();
                    });
                  }

                  // If showing conversation detail, display it instead of the conversations list
                  if (_showingConversationDetail &&
                      _selectedConversation != null &&
                      _conversationDetailProvider != null) {
                    return ChangeNotifierProvider.value(
                      value: _conversationDetailProvider!,
                      child: _buildConversationDetailView(),
                    );
                  }

                  if (_isReloading) {
                    return Container(
                      color: ResponsiveHelper.backgroundSecondary.withOpacity(0.85),
                      child: const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                            ),
                            SizedBox(height: 16),
                            Text(
                              'Reloading conversations...',
                              style: TextStyle(
                                fontSize: 16,
                                color: ResponsiveHelper.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  // Main View: Determine what to show based on state
                  return Container(
                    color: ResponsiveHelper.backgroundSecondary.withOpacity(0.85),
                    child: Stack(
                      children: [
                        // Main content layer
                        if (!hasAnyConversationsInSystem && !isSearchActive)
                          Center(
                            child: DesktopRecordingWidget(
                              hasConversations: false,
                              onStartRecording: _showExpandedRecordingView,
                            ),
                          )
                        else
                          // Case 2 & 3: Has conversations or is recording -> show list view with pull to refresh
                          RefreshIndicator(
                            onRefresh: () async {
                              if (convoProvider.previousQuery.isNotEmpty) {
                                // If searching, refresh search results
                                await convoProvider.searchConversations(convoProvider.previousQuery);
                              } else {
                                // Otherwise refresh all conversations
                                await convoProvider.forceRefreshConversations();
                              }
                            },
                            color: ResponsiveHelper.purplePrimary,
                            backgroundColor: ResponsiveHelper.backgroundSecondary,
                            child: CustomScrollView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              slivers: [
                                const SliverToBoxAdapter(child: SizedBox(height: 48)),

                                // Header section (only show if there are conversations in system)
                                if (hasAnyConversationsInSystem)
                                  SliverToBoxAdapter(
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: _buildHeader(),
                                    ),
                                  ),

                                // Recording widget section
                                // Only show if there are conversations in system and not searching
                                if (hasAnyConversationsInSystem && !isSearchActive && !_showExpandedRecording)
                                  SliverToBoxAdapter(
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: Container(
                                        padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
                                        child: DesktopRecordingWidget(
                                          hasConversations: true,
                                          onStartRecording: _showExpandedRecordingView,
                                        ),
                                      ),
                                    ),
                                  ),

                                // Daily Score + Today Tasks + Goals section (only when not searching)
                                if (hasAnyConversationsInSystem && !isSearchActive)
                                  SliverToBoxAdapter(
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: Container(
                                        padding: const EdgeInsets.fromLTRB(32, 0, 32, 24),
                                        height: 260, // Height to fit 3 tasks/goals
                                        child: Row(
                                          crossAxisAlignment: CrossAxisAlignment.stretch,
                                          children: [
                                            // Daily Score Widget
                                            const Expanded(
                                              child: DesktopDailyScoreWidget(),
                                            ),
                                            const SizedBox(width: 16),
                                            // Today Tasks Widget
                                            const Expanded(
                                              child: DesktopTodayTasksWidget(),
                                            ),
                                            const SizedBox(width: 16),
                                            // Goals Widget
                                            const Expanded(
                                              child: DesktopGoalsWidget(),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),

                                // Search result header (only show if there are conversations in system)
                                if (hasAnyConversationsInSystem)
                                  const SliverToBoxAdapter(child: DesktopSearchResultHeader()),

                                // Main conversations content
                                if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
                                  SliverToBoxAdapter(
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(vertical: 80),
                                        child: Center(
                                          child: _buildEmptyState(convoProvider, isSearchActive),
                                        ),
                                      ),
                                    ),
                                  )
                                else if (convoProvider.groupedConversations.isEmpty &&
                                    convoProvider.isLoadingConversations)
                                  SliverToBoxAdapter(
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 80),
                                      child: const Center(
                                        child: CircularProgressIndicator(
                                          valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                                          strokeWidth: 2,
                                        ),
                                      ),
                                    ),
                                  )
                                else
                                  SliverPadding(
                                    padding: const EdgeInsets.symmetric(horizontal: 32),
                                    sliver: SliverList(
                                      delegate: SliverChildBuilderDelegate(
                                        childCount: convoProvider.groupedConversations.length + 1,
                                        (context, index) {
                                          if (index == convoProvider.groupedConversations.length) {
                                            return VisibilityDetector(
                                              key: const Key('desktop-conversations-load-more'),
                                              onVisibilityChanged: (visibilityInfo) {
                                                var provider =
                                                    Provider.of<ConversationProvider>(context, listen: false);
                                                if (provider.previousQuery.isNotEmpty) {
                                                  if (visibilityInfo.visibleFraction > 0 &&
                                                      !provider.isLoadingConversations &&
                                                      (provider.totalSearchPages > provider.currentSearchPage)) {
                                                    provider.searchMoreConversations();
                                                  }
                                                } else {
                                                  if (visibilityInfo.visibleFraction > 0 &&
                                                      !provider.isLoadingConversations) {
                                                    provider.getMoreConversationsFromServer();
                                                  }
                                                }
                                              },
                                              child: Container(
                                                padding: const EdgeInsets.symmetric(vertical: 32),
                                                child: convoProvider.isLoadingConversations
                                                    ? const Center(
                                                        child: CircularProgressIndicator(
                                                          valueColor: AlwaysStoppedAnimation<Color>(
                                                              ResponsiveHelper.purplePrimary),
                                                          strokeWidth: 2,
                                                        ),
                                                      )
                                                    : const SizedBox(height: 20),
                                              ),
                                            );
                                          }

                                          // Conversation groups
                                          var date = convoProvider.groupedConversations.keys.elementAt(index);
                                          List<ServerConversation> conversationsForDate =
                                              convoProvider.groupedConversations[date]!;

                                          return FadeTransition(
                                            opacity: _fadeAnimation,
                                            child: _buildConversationGroup(date, conversationsForDate, index == 0),
                                          );
                                        },
                                      ),
                                    ),
                                  ),

                                const SliverToBoxAdapter(child: SizedBox(height: 80)),
                              ],
                            ),
                          ),

                        // Expanded recording overlay (only shows over main content area)
                        if (_showExpandedRecording)
                          Container(
                            width: double.infinity,
                            height: double.infinity,
                            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.95),
                            child: DesktopRecordingWidget(
                              onBack: _hideExpandedRecordingView,
                              showTranscript: true,
                              hasConversations: true,
                            ),
                          ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ),
        ));
  }

  Widget _buildConversationDetailView() {
    return DesktopConversationDetailPage(
      conversation: _selectedConversation!,
      showBackButton: true,
      onBackPressed: _navigateBackToConversationsList,
    );
  }

  Widget _buildHeader() {
    final userName = SharedPreferencesUtil().givenName;

    return Container(
      padding: const EdgeInsets.fromLTRB(32, 8, 32, 16),
      child: Consumer<ConversationProvider>(
        builder: (context, convoProvider, _) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Left side - Welcome message
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Welcome back, ${userName.isNotEmpty ? userName : 'User'}',
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w600,
                        color: ResponsiveHelper.textPrimary,
                        letterSpacing: -0.5,
                      ),
                    ),
                  ],
                ),
              ),

              // Right side - Search + Filters
              const DesktopSearchWidget(),
              const SizedBox(width: 8),

              // Starred filter button
              _buildStarredFilterButton(convoProvider),
              const SizedBox(width: 8),

              // Date filter button
              _buildDateFilterButton(convoProvider),
            ],
          );
        },
      ),
    );
  }

  Widget _buildStarredFilterButton(ConversationProvider convoProvider) {
    final isActive = convoProvider.showStarredOnly;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          convoProvider.toggleStarredFilter();
        },
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: isActive
                ? Colors.amber.withValues(alpha: 0.15)
                : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isActive ? Colors.amber.withValues(alpha: 0.4) : ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              FaIcon(
                isActive ? FontAwesomeIcons.solidStar : FontAwesomeIcons.star,
                size: 14,
                color: isActive ? Colors.amber : ResponsiveHelper.textTertiary,
              ),
              const SizedBox(width: 8),
              Text(
                'Starred',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: isActive ? Colors.amber : ResponsiveHelper.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDateFilterButton(ConversationProvider convoProvider) {
    final selectedDate = convoProvider.selectedDate;
    final hasDateFilter = selectedDate != null;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _showDatePicker(convoProvider),
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: hasDateFilter
                ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.15)
                : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: hasDateFilter
                  ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.4)
                  : ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.calendar_today_rounded,
                size: 15,
                color: hasDateFilter ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
              ),
              const SizedBox(width: 8),
              Text(
                hasDateFilter ? DateFormat('MMM d').format(selectedDate) : 'Date',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: hasDateFilter ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                ),
              ),
              // Clear button when date is selected
              if (hasDateFilter) ...[
                const SizedBox(width: 6),
                GestureDetector(
                  onTap: () {
                    convoProvider.clearDateFilter();
                  },
                  child: Container(
                    padding: const EdgeInsets.all(2),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.close,
                      size: 12,
                      color: ResponsiveHelper.purplePrimary,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showDatePicker(ConversationProvider convoProvider) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: convoProvider.selectedDate ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: ResponsiveHelper.purplePrimary,
              onPrimary: Colors.white,
              surface: ResponsiveHelper.backgroundSecondary,
              onSurface: ResponsiveHelper.textPrimary,
            ),
            dialogBackgroundColor: ResponsiveHelper.backgroundSecondary,
          ),
          child: child!,
        );
      },
    );

    if (picked != null) {
      await convoProvider.filterConversationsByDate(picked);
    }
  }

  Widget _buildEmptyState(ConversationProvider convoProvider, bool isSearchActive) {
    // Search empty state
    if (isSearchActive) {
      return const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.search_off_rounded,
            size: 48,
            color: ResponsiveHelper.textTertiary,
          ),
          SizedBox(height: 16),
          Text(
            'No results found',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Try adjusting your search terms',
            style: TextStyle(
              fontSize: 14,
              color: ResponsiveHelper.textTertiary,
            ),
          ),
        ],
      );
    }

    // Starred filter empty state
    if (convoProvider.showStarredOnly) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const FaIcon(
              FontAwesomeIcons.star,
              color: Colors.amber,
              size: 32,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'No starred conversations',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Star conversations to find them quickly here',
            style: TextStyle(
              fontSize: 14,
              color: ResponsiveHelper.textTertiary,
            ),
          ),
        ],
      );
    }

    // Date filter empty state
    if (convoProvider.selectedDate != null) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.calendar_today_rounded,
              color: ResponsiveHelper.purplePrimary,
              size: 32,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'No conversations on ${DateFormat('MMM d, yyyy').format(convoProvider.selectedDate!)}',
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Try selecting a different date',
            style: TextStyle(
              fontSize: 14,
              color: ResponsiveHelper.textTertiary,
            ),
          ),
        ],
      );
    }

    // Default empty state
    return const DesktopEmptyConversations();
  }

  Widget _buildConversationGroup(
    DateTime date,
    List<ServerConversation> conversations,
    bool isFirst,
  ) {
    return Container(
      margin: EdgeInsets.only(top: isFirst ? 8 : 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Date header - "Tue, Jan 6" format
          Padding(
            padding: const EdgeInsets.only(left: 12, bottom: 8),
            child: Text(
              DateFormat('EEE, MMM d').format(date),
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: ResponsiveHelper.textTertiary,
                letterSpacing: 0.2,
              ),
            ),
          ),
          // Conversations list - no gaps between items
          ...conversations.asMap().entries.map((entry) {
            final index = entry.key;
            final conversation = entry.value;

            return DesktopConversationCard(
              conversation: conversation,
              onTap: () => _navigateToConversationDetail(conversation, index, date),
              index: index,
              date: date,
            );
          }),
        ],
      ),
    );
  }
}
