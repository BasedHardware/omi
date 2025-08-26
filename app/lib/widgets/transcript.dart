import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';

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

  // Auto-scroll state management
  bool _userHasScrolled = false;
  bool _isAutoScrolling = false;
  int _previousSegmentCount = 0;
  
  // Search result tracking
  List<GlobalKey> _segmentKeys = [];
  int _previousSearchResultIndex = -1;

  // Define distinct muted colors for different speakers
  static const List<Color> _speakerColors = [
    Color(0xFF3A2E26), // Dark warm brown
    Color(0xFF26313A), // Dark navy blue
    Color(0xFF2E3A26), // Dark forest green
    Color(0xFF3A2634), // Dark burgundy
    Color(0xFF263A34), // Dark teal
    Color(0xFF34332A), // Dark olive
    Color(0xFF2F2A3A), // Dark plum
    Color(0xFF3A3026), // Dark bronze
  ];

  Color _getSpeakerBubbleColor(bool isUser, int speakerId) {
    if (isUser) {
      return Color(0xFF8B5CF6).withOpacity(0.8);
    }
    // Use speakerId to get consistent color for each speaker
    final colorIndex = speakerId % _speakerColors.length;
    return _speakerColors[colorIndex].withOpacity(0.8);
  }

  Color _getSpeakerAvatarColor(bool isUser, int speakerId) {
    if (isUser) {
      return Color(0xFF8B5CF6).withOpacity(0.3);
    }
    final colorIndex = speakerId % _speakerColors.length;
    return _speakerColors[colorIndex].withOpacity(0.3);
  }

  @override
  void initState() {
    super.initState();
    _previousSegmentCount = widget.segments.length;
    _initializeSegmentKeys();

    // Add scroll listener to detect manual scrolling
    _scrollController.addListener(_onScroll);
    
    // Notify parent about scroll controller
    widget.onScrollControllerReady?.call(_scrollController);

    // Auto-scroll to bottom after first frame
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToBottom();
    });
  }
  
  void _initializeSegmentKeys() {
    _segmentKeys = List.generate(widget.segments.length, (index) => GlobalKey());
  }

  @override
  void didUpdateWidget(TranscriptWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    // Reinitialize keys if segment count changed
    if (widget.segments.length != oldWidget.segments.length) {
      _initializeSegmentKeys();
    }

    // Check if new segments were added
    if (widget.segments.length > _previousSegmentCount && !_userHasScrolled) {
      _previousSegmentCount = widget.segments.length;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottom();
      });
    } else {
      _previousSegmentCount = widget.segments.length;
    }
    
    // Handle search result navigation
    if (widget.currentResultIndex != _previousSearchResultIndex && 
        widget.currentResultIndex >= 0 && 
        widget.searchQuery.isNotEmpty) {
      _previousSearchResultIndex = widget.currentResultIndex;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        // Temporarily allow auto-scrolling for search results
        final wasUserScrolled = _userHasScrolled;
        _userHasScrolled = false;
        _scrollToSearchResult();
        // Restore the user scroll state after a delay
        Future.delayed(const Duration(milliseconds: 600), () {
          _userHasScrolled = wasUserScrolled;
        });
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
    if (_isAutoScrolling) return;

    // Check if user manually scrolled up from the bottom
    if (_scrollController.hasClients) {
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.offset;
      final threshold = 100.0; // pixels from bottom

      if (maxScroll - currentScroll > threshold) {
        _userHasScrolled = true;
      } else {
        // User scrolled back to bottom, resume auto-scrolling
        _userHasScrolled = false;
      }
    }
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients || _userHasScrolled) return;

    _isAutoScrolling = true;
    _scrollController
        .animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
    )
        .then((_) {
      _isAutoScrolling = false;
    });
  }
  
  // Calculate the local search index for a specific segment
  int _getLocalSearchIndex(int segmentIndex) {
    if (widget.searchQuery.isEmpty || widget.currentResultIndex < 0) return -1;
    
    int currentMatchCount = 0;
    final searchQuery = widget.searchQuery.toLowerCase();
    
    // Count matches in segments before the current one
    for (int i = 0; i < segmentIndex; i++) {
      final segmentText = _getDecodedText(widget.segments[i].text).toLowerCase();
      int startIndex = 0;
      while (true) {
        int index = segmentText.indexOf(searchQuery, startIndex);
        if (index == -1) break;
        currentMatchCount++;
        startIndex = index + 1;
      }
    }
    
    // Count matches in the current segment to see if our target falls within it
    final currentSegmentText = _getDecodedText(widget.segments[segmentIndex].text).toLowerCase();
    int segmentMatches = 0;
    int startIndex = 0;
    while (true) {
      int index = currentSegmentText.indexOf(searchQuery, startIndex);
      if (index == -1) break;
      segmentMatches++;
      startIndex = index + 1;
    }
    
    // Check if the current result index falls within this segment
    if (widget.currentResultIndex >= currentMatchCount && 
        widget.currentResultIndex < currentMatchCount + segmentMatches) {
      return widget.currentResultIndex - currentMatchCount;
    }
    
    return -1; // Current result is not in this segment
  }

  void _scrollToSearchResult() {
    if (!_scrollController.hasClients || widget.searchQuery.isEmpty) return;
    
    // Find which segment contains the current search result
    int currentMatchCount = 0;
    int targetSegmentIndex = -1;
    
    for (int i = 0; i < widget.segments.length; i++) {
      final segmentText = _getDecodedText(widget.segments[i].text).toLowerCase();
      final searchQuery = widget.searchQuery.toLowerCase();
      
      // Count matches in this segment
      int segmentMatches = 0;
      int startIndex = 0;
      while (true) {
        int index = segmentText.indexOf(searchQuery, startIndex);
        if (index == -1) break;
        segmentMatches++;
        startIndex = index + 1;
      }
      
      // Check if current result index falls within this segment
      if (widget.currentResultIndex < currentMatchCount + segmentMatches) {
        targetSegmentIndex = i;
        break;
      }
      
      currentMatchCount += segmentMatches;
    }
    
    if (targetSegmentIndex >= 0 && targetSegmentIndex < _segmentKeys.length) {
      final targetKey = _segmentKeys[targetSegmentIndex];
      final context = targetKey.currentContext;
      
      if (context != null) {
        _isAutoScrolling = true;
        
        // Use Scrollable.ensureVisible for smoother, more reliable scrolling
        Scrollable.ensureVisible(
          context,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
          alignment: 0.05, // Position the target 5% from the top of the viewport for smaller scroll
        ).then((_) {
          _isAutoScrolling = false;
        });
      }
    }
  }

  String _getDecodedText(String text) {
    if (!_decodedTextCache.containsKey(text)) {
      _decodedTextCache[text] = tryDecodingText(text);
    }
    return _decodedTextCache[text]!;
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
    // Use ListView.builder instead of ListView.separated for better performance
    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.zero,
      itemCount: widget.segments.length + 2,
      itemBuilder: (context, idx) {
        // Handle header and footer items
        if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
        if (idx == widget.segments.length + 1) return SizedBox(height: widget.bottomMargin + 120);

        // Add separator before the item (except for the first one)
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
    );
  }

  Widget _buildSegmentItem(int segmentIdx) {
    final data = widget.segments[segmentIdx];
    final Person? person = data.personId != null ? _getPersonById(data.personId) : null;
    final suggestion = widget.suggestions[data.id];
    final isTagging = widget.taggingSegmentIds.contains(data.id);
    final bool isUser = data.isUser;

    return Container(
      key: segmentIdx < _segmentKeys.length ? _segmentKeys[segmentIdx] : null,
      child: GestureDetector(
      onTap: () {
        widget.editSegment?.call(data.id, data.speakerId);
        MixpanelManager().tagSheetOpened();
      },
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(
          widget.horizontalMargin ? 16 : 0, 
          4.0, 
          widget.horizontalMargin ? 16 : 0, 
          4.0
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (!isUser) ...[
              // Avatar for other speakers (left side)
              Column(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId),
                    child: Image.asset(
                      person != null
                          ? speakerImagePath[person.colorIdx!]
                          : speakerImagePath[data.speakerId % speakerImagePath.length],
                      width: 24,
                      height: 24,
                    ),
                  ),
                  const SizedBox(height: 2),
                ],
              ),
              const SizedBox(width: 8),
            ],
            
            // Message bubble
            Expanded(
              child: Column(
                crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                children: [
                  // Speaker name (only for non-user messages and only if needed)
                  if (!isUser) ...[
                    Padding(
                      padding: const EdgeInsets.only(left: 4, bottom: 2),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            suggestion != null && person == null
                                ? '${suggestion.personName}?'
                                : (person != null ? person?.name ?? 'Deleted Person' : 'Speaker ${data.speakerId}'),
                            style: TextStyle(
                              color: person == null && !isTagging ? Colors.grey.shade400 : Colors.grey.shade300,
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                          if (!data.speechProfileProcessed && (data.personId ?? "").isEmpty) ...[
                            const SizedBox(width: 4),
                            const Icon(
                              Icons.help_outline,
                              color: Colors.orange,
                              size: 12,
                            ),
                          ],
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
                          ] else if (suggestion != null && person == null) ...[
                            const SizedBox(width: 6),
                            GestureDetector(
                              onTap: () => widget.onAcceptSuggestion?.call(suggestion),
                              child: const Text(
                                'Tag',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 11,
                                  decoration: TextDecoration.underline,
                                  decorationColor: Colors.white,
                                ),
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
                            color: _getSpeakerBubbleColor(isUser, data.speakerId),
                            borderRadius: BorderRadius.only(
                              topLeft: Radius.circular(isUser ? 18 : (segmentIdx > 0 && !widget.segments[segmentIdx - 1].isUser) ? 6 : 18),
                              topRight: Radius.circular(isUser ? 18 : 18),
                              bottomLeft: Radius.circular(18),
                              bottomRight: Radius.circular(isUser ? 6 : 18),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.15),
                                blurRadius: 4,
                                offset: const Offset(0, 1),
                              ),
                            ],
                          ),
                          child: SelectionArea(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                RichText(
                                  textAlign: TextAlign.left,
                                  text: TextSpan(
                                    children: widget.searchQuery.isNotEmpty
                                        ? highlightSearchMatches(
                                            _getDecodedText(data.text),
                                            widget.searchQuery,
                                            currentResultIndex: _getLocalSearchIndex(segmentIdx),
                                          ).map((span) {
                                            // Preserve highlight styles, apply default styles only to non-highlighted text
                                            if (span.style?.backgroundColor != null) {
                                              return span; // Keep highlight style as is
                                            }
                                            return TextSpan(
                                              text: span.text,
                                              style: TextStyle(
                                                letterSpacing: 0.0,
                                                color: isUser ? Colors.white : Colors.grey.shade100,
                                                fontSize: 15,
                                                height: 1.4,
                                              ),
                                            );
                                          }).toList()
                                        : [TextSpan(
                                            text: _getDecodedText(data.text),
                                            style: TextStyle(
                                              letterSpacing: 0.0,
                                              color: isUser ? Colors.white : Colors.grey.shade100,
                                              fontSize: 15,
                                              height: 1.4,
                                            ),
                                          )],
                                  ),
                                ),
                                if (data.translations.isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  ...data.translations.map((translation) => Padding(
                                        padding: const EdgeInsets.only(top: 4),
                                        child: Text(
                                          _getDecodedText(translation.text),
                                          style: TextStyle(
                                            letterSpacing: 0.0,
                                            color: isUser ? Colors.white.withOpacity(0.8) : Colors.grey.shade300.withOpacity(0.8),
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
                                // Timestamp inside bubble (bottom right)
                                if (widget.canDisplaySeconds) ...[
                                  const SizedBox(height: 4),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.end,
                                    children: [
                                      Text(
                                        data.getTimestampString(),
                                        style: TextStyle(
                                          color: isUser ? Colors.white.withOpacity(0.7) : Colors.grey.shade400,
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
              Column(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId),
                    child: Image.asset(
                      Assets.images.speaker0Icon.path,
                      width: 24,
                      height: 24,
                    ),
                  ),
                  const SizedBox(height: 2),
                ],
              ),
            ],
          ],
        ),
      ),
    ));
  }

  Widget _buildTranslationNotice() {
    return GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              title: const Text('Translation Notice'),
              content: const Text(
                'Omi translates conversations into your primary language. Update it anytime in Settings →  Profiles.',
                style: TextStyle(fontSize: 14),
              ),
              actions: [
                TextButton(
                  child: const Text('OK'),
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                ),
              ],
            );
          },
        );
      },
      child: Opacity(
        opacity: 0.5,
        child: const Row(
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
  // Cache the processed text to avoid recalculating on every rebuild
  final String? _cachedText;

  LiteTranscriptWidget({
    super.key,
    required this.segments,
  }) : _cachedText = _processText(segments);

  static String? _processText(List<TranscriptSegment> segments) {
    if (segments.isEmpty) return null;

    var text = getLastTranscript(segments, maxCount: 70, includeTimestamps: false);
    return text.replaceAll(RegExp(r"\s+|\n+"), " ");
  }

  @override
  Widget build(BuildContext context) {
    if (_cachedText == null) {
      return const SizedBox.shrink();
    }

    return Text(
      _cachedText!,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
      textAlign: TextAlign.right,
    );
  }
}

String getLastTranscript(List<TranscriptSegment> transcriptSegments, {int? maxCount, bool generate = false, bool includeTimestamps = true}) {
  var transcript = TranscriptSegment.segmentsAsString(transcriptSegments.sublist(transcriptSegments.length >= 50 ? transcriptSegments.length - 50 : 0), includeTimestamps: includeTimestamps);
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

String formatChatTimestamp(DateTime dateTime) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);

  if (messageDate == today) {
    // Today, show time only
    return dateTimeFormat('h:mm a', dateTime);
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    return 'Yesterday ${dateTimeFormat('h:mm a', dateTime)}';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
