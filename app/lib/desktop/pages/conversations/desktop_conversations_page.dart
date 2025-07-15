import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
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
import 'widgets/desktop_empty_conversations.dart';
import 'widgets/desktop_search_widget.dart';
import 'widgets/desktop_search_result_header.dart';
import 'widgets/desktop_recording_widget.dart';

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

  @override
  void dispose() {
    _fadeController.dispose();
    _conversationDetailProvider?.dispose();
    super.dispose();
  }

  void _navigateToConversationDetail(ServerConversation conversation, int index, DateTime date) async {
    // Create and setup the conversation detail provider
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
    final appProvider = Provider.of<AppProvider>(context, listen: false);

    final detailProvider = ConversationDetailProvider();
    detailProvider.conversationIdx = index;
    detailProvider.selectedDate = date;
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.appProvider = appProvider;

    await detailProvider.initConversation();

    // If conversation has no app results, update details
    if (detailProvider.conversation.appResults.isEmpty) {
      await conversationProvider.updateSearchedConvoDetails(detailProvider.conversation.id, date, index);
      detailProvider.updateConversation(index, date);
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

    return Consumer3<ConversationProvider, CaptureProvider, DeviceProvider>(
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
        if (_showingConversationDetail && _selectedConversation != null && _conversationDetailProvider != null) {
          return ChangeNotifierProvider.value(
            value: _conversationDetailProvider!,
            child: _buildConversationDetailView(),
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
                      const SliverToBoxAdapter(child: SizedBox(height: 20)),

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

                      // Search result header (only show if there are conversations in system)
                      if (hasAnyConversationsInSystem) const SliverToBoxAdapter(child: DesktopSearchResultHeader()),

                      getProcessingConversationsWidget(convoProvider.processingConversations),

                      // Main conversations content
                      if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
                        SliverToBoxAdapter(
                          child: FadeTransition(
                            opacity: _fadeAnimation,
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 80),
                              child: Center(
                                child: isSearchActive
                                    ? const Column(
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
                                      )
                                    : const DesktopEmptyConversations(),
                              ),
                            ),
                          ),
                        )
                      else if (convoProvider.groupedConversations.isEmpty && convoProvider.isLoadingConversations)
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
                                      var provider = Provider.of<ConversationProvider>(context, listen: false);
                                      if (provider.previousQuery.isNotEmpty) {
                                        if (visibilityInfo.visibleFraction > 0 &&
                                            !provider.isLoadingConversations &&
                                            (provider.totalSearchPages > provider.currentSearchPage)) {
                                          provider.searchMoreConversations();
                                        }
                                      } else {
                                        if (visibilityInfo.visibleFraction > 0 && !provider.isLoadingConversations) {
                                          provider.getMoreConversationsFromServer();
                                        }
                                      }
                                    },
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 32),
                                      child: convoProvider.isLoadingConversations
                                          ? const Center(
                                              child: CircularProgressIndicator(
                                                valueColor:
                                                    AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
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
    );
  }

  Widget _buildConversationDetailView() {
    return DesktopConversationDetailPage(
      conversation: _selectedConversation!,
      showBackButton: true,
      onBackPressed: _navigateBackToConversationsList,
    );
  }

  Widget _buildHeader() {
    final responsive = ResponsiveHelper(context);

    return Container(
      padding: EdgeInsets.fromLTRB(
        responsive.spacing(baseSpacing: 40),
        responsive.spacing(baseSpacing: 0),
        responsive.spacing(baseSpacing: 40),
        responsive.spacing(baseSpacing: 24),
      ),
      child: Consumer<ConversationProvider>(
        builder: (context, convoProvider, _) {
          final totalConversations = convoProvider.groupedConversations.values
              .fold<int>(0, (sum, conversations) => sum + conversations.length);

          return Row(
            children: [
              // Left side - Title and subtitle
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Conversations',
                      style: responsive.headlineLarge.copyWith(
                        color: ResponsiveHelper.textPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: responsive.spacing(baseSpacing: 4)),
                    Text(
                      convoProvider.previousQuery.isNotEmpty
                          ? 'Search results for "${convoProvider.previousQuery}"'
                          : totalConversations > 0
                              ? 'Your conversation history'
                              : 'No conversations yet',
                      style: responsive.bodyMedium.copyWith(
                        color: ResponsiveHelper.textTertiary,
                      ),
                    ),
                  ],
                ),
              ),
              // Right side - Search bar
              const SizedBox(width: 20),
              const SizedBox(
                width: 320,
                child: DesktopSearchWidget(),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildConversationGroup(
    DateTime date,
    List<ServerConversation> conversations,
    bool isFirst,
  ) {
    return Container(
      margin: EdgeInsets.only(top: isFirst ? 16 : 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.only(
              left: 2,
              bottom: 12,
            ),
            child: Text(
              DateFormat('MMM d, yyyy').format(date),
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: ResponsiveHelper.textTertiary,
                letterSpacing: 0.1,
              ),
            ),
          ),
          ...conversations.asMap().entries.map((entry) {
            final index = entry.key;
            final conversation = entry.value;

            return Container(
              margin: EdgeInsets.only(bottom: index == conversations.length - 1 ? 0 : 8),
              child: DesktopConversationCard(
                conversation: conversation,
                onTap: () => _navigateToConversationDetail(conversation, index, date),
                index: index,
                date: date,
              ),
            );
          }),
        ],
      ),
    );
  }
}
