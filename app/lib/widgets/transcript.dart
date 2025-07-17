import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
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
  final Function(int, int)? editSegment;

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
      return Colors.blue.shade600.withOpacity(0.8);
    }
    // Use speakerId to get consistent color for each speaker
    final colorIndex = speakerId % _speakerColors.length;
    return _speakerColors[colorIndex].withOpacity(0.8);
  }

  Color _getSpeakerAvatarColor(bool isUser, int speakerId) {
    if (isUser) {
      return Colors.blue.shade600.withOpacity(0.3);
    }
    final colorIndex = speakerId % _speakerColors.length;
    return _speakerColors[colorIndex].withOpacity(0.3);
  }

  @override
  void initState() {
    super.initState();
    _previousSegmentCount = widget.segments.length;

    // Add scroll listener to detect manual scrolling
    _scrollController.addListener(_onScroll);

    // Auto-scroll to bottom after first frame
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToBottom();
    });
  }

  @override
  void didUpdateWidget(TranscriptWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    // Check if new segments were added
    if (widget.segments.length > _previousSegmentCount && !_userHasScrolled) {
      _previousSegmentCount = widget.segments.length;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottom();
      });
    } else {
      _previousSegmentCount = widget.segments.length;
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
    final bool isUser = data.isUser;

    final speakerName = isUser
        ? (SharedPreferencesUtil().givenName.isNotEmpty ? SharedPreferencesUtil().givenName : 'You')
        : data.personId != null
            ? person?.name ?? 'Deleted Person'
            : 'Speaker ${data.speakerId}';

    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(widget.horizontalMargin ? 16 : 0, 2.0, widget.horizontalMargin ? 16 : 0, 2.0),
      child: Column(
        children: [
          // Row with bubble and avatars (for proper alignment)
          Row(
            mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              // Speaker avatar (only for others, on the left)
              if (!isUser) ...[
                GestureDetector(
                  onTap: () {
                    widget.editSegment?.call(segmentIdx, data.speakerId);
                    MixpanelManager().assignSheetOpened();
                  },
                  child: CircleAvatar(
                    radius: 16,
                    backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId),
                    child: Image.asset(
                      person != null ? speakerImagePath[person.colorIdx!] : Assets.images.speaker1Icon.path,
                      width: 20,
                      height: 20,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
              ],

              // Chat bubble only (no label here for alignment)
              Flexible(
                child: Align(
                  alignment: isUser ? Alignment.bottomRight : Alignment.bottomLeft,
                  child: GestureDetector(
                    onTap: () {
                      widget.editSegment?.call(segmentIdx, data.speakerId);
                      MixpanelManager().assignSheetOpened();
                    },
                    child: Container(
                      constraints: BoxConstraints(
                        maxWidth: MediaQuery.of(context).size.width * 0.7,
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      decoration: BoxDecoration(
                        color: _getSpeakerBubbleColor(isUser, data.speakerId),
                        borderRadius: BorderRadius.only(
                          topLeft: const Radius.circular(16),
                          topRight: const Radius.circular(16),
                          bottomLeft: Radius.circular(isUser ? 16 : 4),
                          bottomRight: Radius.circular(isUser ? 4 : 16),
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.1),
                            blurRadius: 3,
                            offset: const Offset(0, 1),
                          ),
                        ],
                      ),
                      child: SelectionArea(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _getDecodedText(data.text),
                              style: TextStyle(
                                letterSpacing: 0.0,
                                color: isUser ? Colors.white : Colors.grey.shade200,
                                fontSize: 15,
                                height: 1.3,
                              ),
                              textAlign: TextAlign.left,
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
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),

              // User avatar (only for user, on the right)
              if (isUser) ...[
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: () {
                    widget.editSegment?.call(segmentIdx, data.speakerId);
                    MixpanelManager().assignSheetOpened();
                  },
                  child: CircleAvatar(
                    radius: 16,
                    backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId),
                    child: Image.asset(
                      Assets.images.speaker0Icon.path,
                      width: 20,
                      height: 20,
                    ),
                  ),
                ),
              ],
            ],
          ),

          // Speaker name below the entire row (for all speakers)
          Padding(
            padding: EdgeInsets.only(
              top: 4,
              left: isUser ? 0 : 40, // 32 (avatar + gap) + 8 (extra padding) for non-users
              right: isUser ? 40 : 0, // 32 (avatar + gap) + 8 (extra padding) for users
            ),
            child: Row(
              mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
              children: [
                Text(
                  speakerName,
                  style: const TextStyle(
                    color: Colors.grey,
                    fontSize: 10,
                    fontWeight: FontWeight.w400,
                  ),
                ),
                // Commented out timestamp - can be restored later if needed
                // if (widget.canDisplaySeconds) ...[
                //   const SizedBox(width: 8),
                //   Text(
                //     data.getTimestampString(),
                //     style: const TextStyle(color: Colors.grey, fontSize: 9),
                //   ),
                // ],
              ],
            ),
          ),
        ],
      ),
    );
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
