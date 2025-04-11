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
  
  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
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
      // Don't use shrinkWrap: true for large lists as it's expensive
      shrinkWrap: widget.segments.length < 100, 
      itemCount: widget.segments.length + 2,
      // Allow scrolling when there are many segments
      physics: widget.segments.length > 100 
          ? const ClampingScrollPhysics() 
          : const NeverScrollableScrollPhysics(),
      itemBuilder: (context, idx) {
        // Handle header and footer items
        if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
        if (idx == widget.segments.length + 1) return SizedBox(height: widget.bottomMargin);
        
        // Add separator before the item (except for the first one)
        if (widget.separator && idx > 1) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 16),
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
    
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
          widget.horizontalMargin ? 16 : 0, 0.0, widget.horizontalMargin ? 16 : 0, 0.0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              widget.editSegment?.call(segmentIdx, data.speakerId);
              MixpanelManager().assignSheetOpened();
            },
            child: Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Image.asset(
                  data.isUser
                      ? Assets.images.speaker0Icon.path
                      : person != null
                          ? speakerImagePath[person.colorIdx!]
                          : Assets.images.speaker1Icon.path,
                  width: 26,
                  height: 26,
                ),
                const SizedBox(width: 12),
                Text(
                  data.isUser
                      ? SharedPreferencesUtil().givenName.isNotEmpty
                          ? SharedPreferencesUtil().givenName
                          : 'You'
                      : data.personId != null
                          ? person?.name ?? 'Deleted Person'
                          : 'Speaker ${data.speakerId}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18),
                ),
                if (widget.canDisplaySeconds) ...[
                  const SizedBox(width: 12),
                  Text(
                    data.getTimestampString(),
                    style: const TextStyle(color: Colors.grey, fontSize: 14),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: SelectionArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _getDecodedText(data.text),
                    style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                    textAlign: TextAlign.left,
                  ),
                  if (data.translations.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    ...data.translations.map((translation) => Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            _getDecodedText(translation.text),
                            style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
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

// Cache for getLastTranscript results
final Map<String, String> _transcriptCache = {};

String getLastTranscript(List<TranscriptSegment> transcriptSegments,
    {int? maxCount, bool generate = false, bool includeTimestamps = true}) {
  // Create a cache key based on the parameters
  final cacheKey = '${transcriptSegments.length}_${maxCount ?? 0}_$includeTimestamps';
  
  if (!_transcriptCache.containsKey(cacheKey)) {
    var transcript = TranscriptSegment.segmentsAsString(transcriptSegments, includeTimestamps: includeTimestamps);
    if (maxCount != null) transcript = transcript.substring(max(transcript.length - maxCount, 0));
    try {
      _transcriptCache[cacheKey] = utf8.decode(transcript.codeUnits);
    } catch (e) {
      _transcriptCache[cacheKey] = transcript;
    }
  }
  
  return _transcriptCache[cacheKey]!;
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
