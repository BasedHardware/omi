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
      itemCount: widget.segments.length + 2,
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
    final suggestion = widget.suggestions[data.id];
    final isTagging = widget.taggingSegmentIds.contains(data.id);

    return Padding(
      padding:
          EdgeInsetsDirectional.fromSTEB(widget.horizontalMargin ? 16 : 0, 0.0, widget.horizontalMargin ? 16 : 0, 0.0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              widget.editSegment?.call(data.id, data.speakerId);
              MixpanelManager().tagSheetOpened();
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
                          : speakerImagePath[data.speakerId % speakerImagePath.length],
                  width: 26,
                  height: 26,
                ),
                const SizedBox(width: 12),
                Text(
                  data.isUser
                      ? SharedPreferencesUtil().givenName.isNotEmpty
                          ? SharedPreferencesUtil().givenName
                          : 'You'
                      : suggestion != null && person == null && !data.isUser
                          ? '${suggestion.personName}?'
                          : (person != null ? person?.name ?? 'Deleted Person' : 'Speaker ${data.speakerId}'),
                  style: TextStyle(
                    color: person == null && !data.isUser && !isTagging ? Colors.grey.shade400 : Colors.white,
                    fontSize: 18,
                    fontStyle: person == null && !data.isUser && !isTagging ? FontStyle.italic : FontStyle.normal,
                  ),
                ),
                if (!data.speechProfileProcessed && !data.isUser && (data.personId ?? "").isEmpty)
                  const Padding(
                    padding: EdgeInsets.only(left: 8.0),
                    child: Tooltip(
                      message: 'Speaker identification calibrating',
                      child: Icon(
                        Icons.warning_rounded,
                        color: Colors.orange,
                        size: 16,
                      ),
                    ),
                  ),
                if (isTagging) ...[
                  const SizedBox(width: 8),
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation(Colors.white),
                    ),
                  )
                ] else if (suggestion != null && person == null && !data.isUser) ...[
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: () => widget.onAcceptSuggestion?.call(suggestion),
                    style: TextButton.styleFrom(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(40, 30),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      alignment: Alignment.centerLeft,
                    ),
                    child: const Text(
                      'Tag',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        decoration: TextDecoration.underline,
                        decorationColor: Colors.white,
                      ),
                    ),
                  )
                ],
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
