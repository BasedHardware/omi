import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:provider/provider.dart';

import 'widgets/desktop_action_items_section.dart';
import 'widgets/desktop_conversation_summary.dart';
import 'widgets/desktop_conversation_header.dart';

class DesktopConversationDetailPage extends StatefulWidget {
  final ServerConversation conversation;
  final bool showBackButton;
  final VoidCallback? onBackPressed;

  const DesktopConversationDetailPage({
    super.key,
    required this.conversation,
    this.showBackButton = true,
    this.onBackPressed,
  });

  @override
  State<DesktopConversationDetailPage> createState() => _DesktopConversationDetailPageState();
}

class _DesktopConversationDetailPageState extends State<DesktopConversationDetailPage> with TickerProviderStateMixin {
  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;
  late AnimationController _transcriptAnimationController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;
  late Animation<Offset> _transcriptSlideAnimation;

  bool _animationsInitialized = false;
  bool _showTranscript = false;

  @override
  void initState() {
    super.initState();

    // Initialize animations for modern feel
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

    _transcriptAnimationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );

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

    _transcriptSlideAnimation = Tween<Offset>(
      begin: const Offset(1.0, 0.0),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _transcriptAnimationController,
      curve: Curves.easeOutCubic,
    ));

    // Mark animations as initialized
    _animationsInitialized = true;

    SchedulerBinding.instance.addPostFrameCallback((_) async {
      var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      await provider.initConversation();
      if (provider.conversation.appResults.isEmpty) {
        await Provider.of<ConversationProvider>(context, listen: false).updateSearchedConvoDetails(provider.conversation.id, provider.selectedDate, provider.conversationIdx);
        provider.updateConversation(provider.conversationIdx, provider.selectedDate);
      }

      // Start animations
      _fadeController.forward();
      _slideController.forward();
    });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    _transcriptAnimationController.dispose();
    super.dispose();
  }

  String setTime(DateTime? startedAt, DateTime createdAt, DateTime? finishedAt) {
    return startedAt == null ? dateTimeFormat('h:mm a', createdAt) : '${dateTimeFormat('h:mm a', startedAt)} to ${dateTimeFormat('h:mm a', finishedAt)}';
  }

  @override
  Widget build(BuildContext context) {
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
      ),
      child: Stack(
        children: [
          // Animated background pattern
          _buildAnimatedBackground(),

          // Main content
          Container(
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.02),
            ),
            child: Column(
              children: [
                // Modern header with conversation title and controls (conditionally shown)
                if (widget.showBackButton) _buildModernAppBar(),

                // Main content area
                Expanded(
                  child: _animationsInitialized
                      ? FadeTransition(
                          opacity: _fadeAnimation,
                          child: SlideTransition(
                            position: _slideAnimation,
                            child: _buildMainContent(),
                          ),
                        )
                      : _buildMainContent(),
                ),
              ],
            ),
          ),

          // Transcript drawer overlay - positioned at root level for full height
          if (_showTranscript) _buildTranscriptDrawer(),
        ],
      ),
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

  Widget _buildModernAppBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Back button (conditionally shown)
          if (widget.showBackButton) ...[
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: widget.onBackPressed ?? () => Navigator.pop(context),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    FontAwesomeIcons.arrowLeft,
                    color: ResponsiveHelper.textSecondary,
                    size: 16,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
          ],

          // Conversation emoji and title
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              widget.conversation.structured.getEmoji(),
              style: const TextStyle(fontSize: 16),
            ),
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.conversation.discarded ? 'Discarded Conversation' : (widget.conversation.structured.title.isNotEmpty ? widget.conversation.structured.title.decodeString : 'Untitled Conversation'),
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textPrimary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  '${dateTimeFormat('MMM d, yyyy', widget.conversation.createdAt)} ${widget.conversation.startedAt == null ? 'at' : 'from'} ${setTime(widget.conversation.startedAt, widget.conversation.createdAt, widget.conversation.finishedAt)}',
                  style: TextStyle(
                    fontSize: 14,
                    color: ResponsiveHelper.textSecondary,
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
                if (_showTranscript) {
                  _transcriptAnimationController.reverse().then((_) {
                    setState(() {
                      _showTranscript = false;
                    });
                  });
                } else {
                  setState(() {
                    _showTranscript = true;
                  });
                  _transcriptAnimationController.forward();
                }
              },
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: _showTranscript ? ResponsiveHelper.purplePrimary.withOpacity(0.15) : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(12),
                  border: _showTranscript
                      ? Border.all(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                          width: 1,
                        )
                      : null,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _showTranscript ? FontAwesomeIcons.eye : FontAwesomeIcons.fileLines,
                      color: _showTranscript ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                      size: 14,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _showTranscript ? 'Hide Transcript' : 'View Transcript',
                      style: TextStyle(
                        color: _showTranscript ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMainContent() {
    return Container(
      padding: const EdgeInsets.all(20),
      child: Container(
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.1),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: Column(
            children: [
              // Section header
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                  border: Border(
                    bottom: BorderSide(
                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                      width: 1,
                    ),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      FontAwesomeIcons.fileAlt,
                      color: ResponsiveHelper.textSecondary,
                      size: 16,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Conversation Details',
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),

              // Content
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Action Items Section (above summary as requested)
                      if (widget.conversation.structured.actionItems.where((item) => !item.deleted).isNotEmpty) ...[
                        DesktopActionItemsSection(conversation: widget.conversation),
                        const SizedBox(height: 32),
                      ],

                      // Summary Section
                      DesktopConversationSummary(conversation: widget.conversation),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTranscriptDrawer() {
    return Stack(
      children: [
        // Backdrop blur overlay
        Positioned.fill(
          child: GestureDetector(
            onTap: () {
              _transcriptAnimationController.reverse().then((_) {
                setState(() {
                  _showTranscript = false;
                });
              });
            },
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 8.0, sigmaY: 8.0),
              child: Container(
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundPrimary.withOpacity(0.2),
                ),
              ),
            ),
          ),
        ),

        // Transcript drawer panel
        Positioned(
          top: 0,
          right: 0,
          bottom: 0,
          child: SlideTransition(
            position: _transcriptSlideAnimation,
            child: Container(
              width: 500, // Fixed width similar to app detail drawer
              height: double.infinity,
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundPrimary,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.4),
                    blurRadius: 24,
                    offset: const Offset(-6, 0),
                  ),
                  BoxShadow(
                    color: Colors.black.withOpacity(0.2),
                    blurRadius: 40,
                    offset: const Offset(-12, 0),
                  ),
                ],
              ),
              child: Column(
                children: [
                  // Transcript header
                  Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
                      border: Border(
                        bottom: BorderSide(
                          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                          width: 1,
                        ),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          FontAwesomeIcons.fileLines,
                          color: ResponsiveHelper.textSecondary,
                          size: 18,
                        ),
                        const SizedBox(width: 12),
                        Text(
                          'Transcript',
                          style: TextStyle(
                            color: ResponsiveHelper.textPrimary,
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const Spacer(),
                        if (widget.conversation.transcriptSegments.isNotEmpty)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              '${widget.conversation.transcriptSegments.length} segments',
                              style: TextStyle(
                                color: ResponsiveHelper.textTertiary,
                                fontSize: 12,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        const SizedBox(width: 12),
                        // Close button
                        Material(
                          color: Colors.transparent,
                          child: InkWell(
                            onTap: () {
                              _transcriptAnimationController.reverse().then((_) {
                                setState(() {
                                  _showTranscript = false;
                                });
                              });
                            },
                            borderRadius: BorderRadius.circular(8),
                            child: Container(
                              padding: const EdgeInsets.all(8),
                              child: Icon(
                                FontAwesomeIcons.xmark,
                                color: ResponsiveHelper.textSecondary,
                                size: 16,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Transcript content
                  Expanded(
                    child: widget.conversation.transcriptSegments.isNotEmpty
                        ? TranscriptWidget(
                            segments: widget.conversation.transcriptSegments,
                            horizontalMargin: true,
                            topMargin: true,
                            canDisplaySeconds: true,
                            isConversationDetail: true,
                            bottomMargin: 20,
                          )
                        : _buildEmptyTranscript(),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyTranscript() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(
                FontAwesomeIcons.fileLines,
                size: 48,
                color: ResponsiveHelper.purplePrimary,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'No Transcript Available',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'This conversation doesn\'t have a transcript.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
