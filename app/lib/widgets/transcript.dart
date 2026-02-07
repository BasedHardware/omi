import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

// Use speaker colors from person.dart for bubble colors
final List<Color> _speakerColors = speakerColors;

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool horizontalMargin;
  final bool topMargin;
  final bool separator;
  final bool canDisplaySeconds;
  final bool isConversationDetail;
  final double bottomMargin;
  final Function(String, int)? editSegment;
  final Map<String, SpeakerLabelSuggestionEvent> suggestions;
  final List<String> taggingSegmentIds;
  final Function(SpeakerLabelSuggestionEvent)? onAcceptSuggestion;
  final String searchQuery;
  final int currentResultIndex;
  final Function(ScrollController)? onScrollControllerReady;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;
  final Map<String, TextEditingController>? segmentControllers;
  final Map<String, FocusNode>? segmentFocusNodes;
  final Function(int)? onMatchCountChanged;
  final Function(String)? onSegmentEdit;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.horizontalMargin = true,
    this.topMargin = true,
    this.separator = true,
    this.canDisplaySeconds = true,
    this.isConversationDetail = false,
    this.bottomMargin = 200,
    this.editSegment,
    this.suggestions = const {},
    this.taggingSegmentIds = const [],
    this.onAcceptSuggestion,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onScrollControllerReady,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
    this.segmentControllers,
    this.segmentFocusNodes,
    this.onMatchCountChanged,
    this.onSegmentEdit,
  });

  @override
  State<TranscriptWidget> createState() => _TranscriptWidgetState();
}

class _TranscriptWidgetState extends State<TranscriptWidget> {
  // Cache for person data to avoid repeated lookups
  final Map<String?, Person?> _personCache = {};
  // Cache for decoded text to avoid repeated decoding
  final Map<String, String> _decodedTextCache = {};

  // ScrollController to enable proper scrolling
  final ScrollController _scrollController = ScrollController();

  // Edit state
  String? _editingSegmentId;

  bool _isEditing(String id) => _editingSegmentId == id;

  void _enterEdit(String id) {
    if (widget.segmentControllers == null || widget.segmentFocusNodes == null) return;
    widget.onSegmentEdit?.call(id);
    setState(() {
      _editingSegmentId = id;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.segmentFocusNodes?[id]?.requestFocus();
    });
  }

  void _exitEdit() {
    if (_editingSegmentId == null) return;
    widget.segmentFocusNodes?[_editingSegmentId]?.unfocus();
    setState(() {
      _editingSegmentId = null;
    });
  }

  // Auto-scroll state management
  bool _userHasScrolled = false;
  bool _isAutoScrolling = false;
  int _previousSegmentCount = 0;

  // Search result tracking
  List<GlobalKey> _segmentKeys = [];
  List<int> _segmentMatchOffsets = [];
  int _previousSearchResultIndex = -1;

  // Toggle to show/hide speaker names globally
  bool _showSpeakerNames = false;

  Color _getSpeakerBubbleColor(bool isUser, int speakerId, Person? person) {
    if (isUser) {
      return const Color(0xFF8B5CF6).withValues(alpha: 0.8);
    }
    final colorIndex = (person?.colorIdx ?? speakerId) % _speakerColors.length;
    return _speakerColors[colorIndex].withValues(alpha: 0.8);
  }

  Color _getSpeakerAvatarColor(bool isUser, int speakerId, Person? person) {
    if (isUser) {
      return const Color(0xFF8B5CF6).withValues(alpha: 0.3);
    }
    if (speakerId == omiSpeakerId) {
      return Colors.purple.withValues(alpha: 0.3);
    }
    final colorIndex = (person?.colorIdx ?? speakerId) % _speakerColors.length;
    return _speakerColors[colorIndex].withValues(alpha: 0.3);
  }

