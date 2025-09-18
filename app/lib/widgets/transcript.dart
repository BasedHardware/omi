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
  List<GlobalKey> _matchKeys = [];
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
    _rebuildMatchKeys();

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

  void _rebuildMatchKeys() {
    _matchKeys.clear();
    if (widget.searchQuery.isEmpty) return;

    final searchQuery = widget.searchQuery.toLowerCase();
    int globalMatchCount = 0;

    for (var segment in widget.segments) {
      final text = _getDecodedText(segment.text).toLowerCase();
      final matches = RegExp(RegExp.escape(searchQuery), caseSensitive: false).allMatches(text);
      for (final _ in matches) {
        _matchKeys.add(GlobalKey());
        globalMatchCount++;
      }
    }
  }

  @override
  void didUpdateWidget(TranscriptWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    // Reinitialize keys if segment count changed
    if (widget.segments.length != oldWidget.segments.length) {
      _initializeSegmentKeys();
    }

    if (widget.searchQuery != oldWidget.searchQuery) {
      _rebuildMatchKeys();
      _previousSearchResultIndex = -1;

      if (widget.searchQuery.isNotEmpty && widget.currentResultIndex >= 0) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _scrollToSearchResult();
        });
      }
    }

    // Check if new segments were added
    if (widget.segments.length > _previousSegmentCount && !_userHasScrolled) {
      _previousSegmentCount = widget.segments.length;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottomGently();
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
    if (!_scrollController.hasClients) {
      return;
    }

    if (widget.searchQuery.isEmpty) {
      return;
    }

    if (widget.currentResultIndex < 0 || widget.currentResultIndex >= _matchKeys.length) {
      return;
    }

    final matchKey = _matchKeys[widget.currentResultIndex];
    final context = matchKey.currentContext;

    if (context != null) {
      _scrollToContext(context);
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final retryContext = matchKey.currentContext;
        if (retryContext != null) {
          _scrollToContext(retryContext);
        } else {
          _scrollToSearchResultFallback();
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

  void _scrollToSearchResultFallback() {
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

      final itemHeight = 80.0;
      final headerHeight = widget.topMargin ? 32.0 : 0.0;
      final targetOffset = headerHeight + (targetSegmentIndex * itemHeight);

      _isAutoScrolling = true;
      _scrollController
          .animateTo(
        targetOffset.clamp(0.0, _scrollController.position.maxScrollExtent),
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOutCubic,
      )
          .then((_) {
        _isAutoScrolling = false;
      });
    }
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
    for (int i = 0; i < segmentIndex; i++) {
      final segmentText = _getDecodedText(widget.segments[i].text).toLowerCase();
      final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(segmentText);
      globalMatchIndex += matches.length;
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

      final matchKey = currentGlobalIndex < _matchKeys.length ? _matchKeys[currentGlobalIndex] : null;

      spans.add(WidgetSpan(
        child: Container(
          key: matchKey,
          decoration: BoxDecoration(
            color: isCurrentResult ? Colors.orange.withValues(alpha: 0.9) : Colors.deepPurple.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 1),
          child: Text(
            text.substring(matchStart, matchEnd),
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
            ),
          ),
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

  Widget _buildSegmentItem(int segmentIdx) {
    final data = widget.segments[segmentIdx];
    final Person? person = data.personId != null ? _getPersonById(data.personId) : null;
    final suggestion = widget.suggestions[data.id];
    final isTagging = widget.taggingSegmentIds.contains(data.id);
    final bool isUser = data.isUser;

    return Container(
        key: segmentIdx >= 0 && segmentIdx < _segmentKeys.length ? _segmentKeys[segmentIdx] : null,
        child: GestureDetector(
          onTap: () {
            if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
              widget.onTapWhenSearchEmpty!();
            }
            widget.editSegment?.call(data.id, data.speakerId);
            MixpanelManager().tagSheetOpened();
          },
          child: Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
                widget.horizontalMargin ? 16 : 0, 4.0, widget.horizontalMargin ? 16 : 0, 4.0),
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
                                    : (person != null ? person.name : 'Speaker ${data.speakerId}'),
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
                                                TextSpan(
                                                  text: _getDecodedText(data.text),
                                                )
                                              ],
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
                                    // Timestamp inside bubble (bottom right)
                                    if (widget.canDisplaySeconds) ...[
                                      const SizedBox(height: 4),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.end,
                                        children: [
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
      child: const Opacity(
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

  const LiteTranscriptWidget({
    super.key,
    required this.segments,
  });

  static String? _processText(List<TranscriptSegment> segments) {
    if (segments.isEmpty) return null;

    var text = getLastTranscript(segments, maxCount: 70, includeTimestamps: false);
    return text.replaceAll(RegExp(r"\s+|\n+"), " ");
  }

  @override
  Widget build(BuildContext context) {
    final processedText = _processText(segments);
    if (processedText == null) {
      return const SizedBox.shrink();
    }

    return Text(
      processedText,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
      textAlign: TextAlign.right,
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
