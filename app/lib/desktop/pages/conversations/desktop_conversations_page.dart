import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'desktop_conversation_detail_page.dart';
import 'widgets/desktop_conversation_card.dart';
import 'widgets/desktop_empty_conversations.dart';
import 'widgets/desktop_search_widget.dart';
import 'widgets/desktop_search_result_header.dart';
import 'widgets/desktop_recording_widget.dart';

/// Desktop conversations page - premium minimal design
class DesktopConversationsPage extends StatefulWidget {
  final VoidCallback? onMinimizeRecording;
  final bool isRecordingMinimized;

  const DesktopConversationsPage({
    super.key,
    this.onMinimizeRecording,
    this.isRecordingMinimized = false,
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

  // Search functionality
  late TextEditingController _searchController;
  late FocusNode _searchFocusNode;
  final Debouncer _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  bool _isSearchFocused = false;

  // State for inline conversation detail viewing
  bool _showingConversationDetail = false;
  ServerConversation? _selectedConversation;
  int? _selectedConversationIndex;
  DateTime? _selectedDate;
  ConversationDetailProvider? _conversationDetailProvider;

  @override
  void initState() {
    super.initState();

    // Initialize search controllers
    _searchController = TextEditingController();
    _searchFocusNode = FocusNode();
    _searchFocusNode.addListener(() {
      setState(() {
        _isSearchFocused = _searchFocusNode.hasFocus;
      });
    });

    // Initialize animations for premium feel
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
    _searchController.dispose();
    _searchFocusNode.dispose();
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
      _selectedConversationIndex = index;
      _selectedDate = date;
      _conversationDetailProvider = detailProvider;
    });
  }