  Widget _getSpeakerAvatar(int speakerId, bool isUser, Person? person) {
    if (speakerId == omiSpeakerId) {
      return Image.asset(
        Assets.images.herologo.path,
        height: 16,
        width: 16,
      );
    }
    if (isUser) {
      return Image.asset(
        Assets.images.speaker0Icon.path,
        width: 24,
        height: 24,
      );
    }
    // Always modulo by speakerImagePath.length to prevent index out of bounds
    final imageIndex =
        person != null ? person.colorIdx! % speakerImagePath.length : speakerId % speakerImagePath.length;
    return Image.asset(
      speakerImagePath[imageIndex],
      width: 24,
      height: 24,
    );
  }

  @override
  void initState() {
    super.initState();
    _previousSegmentCount = widget.segments.length;
    _initializeSegmentKeys();
    _calculateMatchOffsets();

    // Add scroll listener to detect manual scrolling
    _scrollController.addListener(_onScroll);

    // Notify parent about scroll controller
    widget.onScrollControllerReady?.call(_scrollController);

    if (widget.segments.isNotEmpty && widget.isConversationDetail) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottomGently();
      });
    }
  }

  void _initializeSegmentKeys() {
    _segmentKeys = List.generate(widget.segments.length, (index) => GlobalKey());
  }

  void _calculateMatchOffsets() {
    if (widget.searchQuery.isEmpty) {
      _segmentMatchOffsets = [];
      return;
    }

    final lowerQuery = widget.searchQuery.toLowerCase();
    int currentTotal = 0;
    _segmentMatchOffsets = [];

    for (var segment in widget.segments) {
      _segmentMatchOffsets.add(currentTotal);
      final segmentText = _getDecodedText(segment.text).toLowerCase();
      final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(segmentText);
      currentTotal += matches.length;
    }
  }

  @override
  void didUpdateWidget(TranscriptWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    bool shouldRecalculate = false;

    // Reinitialize keys if segment count changed
    if (widget.segments.length != oldWidget.segments.length) {
      _initializeSegmentKeys();
      shouldRecalculate = true;
    } else if (widget.segments != oldWidget.segments) {
      shouldRecalculate = true;
    }

    if (widget.searchQuery != oldWidget.searchQuery) {
      _previousSearchResultIndex = -1;
      shouldRecalculate = true;

      if (widget.searchQuery.isNotEmpty && widget.currentResultIndex >= 0) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _scrollToSearchResult();
        });
      }
    }

    if (shouldRecalculate) {
      _calculateMatchOffsets();
    }

    // Check if new segments were added
    if (widget.segments.length > _previousSegmentCount && !_userHasScrolled) {
      _previousSegmentCount = widget.segments.length;
      if (_editingSegmentId == null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _scrollToBottomGently();
        });
      }
    } else {
      _previousSegmentCount = widget.segments.length;
    }

    // Handle search result navigation
    if (widget.currentResultIndex != _previousSearchResultIndex &&
        widget.currentResultIndex >= 0 &&
        widget.searchQuery.isNotEmpty) {
      _previousSearchResultIndex = widget.currentResultIndex;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToSearchResult();
      });
    }
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_isAutoScrolling) {
      return;
    }

    // Check if user manually scrolled up from the bottom
    if (_scrollController.hasClients) {
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.offset;
      final threshold = 100.0;
      final distanceFromBottom = maxScroll - currentScroll;

      if (distanceFromBottom > threshold) {
        _userHasScrolled = true;
      } else if (distanceFromBottom < 50.0) {
        _userHasScrolled = false;
      }
    }
  }

  void _scrollToBottomGently() {
    if (!_scrollController.hasClients) {
      return;
    }

    final maxExtent = _scrollController.position.maxScrollExtent;

    final startOffset = (maxExtent - 30).clamp(0.0, maxExtent);

    _scrollController.jumpTo(startOffset);

    _isAutoScrolling = true;
    _scrollController
        .animateTo(
      maxExtent,
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOut,
    )
        .then((_) {
      _isAutoScrolling = false;
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToBottomGently();
    });
  }

  void _scrollToSearchResult() {
    if (!_scrollController.hasClients || widget.searchQuery.isEmpty) {
      return;
    }

    final searchQuery = widget.searchQuery.toLowerCase();
    int currentMatchIndex = 0;
    int targetSegmentIndex = -1;

    for (int segmentIndex = 0; segmentIndex < widget.segments.length; segmentIndex++) {
      final text = _getDecodedText(widget.segments[segmentIndex].text).toLowerCase();
      final matches = RegExp(RegExp.escape(searchQuery), caseSensitive: false).allMatches(text);

      if (currentMatchIndex + matches.length > widget.currentResultIndex) {
        targetSegmentIndex = segmentIndex;
        break;
      }
      currentMatchIndex += matches.length;
    }

    if (targetSegmentIndex >= 0 && targetSegmentIndex < _segmentKeys.length) {
      final segmentKey = _segmentKeys[targetSegmentIndex];
      final segmentContext = segmentKey.currentContext;

      if (segmentContext != null) {
        _scrollToContext(segmentContext);
        return;
      }

      _isAutoScrolling = true;

      final double estimatedItemHeight = 120.0;
      final double headerHeight = widget.topMargin ? 32.0 : 0.0;
      
      double targetOffset = headerHeight + (targetSegmentIndex * estimatedItemHeight);
      
      if (_scrollController.position.maxScrollExtent > estimatedItemHeight * widget.segments.length) {
          final double progress = targetSegmentIndex / widget.segments.length;
          targetOffset = progress * _scrollController.position.maxScrollExtent;
      }
      
      final double maxExtent = _scrollController.position.maxScrollExtent;
      targetOffset = targetOffset.clamp(0.0, maxExtent);

      _scrollController.animateTo(
        targetOffset,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOut,
      ).then((_) {
        if (segmentKey.currentContext != null) {
          _scrollToContext(segmentKey.currentContext!);
        } else {
          _isAutoScrolling = false;
        }
      });
    }
  }

  void _scrollToContext(BuildContext context) {
    _isAutoScrolling = true;
    Scrollable.ensureVisible(
      context,
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOutCubic,
      alignment: 0.35,
    ).then((_) {
      _isAutoScrolling = false;
    });
  }

  String _getDecodedText(String text) {
    if (!_decodedTextCache.containsKey(text)) {
      _decodedTextCache[text] = tryDecodingText(text);
    }
    return _decodedTextCache[text]!;
  }

  // Create highlighted text spans
  List<InlineSpan> _highlightSearchMatchesWithKeys(
    String text,
    String searchQuery,
    int segmentIndex,
  ) {
    if (searchQuery.isEmpty) {
      return [TextSpan(text: text)];
    }

    final spans = <InlineSpan>[];
    final lowerText = text.toLowerCase();
    final lowerQuery = searchQuery.toLowerCase();

    int globalMatchIndex = 0;
    if (segmentIndex < _segmentMatchOffsets.length) {
      globalMatchIndex = _segmentMatchOffsets[segmentIndex];
    } else {
      for (int i = 0; i < segmentIndex && i < widget.segments.length; i++) {
        final segmentText = _getDecodedText(widget.segments[i].text).toLowerCase();
        final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(segmentText);
        globalMatchIndex += matches.length;
      }
    }

    int start = 0;
    final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(lowerText);

    for (final match in matches) {
      final matchStart = match.start;
      final matchEnd = match.end;

      if (matchStart > start) {
        spans.add(TextSpan(text: text.substring(start, matchStart)));
      }

      final currentGlobalIndex = globalMatchIndex;
      final isCurrentResult = currentGlobalIndex == widget.currentResultIndex;

      spans.add(TextSpan(
        text: text.substring(matchStart, matchEnd),
        style: TextStyle(
          backgroundColor: isCurrentResult
              ? Colors.orange.withValues(alpha: 0.9)
              : Colors.deepPurple.withValues(alpha: 0.6),
          color: Colors.white,
          fontWeight: FontWeight.bold,
        ),
      ));

      start = matchEnd;
      globalMatchIndex++;
    }

    if (start < text.length) {
      spans.add(TextSpan(text: text.substring(start)));
    }

    return spans;
  }

  Person? _getPersonById(String? personId) {
    if (personId == null) return null;
    if (!_personCache.containsKey(personId)) {
      _personCache[personId] = SharedPreferencesUtil().getPersonById(personId);
    }
    return _personCache[personId];
  }

  @override
  Widget build(BuildContext context) {
    final searchBarHeight = widget.searchQuery.isNotEmpty ? 100.0 : 0.0;

    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onTap: () {
        if (_editingSegmentId != null) {
          final node = widget.segmentFocusNodes?[_editingSegmentId!];
          if (node != null && node.hasFocus) return;
          _exitEdit();
          return;
        }

        if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
          widget.onTapWhenSearchEmpty!();
        }
      },
      child: ListView.builder(
        controller: _scrollController,
        padding: EdgeInsets.only(top: searchBarHeight),
        itemCount: widget.segments.length + 2,
        itemBuilder: (context, idx) {
          if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
          if (idx == widget.segments.length + 1) return SizedBox(height: widget.bottomMargin + 120);

          if (widget.separator && idx > 1) {
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 4),
                _buildSegmentItem(idx - 1),
              ],
            );
          }

          return _buildSegmentItem(idx - 1);
        },
      ),
    );
  }

  void _toggleShowSpeakerNames() {
    setState(() {
      _showSpeakerNames = !_showSpeakerNames;
    });
  }

  Widget _buildSegmentItem(int segmentIdx) {
    final data = widget.segments[segmentIdx];
    final Person? person = data.personId != null ? _getPersonById(data.personId) : null;
    final isTagging = widget.taggingSegmentIds.contains(data.id);
    final bool isUser = data.isUser;
    return Container(
        key: segmentIdx >= 0 && segmentIdx < _segmentKeys.length ? _segmentKeys[segmentIdx] : null,
        child: Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
              widget.horizontalMargin ? 16 : 0, 4.0, widget.horizontalMargin ? 16 : 0, 4.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (!isUser) ...[
                // Avatar for other speakers (left side)
                GestureDetector(
                  onTap: data.speakerId == omiSpeakerId
                      ? null
                      : () {
                          widget.editSegment?.call(data.id, data.speakerId);
                          MixpanelManager().tagSheetOpened();
                        },
                  child: Column(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId, person),
                        child: _getSpeakerAvatar(data.speakerId, isUser, person),
                      ),
                      const SizedBox(height: 2),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
              ],

              // Message bubble
              Expanded(
                child: Column(
                  crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                  children: [
                    if (!isUser) ...[
                      Padding(
                        padding: const EdgeInsets.only(left: 4, bottom: 2),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            GestureDetector(
                              onTap: data.speakerId == omiSpeakerId
                                  ? null
                                  : () {
                                      widget.editSegment?.call(data.id, data.speakerId);
                                      MixpanelManager().tagSheetOpened();
                                    },
                              child: Text(
                                data.speakerId == omiSpeakerId ? 'omi' : (person?.name ?? 'Speaker ${data.speakerId}'),
                                style: TextStyle(
                                  color: data.speakerId == omiSpeakerId || person != null
                                      ? Colors.grey.shade300
                                      : Colors.grey.shade400,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            if (isTagging) ...[
                              const SizedBox(width: 6),
                              const SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 1.5,
                                  valueColor: AlwaysStoppedAnimation(Colors.white),
                                ),
                              )
                            ],
                          ],
                        ),
                      ),
                    ],

                    // Chat bubble
                    Row(
                      mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
                      children: [
                        Flexible(
                          child: Container(
                            constraints: BoxConstraints(
                              maxWidth: MediaQuery.of(context).size.width * 0.75,
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                            decoration: BoxDecoration(
                              color: _getSpeakerBubbleColor(isUser, data.speakerId, person),
                              borderRadius: BorderRadius.only(
                                topLeft: Radius.circular(isUser
                                    ? 18
                                    : (segmentIdx > 0 && !widget.segments[segmentIdx - 1].isUser)
                                        ? 6
                                        : 18),
                                topRight: Radius.circular(isUser ? 18 : 18),
                                bottomLeft: Radius.circular(18),
                                bottomRight: Radius.circular(isUser ? 6 : 18),
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.15),
                                  blurRadius: 4,
                                  offset: const Offset(0, 1),
                                ),
                              ],
                            ),
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onDoubleTap: () {
                                if (widget.searchQuery.isNotEmpty) return;
                                if (_isEditing(data.id)) {
                                  _exitEdit();
                                } else {
                                  _enterEdit(data.id);
                                }
                              },
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  _isEditing(data.id)
                                      ? _buildEditor(data, isUser)
                                      : _buildReadOnlyText(data, segmentIdx, isUser),
                                  if (data.translations.isNotEmpty) ...[
                                    const SizedBox(height: 8),
                                    ...data.translations.map((translation) => Padding(
                                          padding: const EdgeInsets.only(top: 4),
                                          child: Text(
                                            _getDecodedText(translation.text),
                                            style: TextStyle(
                                              letterSpacing: 0.0,
                                              color: isUser
                                                  ? Colors.white.withValues(alpha: 0.8)
                                                  : Colors.grey.shade300.withValues(alpha: 0.8),
                                              fontSize: 14,
                                              fontStyle: FontStyle.italic,
                                              height: 1.3,
                                            ),
                                            textAlign: TextAlign.left,
                                          ),
                                        )),
                                    const SizedBox(height: 4),
                                    _buildTranslationNotice(),
                                  ],
                                  // Timestamp, provider, and play button
                                  if (widget.canDisplaySeconds ||
                                      data.sttProvider != null ||
                                      widget.onSegmentTap != null) ...[
                                    const SizedBox(height: 4),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.end,
                                      children: [
                                        if (data.sttProvider != null) ...[
                                          Text(
                                            SttProviderConfig.getDisplayName(data.sttProvider),
                                            style: TextStyle(
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.5) : Colors.grey.shade500,
                                              fontSize: 10,
                                              fontStyle: FontStyle.italic,
                                            ),
                                          ),
                                          if (widget.canDisplaySeconds) ...[
                                            Text(
                                              ' · ',
                                              style: TextStyle(
                                                color:
                                                    isUser ? Colors.white.withValues(alpha: 0.5) : Colors.grey.shade500,
                                                fontSize: 10,
                                              ),
                                            ),
                                          ],
                                        ],
                                        // Play button for tap-to-seek
                                        if (widget.onSegmentTap != null) ...[
                                          GestureDetector(
                                            onTap: () {
                                              HapticFeedback.lightImpact();
                                              widget.onSegmentTap?.call(data);
                                            },
                                            child: Icon(
                                              Icons.play_circle_outline,
                                              size: 16,
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.7) : Colors.grey.shade400,
                                            ),
                                          ),
                                          const SizedBox(width: 6),
                                        ],
                                        if (widget.canDisplaySeconds)
                                          Text(
                                            data.getTimestampString(),
                                            style: TextStyle(
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.7) : Colors.grey.shade400,
                                              fontSize: 11,
                                            ),
                                          ),
                                      ],
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              if (isUser) ...[
                const SizedBox(width: 8),
                // Avatar for user (right side)
                GestureDetector(
                  onTap: () {
                    widget.editSegment?.call(data.id, data.speakerId);
                    MixpanelManager().tagSheetOpened();
                  },
                  child: Column(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId, person),
                        child: _getSpeakerAvatar(data.speakerId, isUser, person),
                      ),
                      const SizedBox(height: 2),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ));
  }

  Widget _buildReadOnlyText(TranscriptSegment data, int segmentIdx, bool isUser) {
    return SelectionArea(
      child: RichText(
        textAlign: TextAlign.left,
        text: TextSpan(
          style: TextStyle(
            letterSpacing: 0.0,
            color: isUser ? Colors.white : Colors.grey.shade100,
            fontSize: 15,
            height: 1.4,
          ),
          children: widget.searchQuery.isNotEmpty
              ? _highlightSearchMatchesWithKeys(
                  _getDecodedText(data.text),
                  widget.searchQuery,
                  segmentIdx,
                )
              : [
                  TextSpan(text: _getDecodedText(data.text)),
                ],
        ),
      ),
    );
  }

  Widget _buildEditor(TranscriptSegment data, bool isUser) {
    final controller = widget.segmentControllers![data.id]!;
    final focusNode = widget.segmentFocusNodes![data.id]!;

    return TextField(
      controller: controller,
      focusNode: focusNode,
      keyboardType: TextInputType.multiline,
      minLines: 1,
      maxLines: null,
      autofocus: false,
      style: TextStyle(
        letterSpacing: 0.0,
        color: isUser ? Colors.white : Colors.grey.shade100,
        fontSize: 15,
        height: 1.4,
      ),
      decoration: const InputDecoration(
        border: InputBorder.none,
        isDense: true,
        contentPadding: EdgeInsets.zero,
      ),
      onEditingComplete: _exitEdit,
    );
  }

  Widget _buildTranslationNotice() {
    return GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              title: Text(context.l10n.translationNotice),
              content: Text(
                context.l10n.translationNoticeMessage,
                style: const TextStyle(fontSize: 14),
              ),
              actions: [
                TextButton(
                  child: Text(context.l10n.ok),
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                ),
              ],
            );
          },
        );
      },
      child: const Opacity(
        opacity: 0.5,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle,
              size: 12,
              color: Colors.grey,
            ),
            SizedBox(width: 4),
            Text(
              'translated by omi',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class LiteTranscriptWidget extends StatelessWidget {
  final List<TranscriptSegment> segments;

  const LiteTranscriptWidget({
    super.key,
    required this.segments,
  });

  static String? _processText(List<TranscriptSegment> segments) {
    if (segments.isEmpty) return null;

    var text = getLastTranscript(segments, maxCount: 70, includeTimestamps: false);
    text = text.replaceAll(RegExp(r"\s+|\n+"), " ");
    // Add ellipsis at the start to indicate there's more content before
    return '...$text';
  }

  @override
  Widget build(BuildContext context) {
    final processedText = _processText(segments);
    if (processedText == null) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(7, 0, 8, 0),
      child: Text(
        processedText,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(context).textTheme.bodyMedium!.copyWith(
              color: Colors.grey.shade300.withValues(alpha: 0.6),
              height: 1.3,
            ),
        textAlign: TextAlign.right,
      ),
    );
  }
}

String getLastTranscript(List<TranscriptSegment> transcriptSegments,
    {int? maxCount, bool generate = false, bool includeTimestamps = true}) {
  var transcript = TranscriptSegment.segmentsAsString(
      transcriptSegments.sublist(transcriptSegments.length >= 50 ? transcriptSegments.length - 50 : 0),
      includeTimestamps: includeTimestamps);
  if (maxCount != null) transcript = transcript.substring(max(transcript.length - maxCount, 0));
  return tryDecodingText(transcript);
}

// Cache for decoded text
final Map<String, String> _decodedTextCache = {};

String tryDecodingText(String text) {
  if (!_decodedTextCache.containsKey(text)) {
    try {
      _decodedTextCache[text] = utf8.decode(text.toString().codeUnits);
    } catch (e) {
      _decodedTextCache[text] = text;
    }
  }
  return _decodedTextCache[text]!;
}

String formatChatTimestamp(DateTime dateTime, {BuildContext? context}) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);
  final timeStr = dateTimeFormat('h:mm a', dateTime);

  if (messageDate == today) {
    // Today, show time only
    return timeStr;
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    if (context != null) {
      return context.l10n.yesterdayAtTime(timeStr);
    }
    return 'Yesterday $timeStr';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
