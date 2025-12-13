import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_avatar.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/molecules/omi_panel_header.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';

import 'widgets/desktop_action_items_section.dart';
import 'widgets/desktop_conversation_summary.dart';

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
  bool _isSharing = false;

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

    _animationsInitialized = true;

    SchedulerBinding.instance.addPostFrameCallback((_) async {
      var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      await provider.initConversation();
      if (provider.conversation.appResults.isEmpty) {
        final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
        final date = provider.selectedDate;
        final idx = convoProvider.getConversationIndexById(provider.conversation.id, date);
        if (idx != -1) {
          await convoProvider.updateSearchedConvoDetails(provider.conversation.id, date, idx);
        }
        provider.updateConversation(provider.conversation.id, provider.selectedDate);
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
    return startedAt == null
        ? dateTimeFormat('h:mm a', createdAt)
        : '${dateTimeFormat('h:mm a', startedAt)} to ${dateTimeFormat('h:mm a', finishedAt)}';
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
                if (widget.showBackButton) _buildAppBar(),

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

          // Transcript drawer overlay
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

  Widget _buildAppBar() {
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
          if (widget.showBackButton) ...[
            MouseRegion(
              cursor: SystemMouseCursors.click,
              child: OmiIconButton(
                icon: Icons.arrow_back_rounded,
                onPressed: widget.onBackPressed ?? () => Navigator.pop(context),
                style: OmiIconButtonStyle.outline,
                borderOpacity: 0.12,
              ),
            ),
            const SizedBox(width: 16),
          ],

          OmiAvatar(
            size: 32,
            fallback: Center(
              child: Text(
                widget.conversation.structured.getEmoji(),
                style: const TextStyle(fontSize: 16),
              ),
            ),
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.conversation.discarded
                      ? 'Discarded Conversation'
                      : (widget.conversation.structured.title.isNotEmpty
                          ? widget.conversation.structured.title.decodeString
                          : 'Untitled Conversation'),
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
                  '${dateTimeFormat('MMM d, yyyy', widget.conversation.startedAt ?? widget.conversation.createdAt)} ${widget.conversation.startedAt == null ? 'at' : 'from'} ${setTime(widget.conversation.startedAt, widget.conversation.createdAt, widget.conversation.finishedAt)}',
                  style: const TextStyle(
                    fontSize: 14,
                    color: ResponsiveHelper.textSecondary,
                  ),
                ),
              ],
            ),
          ),

          // Share button
          OmiButton(
            label: _isSharing ? 'Copied!' : 'Copy Link',
            icon: _isSharing ? null : FontAwesomeIcons.link,
            type: OmiButtonType.neutral,
            enabled: !_isSharing,
            onPressed: _isSharing ? null : _handleCopyConversationLink,
          ),

          const SizedBox(width: 12),

          // Transcript button
          OmiButton(
            label: _showTranscript ? 'Hide Transcript' : 'View Transcript',
            icon: _showTranscript ? FontAwesomeIcons.eye : FontAwesomeIcons.fileLines,
            type: _showTranscript ? OmiButtonType.primary : OmiButtonType.neutral,
            onPressed: () {
              if (_showTranscript) {
                _transcriptAnimationController.reverse().then((_) {
                  setState(() => _showTranscript = false);
                });
              } else {
                setState(() => _showTranscript = true);
                _transcriptAnimationController.forward();
              }
            },
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
                child: const Row(
                  children: [
                    OmiIconButton(
                      icon: FontAwesomeIcons.fileLines,
                      style: OmiIconButtonStyle.neutral,
                      size: 24,
                      iconSize: 12,
                      borderRadius: 6,
                      onPressed: null,
                    ),
                    SizedBox(width: 8),
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
                  // Transcript header (replaced with OmiPanelHeader)
                  OmiPanelHeader(
                    icon: FontAwesomeIcons.fileLines,
                    title: 'Transcript',
                    badgeLabel: widget.conversation.transcriptSegments.isNotEmpty
                        ? '${widget.conversation.transcriptSegments.length} segments'
                        : null,
                    onClose: () {
                      _transcriptAnimationController.reverse().then((_) {
                        setState(() {
                          _showTranscript = false;
                        });
                      });
                    },
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
    return const OmiEmptyState(
      icon: FontAwesomeIcons.fileLines,
      title: 'No Transcript Available',
      message: 'This conversation doesn\'t have a transcript.',
    );
  }

  Future<void> _handleCopyConversationLink() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);

    try {
      bool shared = await setConversationVisibility(widget.conversation.id);
      if (!shared) {
        _showSnackBar('Conversation URL could not be generated.');
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Clipboard.setData(ClipboardData(text: content));
    } catch (e) {
      _showSnackBar('Failed to generate conversation link');
    } finally {
      setState(() => _isSharing = false);
    }
  }

  Future<void> _handleShareConversation() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);

    try {
      bool shared = await setConversationVisibility(widget.conversation.id);
      if (!shared) {
        _showSnackBar('Conversation URL could not be shared.');
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Share.share(content);
    } catch (e) {
      _showSnackBar('Failed to generate share link');
    } finally {
      setState(() => _isSharing = false);
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}