  void _navigateBackToConversationsList() {
    setState(() {
      _showingConversationDetail = false;
      _selectedConversation = null;
      _selectedConversationIndex = null;
      _selectedDate = null;
      _conversationDetailProvider?.dispose();
      _conversationDetailProvider = null;
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
        final showExpandedRecording = isRecordingOrInitializing && !widget.isRecordingMinimized;
        final showConversations = !isRecordingOrInitializing || widget.isRecordingMinimized;

        // If showing conversation detail, display it instead of the conversations list
        if (_showingConversationDetail && _selectedConversation != null && _conversationDetailProvider != null) {
          return ChangeNotifierProvider.value(
            value: _conversationDetailProvider!,
            child: _buildConversationDetailView(),
          );
        }

        // Otherwise show the normal conversations list view
        return Container(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.85),
          child: Stack(
            children: [
              // Main conversations content - ALWAYS visible
              CustomScrollView(
                slivers: [
                  const SliverToBoxAdapter(child: SizedBox(height: 20)),

                  // Hardware cards section (first part - before header)
                  SliverToBoxAdapter(
                    child: FadeTransition(
                      opacity: _fadeAnimation,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 32),
                        child: Column(
                          children: [
                            const SpeechProfileCardWidget(),
                            const SizedBox(height: 12),
                            const UpdateFirmwareCardWidget(),
                          ],
                        ),
                      ),
                    ),
                  ),

                  // Header section with title and compact search
                  SliverToBoxAdapter(
                    child: FadeTransition(
                      opacity: _fadeAnimation,
                      child: _buildHeader(),
                    ),
                  ),

                  // Recording widget section (after header)
                  if (!isRecordingOrInitializing)
                    SliverToBoxAdapter(
                      child: FadeTransition(
                        opacity: _fadeAnimation,
                        child: Container(
                          padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
                          child: DesktopPremiumRecordingWidget(
                            hasConversations: convoProvider.groupedConversations.isNotEmpty,
                          ),
                        ),
                      ),
                    ),

                  const SliverToBoxAdapter(child: DesktopSearchResultHeader()),
                  getProcessingConversationsWidget(convoProvider.processingConversations),

                  // Main conversations content with premium design
                  if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
                    SliverToBoxAdapter(
                      child: FadeTransition(
                        opacity: _fadeAnimation,
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 80),
                          child: const Center(
                            child: DesktopEmptyConversations(),
                          ),
                        ),
                      ),
                    )
                  else if (convoProvider.groupedConversations.isEmpty && convoProvider.isLoadingConversations)
                    SliverToBoxAdapter(
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 80),
                        child: Center(
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
                                      ? Center(
                                          child: CircularProgressIndicator(
                                            valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                                            strokeWidth: 2,
                                          ),
                                        )
                                      : const SizedBox(height: 20),
                                ),
                              );
                            }

                            // Conversation groups with premium spacing
                            var date = convoProvider.groupedConversations.keys.elementAt(index);
                            List<ServerConversation> conversationsForDate = convoProvider.groupedConversations[date]!;

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

              // Full-screen recording overlay
              if (showExpandedRecording)
                AnimatedOpacity(
                  opacity: showExpandedRecording ? 1.0 : 0.0,
                  duration: const Duration(milliseconds: 400),
                  child: Container(
                    width: double.infinity,
                    height: double.infinity,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundSecondary.withOpacity(0.98),
                    ),
                    child: DesktopPremiumRecordingWidget(
                      onMinimize: widget.onMinimizeRecording,
                    ),
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
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 24),
      ),
      child: Row(
        children: [
          // Title section
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
                Consumer<ConversationProvider>(
                  builder: (context, convoProvider, _) {
                    if (convoProvider.isLoadingConversations) {
                      return Text(
                        'Loading conversations...',
                        style: responsive.bodyMedium.copyWith(
                          color: ResponsiveHelper.textTertiary,
                        ),
                      );
                    }

                    final totalConversations = convoProvider.groupedConversations.values
                        .fold<int>(0, (sum, conversations) => sum + conversations.length);

                    return Text(
                      convoProvider.previousQuery.isNotEmpty
                          ? 'Search results for "${convoProvider.previousQuery}"'
                          : totalConversations > 0
                              ? 'Your conversation history'
                              : 'No conversations yet',
                      style: responsive.bodyMedium.copyWith(
                        color: ResponsiveHelper.textTertiary,
                      ),
                    );
                  },
                ),
              ],
            ),
          ),

          // Compact search and filter section
          SizedBox(
            width: responsive.responsiveWidth(baseWidth: 400, maxWidth: 500),
            child: _buildCompactSearch(),
          ),
        ],
      ),
    );
  }

  Widget _buildCompactSearch() {
    return Consumer<ConversationProvider>(
      builder: (context, convoProvider, _) {
        return Row(
          children: [
            // Compact search bar
            Expanded(
              child: _buildSearchBar(convoProvider),
            ),

            const SizedBox(width: 12),

            // Filter button
            _buildFilterButton(convoProvider),
          ],
        );
      },
    );
  }

  Widget _buildSearchBar(ConversationProvider convoProvider) {
    // Update search controller with current query if it's different
    if (_searchController.text != convoProvider.previousQuery) {
      _searchController.text = convoProvider.previousQuery;
    }

    return Container(
      height: 48,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: _isSearchFocused
              ? ResponsiveHelper.purplePrimary.withOpacity(0.6)
              : ResponsiveHelper.backgroundQuaternary,
          width: 1,
        ),
        boxShadow: _isSearchFocused
            ? [
                BoxShadow(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ]
            : [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 4,
                  offset: const Offset(0, 1),
                ),
              ],
      ),
      child: TextFormField(
        controller: _searchController,
        focusNode: _searchFocusNode,
        onChanged: (value) {
          _debouncer.run(() async {
            await convoProvider.searchConversations(value);
          });
          setState(() {}); // Update UI for clear button visibility
        },
        style: const TextStyle(
          color: ResponsiveHelper.textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w400,
        ),
        decoration: InputDecoration(
          hintText: 'Search conversations...',
          hintStyle: const TextStyle(
            color: ResponsiveHelper.textTertiary,
            fontSize: 14,
            fontWeight: FontWeight.w400,
          ),
          filled: false,
          border: InputBorder.none,
          focusedBorder: InputBorder.none,
          enabledBorder: InputBorder.none,
          prefixIcon: Container(
            width: 20,
            height: 20,
            margin: const EdgeInsets.only(left: 14, right: 8),
            child: Center(
              child: Icon(
                Icons.search_rounded,
                color: _isSearchFocused ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                size: 16,
              ),
            ),
          ),
          suffixIcon: _searchController.text.isNotEmpty
              ? Container(
                  width: 20,
                  height: 20,
                  margin: const EdgeInsets.only(right: 14),
                  child: Center(
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () async {
                          await convoProvider.searchConversations("");
                          _searchController.clear();
                          setState(() {});
                        },
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          width: 18,
                          height: 18,
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundQuaternary,
                            borderRadius: BorderRadius.circular(9),
                          ),
                          child: const Icon(
                            Icons.close_rounded,
                            color: ResponsiveHelper.textSecondary,
                            size: 10,
                          ),
                        ),
                      ),
                    ),
                  ),
                )
              : null,
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 12,
          ),
        ),
      ),
    );
  }

  Widget _buildFilterButton(ConversationProvider convoProvider) {
    bool isFiltered = convoProvider.showDiscardedConversations;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: convoProvider.toggleDiscardConversations,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: isFiltered ? ResponsiveHelper.purplePrimary.withOpacity(0.15) : ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color:
                  isFiltered ? ResponsiveHelper.purplePrimary.withOpacity(0.4) : ResponsiveHelper.backgroundQuaternary,
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.05),
                blurRadius: 4,
                offset: const Offset(0, 1),
              ),
            ],
          ),
          child: Icon(
            isFiltered ? Icons.filter_alt_off_rounded : Icons.filter_alt_rounded,
            color: isFiltered ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
            size: 18,
          ),
        ),
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
          // Clean date header with minimal typography - inspired by reference
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

          // Conversations list with premium spacing
          ...conversations.asMap().entries.map((entry) {
            final index = entry.key;
            final conversation = entry.value;

            return Container(
              margin: EdgeInsets.only(bottom: index == conversations.length - 1 ? 0 : 8),
              child: DesktopConversationCard(
                conversation: conversation,
                onTap: () => _navigateToConversationDetail(conversation, index, date),
              ),
            );
          }).toList(),
        ],
      ),
    );
  }
}
